from datetime import date, timedelta

from django.db.models import Count, Q
from django.db.models.functions import TruncDate
from django.utils import dateparse, timezone

from .models import CollateralRegistration, CollateralRegistrationStatus


POSTMINI_DONE_STATUSES = ["Đã cập nhật", "Đã cập nhật 1 dòng"]


def _today():
    now = timezone.now()
    if timezone.is_aware(now):
        now = timezone.localtime(now)
    return now.date()


def resolve_dashboard_period(params):
    today = _today()
    period = (params.get("period") or "month").strip()
    if period == "today":
        return period, today, today
    if period == "range":
        date_from = dateparse.parse_date(params.get("date_from") or "")
        date_to = dateparse.parse_date(params.get("date_to") or "")
        if not date_from or not date_to:
            raise ValueError("Vui lòng chọn đủ ngày bắt đầu và ngày kết thúc.")
        if date_from > date_to:
            raise ValueError("Ngày bắt đầu không được sau ngày kết thúc.")
        if (date_to - date_from).days > 366:
            raise ValueError("Dashboard chỉ hỗ trợ tối đa 366 ngày mỗi lần.")
        return period, date_from, date_to

    month_value = (params.get("month") or today.strftime("%Y-%m")).strip()
    month_start = dateparse.parse_date(f"{month_value}-01")
    if not month_start:
        raise ValueError("Tháng thống kê không hợp lệ.")
    if month_start.month == 12:
        next_month = date(month_start.year + 1, 1, 1)
    else:
        next_month = date(month_start.year, month_start.month + 1, 1)
    return "month", month_start, next_month - timedelta(days=1)


def _source_breakdown(queryset):
    f88 = queryset.filter(
        Q(disbursement_source__iexact="F88")
        | Q(disbursement_source__iexact="F88 Fund")
    ).count()
    cimb = queryset.filter(
        Q(disbursement_source__iexact="CIMB")
        | Q(disbursement_source__iexact="CIMB Fund")
    ).count()
    mb = queryset.filter(
        Q(disbursement_source__isnull=True)
        | Q(disbursement_source="")
        | Q(disbursement_source__iexact="MB")
        | Q(disbursement_source__iexact="MB Fund")
    ).count()
    total = queryset.count()
    return [
        {"label": "F88", "value": f88},
        {"label": "CIMB", "value": cimb},
        {"label": "MB", "value": mb},
        {"label": "Khác", "value": max(0, total - f88 - cimb - mb)},
    ]


def _asset_breakdown(queryset):
    rows = list(
        queryset.values("asset_type")
        .annotate(value=Count("registration_id"))
        .order_by("-value", "asset_type")
    )
    result = []
    for row in rows:
        label = (row["asset_type"] or "").strip() or "Chưa xác định"
        result.append({"label": label, "value": row["value"]})
    return result or [{"label": "Chưa xác định", "value": 0}]


def build_gddb_dashboard_data(params):
    period, date_from, date_to = resolve_dashboard_period(params)
    today = _today()
    month_start = today.replace(day=1)
    now = timezone.now()

    all_cases = CollateralRegistration.objects.filter(is_duplicate=False)
    selected = all_cases.filter(
        created_at__date__gte=date_from,
        created_at__date__lte=date_to,
    )

    selected_total = selected.count()
    pending_selected = selected.filter(
        gddb_status=CollateralRegistrationStatus.PENDING
    ).count()
    waiting_posmini_selected = selected.filter(
        gddb_status=CollateralRegistrationStatus.REGISTERED,
        archived_at__isnull=True,
    ).exclude(postmini_updated__in=POSTMINI_DONE_STATUSES).count()
    not_registered_selected = selected.filter(
        gddb_status=CollateralRegistrationStatus.NOT_REGISTERED
    ).count()
    completed_registered_selected = selected.filter(
        gddb_status=CollateralRegistrationStatus.REGISTERED,
        archived_at__isnull=False,
        postmini_updated__in=POSTMINI_DONE_STATUSES,
    ).count()

    daily_rows = list(
        selected.annotate(day=TruncDate("created_at"))
        .values("day")
        .annotate(value=Count("registration_id"))
        .order_by("day")
    )
    daily_map = {row["day"]: row["value"] for row in daily_rows}
    daily = []
    cursor = date_from
    while cursor <= date_to:
        daily.append({"label": cursor.isoformat(), "value": daily_map.get(cursor, 0)})
        cursor += timedelta(days=1)

    checker_rows = list(
        all_cases.filter(
            gddb_status=CollateralRegistrationStatus.REGISTERED,
            registered_at__date__gte=date_from,
            registered_at__date__lte=date_to,
        )
        .values("registered_by__username")
        .annotate(value=Count("registration_id"))
        .order_by("-value", "registered_by__username")
    )
    checker = [
        {
            "label": row["registered_by__username"] or "Chưa xác định",
            "value": row["value"],
        }
        for row in checker_rows
    ]

    active_queue = all_cases.filter(archived_at__isnull=True)
    realtime_pending = active_queue.filter(
        gddb_status=CollateralRegistrationStatus.PENDING
    )
    realtime_waiting_posmini = active_queue.filter(
        gddb_status=CollateralRegistrationStatus.REGISTERED
    ).exclude(postmini_updated__in=POSTMINI_DONE_STATUSES)

    return {
        "generated_at": now.isoformat(),
        "period": {
            "type": period,
            "date_from": date_from.isoformat(),
            "date_to": date_to.isoformat(),
        },
        "cards": {
            "selected_total": selected_total,
            "today_total": all_cases.filter(created_at__date=today).count(),
            "month_total": all_cases.filter(created_at__date__gte=month_start).count(),
            "pending": realtime_pending.count(),
            "held": realtime_pending.filter(
                processing_by__isnull=False,
                processing_expires_at__gt=now,
            ).count(),
            "unassigned": realtime_pending.filter(
                Q(processing_by__isnull=True)
                | Q(processing_expires_at__isnull=True)
                | Q(processing_expires_at__lte=now)
            ).count(),
            "waiting_posmini": realtime_waiting_posmini.count(),
            "completed_today": all_cases.filter(
                archived_at__date=today,
            ).count(),
        },
        "daily": daily,
        "status": [
            {"label": "Chưa đăng ký", "value": pending_selected},
            {"label": "Chờ PosMini", "value": waiting_posmini_selected},
            {"label": "Không đăng ký", "value": not_registered_selected},
            {"label": "Hoàn tất đăng ký", "value": completed_registered_selected},
        ],
        "source": _source_breakdown(selected),
        "asset": _asset_breakdown(selected),
        "checker": checker,
    }
