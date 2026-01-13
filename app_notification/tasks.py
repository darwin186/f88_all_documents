from celery import shared_task
from django.utils import timezone

from .models import NotificationChannel, NotificationSchedule
from .services import NotificationSendError, send_message


@shared_task
def ping_notification():
    return f"notification ping at {timezone.now()}"


@shared_task(bind=True, max_retries=3, default_retry_delay=180)
def send_notification_schedule(self, schedule_id: int):
    try:
        schedule = NotificationSchedule.objects.select_related("subscription", "report").get(pk=schedule_id)
    except NotificationSchedule.DoesNotExist:
        return "Schedule not found"

    if schedule.status != NotificationSchedule.Status.PENDING:
        return f"Skip schedule {schedule_id} with status {schedule.status}"

    if schedule.schedule_at and schedule.schedule_at > timezone.now():
        eta = schedule.schedule_at
        self.apply_async(args=[schedule_id], eta=eta)
        return f"Rescheduled {schedule_id} to {eta}"

    try:
        send_result = send_message(schedule.channel, schedule.target, schedule.message)
    except NotificationSendError as exc:
        schedule.status = NotificationSchedule.Status.FAILED
        schedule.last_error = str(exc)
        schedule.updated_at = timezone.now()
        schedule.save(update_fields=["status", "last_error", "updated_at"])
        raise self.retry(exc=exc)
    except Exception as exc:
        schedule.status = NotificationSchedule.Status.FAILED
        schedule.last_error = str(exc)
        schedule.updated_at = timezone.now()
        schedule.save(update_fields=["status", "last_error", "updated_at"])
        raise self.retry(exc=exc)
    else:
        now = timezone.now()
        schedule.status = NotificationSchedule.Status.SENT
        schedule.sent_at = now
        schedule.last_error = ""
        schedule.updated_at = now
        schedule.metadata = (schedule.metadata or {}) | {"send_result": send_result}
        schedule.save(update_fields=["status", "sent_at", "last_error", "metadata", "updated_at"])
        return f"Sent schedule {schedule_id} to {schedule.target} via {schedule.channel} at {now}"
