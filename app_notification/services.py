from typing import Any, Dict

from app_documents.gapo import (
    GapoMessageError,
    build_gapo_body,
    build_gapo_payload,
    post_gapo_message,
)
from .models import NotificationChannel


class NotificationSendError(Exception):
    pass


def send_via_gapo(
    target: str,
    message: str,
    *,
    body_type: str = "text",
    body_metadata: Dict[str, Any] | None = None,
    target_type: str = "receiver",
) -> Dict[str, Any]:
    try:
        body = build_gapo_body(
            body_type=body_type,
            text=message,
            metadata=body_metadata,
        )
        target_kwargs = {
            "receiver_id": target if target_type == "receiver" else None,
            "thread_id": target if target_type == "thread" else None,
            "collab_id": target if target_type == "collab" else None,
        }
        payload = build_gapo_payload(body=body, **target_kwargs)
        return post_gapo_message(payload)
    except GapoMessageError as exc:
        raise NotificationSendError(str(exc)) from exc


def send_message(channel: str, target: str, message: str) -> Dict[str, Any]:
    if channel == NotificationChannel.GAPO:
        return send_via_gapo(target, message)
    raise NotificationSendError(f"Channel {channel} is not supported yet")
