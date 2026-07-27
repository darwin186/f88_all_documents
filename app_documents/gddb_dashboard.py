from collections import Counter, defaultdict
from datetime import date, datetime, time, timedelta

from django.conf import settings
from django.db.models import Count, Q
from django.db.models.functions import TruncDate
from django.utils import dateparse, timezone

from .models import (
    CollateralRegistration,
    CollateralRegistrationHoliday,
    CollateralRegistrationLog,
    CollateralRegistrationStatus,
)


POSTMINI_DONE_STATUSES = ["Đã cập nhật", "Đã cập nhật 1 dòng"]
SLA_CALENDAR_DAYS = 3
SLA_NEAR_SECONDS = 24 * 60 * 60
BATCH_SLOT_HOURS = {1: 9, 2: 13, 3: 16, 4: 19}


def _today():
    now = timezone.now()
    if timezone.is_aware(now):
        now = timezone.localtime(now)
    return now.date()


def _local_datetime(value):
    if value and timezone.is_aware(value):
        return timezone.localtime(value)
    return value


def _local_date(value):
    if not value:
        return None
    if hasattr(value, "hour") and timezone.is_aware(value):
        value = timezone.localtime(value)
    return value.date() if hasattr(value, "date") else value


def _datetime_boundary(value):
    boundary = datetime.combine(value, time.min)
    if settings.USE_TZ:
        boundary = timezone.make_aware(boundary, timezone.get_current_timezone())
    return boundary


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


def _is_business_day(value, holidays):
    return value.weekday() < 5 and value not in holidays


def calculate_sla_due_at(effective_at, holidays):
    """Add three calendar days, then roll a non-working deadline forward."""
    due_at = effective_at + timedelta(days=SLA_CALENDAR_DAYS)
    while not _is_business_day(due_at.date(), holidays):
        due_at += timedelta(days=1)
    return due_at


def business_days_between(start_date, end_date, holidays):
    """Count working days after start_date through end_date."""
    if not start_date or not end_date or end_date <= start_date:
        return 0
    count = 0
    cursor = start_date + timedelta(days=1)
    while cursor <= end_date:
        if _is_business_day(cursor, holidays):
            count += 1
        cursor += timedelta(days=1)
    return count


def _case_effective_at(case):
    if not case.disbursement_date:
        return None
    batch = case.import_batch if case.import_batch_id else None
    batch_datetime = _local_datetime(
        batch.created_at if batch else case.created_at
    )
    slot_hour = BATCH_SLOT_HOURS.get(batch.slot_number) if batch else None
    effective_time = (
        time(hour=slot_hour)
        if slot_hour is not None
        else (
            batch_datetime.time().replace(second=0, microsecond=0)
            if batch_datetime
            else time.min
        )
    )
    effective_at = datetime.combine(case.disbursement_date, effective_time)
    if settings.USE_TZ:
        effective_at = timezone.make_aware(
            effective_at,
            timezone.get_current_timezone(),
        )
    return effective_at


def _duration_label(total_seconds):
    seconds = max(0, int(total_seconds))
    days, remainder = divmod(seconds, 24 * 60 * 60)
    hours, remainder = divmod(remainder, 60 * 60)
    minutes = remainder // 60
    parts = []
    if days:
        parts.append(f"{days} ngày")
    if hours:
        parts.append(f"{hours} giờ")
    if not days and minutes:
        parts.append(f"{minutes} phút")
    return " ".join(parts) or "0 phút"


def _sla_result(case, now, holidays):
    effective_at = _case_effective_at(case)
    if not effective_at:
        return {
            "measurable": False,
            "effective_at": None,
            "due_at": None,
            "completed_at": _local_datetime(case.archived_at),
            "completed": bool(case.archived_at),
            "achieved": False,
            "overdue": False,
            "remaining_business_days": None,
            "elapsed_business_days": None,
            "remaining_seconds": None,
            "elapsed_seconds": None,
            "age_label": "Thiếu ngày giải ngân",
            "countdown_label": "Thiếu ngày giải ngân",
        }

    due_at = calculate_sla_due_at(effective_at, holidays)
    completed_at = _local_datetime(case.archived_at)
    reference_at = completed_at or now
    completed = bool(completed_at)
    overdue = reference_at > due_at
    achieved = completed and completed_at <= due_at
    remaining_seconds = int((due_at - now).total_seconds())
    elapsed_seconds = int(max(0, (reference_at - effective_at).total_seconds()))
    if completed:
        countdown_label = "Đạt SLA" if achieved else f"Quá {_duration_label((completed_at - due_at).total_seconds())}"
    elif remaining_seconds < 0:
        countdown_label = f"Quá {_duration_label(-remaining_seconds)}"
    elif remaining_seconds == 0:
        countdown_label = "Đến hạn"
    else:
        countdown_label = f"Còn {_duration_label(remaining_seconds)}"
    return {
        "measurable": True,
        "effective_at": effective_at,
        "due_at": due_at,
        "completed_at": completed_at,
        "completed": completed,
        "achieved": achieved,
        "overdue": overdue,
        "remaining_business_days": (
            business_days_between(now.date(), due_at.date(), holidays)
            if remaining_seconds >= 0
            else -business_days_between(due_at.date(), now.date(), holidays)
        ),
        "elapsed_business_days": business_days_between(
            effective_at.date(), reference_at.date(), holidays
        ),
        "remaining_seconds": remaining_seconds,
        "elapsed_seconds": elapsed_seconds,
        "age_label": _duration_label(elapsed_seconds),
        "countdown_label": countdown_label,
    }


def calculate_case_sla(case, *, now=None, holidays=None):
    """Shared SLA calculation for dashboard and reconciliation exports."""
    calculation_time = _local_datetime(now or timezone.now())
    if holidays is None:
        holidays = set(
            CollateralRegistrationHoliday.objects.filter(
                is_active=True,
            ).values_list("holiday_date", flat=True)
        )
    return _sla_result(case, calculation_time, holidays)


def _source_group(value):
    normalized = (value or "").strip().casefold()
    if normalized in {"f88", "f88 fund"}:
        return "F88"
    if normalized in {"cimb", "cimb fund"}:
        return "CIMB"
    if not normalized or normalized in {"mb", "mb fund"}:
        return "MB"
    return "Khác"


def _asset_group(value):
    return (value or "").strip() or "Chưa xác định"


def _source_breakdown(queryset):
    rows = Counter(
        _source_group(value)
        for value in queryset.values_list("disbursement_source", flat=True)
    )
    return [
        {"label": label, "value": rows[label]}
        for label in ["F88", "CIMB", "MB", "Khác"]
    ]


def _asset_breakdown(queryset):
    rows = list(
        queryset.values("asset_type")
        .annotate(value=Count("registration_id"))
        .order_by("-value", "asset_type")
    )
    result = [
        {
            "label": (row["asset_type"] or "").strip() or "Chưa xác định",
            "value": row["value"],
        }
        for row in rows
    ]
    return result or [{"label": "Chưa xác định", "value": 0}]


def _trend_bucket(value, mode):
    value = _local_date(value)
    if mode == "month":
        return value.replace(day=1)
    return value - timedelta(days=value.weekday())


def _trend_payload(cases, mode):
    source_counts = defaultdict(Counter)
    asset_counts = defaultdict(Counter)
    buckets = set()
    for case in cases:
        bucket = _trend_bucket(case.created_at, mode)
        buckets.add(bucket)
        source_counts[_source_group(case.disbursement_source)][bucket] += 1
        asset_counts[_asset_group(case.asset_type)][bucket] += 1
    labels = sorted(buckets)
    return {
        "labels": [value.isoformat() for value in labels],
        "source": {
            label: [source_counts[label][bucket] for bucket in labels]
            for label in sorted(source_counts)
        },
        "asset": {
            label: [asset_counts[label][bucket] for bucket in labels]
            for label in sorted(asset_counts)
        },
    }


def _case_owner(case):
    return case.processing_by or case.registered_by


def _case_summary(case, sla):
    owner = _case_owner(case)
    return {
        "registration_id": case.registration_id,
        "contract_code": case.contract_code,
        "shop_name": case.shop_name or "",
        "source": _source_group(case.disbursement_source),
        "asset_type": _asset_group(case.asset_type),
        "status": case.gddb_status,
        "status_label": case.get_gddb_status_display(),
        "postmini_updated": case.postmini_updated or "Chưa cập nhật",
        "owner": owner.username if owner else "",
        "disbursement_date": (
            case.disbursement_date.isoformat() if case.disbursement_date else None
        ),
        "effective_at": (
            sla["effective_at"].isoformat() if sla["effective_at"] else None
        ),
        "due_at": sla["due_at"].isoformat() if sla["due_at"] else None,
        "due_date": sla["due_at"].date().isoformat() if sla["due_at"] else None,
        "elapsed_business_days": sla["elapsed_business_days"],
        "remaining_business_days": sla["remaining_business_days"],
        "remaining_seconds": sla["remaining_seconds"],
        "age_label": sla["age_label"],
        "countdown_label": sla["countdown_label"],
        "overdue": sla["overdue"],
    }


def _workload_payload(active_cases, now, holidays):
    rows = defaultdict(
        lambda: {
            "assigned": 0,
            "pending": 0,
            "waiting_posmini": 0,
            "overdue": 0,
        }
    )
    for case in active_cases:
        owner = _case_owner(case)
        label = owner.username if owner else "Chưa phân công"
        rows[label]["assigned"] += 1
        if case.gddb_status == CollateralRegistrationStatus.PENDING:
            rows[label]["pending"] += 1
        elif case.gddb_status == CollateralRegistrationStatus.REGISTERED:
            rows[label]["waiting_posmini"] += 1
        if _sla_result(case, now, holidays)["overdue"]:
            rows[label]["overdue"] += 1
    return [
        {"checker": checker, **values}
        for checker, values in sorted(
            rows.items(),
            key=lambda item: (-item[1]["assigned"], item[0]),
        )
    ]


def _action_label(log):
    return {
        "case_claim": "Nhận case",
        "case_release": "Trả case",
        "case_expire": "Hết hạn giữ case",
        "status_update": "Cập nhật trạng thái",
        "postmini_update": "Cập nhật PosMini",
        "note_update": "Cập nhật ghi chú",
    }.get(log.action, log.action)


def _personal_payload(user, all_cases, now, today, month_start, holidays):
    today_start = _datetime_boundary(today)
    tomorrow_start = _datetime_boundary(today + timedelta(days=1))
    month_start_at = _datetime_boundary(month_start)
    assigned_q = Q(processing_by=user) | Q(
        processing_by__isnull=True,
        registered_by=user,
    )
    assigned_cases = list(
        all_cases.filter(archived_at__isnull=True)
        .filter(assigned_q)
        .select_related("processing_by", "registered_by", "import_batch")
        .order_by("disbursement_date", "created_at")[:100]
    )
    assigned_rows = []
    for case in assigned_cases:
        sla = _sla_result(case, now, holidays)
        assigned_rows.append(_case_summary(case, sla))
    assigned_rows.sort(
        key=lambda row: (
            not row["overdue"],
            row["due_at"] or "9999-12-31T23:59:59",
            row["contract_code"],
        )
    )

    completed_owned = all_cases.filter(archived_at__isnull=False).filter(
        Q(processing_by=user) | Q(registered_by=user)
    )
    today_completed = completed_owned.filter(
        archived_at__gte=today_start,
        archived_at__lt=tomorrow_start,
    ).count()
    month_completed_cases = list(
        completed_owned.filter(archived_at__gte=month_start_at)
        .select_related("processing_by", "registered_by", "import_batch")
    )
    month_sla = [
        _sla_result(case, now, holidays)
        for case in month_completed_cases
        if case.disbursement_date
    ]
    month_sla_rate = (
        round(
            sum(1 for item in month_sla if item["achieved"])
            * 100
            / len(month_sla),
            1,
        )
        if month_sla
        else None
    )
    history = list(
        CollateralRegistrationLog.objects.filter(created_by=user)
        .select_related("registration")
        .order_by("-created_at")[:30]
    )
    return {
        "cards": {
            "assigned": len(assigned_cases),
            "overdue": sum(1 for row in assigned_rows if row["overdue"]),
            "completed_today": today_completed,
            "completed_month": len(month_completed_cases),
            "sla_month_rate": month_sla_rate,
        },
        "assigned_cases": assigned_rows,
        "action_history": [
            {
                "action": log.action,
                "action_label": _action_label(log),
                "contract_code": log.registration.contract_code,
                "note": log.note or "",
                "from_status": log.from_status or "",
                "to_status": log.to_status or "",
                "created_at": log.created_at.isoformat(),
            }
            for log in history
        ],
    }


def build_gddb_dashboard_data(params, *, user=None, is_admin=True):
    period, date_from, date_to = resolve_dashboard_period(params)
    today = _today()
    month_start = today.replace(day=1)
    now = _local_datetime(timezone.now())
    today_start = _datetime_boundary(today)
    tomorrow_start = _datetime_boundary(today + timedelta(days=1))
    month_start_at = _datetime_boundary(month_start)

    all_cases = CollateralRegistration.objects.filter(is_duplicate=False)
    selected_from = _datetime_boundary(date_from)
    selected_until = _datetime_boundary(date_to + timedelta(days=1))
    selected = all_cases.filter(
        created_at__gte=selected_from,
        created_at__lt=selected_until,
    )
    active_queue = all_cases.filter(archived_at__isnull=True)
    holidays = set(
        CollateralRegistrationHoliday.objects.filter(
            is_active=True,
        ).values_list("holiday_date", flat=True)
    )

    personal = (
        _personal_payload(user, all_cases, now, today, month_start, holidays)
        if user is not None
        else None
    )
    base_result = {
        "generated_at": now.isoformat(),
        "role": "admin" if is_admin else "checker",
        "sla_policy": {
            "calendar_days": SLA_CALENDAR_DAYS,
            "time_source": "batch_slot",
            "roll_non_working_day_forward": True,
            "exclude_weekends": True,
            "holiday_count_loaded": len(holidays),
        },
        "period": {
            "type": period,
            "date_from": date_from.isoformat(),
            "date_to": date_to.isoformat(),
        },
        "personal": personal,
    }
    if not is_admin:
        return base_result

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
            registered_at__gte=selected_from,
            registered_at__lt=selected_until,
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

    realtime_pending = active_queue.filter(
        gddb_status=CollateralRegistrationStatus.PENDING
    )
    realtime_waiting_posmini = active_queue.filter(
        gddb_status=CollateralRegistrationStatus.REGISTERED
    ).exclude(postmini_updated__in=POSTMINI_DONE_STATUSES)

    selected_cases = list(
        selected.select_related(
            "processing_by",
            "registered_by",
            "import_batch",
        ).order_by(
            "disbursement_date", "created_at"
        )
    )
    sla_rows = [
        (case, _sla_result(case, now, holidays))
        for case in selected_cases
    ]
    measurable = [(case, sla) for case, sla in sla_rows if sla["measurable"]]
    assessed = [
        (case, sla)
        for case, sla in measurable
        if sla["completed"] or sla["overdue"]
    ]
    achieved_count = sum(1 for _, sla in assessed if sla["achieved"])
    overdue_count = sum(1 for _, sla in measurable if sla["overdue"])
    sla_rate = (
        round(achieved_count * 100 / len(assessed), 1) if assessed else None
    )
    overdue_rate = (
        round(overdue_count * 100 / len(measurable), 1) if measurable else None
    )
    near_sla = [
        _case_summary(case, sla)
        for case, sla in measurable
        if not sla["completed"]
        and not sla["overdue"]
        and sla["remaining_seconds"] <= SLA_NEAR_SECONDS
    ]
    near_sla.sort(
        key=lambda row: (
            row["remaining_seconds"],
            row["due_at"],
            row["contract_code"],
        )
    )

    active_cases = list(
        active_queue.select_related(
            "processing_by",
            "registered_by",
            "import_batch",
        )
    )
    base_result.update({
        "cards": {
            "selected_total": selected_total,
            "today_total": all_cases.filter(
                created_at__gte=today_start,
                created_at__lt=tomorrow_start,
            ).count(),
            "month_total": all_cases.filter(created_at__gte=month_start_at).count(),
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
                archived_at__gte=today_start,
                archived_at__lt=tomorrow_start,
            ).count(),
            "sla_rate": sla_rate,
            "sla_achieved": achieved_count,
            "sla_assessed": len(assessed),
            "sla_overdue": overdue_count,
            "sla_overdue_rate": overdue_rate,
            "sla_unmeasured": len(sla_rows) - len(measurable),
            "near_sla": len(near_sla),
        },
        "daily": daily,
        "status": [
            {"label": "Chưa đăng ký", "value": pending_selected},
            {"label": "Cập nhật PosMini", "value": waiting_posmini_selected},
            {"label": "Không đăng ký", "value": not_registered_selected},
            {"label": "Hoàn tất đăng ký", "value": completed_registered_selected},
        ],
        "source": _source_breakdown(selected),
        "asset": _asset_breakdown(selected),
        "checker": checker,
        "workload": _workload_payload(active_cases, now, holidays),
        "near_sla_cases": near_sla[:100],
        "trend": {
            "weekly": _trend_payload(selected_cases, "week"),
            "monthly": _trend_payload(selected_cases, "month"),
        },
    })
    return base_result
