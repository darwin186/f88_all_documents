from datetime import datetime, timedelta
from typing import Dict, Any, List
import calendar
from django.db.models import Count, Min
from django.contrib.auth.models import User
from django.utils import timezone
from .models import (
    DocumentsDetail,
    DocumentsTransactionChecking,
    CheckingTransactionStatus,
    Folder,
)


def parse_dates(start_date_str: str, end_date_str: str):
    today = timezone.now().date()
    default_start = today - timedelta(days=30)
    try:
        start_date = (
            datetime.strptime(start_date_str, "%Y-%m-%d").date()
            if start_date_str
            else default_start
        )
    except ValueError:
        start_date = default_start
    try:
        end_date = (
            datetime.strptime(end_date_str, "%Y-%m-%d").date()
            if end_date_str
            else today
        )
    except ValueError:
        end_date = today
    return start_date, end_date


def get_dashboard_metrics(start_date, end_date, checker_user_id=None, heatmap_mode="hour") -> Dict[str, Any]:
    approved_status_qs = CheckingTransactionStatus.objects.filter(
        checking_status_type__status_type_code=101
    )
    drop_checkers = User.objects.filter(groups__name="checker").order_by("username")

    filter_common = {
        "trans_created_by__groups__name": "checker",
        "documents_id__contract_id__isnull": False,
    }
    if checker_user_id:
        filter_common["trans_created_by_id"] = checker_user_id

    # Contracts approved (document_status.is_checked=True)
    approved_docs_filter = {
        "document_status_id__is_checked": True,
        "contract_id__isnull": False,
        "lastest_checked_date__date__range": (start_date, end_date),
    }
    if checker_user_id:
        approved_docs_filter["lastest_checked_by_id"] = checker_user_id
    approved_contracts = (
        DocumentsDetail.objects.filter(**approved_docs_filter)
        .values("contract_id")
        .distinct()
        .count()
    )

    # Logs in range
    base_all_qs = (
        DocumentsTransactionChecking.objects.filter(
            trans_created_date__date__range=(start_date, end_date), **filter_common
        )
        .select_related(
            "trans_created_by",
            "documents_id",
            "checking_status_id",
            "checking_status_id__checking_status_type",
            "documents_id__contract_id",
        )
        .order_by("documents_id__contract_id", "trans_created_date", "trans_id")
    )

    # First approvals (status type 101)
    first_time_contracts = 0
    if approved_status_qs.exists():
        filter_first = {**filter_common, "checking_status_id__in": approved_status_qs}
        grouped_first = (
            DocumentsTransactionChecking.objects.filter(**filter_first)
            .values("documents_id__contract_id")
            .annotate(first_date=Min("trans_created_date"))
            .filter(first_date__date__range=(start_date, end_date))
        )
        first_time_contracts = grouped_first.count()

    # Heatmap
    # Heatmap by mode
    heatmap_data: Dict[int, int] = {}
    if heatmap_mode == "hour":
        heatmap_data = {h: 0 for h in range(8, 19)}  # 8h-18h
        for log in base_all_qs:
            hr = log.trans_created_date.hour
            if 8 <= hr <= 18:
                heatmap_data[hr] = heatmap_data.get(hr, 0) + 1
    elif heatmap_mode == "week":
        heatmap_data = {k: 0 for k in range(2, 8)}  # Mon=2 .. Sat=7
        for log in base_all_qs:
            wd = log.trans_created_date.isoweekday()
            if 1 <= wd <= 6:
                key = wd + 1
                heatmap_data[key] = heatmap_data.get(key, 0) + 1
    elif heatmap_mode == "month":
        days_in_month = calendar.monthrange(start_date.year, start_date.month)[1]
        heatmap_data = {d: 0 for d in range(1, days_in_month + 1)}
        for log in base_all_qs:
            day_num = log.trans_created_date.day
            heatmap_data[day_num] = heatmap_data.get(day_num, 0) + 1
    heatmap_list = [{"hour": k, "count": v} for k, v in heatmap_data.items()]

    # Productivity per checker
    valid_type_code = 101
    reject_type_code = 102
    stats: Dict[int, Dict[str, Any]] = {}

    for log in base_all_qs:
        checker_id = log.trans_created_by_id
        fn = getattr(log.trans_created_by, "first_name", "") or ""
        ln = getattr(log.trans_created_by, "last_name", "") or ""
        checker_name = (ln + " " + fn).strip() or getattr(log.trans_created_by, "username", "")
        contract_id = getattr(
            getattr(log.documents_id, "contract_id", None), "contract_id", None
        )
        status_type_code = getattr(
            getattr(log.checking_status_id, "checking_status_type", None),
            "status_type_code",
            None,
        )
        if contract_id is None:
            continue
        stats.setdefault(
            checker_id,
            {
                "name": checker_name,
                "total_actions": 0,
                "approved_contracts_set": set(),
                "first_approvals": 0,
                "reject_actions": 0,
            },
        )
        stats[checker_id]["total_actions"] += 1
        if status_type_code == valid_type_code:
            stats[checker_id]["approved_contracts_set"].add(contract_id)
        if status_type_code == reject_type_code:
            stats[checker_id]["reject_actions"] += 1

    # First approvals per checker (earliest valid log per contract)
    valid_logs = base_all_qs.filter(
        checking_status_id__checking_status_type__status_type_code=valid_type_code
    )
    seen_contracts = set()
    for log in valid_logs:
        contract_id = getattr(
            getattr(log.documents_id, "contract_id", None), "contract_id", None
        )
        if contract_id is None or contract_id in seen_contracts:
            continue
        seen_contracts.add(contract_id)
        checker_id = log.trans_created_by_id
        if checker_id in stats:
            stats[checker_id]["first_approvals"] += 1

    ranking: List[Dict[str, Any]] = []
    for cid, data in stats.items():
        approved_count = len(data["approved_contracts_set"])
        reject_count = data["reject_actions"]
        total = data["total_actions"]
        reject_rate = (reject_count / total * 100) if total else 0
        ranking.append(
            {
                "checker_id": cid,
                "name": data["name"],
                "total_actions": total,
                "approved_contracts": approved_count,
                "first_approvals": data["first_approvals"],
                "reject_actions": reject_count,
                "reject_rate": round(reject_rate, 1),
            }
        )
    ranking = sorted(ranking, key=lambda x: x["total_actions"], reverse=True)[:10]

    # Folder received count
    folder_received_count = (
        Folder.objects.filter(
            folder_status_id__is_received=True,
            lastest_received_date__date__range=(start_date, end_date),
        ).count()
    )

    return {
        "drop_checkers": drop_checkers,
        "approved_contracts": approved_contracts,
        "first_time_contracts": first_time_contracts,
        "heatmap_list": heatmap_list,
        "ranking": ranking,
        "folder_received_count": folder_received_count,
    }


def get_folder_received_metrics(start_date, end_date) -> Dict[str, Any]:
    count_received = (
        Folder.objects.filter(
            folder_status_id__is_received=True,
            lastest_received_date__date__range=(start_date, end_date),
        ).count()
    )
    return {"folder_received_count": count_received}
