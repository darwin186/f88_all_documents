import re
from dataclasses import dataclass
from email.utils import formataddr
from html import escape

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.utils import timezone

from app_document_campaigns.models import CampaignAreaEmailConfig, CampaignEmailConfig, CampaignError
from app_document_campaigns.services.email_html import is_html_email_template


TOKEN_PATTERN = re.compile(r"{{\s*([a-z_]+)\s*}}")
ALLOWED_VARIABLES = {
    "campaign_code": "Mã chiến dịch",
    "campaign_name": "Tên chiến dịch",
    "report_month": "Kỳ tháng",
    "shop_code": "Mã PGD",
    "shop_name": "Tên PGD",
    "error_count": "Số dòng lỗi cần PGD phản hồi",
    "document_error_count": "Số lượng dòng lỗi chứng từ trong link PGD",
    "response_start_date": "Ngày bắt đầu phản hồi",
    "response_end_date": "Ngày kết thúc phản hồi",
    "area_manager_name": "Tên Quản lý khu vực",
    "area_manager_email": "Email Quản lý khu vực",
    "shop_email": "Email PGD",
    "shop_manager_email": "Email trưởng PGD",
    "response_deadline": "Hạn PGD phản hồi",
    "link_expires_at": "Ngày link hết hạn",
    "response_url": "Unique link phản hồi",
    "support_email": "Email hỗ trợ",
}
AREA_ALLOWED_VARIABLES = {
    "campaign_code": "Mã chiến dịch",
    "campaign_name": "Tên chiến dịch",
    "report_month": "Kỳ tháng",
    "area_manager_code": "Mã Quản lý khu vực",
    "area_manager_name": "Tên Quản lý khu vực",
    "area_manager_email": "Email Quản lý khu vực",
    "link_expires_at": "Ngày link hết hạn",
    "manager_url": "Unique link QLKV",
    "report_url": "Link báo cáo lỗi Power BI",
    "report_guide_url": "Link hướng dẫn xem báo cáo",
    "response_end_date": "Ngày cuối PGD phản hồi",
    "confirmation_guide_url": "Link hướng dẫn QLKV phản hồi",
    "area_response_end_date": "Ngày cuối QLKV xác nhận",
    "support_email": "Email hỗ trợ",
}


class EmailTemplateError(ValueError):
    pass


@dataclass(frozen=True)
class RenderedCampaignEmail:
    subject: str
    body: str
    to: list[str]
    cc: list[str]
    bcc: list[str]
    from_email: str
    area_email: str
    area_manager_id: int | None


def campaign_email_config(campaign):
    config, _ = CampaignEmailConfig.objects.get_or_create(campaign=campaign)
    return config


def campaign_area_email_config(campaign):
    config, _ = CampaignAreaEmailConfig.objects.get_or_create(campaign=campaign)
    return config


def validate_templates(subject, body):
    subject = subject or ""
    body = body or ""
    unknown = sorted((set(TOKEN_PATTERN.findall(subject)) | set(TOKEN_PATTERN.findall(body))) - set(ALLOWED_VARIABLES))
    if unknown:
        raise EmailTemplateError(f"Tham số không được hỗ trợ: {', '.join(unknown)}")
    if "{{response_url}}" not in body.replace(" ", ""):
        raise EmailTemplateError("Nội dung email bắt buộc có {{response_url}}.")
    stripped = TOKEN_PATTERN.sub("", subject + body)
    if "{{" in stripped or "}}" in stripped:
        raise EmailTemplateError("Cú pháp tham số email không hợp lệ.")
    if not subject.strip():
        raise EmailTemplateError("Subject không được để trống.")
    if "\n" in subject or "\r" in subject:
        raise EmailTemplateError("Subject chỉ được nằm trên một dòng.")
    if not body.strip():
        raise EmailTemplateError("Nội dung email không được để trống.")


def _validate_area_pair(subject, body, label):
    subject, body = subject or "", body or ""
    unknown = sorted((set(TOKEN_PATTERN.findall(subject)) | set(TOKEN_PATTERN.findall(body))) - set(AREA_ALLOWED_VARIABLES))
    if unknown:
        raise EmailTemplateError(f"{label}: tham số không được hỗ trợ: {', '.join(unknown)}")
    if "{{manager_url}}" not in body.replace(" ", ""):
        raise EmailTemplateError(f"{label}: nội dung bắt buộc có {{{{manager_url}}}}.")
    if not subject.strip() or "\n" in subject or "\r" in subject:
        raise EmailTemplateError(f"{label}: Subject không hợp lệ.")
    if not body.strip():
        raise EmailTemplateError(f"{label}: nội dung không được để trống.")
    stripped = TOKEN_PATTERN.sub("", subject + body)
    if "{{" in stripped or "}}" in stripped:
        raise EmailTemplateError(f"{label}: cú pháp tham số không hợp lệ.")


def validate_area_templates(monitor_subject, monitor_body, confirmation_subject, confirmation_body):
    _validate_area_pair(monitor_subject, monitor_body, "Email theo dõi PGD")
    _validate_area_pair(confirmation_subject, confirmation_body, "Email xác nhận lỗi")


def validate_template_for_type(email_type, subject, body):
    from app_document_campaigns.models import EmailTemplateMaster

    if email_type == EmailTemplateMaster.EmailType.PGD_RESPONSE:
        validate_templates(subject, body)
    elif email_type in {
        EmailTemplateMaster.EmailType.AREA_MONITORING,
        EmailTemplateMaster.EmailType.AREA_CONFIRMATION,
    }:
        _validate_area_pair(subject, body, "Template QLKV")
    else:
        raise EmailTemplateError("Loại template email không hợp lệ.")


def validate_recipient_template(value, allowed_variables):
    value = value or ""
    unknown = sorted(set(TOKEN_PATTERN.findall(value)) - set(allowed_variables))
    if unknown:
        raise EmailTemplateError(f"Tham số người nhận không được hỗ trợ: {', '.join(unknown)}")
    stripped = TOKEN_PATTERN.sub("", value)
    if "{{" in stripped or "}}" in stripped:
        raise EmailTemplateError("Cú pháp tham số CC/BCC không hợp lệ.")
    for item in re.split(r"[;,\n]+", stripped):
        item = item.strip()
        if item and not _valid_email(item):
            raise EmailTemplateError(f"Email CC/BCC không hợp lệ: {item}")


def render_recipient_template(value, context, excluded=()):
    rendered = _render(value or "", context)
    emails = []
    for item in re.split(r"[;,\n]+", rendered):
        item = item.strip()
        if not item:
            continue
        if not _valid_email(item):
            raise EmailTemplateError(f"Email CC/BCC không hợp lệ sau khi điền tham số: {item}")
        emails.append(item)
    return _dedupe(emails, excluded)


def _valid_email(value):
    value = (value or "").strip()
    if not value:
        return ""
    try:
        validate_email(value)
    except ValidationError:
        return ""
    return value


def _dedupe(values, excluded=()):
    seen = {value.lower() for value in excluded if value}
    result = []
    for raw in values:
        value = _valid_email(raw)
        if not value or value.lower() in seen:
            continue
        seen.add(value.lower())
        result.append(value)
    return result


def area_manager_details(shop):
    manager = getattr(shop, "manager_id", None)
    if not manager:
        return None, "", ""
    area = getattr(manager, "areaManager", None)
    if area and area.is_active:
        return area.pk, area.areaManager_name or "", (area.areaManager_email or "").strip()
    return None, manager.qlkv_name or "", (manager.qlkv_email or "").strip()


def shop_manager_email(shop):
    """Only CC a manager whose current Shop contact record is complete."""
    if not (shop.shop_manager_name or "").strip() or not (shop.shop_manager_employee_code or "").strip():
        return ""
    return _valid_email(shop.shop_manager_email)


def _date_text(value):
    if not value:
        return "Chưa cấu hình"
    if timezone.is_aware(value):
        value = timezone.localtime(value)
    return value.strftime("%d/%m/%Y")


def template_context(campaign, shop, response_url, *, response_deadline=None):
    _, area_name, area_email = area_manager_details(shop)
    deadline = response_deadline or campaign.response_deadline
    error_count = (
        CampaignError.objects.filter(campaign=campaign, shop=shop)
        .exclude(status__in=[CampaignError.Status.EXCLUDED, CampaignError.Status.CANCELLED])
        .count()
    )
    return {
        "campaign_code": campaign.code,
        "campaign_name": campaign.name,
        "report_month": campaign.report_month.strftime("%m/%Y"),
        "shop_code": str(shop.shop_code or ""),
        "shop_name": shop.shop_name,
        "error_count": error_count,
        "document_error_count": error_count,
        "response_start_date": _date_text(campaign.response_opens_at),
        "response_end_date": _date_text(deadline),
        "area_manager_name": area_name or "—",
        "area_manager_email": _valid_email(area_email),
        "shop_email": _valid_email(shop.shop_email),
        "shop_manager_email": shop_manager_email(shop),
        "response_deadline": campaign.response_deadline.strftime("%H:%M %d/%m/%Y") if campaign.response_deadline else "Chưa cấu hình",
        "link_expires_at": campaign.link_expires_at.strftime("%H:%M %d/%m/%Y") if campaign.link_expires_at else "Chưa cấu hình",
        "response_url": response_url,
        "support_email": "",
    }


def _render(template, context):
    html_mode = is_html_email_template(template)
    return TOKEN_PATTERN.sub(
        lambda match: escape(str(context.get(match.group(1), "")), quote=True)
        if html_mode else str(context.get(match.group(1), "")),
        template,
    )


def render_campaign_email(
    config,
    campaign,
    shop,
    response_url,
    *,
    recipient_override=None,
    response_deadline=None,
):
    validate_templates(config.subject_template, config.body_template)
    validate_recipient_template(config.cc_template, ALLOWED_VARIABLES)
    validate_recipient_template(config.bcc_template, ALLOWED_VARIABLES)
    context = template_context(
        campaign,
        shop,
        response_url,
        response_deadline=response_deadline,
    )
    context["support_email"] = config.support_email or ""
    to_email = _valid_email(recipient_override or shop.shop_email)
    if not to_email:
        raise EmailTemplateError("Email PGD/người nhận thử chưa hợp lệ.")

    area_id, _, area_email = area_manager_details(shop)
    cc = [] if recipient_override else render_recipient_template(config.cc_template, context, [to_email])
    bcc = [] if recipient_override else render_recipient_template(config.bcc_template, context, [to_email, *cc])
    from_address = _valid_email(settings.DEFAULT_FROM_EMAIL or settings.EMAIL_HOST_USER)
    if not from_address:
        raise EmailTemplateError("Địa chỉ From của hệ thống chưa được cấu hình hợp lệ.")
    from_email = formataddr((config.from_name, from_address)) if config.from_name and from_address else from_address
    return RenderedCampaignEmail(
        subject=_render(config.subject_template, context).strip(),
        body=_render(config.body_template, context),
        to=[to_email],
        cc=cc,
        bcc=bcc,
        from_email=from_email,
        area_email=area_email if area_email in cc else "",
        area_manager_id=area_id if area_email in cc else None,
    )


def render_area_email(config, campaign, area, manager_url, *, confirmation_mode=False, recipient_override=None, expires_at=None):
    validate_area_templates(
        config.monitoring_subject_template, config.monitoring_body_template,
        config.confirmation_subject_template, config.confirmation_body_template,
    )
    to_email = _valid_email(recipient_override or area.areaManager_email)
    if not to_email:
        raise EmailTemplateError("Email QLKV/người nhận thử chưa hợp lệ.")
    context = area_template_context(campaign, area, manager_url, expires_at=expires_at)
    context["support_email"] = config.support_email or ""
    context["report_url"] = config.monitoring_report_url or "Chưa cấu hình"
    context["report_guide_url"] = config.monitoring_guide_url or "Chưa cấu hình"
    context["confirmation_guide_url"] = config.confirmation_guide_url or "Chưa cấu hình"
    subject_template = config.confirmation_subject_template if confirmation_mode else config.monitoring_subject_template
    body_template = config.confirmation_body_template if confirmation_mode else config.monitoring_body_template
    cc_template = config.confirmation_cc_template if confirmation_mode else config.monitoring_cc_template
    bcc_template = config.confirmation_bcc_template if confirmation_mode else config.monitoring_bcc_template
    validate_recipient_template(cc_template, AREA_ALLOWED_VARIABLES)
    validate_recipient_template(bcc_template, AREA_ALLOWED_VARIABLES)
    cc = [] if recipient_override else render_recipient_template(cc_template, context, [to_email])
    bcc = [] if recipient_override else render_recipient_template(bcc_template, context, [to_email, *cc])
    from_address = _valid_email(settings.DEFAULT_FROM_EMAIL or settings.EMAIL_HOST_USER)
    if not from_address:
        raise EmailTemplateError("Địa chỉ From của hệ thống chưa được cấu hình hợp lệ.")
    return RenderedCampaignEmail(
        subject=_render(subject_template, context).strip(), body=_render(body_template, context),
        to=[to_email], cc=cc, bcc=bcc,
        from_email=formataddr((config.from_name, from_address)) if config.from_name else from_address,
        area_email=to_email, area_manager_id=area.pk,
    )


def area_template_context(campaign, area, manager_url, *, expires_at=None):
    return {
        "campaign_code": campaign.code,
        "campaign_name": campaign.name,
        "report_month": campaign.report_month.strftime("%m/%Y"),
        "area_manager_code": area.areaManager_code or "",
        "area_manager_name": area.areaManager_name or "",
        "area_manager_email": _valid_email(area.areaManager_email),
        "link_expires_at": (expires_at or campaign.link_expires_at).strftime("%H:%M %d/%m/%Y") if (expires_at or campaign.link_expires_at) else "Chưa cấu hình",
        "manager_url": manager_url,
        "report_url": "",
        "report_guide_url": "",
        "response_end_date": _date_text(campaign.response_deadline),
        "confirmation_guide_url": "",
        "area_response_end_date": _date_text(campaign.area_response_deadline),
        "support_email": "",
    }


def preflight_campaign_email(campaign, shops, config):
    validate_templates(config.subject_template, config.body_template)
    validate_recipient_template(config.cc_template, ALLOWED_VARIABLES)
    validate_recipient_template(config.bcc_template, ALLOWED_VARIABLES)
    issues = []
    valid = 0
    missing_area = 0
    missing_shop_manager = 0
    for shop in shops:
        shop_email = _valid_email(shop.shop_email)
        if not shop_email:
            issues.append({"shop_id": shop.pk, "shop": f"{shop.shop_code} · {shop.shop_name}", "issue": "Email PGD trống hoặc không hợp lệ"})
            continue
        _, _, area_email = area_manager_details(shop)
        recipients_template = (config.cc_template or "") + "\n" + (config.bcc_template or "")
        if "{{area_manager_email}}" in recipients_template.replace(" ", "") and not _valid_email(area_email):
            missing_area += 1
            issues.append({"shop_id": shop.pk, "shop": f"{shop.shop_code} · {shop.shop_name}", "issue": "Thiếu email Quản lý khu vực; PGD vẫn có thể nhận email"})
        if "{{shop_manager_email}}" in recipients_template.replace(" ", "") and not shop_manager_email(shop):
            missing_shop_manager += 1
            issues.append({"shop_id": shop.pk, "shop": f"{shop.shop_code} · {shop.shop_name}", "issue": "Chưa đủ tên, mã nhân viên F và email trưởng PGD; PGD vẫn có thể nhận email"})
        valid += 1
    return {
        "total": len(shops),
        "valid": valid,
        "invalid": len(shops) - valid,
        "missing_area": missing_area,
        "missing_shop_manager": missing_shop_manager,
        "issues": issues[:100],
        "truncated": len(issues) > 100,
    }
