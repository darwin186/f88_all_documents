from __future__ import annotations

from typing import Any

import requests
from django.conf import settings


class GapoMessageError(Exception):
    pass


def _gapo_config() -> tuple[str, str, str]:
    gapo_url = getattr(settings, "GAPO_API_URL", "")
    api_key = getattr(settings, "GAPO_BOT_API_KEY", "")
    bot_id = getattr(settings, "GAPO_BOT_ID", "")
    if not (gapo_url and api_key and bot_id):
        raise GapoMessageError("Missing GAPO config")
    return gapo_url, api_key, str(bot_id)


def build_gapo_body(
    *,
    body_type: str = "text",
    text: str = "",
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    body = {"type": body_type}
    if text:
        body["text"] = text
    if body_type == "text" and "is_markdown_text" not in (metadata or {}):
        body["is_markdown_text"] = True
    if metadata:
        body.update(metadata)
    return body


def build_gapo_payload(
    *,
    receiver_id: str | int | None = None,
    thread_id: str | int | None = None,
    collab_id: str | None = None,
    body: dict[str, Any],
    bot_id: str | int | None = None,
) -> dict[str, Any]:
    _, _, config_bot_id = _gapo_config()
    resolved_bot_id = bot_id or config_bot_id
    payload = {
        "bot_id": int(resolved_bot_id) if str(resolved_bot_id).isdigit() else resolved_bot_id,
        "body": body,
    }
    targets = [
        ("receiver_id", receiver_id),
        ("thread_id", thread_id),
        ("collab_id", collab_id),
    ]
    chosen = [(key, value) for key, value in targets if value not in (None, "")]
    if len(chosen) != 1:
        raise GapoMessageError("Exactly one GAPO target is required: receiver_id, thread_id or collab_id.")
    key, value = chosen[0]
    payload[key] = int(value) if key != "collab_id" and str(value).isdigit() else value
    return payload


def post_gapo_message(payload: dict[str, Any]) -> dict[str, Any]:
    gapo_url, api_key, _ = _gapo_config()
    headers = {
        "x-gapo-api-key": api_key,
        "Content-Type": "application/json",
    }
    response = requests.post(gapo_url, json=payload, headers=headers, timeout=10)
    if response.status_code >= 400:
        raise GapoMessageError(f"Gapo error {response.status_code}: {response.text}")
    try:
        return response.json()
    except Exception:
        return {"status": "ok", "raw": response.text}
