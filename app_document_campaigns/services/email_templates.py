import re
from dataclasses import dataclass
from email.utils import formataddr
from html import escape

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import validate_email

from app_document_campaigns.models import CampaignAreaEmailConfig, CampaignEmailConfig
from app_document_campaigns.services.email_html import is_html_email_template


TOKEN_PATTERN = re.compile(r"{{\s*([a-z_]+)\s*}}")
ALLOWED_VARIABLES = {
    "campaign_code": "Mã chiến dịch",
    "campaign_name": "Tên chiến dịch",
    "report_month": "Kỳ tháng",
    "shop_code": "Mã PGD",
    "shop_name": "Tên PGD",
    "area_manager_name": "Tên Quản lý khu vực",
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
    "link_expires_at": "Ngày link hết hạn",
    "manager_url": "Unique link QLKV",
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


def template_context(campaign, shop, response_url):
    _, area_name, _ = area_manager_details(shop)
    return {
        "campaign_code": campaign.code,
        "campaign_name": campaign.name,
        "report_month": campaign.report_month.strftime("%m/%Y"),
        "shop_code": str(shop.shop_code or ""),
        "shop_name": shop.shop_name,
        "area_manager_name": area_name or "—",
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


def render_campaign_email(config, campaign, shop, response_url, *, recipient_override=None):
    validate_templates(config.subject_template, config.body_template)
    context = template_context(campaign, shop, response_url)
    context["support_email"] = config.support_email or ""
    to_email = _valid_email(recipient_override or shop.shop_email)
    if not to_email:
        raise EmailTemplateError("Email PGD/người nhận thử chưa hợp lệ.")

    area_id, _, area_email = area_manager_details(shop)
    cc_candidates = list(config.cc_emails or [])
    if config.cc_area_manager and not recipient_override:
        cc_candidates.insert(0, area_email)
    cc = [] if recipient_override else _dedupe(cc_candidates, [to_email])
    bcc = [] if recipient_override else _dedupe(config.bcc_emails or [], [to_email, *cc])
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
        area_email=area_email if config.cc_area_manager and area_email in cc else "",
        area_manager_id=area_id if config.cc_area_manager and area_email in cc else None,
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
    subject_template = config.confirmation_subject_template if confirmation_mode else config.monitoring_subject_template
    body_template = config.confirmation_body_template if confirmation_mode else config.monitoring_body_template
    cc = [] if recipient_override else _dedupe(config.cc_emails or [], [to_email])
    bcc = [] if recipient_override else _dedupe(config.bcc_emails or [], [to_email, *cc])
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
        "link_expires_at": (expires_at or campaign.link_expires_at).strftime("%H:%M %d/%m/%Y") if (expires_at or campaign.link_expires_at) else "Chưa cấu hình",
        "manager_url": manager_url,
        "support_email": "",
    }


def preflight_campaign_email(campaign, shops, config):
    validate_templates(config.subject_template, config.body_template)
    issues = []
    valid = 0
    missing_area = 0
    for shop in shops:
        shop_email = _valid_email(shop.shop_email)
        if not shop_email:
            issues.append({"shop_id": shop.pk, "shop": f"{shop.shop_code} · {shop.shop_name}", "issue": "Email PGD trống hoặc không hợp lệ"})
            continue
        _, _, area_email = area_manager_details(shop)
        if config.cc_area_manager and not _valid_email(area_email):
            missing_area += 1
            issues.append({"shop_id": shop.pk, "shop": f"{shop.shop_code} · {shop.shop_name}", "issue": "Thiếu email Quản lý khu vực; PGD vẫn có thể nhận email"})
        valid += 1
    return {
        "total": len(shops),
        "valid": valid,
        "invalid": len(shops) - valid,
        "missing_area": missing_area,
        "issues": issues[:100],
        "truncated": len(issues) > 100,
    }
