from django.contrib.auth import get_user_model
from django.db import models
from django.utils import timezone

User = get_user_model()


class NotificationChannel(models.TextChoices):
    GAPO = "gapo", "Gapo Chat"
    EMAIL = "email", "Email"
    TEAMS = "teams", "Microsoft Teams"


class NotificationReport(models.Model):
    code = models.CharField(max_length=100, unique=True)
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    default_channel = models.CharField(
        max_length=20, choices=NotificationChannel.choices, default=NotificationChannel.GAPO
    )
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name="notification_reports"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "f_notification_report"
        ordering = ["name"]

    def __str__(self) -> str:
        return f"{self.name} ({self.code})"


class NotificationSubscription(models.Model):
    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="notification_subscriptions"
    )
    report = models.ForeignKey(
        NotificationReport, on_delete=models.CASCADE, related_name="subscriptions"
    )
    channel = models.CharField(
        max_length=20, choices=NotificationChannel.choices, default=NotificationChannel.GAPO
    )
    target = models.CharField(
        max_length=255,
        help_text="Địa chỉ nhận: Gapo user id, email hoặc webhook",
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "f_notification_subscription"
        unique_together = ("user", "report", "channel", "target")
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.user} - {self.report} [{self.channel}]"


class NotificationSchedule(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        SENT = "sent", "Sent"
        FAILED = "failed", "Failed"
        CANCELLED = "cancelled", "Cancelled"

    report = models.ForeignKey(
        NotificationReport, on_delete=models.SET_NULL, null=True, blank=True, related_name="schedules"
    )
    subscription = models.ForeignKey(
        NotificationSubscription, on_delete=models.SET_NULL, null=True, blank=True, related_name="schedules"
    )
    channel = models.CharField(max_length=20, choices=NotificationChannel.choices)
    target = models.CharField(max_length=255)
    message = models.TextField()
    schedule_at = models.DateTimeField(default=timezone.now)
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.PENDING
    )
    sent_at = models.DateTimeField(null=True, blank=True)
    last_error = models.TextField(null=True, blank=True)
    metadata = models.JSONField(null=True, blank=True)
    created_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name="created_notifications"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "f_notification_schedule"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status", "schedule_at"]),
        ]

    def __str__(self) -> str:
        target_display = self.target if len(self.target) <= 30 else f"{self.target[:27]}..."
        return f"{self.report or 'Ad-hoc'} -> {target_display}"
