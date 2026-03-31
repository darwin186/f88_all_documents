from celery import shared_task
from django.utils import timezone

from .gapo import GapoMessageError, build_gapo_body, build_gapo_payload, post_gapo_message
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

    try:
        body = build_gapo_body(
            body_type=schedule.body_type,
            text=schedule.message,
            metadata=schedule.body_metadata,
        )
        payload = build_gapo_payload(
            receiver_id=schedule.receiver_id,
            thread_id=schedule.thread_id,
            collab_id=schedule.collab_id,
            body=body,
        )
        post_gapo_message(payload)
    except Exception as exc:
        if isinstance(exc, GapoMessageError):
            error_text = str(exc)
        else:
            error_text = str(exc)
        schedule.status = GapoScheduledMessage.Status.FAILED
        schedule.last_error = error_text
        schedule.save(update_fields=["status", "last_error", "updated_at"])
        self.retry(exc=exc)
    else:
        now = timezone.now()
        schedule.status = GapoScheduledMessage.Status.SENT
        schedule.sent_at = now
        schedule.save(update_fields=["status", "sent_at", "updated_at"])
        return f"Sent to {schedule.target_value} at {now}"
