import json
from typing import List

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseBadRequest, HttpResponseForbidden, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from .forms import NotificationSubscriptionForm
from .models import (
    NotificationChannel,
    NotificationReport,
    NotificationSchedule,
    NotificationSubscription,
)
from .tasks import send_notification_schedule


@login_required
def notification_dashboard(request):
    profile = getattr(request.user, "profile", None)
    default_target = getattr(profile, "gapo_user_id", "") if profile else ""

    if request.method == "POST":
        form = NotificationSubscriptionForm(request.POST, user=request.user)
        if form.is_valid():
            cleaned = form.cleaned_data
            subscription, created = NotificationSubscription.objects.update_or_create(
                user=request.user,
                report=cleaned["report"],
                channel=cleaned["channel"],
                target=cleaned["target"],
                defaults={"is_active": cleaned["is_active"]},
            )
            msg = "Đã đăng ký nhận thông báo" if created else "Đã cập nhật đăng ký nhận thông báo"
            messages.success(request, f"{msg} cho {subscription.report.name}")
            return redirect("app_notification:notification_dashboard")
        else:
            messages.error(request, "Thông tin đăng ký chưa hợp lệ, vui lòng kiểm tra lại.")
    else:
        form = NotificationSubscriptionForm(
            user=request.user,
            initial={"target": default_target, "channel": NotificationChannel.GAPO},
        )

    reports = NotificationReport.objects.filter(is_active=True).order_by("name")
    subscriptions = (
        NotificationSubscription.objects.filter(user=request.user)
        .select_related("report")
        .order_by("-updated_at")
    )
    recent_schedules = (
        NotificationSchedule.objects.filter(subscription__user=request.user)
        .select_related("report")
        .order_by("-created_at")[:10]
    )

    context = {
        "reports": reports,
        "subscriptions": subscriptions,
        "form": form,
        "recent_schedules": recent_schedules,
    }
    return render(request, "app_notification/dashboard.html", context)


@login_required
def subscription_toggle(request, pk: int):
    subscription = get_object_or_404(NotificationSubscription, pk=pk, user=request.user)
    subscription.is_active = not subscription.is_active
    subscription.save(update_fields=["is_active", "updated_at"])
    state = "bật" if subscription.is_active else "tắt"
    messages.info(request, f"Đã {state} đăng ký nhận báo cáo {subscription.report.name}")
    return redirect("app_notification:notification_dashboard")


@csrf_exempt
@require_POST
def notification_trigger(request):
    secret = getattr(settings, "NOTIFICATION_WEBHOOK_SECRET", None)
    if secret:
        token = request.headers.get("X-Notification-Token") or request.headers.get("Authorization")
        if token and token.startswith("Bearer "):
            token = token.replace("Bearer ", "", 1)
        if token != secret:
            return HttpResponseForbidden("Invalid token")

    try:
        payload = json.loads(request.body.decode("utf-8") or "{}")
    except json.JSONDecodeError:
        return HttpResponseBadRequest("Invalid JSON payload")

    report_code = payload.get("report_code") or payload.get("report")
    message_text = payload.get("message") or payload.get("text")
    schedule_at_raw = payload.get("schedule_at")
    receivers: List[dict] = payload.get("receivers") or []

    if not message_text:
        return JsonResponse({"error": "message is required"}, status=400)

    report = None
    if report_code:
        report = NotificationReport.objects.filter(code=report_code, is_active=True).first()
        if not report:
            return JsonResponse({"error": f"Report {report_code} not found or inactive"}, status=404)

    if not receivers and report:
        subscribers = NotificationSubscription.objects.filter(
            report=report, is_active=True
        ).select_related("report")
        receivers = [
            {"channel": sub.channel, "target": sub.target, "subscription_id": sub.id}
            for sub in subscribers
        ]

    if not receivers:
        return JsonResponse({"error": "No receivers provided or active subscriptions found"}, status=400)

    schedule_at = timezone.now()
    if schedule_at_raw:
        parsed_dt = parse_datetime(schedule_at_raw)
        if not parsed_dt:
            return JsonResponse({"error": "schedule_at must be ISO datetime"}, status=400)
        if timezone.is_naive(parsed_dt):
            parsed_dt = timezone.make_aware(parsed_dt, timezone.get_current_timezone())
        schedule_at = parsed_dt

    valid_channels = {choice.value for choice in NotificationChannel}
    scheduled_ids = []
    for receiver in receivers:
        channel = (receiver.get("channel") or (report.default_channel if report else NotificationChannel.GAPO)).lower()
        if channel not in valid_channels:
            return JsonResponse({"error": f"Unsupported channel {channel}"}, status=400)

        target = receiver.get("target")
        if not target:
            return JsonResponse({"error": "receiver target is required"}, status=400)

        subscription = None
        subscription_id = receiver.get("subscription_id")
        if subscription_id:
            subscription = NotificationSubscription.objects.filter(id=subscription_id).first()

        schedule = NotificationSchedule.objects.create(
            report=report,
            subscription=subscription,
            channel=channel,
            target=target,
            message=message_text,
            schedule_at=schedule_at,
            status=NotificationSchedule.Status.PENDING,
            metadata={"trigger_payload": payload},
        )
        eta = schedule_at if schedule_at > timezone.now() else None
        if eta:
            send_notification_schedule.apply_async(args=[schedule.id], eta=eta)
        else:
            send_notification_schedule.apply_async(args=[schedule.id])
        scheduled_ids.append(schedule.id)

    return JsonResponse({"scheduled": scheduled_ids, "count": len(scheduled_ids)})
