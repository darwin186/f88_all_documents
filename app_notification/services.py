import json
from typing import Any, Dict

import requests
from django.conf import settings

from .models import NotificationChannel


class NotificationSendError(Exception):
    pass


def send_via_gapo(target: str, message: str) -> Dict[str, Any]:
    gapo_url = getattr(settings, "GAPO_API_URL", "")
    api_key = getattr(settings, "GAPO_BOT_API_KEY", "")
    bot_id = getattr(settings, "GAPO_BOT_ID", "")
    if not (gapo_url and api_key and bot_id):
        raise NotificationSendError("Missing GAPO config")

    payload = {
        "bot_id": bot_id,
        "receiver_id": int(target) if str(target).isdigit() else target,
        "body": {
            "type": "text",
            "text": message,
            "is_markdown_text": True,
        },
    }
    headers = {"x-gapo-api-key": api_key, "Content-Type": "application/json"}
    response = requests.post(gapo_url, json=payload, headers=headers, timeout=10)
    if response.status_code >= 400:
        raise NotificationSendError(f"Gapo error {response.status_code}: {response.text}")
    try:
        return response.json()
    except Exception:
        return {"status": "ok", "raw": response.text}


def send_message(channel: str, target: str, message: str) -> Dict[str, Any]:
    if channel == NotificationChannel.GAPO:
        return send_via_gapo(target, message)
    raise NotificationSendError(f"Channel {channel} is not supported yet")
