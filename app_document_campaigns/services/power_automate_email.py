import hashlib
import hmac
import json
import re
import time
import uuid
from dataclasses import dataclass
from email.utils import parseaddr

import requests
from django.conf import settings
from django.utils import timezone

from app_document_campaigns.models import CampaignEmailAttempt, CampaignEmailBatch, CampaignEmailDelivery
from app_document_campaigns.services.email_html import email_body_html


class PowerAutomateConfigurationError(RuntimeError):
    pass


class PowerAutomateTransportError(RuntimeError):
    def __init__(self, message, *, retryable=False, code="transport_error"):
        super().__init__(message)
        self.retryable = retryable
        self.code = code


@dataclass(frozen=True)
class DispatchResult:
    request_id: str
    provider_batch_id: str
    accepted_message_ids: tuple[str, ...]


def _configuration():
    url = settings.POWER_AUTOMATE_EMAIL_WEBHOOK_URL
    secret = settings.POWER_AUTOMATE_EMAIL_WEBHOOK_SECRET
    callback_url = settings.POWER_AUTOMATE_EMAIL_CALLBACK_URL
    if not url or not secret or not callback_url:
        raise PowerAutomateConfigurationError(
            "Thiếu POWER_AUTOMATE_EMAIL_WEBHOOK_URL, POWER_AUTOMATE_EMAIL_WEBHOOK_SECRET "
            "hoặc POWER_AUTOMATE_EMAIL_CALLBACK_URL."
        )
    return url, secret, callback_url


def dispatch_email_chunk(batch: CampaignEmailBatch, messages: list[dict]) -> DispatchResult:
    """Submit one chunk and mark only accepted messages; HTTP 202 is not `sent`."""
    url, secret, callback_url = _configuration()
    request_id = str(uuid.uuid4())
    requested_at = timezone.now()
    payload = {
        "schema_version": "1.0",
        "batch_id": str(batch.pk),
        "request_id": request_id,
        "requested_at": requested_at.isoformat(),
        "source": "ida-chungtu",
        "email_type": batch.email_type,
        "campaign": {
            "id": batch.campaign_id,
            "code": batch.campaign.code,
            "name": batch.campaign.name,
            "report_month": batch.campaign.report_month.strftime("%Y-%m"),
        },
        "callback": {"url": callback_url},
        "messages": messages,
    }
    encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    timestamp = str(int(requested_at.timestamp()))
    signature = hmac.new(secret.encode("utf-8"), timestamp.encode("ascii") + b"." + encoded, hashlib.sha256).hexdigest()
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": "ida-chungtu/1.0",
        "X-Schema-Version": "1",
        "X-Request-ID": request_id,
        "Idempotency-Key": f"{batch.idempotency_key}:request:{request_id}",
        "X-Timestamp": timestamp,
        "X-Webhook-Secret": secret,
        "X-Signature": f"sha256={signature}",
    }
    delivery_ids = [message["message_id"] for message in messages]
    deliveries = list(CampaignEmailDelivery.objects.filter(batch=batch, pk__in=delivery_ids))
    CampaignEmailDelivery.objects.filter(pk__in=delivery_ids, status=CampaignEmailDelivery.Status.QUEUED).update(
        status=CampaignEmailDelivery.Status.SUBMITTING
    )
    batch.status = CampaignEmailBatch.Status.DISPATCHING
    batch.save(update_fields=["status", "updated_at"])
    started = time.monotonic()
    try:
        response = requests.post(
            url,
            data=encoded,
            headers=headers,
            timeout=(settings.POWER_AUTOMATE_EMAIL_CONNECT_TIMEOUT, settings.POWER_AUTOMATE_EMAIL_READ_TIMEOUT),
        )
    except requests.Timeout as exc:
        _record_attempts(deliveries, request_id, None, "timeout", started, error_code="timeout")
        CampaignEmailDelivery.objects.filter(pk__in=delivery_ids).update(status=CampaignEmailDelivery.Status.QUEUED)
        raise PowerAutomateTransportError("Power Automate timeout.", retryable=True, code="timeout") from exc
    except requests.RequestException as exc:
        _record_attempts(deliveries, request_id, None, "transport_error", started, error_code="connection_error")
        CampaignEmailDelivery.objects.filter(pk__in=delivery_ids).update(status=CampaignEmailDelivery.Status.QUEUED)
        raise PowerAutomateTransportError("Không kết nối được Power Automate.", retryable=True, code="connection_error") from exc

    retryable = response.status_code == 429 or response.status_code >= 500
    if response.status_code != 202:
        _record_attempts(deliveries, request_id, response.status_code, "rejected", started, error_code="http_rejected")
        CampaignEmailDelivery.objects.filter(pk__in=delivery_ids).update(
            status=CampaignEmailDelivery.Status.QUEUED if retryable else CampaignEmailDelivery.Status.FAILED,
            error_code="http_rejected",
            error_message=f"Power Automate trả HTTP {response.status_code}.",
        )
        raise PowerAutomateTransportError(
            f"Power Automate từ chối request (HTTP {response.status_code}).",
            retryable=retryable,
            code="http_rejected",
        )
    try:
        result = response.json()
    except ValueError as exc:
        _record_attempts(deliveries, request_id, 202, "rejected", started, error_code="invalid_json")
        CampaignEmailDelivery.objects.filter(pk__in=delivery_ids).update(
            status=CampaignEmailDelivery.Status.QUEUED,
            error_code="invalid_json",
            error_message="Power Automate trả response không phải JSON.",
        )
        raise PowerAutomateTransportError("Power Automate trả response không phải JSON.", retryable=True, code="invalid_json") from exc
    if str(result.get("batch_id")) != str(batch.pk) or result.get("request_id") != request_id or result.get("status") != "accepted":
        _record_attempts(deliveries, request_id, 202, "rejected", started, error_code="invalid_response")
        CampaignEmailDelivery.objects.filter(pk__in=delivery_ids).update(
            status=CampaignEmailDelivery.Status.FAILED,
            failed_at=timezone.now(),
            error_code="invalid_response",
            error_message="Response Power Automate không khớp request.",
        )
        raise PowerAutomateTransportError("Response Power Automate không khớp request.", retryable=False, code="invalid_response")

    result_ids = {
        str(item.get("message_id")) for item in result.get("results", []) if item.get("status") == "accepted"
    }
    accepted_ids = tuple(message_id for message_id in delivery_ids if str(message_id) in result_ids)
    now = timezone.now()
    provider_batch_id = str(result.get("provider_batch_id") or "")[:255]
    CampaignEmailDelivery.objects.filter(pk__in=accepted_ids).update(
        status=CampaignEmailDelivery.Status.ACCEPTED,
        provider_batch_id=provider_batch_id,
        accepted_at=now,
        error_code="",
        error_message="",
    )
    rejected_ids = [message_id for message_id in delivery_ids if str(message_id) not in result_ids]
    CampaignEmailDelivery.objects.filter(pk__in=rejected_ids).update(
        status=CampaignEmailDelivery.Status.FAILED,
        failed_at=now,
        error_code="not_accepted",
        error_message="Power Automate không nhận message này.",
    )
    _record_attempts(deliveries, request_id, 202, "accepted", started, provider_batch_id=provider_batch_id)
    batch.provider_batch_id = provider_batch_id
    batch.submitted_at = now
    batch.status = CampaignEmailBatch.Status.ACCEPTED
    batch.save(update_fields=["provider_batch_id", "submitted_at", "status", "updated_at"])
    return DispatchResult(request_id, provider_batch_id, accepted_ids)


def dispatch_shop_email(link, rendered, template_version, legacy_delivery):
    batch_key = f"campaign:{link.campaign_id}:pgd:{link.shop_id}:link:{link.public_id}:template:{template_version}"
    batch, _ = CampaignEmailBatch.objects.get_or_create(
        idempotency_key=batch_key,
        defaults={
            "campaign": link.campaign,
            "email_type": CampaignEmailBatch.EmailType.PGD_RESPONSE,
            "requested_by": link.created_by,
            "total_count": 1,
        },
    )
    delivery, _ = CampaignEmailDelivery.objects.get_or_create(
        idempotency_key=batch_key,
        defaults={
            "batch": batch,
            "target_type": CampaignEmailDelivery.TargetType.SHOP,
            "target_id": link.shop_id,
            "shop_access_link": link,
            "legacy_shop_delivery": legacy_delivery,
            "to_emails": rendered.to,
            "cc_emails": rendered.cc,
            "bcc_emails": rendered.bcc,
            "from_email": parseaddr(rendered.from_email)[1],
            "from_name": parseaddr(rendered.from_email)[0],
            "rendered_subject": rendered.subject,
            "rendered_body_redacted": _redact_access_urls(email_body_html(rendered.body)),
            "template_version": template_version,
        },
    )
    if delivery.status in {CampaignEmailDelivery.Status.ACCEPTED, CampaignEmailDelivery.Status.SENT}:
        return DispatchResult("duplicate", delivery.provider_batch_id, (str(delivery.pk),))
    delivery.status = CampaignEmailDelivery.Status.QUEUED
    delivery.save(update_fields=["status", "updated_at"])
    return dispatch_email_chunk(batch, [_message_payload(delivery, link.shop, rendered, {
        "shop_link_id": link.pk,
        "template_version": template_version,
        "response_deadline": link.response_deadline.isoformat(),
        "link_expires_at": link.expires_at.isoformat(),
    })])


def dispatch_area_email(link, rendered, template_version):
    email_type = (
        CampaignEmailBatch.EmailType.AREA_CONFIRMATION
        if link.stage == "confirmation" else CampaignEmailBatch.EmailType.AREA_MONITORING
    )
    batch_key = f"campaign:{link.campaign_id}:area:{link.area_manager_id}:stage:{link.stage}:link:{link.public_id}:template:{template_version}"
    batch, _ = CampaignEmailBatch.objects.get_or_create(
        idempotency_key=batch_key,
        defaults={
            "campaign": link.campaign,
            "email_type": email_type,
            "requested_by": link.created_by,
            "total_count": 1,
        },
    )
    delivery, _ = CampaignEmailDelivery.objects.get_or_create(
        idempotency_key=batch_key,
        defaults={
            "batch": batch,
            "target_type": CampaignEmailDelivery.TargetType.AREA_MANAGER,
            "target_id": link.area_manager_id,
            "area_access_link": link,
            "to_emails": rendered.to,
            "cc_emails": rendered.cc,
            "bcc_emails": rendered.bcc,
            "from_email": parseaddr(rendered.from_email)[1],
            "from_name": parseaddr(rendered.from_email)[0],
            "rendered_subject": rendered.subject,
            "rendered_body_redacted": _redact_access_urls(email_body_html(rendered.body)),
            "template_version": template_version,
        },
    )
    if delivery.status in {CampaignEmailDelivery.Status.ACCEPTED, CampaignEmailDelivery.Status.SENT}:
        return DispatchResult("duplicate", delivery.provider_batch_id, (str(delivery.pk),))
    delivery.status = CampaignEmailDelivery.Status.QUEUED
    delivery.save(update_fields=["status", "updated_at"])
    area = link.area_manager
    return dispatch_email_chunk(batch, [_message_payload(delivery, area, rendered, {
        "area_access_link_id": link.pk,
        "template_version": template_version,
        "link_expires_at": link.expires_at.isoformat(),
    })])


def _redact_access_urls(body):
    return re.sub(r"/(respond|manager-view)/[^/&<\s]+/?", r"/\1/[REDACTED]/", body)


def _message_payload(delivery, target, rendered, metadata):
    if delivery.target_type == CampaignEmailDelivery.TargetType.SHOP:
        target_data = {"type": "shop", "id": target.pk, "code": str(target.shop_code or ""), "name": target.shop_name}
    else:
        target_data = {"type": "area_manager", "id": target.pk, "code": str(target.areaManager_code or ""), "name": target.areaManager_name}
    return {
        "message_id": str(delivery.pk),
        "idempotency_key": delivery.idempotency_key,
        "target": target_data,
        "from": {"address": parseaddr(rendered.from_email)[1], "name": parseaddr(rendered.from_email)[0]},
        "to": rendered.to,
        "cc": rendered.cc,
        "bcc": rendered.bcc,
        "subject": rendered.subject,
        "body": {"content_type": "html", "content": email_body_html(rendered.body)},
        "metadata": metadata,
    }


def _record_attempts(deliveries, request_id, http_status, outcome, started, *, provider_batch_id="", error_code=""):
    duration_ms = max(0, int((time.monotonic() - started) * 1000))
    for delivery in deliveries:
        attempt_number = delivery.attempt_count + 1
        CampaignEmailAttempt.objects.create(
            delivery=delivery,
            attempt_number=attempt_number,
            request_id=request_id,
            http_status=http_status,
            provider_batch_id=provider_batch_id,
            outcome=outcome,
            duration_ms=duration_ms,
            error_code=error_code,
        )
        CampaignEmailDelivery.objects.filter(pk=delivery.pk).update(attempt_count=attempt_number)
