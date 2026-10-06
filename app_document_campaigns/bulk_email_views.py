import json
import uuid
from email.utils import parseaddr

from django import forms
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import F
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from app_documents.models import AreaManager, Manager, Shop
from app_document_campaigns.models import (
    AreaManagerAccessLink,
    Campaign,
    CampaignEmailBatch,
    CampaignEmailDelivery,
    CampaignError,
    ShopAccessLink,
    ShopEmailDelivery,
    ShopSubmission,
)
from app_document_campaigns.services.access_links import issue_area_manager_access_link, issue_shop_access_link
from app_document_campaigns.services.area_confirmation_excel import step5_errors
from app_document_campaigns.services.email_html import email_body_html
from app_document_campaigns.services.email_templates import (
    EmailTemplateError,
    campaign_area_email_config,
    campaign_email_config,
    render_area_email,
    render_campaign_email,
    validate_area_templates,
    validate_templates,
)
from app_document_campaigns.services.email_delivery_payload import message_payload, redact_access_urls


SUPPORTED_KINDS = {
    CampaignEmailBatch.EmailType.PGD_RESPONSE,
    CampaignEmailBatch.EmailType.AREA_MONITORING,
    CampaignEmailBatch.EmailType.AREA_CONFIRMATION,
}


def _is_admin(user):
    return user.is_superuser or user.groups.filter(name="admin").exists()


def _chunk_size():
    return max(1, min(int(settings.MICROSOFT_GRAPH_EMAIL_CHUNK_SIZE), 50))


def _validate_graph_configuration():
    if not all((
        settings.MICROSOFT_GRAPH_TENANT_ID,
        settings.MICROSOFT_GRAPH_CLIENT_ID,
        settings.MICROSOFT_GRAPH_CLIENT_SECRET,
        settings.MICROSOFT_GRAPH_MAILBOX_EMAIL,
        settings.MICROSOFT_GRAPH_SENDER_EMAIL,
    )):
        raise ValueError("Microsoft Graph chưa được cấu hình đầy đủ.")


def _valid_email(value):
    try:
        return forms.EmailField().clean(value)
    except forms.ValidationError:
        return ""


def _area_email(area):
    direct = _valid_email(area.areaManager_email)
    if direct:
        return direct
    candidates = (
        Manager.objects.filter(areaManager=area, is_valid=True)
        .exclude(qlkv_email__isnull=True)
        .exclude(qlkv_email="")
        .order_by("manager_id")
        .values_list("qlkv_email", flat=True)
    )
    for candidate in candidates:
        valid = _valid_email(candidate)
        if valid:
            return valid
    return ""


def _eligible_shop_ids(campaign):
    submitted = ShopSubmission.objects.filter(campaign=campaign).values_list("shop_id", flat=True)
    return list(
        CampaignError.objects.filter(campaign=campaign)
        .exclude(status__in=[CampaignError.Status.EXCLUDED, CampaignError.Status.CANCELLED])
        .exclude(shop_id__in=submitted)
        .order_by("shop__shop_code", "shop_id")
        .values_list("shop_id", flat=True)
        .distinct()
    )


def _eligible_area_ids(campaign, *, confirmation=False):
    errors = step5_errors(campaign) if confirmation else CampaignError.objects.filter(campaign=campaign).exclude(
        status__in=[CampaignError.Status.EXCLUDED, CampaignError.Status.CANCELLED]
    )
    return list(
        errors
        .exclude(shop__manager_id__areaManager_id__isnull=True)
        .order_by("shop__manager_id__areaManager__areaManager_name", "shop__manager_id__areaManager_id")
        .values_list("shop__manager_id__areaManager_id", flat=True)
        .distinct()
    )


def _targets(campaign, kind):
    if kind == CampaignEmailBatch.EmailType.PGD_RESPONSE:
        objects = Shop.objects.filter(pk__in=_eligible_shop_ids(campaign)).order_by("shop_code", "pk")
        return objects, lambda item: _valid_email(item.shop_email), lambda item: f"{item.shop_code} · {item.shop_name}"
    objects = AreaManager.objects.filter(
        pk__in=_eligible_area_ids(
            campaign, confirmation=kind == CampaignEmailBatch.EmailType.AREA_CONFIRMATION
        )
    ).order_by("areaManager_name", "pk")
    return objects, _area_email, lambda item: f"{item.areaManager_code} · {item.areaManager_name}"


def _validate_campaign(campaign, kind):
    if kind == CampaignEmailBatch.EmailType.PGD_RESPONSE:
        if (campaign.status != Campaign.Status.ACTIVE or not campaign.response_deadline
                or campaign.response_deadline <= timezone.now() or not campaign.link_expires_at
                or campaign.link_expires_at <= timezone.now()):
            raise ValueError("Chiến dịch không còn trong thời gian PGD phản hồi.")
        config = campaign_email_config(campaign)
        validate_templates(config.subject_template, config.body_template)
    elif kind == CampaignEmailBatch.EmailType.AREA_CONFIRMATION:
        if not campaign.area_response_deadline or campaign.area_response_deadline <= timezone.now():
            raise ValueError("Hạn QLKV xác nhận chưa được cấu hình hoặc đã hết hạn.")
        config = campaign_area_email_config(campaign)
        validate_area_templates(
            config.monitoring_subject_template, config.monitoring_body_template,
            config.confirmation_subject_template, config.confirmation_body_template,
        )
    else:
        if (campaign.status != Campaign.Status.ACTIVE or not campaign.link_expires_at
                or campaign.link_expires_at <= timezone.now()):
            raise ValueError("Link theo dõi QLKV chưa được cấu hình hoặc đã hết hạn.")
        config = campaign_area_email_config(campaign)
        validate_area_templates(
            config.monitoring_subject_template, config.monitoring_body_template,
            config.confirmation_subject_template, config.confirmation_body_template,
        )
    return config


@login_required
@require_GET
def prepare_bulk_email_batches(request, campaign_id):
    if not _is_admin(request.user):
        return JsonResponse({"ok": False, "error": "Chỉ Admin được gửi email hàng loạt."}, status=403)
    campaign = get_object_or_404(Campaign, pk=campaign_id)
    kind = request.GET.get("kind", "")
    if kind not in SUPPORTED_KINDS:
        return JsonResponse({"ok": False, "error": "Loại email hàng loạt không hợp lệ."}, status=400)
    try:
        _validate_campaign(campaign, kind)
        _validate_graph_configuration()
    except (ValueError, EmailTemplateError) as exc:
        return JsonResponse({"ok": False, "error": str(exc)}, status=409)
    objects, email_for, label_for = _targets(campaign, kind)
    eligible, invalid = [], []
    for item in objects:
        target = {"id": item.pk, "label": label_for(item), "email": email_for(item)}
        (eligible if target["email"] else invalid).append(target)
    size = _chunk_size()
    batches = []
    for offset in range(0, len(eligible), size):
        rows = eligible[offset:offset + size]
        batches.append({
            "index": len(batches) + 1,
            "target_ids": [row["id"] for row in rows],
            "count": len(rows),
            "first": rows[0]["label"],
            "last": rows[-1]["label"],
        })
    return JsonResponse({
        "ok": True, "kind": kind, "chunk_size": size, "eligible": len(eligible),
        "invalid": len(invalid), "invalid_samples": invalid[:10], "batches": batches,
    })


def _build_shop_batch(request, campaign, target_ids, config):
    valid_ids = set(_eligible_shop_ids(campaign))
    ids = [item for item in target_ids if item in valid_ids]
    shops = list(Shop.objects.filter(pk__in=ids).select_related("manager_id__areaManager").order_by("shop_code", "pk"))
    if len(shops) != len(set(target_ids)):
        raise ValueError("Danh sách PGD đã thay đổi; hãy chuẩn bị lại batch.")
    batch = CampaignEmailBatch.objects.create(
        campaign=campaign, email_type=CampaignEmailBatch.EmailType.PGD_RESPONSE,
        transport_provider=CampaignEmailBatch.TransportProvider.MICROSOFT_GRAPH,
        idempotency_key=f"bulk:{campaign.pk}:pgd:{uuid.uuid4()}", total_count=len(shops), requested_by=request.user,
    )
    messages = []
    for shop in shops:
        email = _valid_email(shop.shop_email)
        if not email:
            raise ValueError(f"Email PGD {shop.shop_code} không hợp lệ; hãy chuẩn bị lại batch.")
        existing = ShopAccessLink.objects.filter(campaign=campaign, shop=shop).first()
        response_deadline = existing.response_deadline if existing else campaign.response_deadline
        expires_at = existing.expires_at if existing and existing.expires_at > response_deadline else campaign.link_expires_at
        link, token = issue_shop_access_link(
            campaign=campaign, shop=shop, allowed_email=email, created_by=request.user,
            response_deadline=response_deadline, expires_at=expires_at,
        )
        url = request.build_absolute_uri(reverse("document_campaigns:shop_response", kwargs={"raw_token": token}))
        rendered = render_campaign_email(config, campaign, shop, url)
        legacy = ShopEmailDelivery.objects.create(link=link)
        key = f"batch:{batch.pk}:shop:{shop.pk}:template:{config.template_version}"
        delivery = CampaignEmailDelivery.objects.create(
            batch=batch, target_type=CampaignEmailDelivery.TargetType.SHOP, target_id=shop.pk,
            shop_access_link=link, legacy_shop_delivery=legacy, to_emails=rendered.to,
            cc_emails=rendered.cc, bcc_emails=rendered.bcc,
            from_email=parseaddr(rendered.from_email)[1], from_name=parseaddr(rendered.from_email)[0],
            rendered_subject=rendered.subject,
            rendered_body_redacted=redact_access_urls(email_body_html(rendered.body)),
            template_version=config.template_version, idempotency_key=key,
        )
        messages.append(message_payload(delivery, shop, rendered, {
            "shop_link_id": link.pk, "template_version": config.template_version,
            "response_deadline": link.response_deadline.isoformat(), "link_expires_at": link.expires_at.isoformat(),
        }))
    return batch, messages


def _build_area_batch(request, campaign, target_ids, config, kind):
    confirmation_mode = kind == CampaignEmailBatch.EmailType.AREA_CONFIRMATION
    valid_ids = set(_eligible_area_ids(campaign, confirmation=confirmation_mode))
    ids = [item for item in target_ids if item in valid_ids]
    areas = list(AreaManager.objects.filter(pk__in=ids).order_by("areaManager_name", "pk"))
    if len(areas) != len(set(target_ids)):
        raise ValueError("Danh sách QLKV đã thay đổi; hãy chuẩn bị lại batch.")
    batch = CampaignEmailBatch.objects.create(
        campaign=campaign, email_type=kind,
        transport_provider=CampaignEmailBatch.TransportProvider.MICROSOFT_GRAPH,
        idempotency_key=f"bulk:{campaign.pk}:{kind}:{uuid.uuid4()}", total_count=len(areas), requested_by=request.user,
    )
    messages = []
    for area in areas:
        email = _area_email(area)
        if not email:
            raise ValueError(f"Email QLKV {area.areaManager_code} không hợp lệ; hãy chuẩn bị lại batch.")
        link, token = issue_area_manager_access_link(
            campaign=campaign, area_manager=area, allowed_email=email, created_by=request.user,
            stage=(
                AreaManagerAccessLink.Stage.CONFIRMATION
                if confirmation_mode else AreaManagerAccessLink.Stage.MONITORING
            ),
            expires_at=campaign.area_response_deadline if confirmation_mode else campaign.link_expires_at,
        )
        url = request.build_absolute_uri(reverse("document_campaigns:public_area_manager_view", kwargs={"raw_token": token}))
        rendered = render_area_email(
            config, campaign, area, url, confirmation_mode=confirmation_mode, expires_at=link.expires_at,
        )
        key = f"batch:{batch.pk}:area:{area.pk}:{link.stage}:template:{config.template_version}"
        delivery = CampaignEmailDelivery.objects.create(
            batch=batch, target_type=CampaignEmailDelivery.TargetType.AREA_MANAGER, target_id=area.pk,
            area_access_link=link, to_emails=rendered.to, cc_emails=rendered.cc, bcc_emails=rendered.bcc,
            from_email=parseaddr(rendered.from_email)[1], from_name=parseaddr(rendered.from_email)[0],
            rendered_subject=rendered.subject,
            rendered_body_redacted=redact_access_urls(email_body_html(rendered.body)),
            template_version=config.template_version, idempotency_key=key,
        )
        AreaManagerAccessLink.objects.filter(pk=link.pk).update(
            email_status=AreaManagerAccessLink.EmailStatus.QUEUED, email_message="Đang chờ gửi email hàng loạt."
        )
        messages.append(message_payload(delivery, area, rendered, {
            "area_access_link_id": link.pk, "template_version": config.template_version,
            "link_expires_at": link.expires_at.isoformat(),
        }))
    return batch, messages


@login_required
@require_POST
def send_bulk_email_batches(request, campaign_id):
    if not _is_admin(request.user):
        return JsonResponse({"ok": False, "error": "Chỉ Admin được gửi email hàng loạt."}, status=403)
    campaign = get_object_or_404(Campaign, pk=campaign_id)
    try:
        payload = json.loads(request.body)
        kind = payload["kind"]
        selections = payload["batches"]
        if kind not in SUPPORTED_KINDS or not isinstance(selections, list) or not selections:
            raise ValueError
        normalized = []
        for selection in selections:
            ids = [int(item) for item in selection]
            if not ids or len(ids) > 50 or len(ids) != len(set(ids)):
                raise ValueError
            normalized.append(ids)
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        return JsonResponse({"ok": False, "error": "Danh sách batch không hợp lệ."}, status=400)
    try:
        config = _validate_campaign(campaign, kind)
        _validate_graph_configuration()
        queued = []
        with transaction.atomic():
            for ids in normalized:
                batch, messages = (
                    _build_shop_batch(request, campaign, ids, config)
                    if kind == CampaignEmailBatch.EmailType.PGD_RESPONSE
                    else _build_area_batch(request, campaign, ids, config, kind)
                )
                queued.append({"batch_id": str(batch.pk), "messages": messages})
    except (ValueError, EmailTemplateError) as exc:
        return JsonResponse({"ok": False, "error": str(exc)}, status=409)
    from app_document_campaigns.tasks import send_bulk_campaign_email_batches
    try:
        send_bulk_campaign_email_batches.delay(queued)
    except Exception:
        batch_ids = [item["batch_id"] for item in queued]
        CampaignEmailBatch.objects.filter(pk__in=batch_ids).update(
            status=CampaignEmailBatch.Status.FAILED,
            failed_count=F("total_count"),
            completed_at=timezone.now(),
            last_error_code="queue_unavailable",
            last_error_message="Không kết nối được Celery broker.",
        )
        return JsonResponse({"ok": False, "error": "Đã chuẩn bị batch nhưng không kết nối được hàng đợi xử lý."}, status=503)
    return JsonResponse({"ok": True, "batch_count": len(queued), "email_count": sum(len(item["messages"]) for item in queued), "message": "Đã đưa các batch email vào hàng đợi."}, status=202)
