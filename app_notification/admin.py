from django.contrib import admin

from .models import NotificationReport, NotificationSchedule, NotificationSubscription


@admin.register(NotificationReport)
class NotificationReportAdmin(admin.ModelAdmin):
    list_display = ("name", "code", "default_channel", "is_active", "updated_at")
    search_fields = ("name", "code")
    list_filter = ("default_channel", "is_active")
    ordering = ("name",)


@admin.register(NotificationSubscription)
class NotificationSubscriptionAdmin(admin.ModelAdmin):
    list_display = ("user", "report", "channel", "target", "is_active", "updated_at")
    search_fields = ("user__username", "user__email", "report__name", "target")
    list_filter = ("channel", "is_active")
    raw_id_fields = ("user",)


@admin.register(NotificationSchedule)
class NotificationScheduleAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "report",
        "channel",
        "target",
        "status",
        "schedule_at",
        "sent_at",
    )
    search_fields = ("target", "message", "report__name", "report__code")
    list_filter = ("status", "channel")
    raw_id_fields = ("subscription", "report", "created_by")
    readonly_fields = ("created_at", "updated_at", "sent_at")
