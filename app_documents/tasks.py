from celery import shared_task
from django.utils import timezone
from django.conf import settings
import requests
from .models import GapoScheduledMessage


@shared_task
def ping():
    return f"ping at {timezone.now()}"


@shared_task(bind=True, max_retries=3, default_retry_delay=300)
def send_gapo_scheduled_message(self, schedule_id):
    try:
        schedule = GapoScheduledMessage.objects.get(pk=schedule_id)
    except GapoScheduledMessage.DoesNotExist:
        return "Schedule not found"
    if schedule.status != GapoScheduledMessage.Status.PENDING:
        return f"Skip schedule {schedule_id} with status {schedule.status}"

    gapo_url = getattr(settings, "GAPO_API_URL", "")
    api_key = getattr(settings, "GAPO_BOT_API_KEY", "")
    bot_id = getattr(settings, "GAPO_BOT_ID", "")
    if not (gapo_url and api_key and bot_id):
        schedule.status = GapoScheduledMessage.Status.FAILED
        schedule.last_error = "Missing GAPO config"
        schedule.save(update_fields=["status", "last_error", "updated_at"])
        return "Missing GAPO config"

    payload = {
        "bot_id": bot_id,
        "receiver_id": int(schedule.receiver_id) if str(schedule.receiver_id).isdigit() else schedule.receiver_id,
        "body": {
            "type": "text",
            "text": schedule.message,
            "is_markdown_text": True,
        },
    }
    headers = {"x-gapo-api-key": api_key, "Content-Type": "application/json"}
    try:
        resp = requests.post(gapo_url, json=payload, headers=headers, timeout=10)
        if resp.status_code >= 400:
            raise requests.HTTPError(f"Status {resp.status_code}: {resp.text}")
    except Exception as exc:
        schedule.status = GapoScheduledMessage.Status.FAILED
        schedule.last_error = str(exc)
        schedule.save(update_fields=["status", "last_error", "updated_at"])
        self.retry(exc=exc)
    else:
        now = timezone.now()
        schedule.status = GapoScheduledMessage.Status.SENT
        schedule.sent_at = now
        schedule.save(update_fields=["status", "sent_at", "updated_at"])
        return f"Sent to {schedule.receiver_id} at {now}"
