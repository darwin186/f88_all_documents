from __future__ import annotations

import hashlib
import json
import random
import uuid
from dataclasses import dataclass
from datetime import timedelta
from typing import Any, Iterable

from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from .models import GapoRelayEvent


@dataclass(frozen=True)
class NackResult:
    event: GapoRelayEvent | None
    retry_after_seconds: float | None


def canonical_payload_bytes(payload: dict[str, Any]) -> bytes:
    """Serialize exactly like Project Ops does when it has to derive an ID."""
    return json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")


def make_event_id(payload: dict[str, Any]) -> str:
    supplied = payload.get("id") or payload.get("event_id")
    if supplied:
        return str(supplied)
    digest = hashlib.sha256(canonical_payload_bytes(payload)).hexdigest()
    return f"sha256:{digest}"


def payload_metadata(payload: dict[str, Any]) -> tuple[str, str | None, str | None]:
    message = payload.get("message")
    if not isinstance(message, dict):
        message = {}
    thread = message.get("thread")
    if not isinstance(thread, dict):
        thread = {}

    # Raw payload remains complete; cap only the indexed operational metadata to
    # the model's declared width so an unexpected GAPO value cannot reject it.
    event_type = str(payload.get("event") or payload.get("type") or "unknown")[:100]
    thread_id = str(payload.get("thread_id") or thread.get("id") or "") or None
    message_id = str(message.get("id") or payload.get("message_id") or "") or None
    return event_type, thread_id, message_id


def store_event(
    payload: dict[str, Any],
    raw_body: bytes,
    *,
    received_at=None,
) -> tuple[GapoRelayEvent, bool]:
    now = received_at if received_at is not None else timezone.now()
    event_type, thread_id, message_id = payload_metadata(payload)
    defaults = {
        "event_type": event_type,
        "thread_id": thread_id,
        "message_id": message_id,
        "received_at": now,
        "raw_payload": payload,
        "payload_sha256": hashlib.sha256(raw_body).hexdigest(),
        "next_attempt_at": now,
    }
    # The outer transaction completes before the view returns 200. get_or_create
    # also handles a concurrent insert of the same primary key safely.
    with transaction.atomic():
        event, created = GapoRelayEvent.objects.get_or_create(
            event_id=make_event_id(payload),
            defaults=defaults,
        )
    return event, created


def claim_events(limit: int, lease_seconds: int) -> tuple[uuid.UUID, list[GapoRelayEvent]]:
    now = timezone.now()
    lease_token = uuid.uuid4()
    max_attempts = int(getattr(settings, "GAPO_RELAY_MAX_ATTEMPTS", 20))
    claimable_window = Q(
        delivery_status=GapoRelayEvent.Status.PENDING,
        next_attempt_at__lte=now,
    ) | Q(
        delivery_status=GapoRelayEvent.Status.LEASED,
        lease_until__lt=now,
    )
    with transaction.atomic():
        exhausted_events = list(
            GapoRelayEvent.objects.select_for_update(skip_locked=True)
            .filter(claimable_window, attempt_count__gte=max_attempts)
            .order_by("received_at", "event_id")[:limit]
        )
        for event in exhausted_events:
            event.delivery_status = GapoRelayEvent.Status.DEAD_LETTER
            event.lease_token = None
            event.lease_until = None
            event.next_attempt_at = now
            event.last_error = "Maximum delivery attempts reached after lease expiry."
            event.updated_at = now
        if exhausted_events:
            GapoRelayEvent.objects.bulk_update(
                exhausted_events,
                [
                    "delivery_status",
                    "lease_token",
                    "lease_until",
                    "next_attempt_at",
                    "last_error",
                    "updated_at",
                ],
            )

        events = list(
            GapoRelayEvent.objects.select_for_update(skip_locked=True)
            .filter(claimable_window, attempt_count__lt=max_attempts)
            .order_by("received_at", "event_id")[:limit]
        )
        lease_until = now + timedelta(seconds=lease_seconds)
        for event in events:
            event.delivery_status = GapoRelayEvent.Status.LEASED
            event.lease_token = lease_token
            event.lease_until = lease_until
            event.attempt_count += 1
            event.updated_at = now
        if events:
            GapoRelayEvent.objects.bulk_update(
                events,
                [
                    "delivery_status",
                    "lease_token",
                    "lease_until",
                    "attempt_count",
                    "updated_at",
                ],
            )
    return lease_token, events


def acknowledge_events(lease_token: uuid.UUID, event_ids: Iterable[str]) -> int:
    now = timezone.now()
    return GapoRelayEvent.objects.filter(
        event_id__in=list(event_ids),
        lease_token=lease_token,
        delivery_status=GapoRelayEvent.Status.LEASED,
    ).update(
        delivery_status=GapoRelayEvent.Status.DELIVERED,
        delivered_at=now,
        lease_token=None,
        lease_until=None,
        last_http_status=200,
        last_error="",
        updated_at=now,
    )


def retry_delay_seconds(attempt_count: int) -> float:
    max_backoff = int(getattr(settings, "GAPO_RELAY_MAX_BACKOFF_SECONDS", 900))
    exponent = min(max(attempt_count, 0), 30)
    base = min(5 * (2**exponent), max_backoff)
    jitter_ceiling = min(base * 0.2, 30.0)
    return base + random.uniform(0, jitter_ceiling)


def reject_event(
    lease_token: uuid.UUID,
    event_id: str,
    error: str,
    http_status: int | None = None,
) -> NackResult:
    now = timezone.now()
    max_attempts = int(getattr(settings, "GAPO_RELAY_MAX_ATTEMPTS", 20))
    with transaction.atomic():
        event = (
            GapoRelayEvent.objects.select_for_update()
            .filter(
                event_id=event_id,
                lease_token=lease_token,
                delivery_status=GapoRelayEvent.Status.LEASED,
            )
            .first()
        )
        if event is None:
            return NackResult(event=None, retry_after_seconds=None)

        is_dead_letter = event.attempt_count >= max_attempts
        retry_after = None if is_dead_letter else retry_delay_seconds(event.attempt_count)
        event.delivery_status = (
            GapoRelayEvent.Status.DEAD_LETTER
            if is_dead_letter
            else GapoRelayEvent.Status.PENDING
        )
        event.next_attempt_at = (
            now if retry_after is None else now + timedelta(seconds=retry_after)
        )
        event.lease_token = None
        event.lease_until = None
        event.last_http_status = http_status
        event.last_error = error
        event.save(
            update_fields=[
                "delivery_status",
                "next_attempt_at",
                "lease_token",
                "lease_until",
                "last_http_status",
                "last_error",
                "updated_at",
            ]
        )
    return NackResult(event=event, retry_after_seconds=retry_after)
