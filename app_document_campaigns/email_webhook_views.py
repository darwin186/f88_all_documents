import hashlib
import json
import secrets
import uuid

from django.conf import settings
from django.db import transaction
from django.db.models import Count, Q
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from app_document_campaigns.models import (
    AreaManagerAccessLink,
    CampaignEmailBatch,
    CampaignEmailDelivery,
    CampaignEmailWebhookEvent,
    ShopEmailDelivery,
)


def _error(message, status):
    return JsonResponse({"ok": False, "error": message}, status=status)


@csrf_exempt
@require_POST
def power_automate_email_callback(request):
    expected = settings.POWER_AUTOMATE_EMAIL_CALLBACK_SECRET
    supplied = request.headers.get("X-Webhook-Secret", "")
    if not expected or not secrets.compare_digest(supplied, expected):
        return _error("Unauthorized webhook.", 401)
    if len(request.body) > settings.POWER_AUTOMATE_EMAIL_MAX_CALLBACK_BYTES:
        return _error("Payload quá lớn.", 413)
    if request.content_type != "application/json":
        return _error("Content-Type phải là application/json.", 415)
    try:
        payload = json.loads(request.body)
        event_id = uuid.UUID(str(payload["event_id"]))
        batch_id = uuid.UUID(str(payload["batch_id"]))
        results = payload["results"]
        if not isinstance(results, list):
            raise ValueError
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        return _error("Payload callback không hợp lệ.", 400)

    digest = hashlib.sha256(request.body).hexdigest()
    with transaction.atomic():
        batch = CampaignEmailBatch.objects.select_for_update().filter(pk=batch_id).first()
        if batch is None:
            return _error("Không tìm thấy batch.", 404)
        existing = CampaignEmailWebhookEvent.objects.filter(event_id=event_id).first()
        if existing:
            if existing.payload_digest != digest:
                return _error("event_id đã được dùng cho payload khác.", 409)
            return JsonResponse({"ok": True, "duplicate": True, "batch_id": str(batch.pk)})

        event = CampaignEmailWebhookEvent.objects.create(
            event_id=event_id,
            batch=batch,
            payload_digest=digest,
            status=CampaignEmailWebhookEvent.Status.REJECTED,
        )
        now = timezone.now()
        if any(not isinstance(item, dict) or item.get("status") not in {"accepted", "sent", "failed"} for item in results):
            event.message = "Có status kết quả không được hỗ trợ."
            event.processed_at = now
            event.save(update_fields=["message", "processed_at"])
            return _error("Status callback không hợp lệ.", 400)
        for result in results:
            try:
                message_id = uuid.UUID(str(result["message_id"]))
                result_status = result["status"]
            except (KeyError, TypeError, ValueError):
                event.message = "Có result không hợp lệ."
                event.processed_at = now
                event.save(update_fields=["message", "processed_at"])
                return _error("Result callback không hợp lệ.", 400)
            delivery = CampaignEmailDelivery.objects.select_for_update().filter(pk=message_id, batch=batch).first()
            if delivery is None:
                event.message = "message_id không thuộc batch."
                event.processed_at = now
                event.save(update_fields=["message", "processed_at"])
                return _error("message_id không thuộc batch.", 400)
            _apply_result(delivery, result, result_status, now)

        counts = batch.deliveries.aggregate(
            accepted=Count("id", filter=Q(status=CampaignEmailDelivery.Status.ACCEPTED)),
            sent=Count("id", filter=Q(status=CampaignEmailDelivery.Status.SENT)),
            failed=Count("id", filter=Q(status=CampaignEmailDelivery.Status.FAILED)),
            skipped=Count("id", filter=Q(status=CampaignEmailDelivery.Status.SKIPPED)),
        )
        batch.accepted_count = counts["accepted"]
        batch.sent_count = counts["sent"]
        batch.failed_count = counts["failed"]
        batch.skipped_count = counts["skipped"]
        terminal = batch.sent_count + batch.failed_count + batch.skipped_count
        if terminal >= batch.total_count:
            batch.status = CampaignEmailBatch.Status.COMPLETED if not batch.failed_count else (
                CampaignEmailBatch.Status.FAILED if batch.failed_count == batch.total_count else CampaignEmailBatch.Status.PARTIALLY_FAILED
            )
            batch.completed_at = now
        else:
            batch.status = CampaignEmailBatch.Status.PROCESSING
        batch.save(update_fields=["accepted_count", "sent_count", "failed_count", "skipped_count", "status", "completed_at", "updated_at"])
        event.status = CampaignEmailWebhookEvent.Status.PROCESSED
        event.message = f"Đã xử lý {len(results)} kết quả."
        event.processed_at = now
        event.save(update_fields=["status", "message", "processed_at"])
    return JsonResponse({"ok": True, "duplicate": False, "batch_id": str(batch.pk), "status": batch.status})


def _apply_result(delivery, result, result_status, now):
    # SENT is monotonic: a delayed failed callback must never downgrade it.
    if delivery.status == CampaignEmailDelivery.Status.SENT:
        return
    provider_message_id = str(result.get("provider_message_id") or "")[:255]
    if result_status == "sent":
        delivery.status = CampaignEmailDelivery.Status.SENT
        delivery.sent_at = now
        delivery.failed_at = None
        delivery.error_code = ""
        delivery.error_message = ""
    elif result_status == "failed":
        delivery.status = CampaignEmailDelivery.Status.FAILED
        delivery.failed_at = now
        delivery.error_code = str(result.get("error_code") or "provider_failed")[:100]
        delivery.error_message = str(result.get("error_message") or "Power Automate gửi email thất bại.")[:500]
    elif result_status == "accepted":
        delivery.status = CampaignEmailDelivery.Status.ACCEPTED
        delivery.accepted_at = delivery.accepted_at or now
    else:
        raise ValueError("Unsupported callback status")
    delivery.provider_message_id = provider_message_id
    delivery.save(update_fields=["status", "accepted_at", "sent_at", "failed_at", "error_code", "error_message", "provider_message_id", "updated_at"])
    if delivery.legacy_shop_delivery_id:
        legacy_status = "sent" if delivery.status == CampaignEmailDelivery.Status.SENT else (
            "failed" if delivery.status == CampaignEmailDelivery.Status.FAILED else "sending"
        )
        ShopEmailDelivery.objects.filter(pk=delivery.legacy_shop_delivery_id).update(
            status=legacy_status,
            message="Đã gửi email thành công." if legacy_status == "sent" else delivery.error_message,
            finished_at=now if legacy_status in {"sent", "failed"} else None,
        )
    if delivery.area_access_link_id:
        area_status = AreaManagerAccessLink.EmailStatus.SENT if delivery.status == CampaignEmailDelivery.Status.SENT else (
            AreaManagerAccessLink.EmailStatus.FAILED if delivery.status == CampaignEmailDelivery.Status.FAILED else AreaManagerAccessLink.EmailStatus.QUEUED
        )
        AreaManagerAccessLink.objects.filter(pk=delivery.area_access_link_id).update(
            email_status=area_status,
            email_message="Đã gửi email QLKV thành công." if area_status == AreaManagerAccessLink.EmailStatus.SENT else delivery.error_message,
            emailed_at=now if area_status == AreaManagerAccessLink.EmailStatus.SENT else None,
        )
