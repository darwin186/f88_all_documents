import base64
import json
import logging
import threading
import time
import uuid
from dataclasses import dataclass
from email.utils import parseaddr
from urllib.parse import quote

import requests
from django.conf import settings
from django.db.models import Count, Q
from django.utils import timezone

from app_document_campaigns.models import (
    AreaManagerAccessLink,
    CampaignEmailAttempt,
    CampaignEmailBatch,
    CampaignEmailDelivery,
    ShopEmailDelivery,
)
from app_document_campaigns.services.email_html import email_body_html


logger = logging.getLogger(__name__)
_token_lock = threading.Lock()
_token_value = ""
_token_expires_at = 0.0


class MicrosoftGraphConfigurationError(RuntimeError):
    pass


class MicrosoftGraphTransportError(RuntimeError):
    def __init__(self, message, *, code="graph_error", retryable=False, http_status=None):
        super().__init__(message)
        self.code = code
        self.retryable = retryable
        self.http_status = http_status


@dataclass(frozen=True)
class GraphSendResult:
    request_id: str
    http_status: int


def _configuration():
    tenant_id = settings.MICROSOFT_GRAPH_TENANT_ID
    client_id = settings.MICROSOFT_GRAPH_CLIENT_ID
    client_secret = settings.MICROSOFT_GRAPH_CLIENT_SECRET
    sender_email = settings.MICROSOFT_GRAPH_SENDER_EMAIL
    mailbox_email = settings.MICROSOFT_GRAPH_MAILBOX_EMAIL
    if not tenant_id or not client_id or not client_secret or not sender_email or not mailbox_email:
        raise MicrosoftGraphConfigurationError(
            "Thiếu MS_TENANT_ID, MS_APPLICATION_ID, MS_VALUE, địa chỉ hiển thị "
            "MS_GRAPH_SENDER_EMAIL hoặc mailbox MS_GRAPH_MAILBOX_EMAIL."
        )
    return tenant_id, client_id, client_secret, mailbox_email, sender_email


def _access_token(*, force_refresh=False):
    global _token_value, _token_expires_at
    now = time.monotonic()
    if not force_refresh and _token_value and now < _token_expires_at - 60:
        return _token_value
    with _token_lock:
        now = time.monotonic()
        if not force_refresh and _token_value and now < _token_expires_at - 60:
            return _token_value
        tenant_id, client_id, client_secret, _, _ = _configuration()
        request_id = str(uuid.uuid4())
        try:
            response = requests.post(
                f"https://login.microsoftonline.com/{quote(tenant_id, safe='')}/oauth2/v2.0/token",
                data={
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "scope": "https://graph.microsoft.com/.default",
                    "grant_type": "client_credentials",
                },
                headers={"Accept": "application/json", "client-request-id": request_id},
                timeout=(settings.MICROSOFT_GRAPH_CONNECT_TIMEOUT, settings.MICROSOFT_GRAPH_READ_TIMEOUT),
            )
        except requests.Timeout as exc:
            raise MicrosoftGraphTransportError(
                "Microsoft identity token endpoint bị timeout.", code="token_timeout", retryable=True
            ) from exc
        except requests.RequestException as exc:
            raise MicrosoftGraphTransportError(
                "Không kết nối được Microsoft identity token endpoint.",
                code="token_connection_error",
                retryable=True,
            ) from exc
        if response.status_code != 200:
            logger.error(
                "MICROSOFT_GRAPH_TOKEN_REJECTED status=%s request_id=%s",
                response.status_code,
                request_id,
            )
            raise MicrosoftGraphTransportError(
                f"Microsoft identity từ chối thông tin ứng dụng (HTTP {response.status_code}).",
                code="token_rejected",
                retryable=response.status_code == 429 or response.status_code >= 500,
                http_status=response.status_code,
            )
        try:
            payload = response.json()
            token = payload["access_token"]
            expires_in = max(120, int(payload.get("expires_in", 3600)))
        except (KeyError, TypeError, ValueError) as exc:
            raise MicrosoftGraphTransportError(
                "Microsoft identity trả token không hợp lệ.", code="invalid_token_response"
            ) from exc
        try:
            encoded_claims = token.split(".")[1]
            encoded_claims += "=" * (-len(encoded_claims) % 4)
            claims = json.loads(base64.urlsafe_b64decode(encoded_claims))
        except (IndexError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise MicrosoftGraphTransportError(
                "Microsoft identity trả access token không đọc được.", code="invalid_access_token"
            ) from exc
        # Exchange Online Application RBAC grants are independent from Entra
        # application permissions. With RBAC, a valid app-only token may not
        # contain a Mail.Send role claim; Exchange evaluates the scoped role
        # when /users/{sender}/sendMail is called. Do not reject that valid
        # setup before Graph has a chance to authorize the sender mailbox.
        if "Mail.Send" not in (claims.get("roles") or []):
            logger.warning(
                "MICROSOFT_GRAPH_TOKEN_WITHOUT_MAIL_SEND_ROLE "
                "client_id=%s relying_on=exchange_application_rbac",
                claims.get("appid") or claims.get("azp") or client_id,
            )
        _token_value = token
        _token_expires_at = time.monotonic() + expires_in
        return token


def _recipient(address):
    return {"emailAddress": {"address": address}}


def _graph_message(payload):
    body = payload.get("body") or {}
    message = {
        "subject": payload.get("subject") or "",
        "body": {
            "contentType": "HTML" if str(body.get("content_type", "html")).lower() == "html" else "Text",
            "content": body.get("content") or "",
        },
        "toRecipients": [_recipient(value) for value in payload.get("to") or []],
        "ccRecipients": [_recipient(value) for value in payload.get("cc") or []],
        "bccRecipients": [_recipient(value) for value in payload.get("bcc") or []],
    }
    from_address = parseaddr((payload.get("from") or {}).get("address", ""))[1]
    if from_address:
        message["from"] = _recipient(from_address)
    return message


def send_message(payload, *, token=None):
    _, _, _, configured_mailbox, configured_sender = _configuration()
    requested_sender = parseaddr((payload.get("from") or {}).get("address", ""))[1]
    if requested_sender and requested_sender.casefold() != configured_sender.casefold():
        logger.warning(
            "MICROSOFT_GRAPH_FROM_OVERRIDDEN requested_sender=%s configured_sender=%s",
            requested_sender,
            configured_sender,
        )
    payload = dict(payload)
    payload["from"] = {**(payload.get("from") or {}), "address": configured_sender}
    if not payload.get("to"):
        raise MicrosoftGraphConfigurationError("Email Microsoft Graph không có người nhận.")
    access_token = token or _access_token()
    request_id = str(uuid.uuid4())
    endpoint = f"https://graph.microsoft.com/v1.0/users/{quote(configured_mailbox, safe='@.')}/sendMail"
    try:
        response = requests.post(
            endpoint,
            json={"message": _graph_message(payload), "saveToSentItems": True},
            headers={
                "Authorization": f"Bearer {access_token}",
                "Accept": "application/json",
                "Content-Type": "application/json",
                "client-request-id": request_id,
                "return-client-request-id": "true",
            },
            timeout=(settings.MICROSOFT_GRAPH_CONNECT_TIMEOUT, settings.MICROSOFT_GRAPH_READ_TIMEOUT),
        )
    except requests.Timeout as exc:
        raise MicrosoftGraphTransportError(
            "Microsoft Graph gửi email bị timeout; chưa thể xác định email đã được nhận hay chưa.",
            code="graph_timeout_unknown",
            retryable=False,
        ) from exc
    except requests.RequestException as exc:
        raise MicrosoftGraphTransportError(
            "Không kết nối được Microsoft Graph.", code="graph_connection_error", retryable=True
        ) from exc
    if response.status_code != 202:
        logger.error(
            "MICROSOFT_GRAPH_SEND_REJECTED status=%s request_id=%s mailbox=%s sender=%s",
            response.status_code,
            request_id,
            configured_mailbox,
            configured_sender,
        )
        raise MicrosoftGraphTransportError(
            f"Microsoft Graph từ chối email (HTTP {response.status_code}).",
            code="graph_rejected",
            retryable=response.status_code == 429 or response.status_code >= 500,
            http_status=response.status_code,
        )
    return GraphSendResult(request_id=request_id, http_status=response.status_code)


def send_rendered_email(rendered):
    return send_message({
        "from": {"address": parseaddr(rendered.from_email)[1]},
        "to": rendered.to,
        "cc": rendered.cc,
        "bcc": rendered.bcc,
        "subject": rendered.subject,
        "body": {"content_type": "html", "content": email_body_html(rendered.body)},
    })


def _record_attempt(delivery, result=None, error=None, started=None):
    duration_ms = max(0, int((time.monotonic() - started) * 1000)) if started is not None else 0
    attempt_number = delivery.attempt_count + 1
    if result:
        outcome = CampaignEmailAttempt.Outcome.ACCEPTED
        request_id = result.request_id
        http_status = result.http_status
        error_code = ""
        error_message = ""
    else:
        outcome = (
            CampaignEmailAttempt.Outcome.TIMEOUT
            if getattr(error, "code", "") == "graph_timeout_unknown"
            else CampaignEmailAttempt.Outcome.REJECTED
        )
        request_id = uuid.uuid4()
        http_status = getattr(error, "http_status", None)
        error_code = getattr(error, "code", "graph_send_failed")
        error_message = str(error)[:500]
    CampaignEmailAttempt.objects.create(
        delivery=delivery,
        attempt_number=attempt_number,
        request_id=request_id,
        http_status=http_status,
        provider_batch_id=f"graph:{delivery.batch_id}",
        outcome=outcome,
        duration_ms=duration_ms,
        error_code=error_code,
        error_message=error_message,
    )
    CampaignEmailDelivery.objects.filter(pk=delivery.pk).update(attempt_count=attempt_number)


def dispatch_email_batch(batch, messages):
    now = timezone.now()
    provider_batch_id = f"graph:{batch.pk}"
    CampaignEmailBatch.objects.filter(pk=batch.pk).update(
        status=CampaignEmailBatch.Status.DISPATCHING,
        submitted_at=now,
        provider_batch_id=provider_batch_id,
    )
    token = _access_token()
    _, _, _, _, configured_sender = _configuration()
    for payload in messages:
        delivery = CampaignEmailDelivery.objects.get(pk=payload["message_id"], batch=batch)
        CampaignEmailDelivery.objects.filter(pk=delivery.pk).update(
            status=CampaignEmailDelivery.Status.SUBMITTING,
            from_email=configured_sender,
        )
        started = time.monotonic()
        try:
            result = send_message(payload, token=token)
            sent_at = timezone.now()
            _record_attempt(delivery, result=result, started=started)
            CampaignEmailDelivery.objects.filter(pk=delivery.pk).update(
                status=CampaignEmailDelivery.Status.SENT,
                provider_batch_id=provider_batch_id,
                provider_message_id=result.request_id,
                accepted_at=sent_at,
                sent_at=sent_at,
                failed_at=None,
                error_code="",
                error_message="",
            )
            if delivery.legacy_shop_delivery_id:
                ShopEmailDelivery.objects.filter(pk=delivery.legacy_shop_delivery_id).update(
                    status="sent",
                    message="Microsoft Graph đã nhận yêu cầu gửi email.",
                    finished_at=sent_at,
                )
            if delivery.area_access_link_id:
                AreaManagerAccessLink.objects.filter(pk=delivery.area_access_link_id).update(
                    email_status=AreaManagerAccessLink.EmailStatus.SENT,
                    email_message="Microsoft Graph đã nhận yêu cầu gửi email QLKV.",
                    emailed_at=sent_at,
                )
        except Exception as exc:
            failed_at = timezone.now()
            _record_attempt(delivery, error=exc, started=started)
            CampaignEmailDelivery.objects.filter(pk=delivery.pk).update(
                status=CampaignEmailDelivery.Status.FAILED,
                failed_at=failed_at,
                error_code=getattr(exc, "code", "graph_send_failed"),
                error_message=str(exc)[:500],
            )
            if delivery.legacy_shop_delivery_id:
                ShopEmailDelivery.objects.filter(pk=delivery.legacy_shop_delivery_id).update(
                    status="failed", message="Không gửi được email qua Microsoft Graph.", finished_at=failed_at
                )
            if delivery.area_access_link_id:
                AreaManagerAccessLink.objects.filter(pk=delivery.area_access_link_id).update(
                    email_status=AreaManagerAccessLink.EmailStatus.FAILED,
                    email_message="Không gửi được email QLKV qua Microsoft Graph.",
                )
    counts = batch.deliveries.aggregate(
        sent=Count("id", filter=Q(status=CampaignEmailDelivery.Status.SENT)),
        failed=Count("id", filter=Q(status=CampaignEmailDelivery.Status.FAILED)),
    )
    status = CampaignEmailBatch.Status.COMPLETED
    if counts["failed"]:
        status = (
            CampaignEmailBatch.Status.FAILED
            if counts["failed"] == batch.total_count
            else CampaignEmailBatch.Status.PARTIALLY_FAILED
        )
    CampaignEmailBatch.objects.filter(pk=batch.pk).update(
        status=status,
        sent_count=counts["sent"],
        failed_count=counts["failed"],
        completed_at=timezone.now(),
    )
    return counts
