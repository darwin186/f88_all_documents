from __future__ import annotations

import json
import logging
import uuid
from typing import Any

from django.conf import settings
from django.core.exceptions import RequestDataTooBig
from django.db import DatabaseError, connection
from django.http import HttpRequest, JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from .credentials import verify_relay_secret
from .models import GapoRelayCredential
from .services import acknowledge_events, claim_events, reject_event, store_event

logger = logging.getLogger(__name__)


def _reject_json_constant(value: str):
    raise ValueError(f"Invalid JSON constant: {value}")


def _unauthorized() -> JsonResponse:
    response = JsonResponse({"ok": False, "error": "unauthorized"}, status=401)
    response["WWW-Authenticate"] = "Bearer"
    return response


def _delivery_auth_error(request: HttpRequest) -> JsonResponse | None:
    authorization = request.headers.get("Authorization", "")
    supplied = authorization[7:] if authorization.startswith("Bearer ") else ""
    try:
        authorized = verify_relay_secret(
            GapoRelayCredential.Kind.DELIVERY,
            supplied,
        )
    except DatabaseError:
        logger.exception("GAPO relay credential lookup failed")
        return JsonResponse({"ok": False, "error": "database_error"}, status=500)
    return None if authorized else _unauthorized()


def _content_length(request: HttpRequest) -> int | None:
    supplied = request.META.get("CONTENT_LENGTH")
    try:
        return int(supplied) if supplied not in (None, "") else None
    except (TypeError, ValueError):
        return None


def _read_json_object(
    request: HttpRequest, max_body_bytes: int
) -> tuple[dict[str, Any] | None, JsonResponse | None, bytes | None]:
    if (request.content_type or "").lower() != "application/json":
        return None, JsonResponse(
            {"ok": False, "error": "json_required"}, status=415
        ), None

    content_length = _content_length(request)
    if content_length is not None and content_length > max_body_bytes:
        return None, JsonResponse(
            {"ok": False, "error": "payload_too_large"}, status=413
        ), None
    try:
        raw_body = request.body
    except RequestDataTooBig:
        return None, JsonResponse(
            {"ok": False, "error": "payload_too_large"}, status=413
        ), None
    if len(raw_body) > max_body_bytes:
        return None, JsonResponse(
            {"ok": False, "error": "payload_too_large"}, status=413
        ), None
    try:
        payload = json.loads(
            raw_body.decode("utf-8"),
            parse_constant=_reject_json_constant,
        )
    except (UnicodeDecodeError, ValueError, RecursionError):
        return None, JsonResponse(
            {"ok": False, "error": "invalid_json"}, status=400
        ), None
    if not isinstance(payload, dict):
        return None, JsonResponse(
            {"ok": False, "error": "object_required"}, status=400
        ), None
    return payload, None, raw_body


def _api_payload(request: HttpRequest) -> tuple[dict[str, Any] | None, JsonResponse | None]:
    max_bytes = int(getattr(settings, "GAPO_RELAY_DELIVERY_MAX_BODY_BYTES", 65536))
    payload, error, _ = _read_json_object(request, max_bytes)
    return payload, error


def _rfc3339(value) -> str:
    local_timezone = timezone.get_default_timezone()
    if timezone.is_naive(value):
        value = timezone.make_aware(value, local_timezone)
    return value.astimezone(local_timezone).isoformat()


def _integer_field(
    payload: dict[str, Any],
    name: str,
    *,
    default: int | None = None,
    minimum: int,
    maximum: int,
) -> tuple[int | None, JsonResponse | None]:
    value = payload.get(name, default)
    if isinstance(value, bool) or not isinstance(value, int):
        return None, JsonResponse(
            {"ok": False, "error": f"invalid_{name}"}, status=400
        )
    if value < minimum or value > maximum:
        return None, JsonResponse(
            {"ok": False, "error": f"invalid_{name}"}, status=400
        )
    return value, None


def _lease_token(payload: dict[str, Any]) -> tuple[uuid.UUID | None, JsonResponse | None]:
    try:
        return uuid.UUID(str(payload.get("lease_token", ""))), None
    except (ValueError, TypeError, AttributeError):
        return None, JsonResponse(
            {"ok": False, "error": "invalid_lease_token"}, status=400
        )


@require_GET
def health(request: HttpRequest) -> JsonResponse:
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
    except DatabaseError:
        logger.exception("GAPO relay database health check failed")
        return JsonResponse({"ok": False, "database": "error"}, status=503)
    return JsonResponse({"ok": True, "database": "ok"})


@csrf_exempt
@require_POST
def ingress(request: HttpRequest, secret: str) -> JsonResponse:
    received_at = timezone.now()
    try:
        authorized = verify_relay_secret(GapoRelayCredential.Kind.INGRESS, secret)
    except DatabaseError:
        logger.exception("GAPO relay credential lookup failed")
        return JsonResponse({"ok": False, "error": "database_error"}, status=500)
    if not authorized:
        return _unauthorized()

    max_bytes = int(getattr(settings, "GAPO_RELAY_MAX_BODY_BYTES", 10 * 1024 * 1024))
    payload, error, raw_body = _read_json_object(request, max_bytes)
    if error is not None:
        return error
    assert payload is not None and raw_body is not None

    try:
        event, created = store_event(payload, raw_body, received_at=received_at)
    except DatabaseError:
        logger.exception("GAPO relay failed to persist an ingress event")
        return JsonResponse({"ok": False, "error": "database_error"}, status=500)

    return JsonResponse(
        {
            "ok": True,
            "event_id": event.event_id,
            "duplicate": not created,
            "received_at": _rfc3339(event.received_at),
        }
    )


@csrf_exempt
@require_POST
def claim(request: HttpRequest) -> JsonResponse:
    auth_error = _delivery_auth_error(request)
    if auth_error is not None:
        return auth_error
    payload, error = _api_payload(request)
    if error is not None:
        return error
    assert payload is not None

    consumer_id = payload.get("consumer_id")
    if not isinstance(consumer_id, str) or not consumer_id.strip() or len(consumer_id) > 200:
        return JsonResponse({"ok": False, "error": "invalid_consumer_id"}, status=400)

    max_batch = int(getattr(settings, "GAPO_RELAY_MAX_BATCH_SIZE", 100))
    limit, error = _integer_field(
        payload, "limit", default=min(50, max_batch), minimum=1, maximum=max_batch
    )
    if error is not None:
        return error
    max_lease = int(getattr(settings, "GAPO_RELAY_MAX_LEASE_SECONDS", 3600))
    lease_seconds, error = _integer_field(
        payload,
        "lease_seconds",
        default=int(getattr(settings, "GAPO_RELAY_DEFAULT_LEASE_SECONDS", 120)),
        minimum=1,
        maximum=max_lease,
    )
    if error is not None:
        return error
    assert limit is not None and lease_seconds is not None

    lease_token, events = claim_events(limit, lease_seconds)
    return JsonResponse(
        {
            "lease_token": str(lease_token),
            "events": [
                {
                    "event_id": event.event_id,
                    "event_type": event.event_type,
                    "received_at": _rfc3339(event.received_at),
                    "thread_id": event.thread_id,
                    "message_id": event.message_id,
                    "attempt_count": event.attempt_count,
                    "payload_sha256": event.payload_sha256,
                    "payload": event.raw_payload,
                }
                for event in events
            ],
        }
    )


@csrf_exempt
@require_POST
def ack(request: HttpRequest) -> JsonResponse:
    auth_error = _delivery_auth_error(request)
    if auth_error is not None:
        return auth_error
    payload, error = _api_payload(request)
    if error is not None:
        return error
    assert payload is not None

    lease_token, error = _lease_token(payload)
    if error is not None:
        return error
    event_ids = payload.get("event_ids")
    max_batch = int(getattr(settings, "GAPO_RELAY_MAX_BATCH_SIZE", 100))
    if (
        not isinstance(event_ids, list)
        or not event_ids
        or len(event_ids) > max_batch
        or any(not isinstance(event_id, str) or not event_id for event_id in event_ids)
    ):
        return JsonResponse({"ok": False, "error": "invalid_event_ids"}, status=400)
    unique_event_ids = list(dict.fromkeys(event_ids))
    assert lease_token is not None
    acknowledged = acknowledge_events(lease_token, unique_event_ids)
    return JsonResponse(
        {
            "ok": True,
            "acknowledged": acknowledged,
            "ignored": len(unique_event_ids) - acknowledged,
        }
    )


@csrf_exempt
@require_POST
def nack(request: HttpRequest) -> JsonResponse:
    auth_error = _delivery_auth_error(request)
    if auth_error is not None:
        return auth_error
    payload, error_response = _api_payload(request)
    if error_response is not None:
        return error_response
    assert payload is not None

    lease_token, error_response = _lease_token(payload)
    if error_response is not None:
        return error_response
    event_id = payload.get("event_id")
    error_message = payload.get("error")
    if not isinstance(event_id, str) or not event_id:
        return JsonResponse({"ok": False, "error": "invalid_event_id"}, status=400)
    if not isinstance(error_message, str):
        return JsonResponse({"ok": False, "error": "invalid_error"}, status=400)

    http_status = payload.get("http_status")
    if http_status is not None and (
        isinstance(http_status, bool)
        or not isinstance(http_status, int)
        or not 100 <= http_status <= 599
    ):
        return JsonResponse({"ok": False, "error": "invalid_http_status"}, status=400)
    assert lease_token is not None
    result = reject_event(
        lease_token,
        event_id,
        error_message,
        http_status=http_status,
    )
    if result.event is None:
        return JsonResponse({"ok": False, "error": "lease_not_found"}, status=409)
    return JsonResponse(
        {
            "ok": True,
            "event_id": result.event.event_id,
            "status": result.event.delivery_status,
            "retry_after_seconds": result.retry_after_seconds,
        }
    )
