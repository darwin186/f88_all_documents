from django.shortcuts import render, redirect, get_object_or_404
from django.http import HttpResponse, JsonResponse, HttpResponseRedirect
from django.urls import reverse, path
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth import authenticate, login, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.contrib.auth.models import User
from django.contrib.auth.views import PasswordResetView
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.core.exceptions import ValidationError
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from django.utils import timezone, dateparse
from django.utils.dateparse import parse_datetime
from django.conf import settings
from django.db import IntegrityError, transaction, connection
from django.db.models import Count, Max, Q, Min, Prefetch, F, Sum
from django.forms.models import model_to_dict
from django.core.serializers.json import DjangoJSONEncoder
from urllib.parse import urlencode
from django.utils.http import urlsafe_base64_encode
from django.utils.encoding import force_bytes
import csv
import hashlib
import hmac
import json
import re
import logging
import os
import secrets
import requests
import pandas as pd
from datetime import datetime, timedelta
import calendar
from django.db.models.functions import ExtractHour, TruncMonth
import openpyxl
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font, Alignment, PatternFill, Border, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation
from openpyxl.worksheet.table import Table, TableStyleInfo
from io import BytesIO
# Import các model
from .models import (
    Manager,
    Shop,
    DocumentType,
    BusinessType,
    FolderType,
    DocumentsDetail, 
    LoanDetail, 
    ContractDetail,
    Employee,
    LoanCustomer,
    CheckingTransactionStatus, 
    DocumentsTransactionChecking, 
    FoldersTransactionReceiving,
    UserProfile,
    CheckingAdditional, 
    DocumentStatus,
    PackageDocumentHistory,
    FolderStatus,
    Folder,
    PackageFolderHistory,
    Package,
    PartnerPackage,
    PartnerPackageStatus,
    PartnerPackageHistory,
    Partner,
    Region,
    HistoricalFolder,
    HistoricalDocuments,
    DocumentKpiSetting,
    ChangeRequest,
    BorrowingDocument,
    BorrowingStatus,
    BorrowRequest,
    BorrowRequestItem,
    BorrowRequestLog,
    UiScreen,
    UiPermission,
    FolderIssueType,
    FolderIssue,
    FolderAppointmentLog,
    UserPresenceDaily,
    UserPresenceHourly,
    BorrowRequestStatus,
    BorrowRequestItemStatus,
    GapoScheduledMessage,
    GapoWebhookEvent,
    CollateralRegistration,
    CollateralRegistrationApiToken,
    CollateralRegistrationExternalIdentity,
    CollateralRegistrationImportBatch,
    CollateralRegistrationLog,
    CollateralRegistrationStatus,
)
# Import các form
from .forms import PackageForm, GapoPasswordResetForm, GapoScheduleForm
# Import các custom utilities
from .access_controls import AccessControls
from .utils import get_user_context, check_on_time, UI_SCREENS, ROLE_CODES, ensure_ui_screens, get_role_codes
from .dashboard import parse_dates, get_dashboard_metrics, get_folder_received_metrics
from .tasks import send_gapo_scheduled_message
from .utils import require_ui_permission
from .gddb import (
    import_collateral_registrations,
    load_records_from_excel_url,
    parse_pasted_tabular_records,
    resolve_intake_field_name,
)
from app_admindocuments.models import AdmParcelRecipientCatalog, AdmParcelRecipientImportBatch

AI_STYLE_HINTS = {
    "formal": "Viết ngắn gọn, lịch sự, trang trọng, dùng đại từ phù hợp công việc.",
    "friendly": "Viết thân thiện, gần gũi, rõ ràng, tránh từ ngữ quá trang trọng.",
    "fun": "Viết vui vẻ, dí dỏm, tích cực nhưng vẫn lịch sự.",
}

GDDB_POSTMINI_STATUS_CHOICES = [
    ("Đã cập nhật", "Đã cập nhật"),
    ("Chưa cập nhật", "Chưa cập nhật"),
    ("Đã cập nhật 1 dòng", "Đã cập nhật 1 dòng"),
]

GDDB_NON_REGISTRATION_REASON_CHOICES = [
    "Hợp đồng hết hiệu lực",
    "Hợp đồng đã tất toán",
    "Hợp đồng không đủ điều kiện đăng ký",
    "Thông tin hợp đồng/tài sản không hợp lệ",
    "Trùng giao dịch bảo đảm",
    "Khác",
]

GDDB_REGISTRATION_REASON_CHOICES = [
    "Đăng ký mới",
    "Đăng ký lại",
    "Bổ sung/thay đổi thông tin",
    "Khác",
]

def _normalize_issue_type_ids(issue_type_ids_raw):
    if not isinstance(issue_type_ids_raw, list):
        return []
    issue_type_ids = []
    for item in issue_type_ids_raw:
        try:
            issue_type_ids.append(int(item))
        except (TypeError, ValueError):
            continue
    seen = set()
    unique_ids = []
    for item in issue_type_ids:
        if item in seen:
            continue
        seen.add(item)
        unique_ids.append(item)
    return unique_ids


def _get_valid_issue_types(issue_type_ids):
    if not issue_type_ids:
        return [], 'Vui lòng chọn ít nhất 1 trạng thái lỗi.'
    issue_types = list(FolderIssueType.objects.filter(is_active=True, issue_type_id__in=issue_type_ids))
    if len(issue_types) != len(issue_type_ids):
        return [], 'Trạng thái lỗi không hợp lệ.'
    if any(t.is_no_issue for t in issue_types) and len(issue_types) > 1:
        return [], 'Không thể chọn "Không lỗi" cùng các lỗi khác.'
    return issue_types, None


def _replace_folder_issues(folder, issue_types, user):
    FolderIssue.objects.filter(folder_id=folder).delete()
    if issue_types:
        FolderIssue.objects.bulk_create([
            FolderIssue(folder=folder, issue_type=issue_type, created_by=user)
            for issue_type in issue_types
        ])


def _json_body(request):
    if not request.body:
        return {}
    return json.loads(request.body.decode("utf-8"))


def _is_gddb_admin(user):
    return user.is_superuser or user.groups.filter(name="admin").exists()


def _is_gddb_checker(user):
    return user.is_superuser or user.groups.filter(name="checker").exists()


def _gddb_current_date():
    current_time = timezone.now()
    if timezone.is_aware(current_time):
        return timezone.localtime(current_time).date()
    return current_time.date()


def _gddb_intake_identity(request):
    expected_token = (getattr(settings, "GDDB_INTAKE_TOKEN", "") or "").strip()
    auth_header = request.headers.get("Authorization", "")
    bearer_token = auth_header.removeprefix("Bearer ").strip() if auth_header.startswith("Bearer ") else ""
    supplied_tokens = [token.strip() for token in (request.headers.get("X-GDDB-Token", ""), bearer_token) if token.strip()]
    if not supplied_tokens:
        return False, None

    for supplied_token in supplied_tokens:
        token_hash = hashlib.sha256(supplied_token.encode("utf-8")).hexdigest()
        managed_token = CollateralRegistrationApiToken.objects.select_related("owner").filter(
            token_hash=token_hash,
            is_active=True,
            owner__is_active=True,
        ).first()
        if managed_token:
            managed_token.last_used_at = timezone.now()
            managed_token.save(update_fields=["last_used_at"])
            return True, managed_token.owner
        if expected_token and hmac.compare_digest(supplied_token, expected_token):
            return True, None
    return False, None


def _gddb_filtered_registrations(request, *, default_pending=True, rollup_days=None):
    use_default_work_queue = default_pending and "status_present" not in request.GET
    if "status_present" in request.GET:
        selected_statuses = [
            value
            for value in request.GET.getlist("status")
            if value in dict(CollateralRegistrationStatus.choices)
        ]
    else:
        selected_statuses = []

    query = (request.GET.get("q") or "").strip()
    date_from = dateparse.parse_date(request.GET.get("date_from") or "")
    date_to = dateparse.parse_date(request.GET.get("date_to") or "")
    registrations = CollateralRegistration.objects.filter(is_duplicate=False)
    if rollup_days:
        registrations = registrations.filter(created_at__gte=timezone.now() - timedelta(days=rollup_days))
    if use_default_work_queue:
        registrations = registrations.filter(
            Q(gddb_status=CollateralRegistrationStatus.PENDING)
            | (
                Q(gddb_status=CollateralRegistrationStatus.REGISTERED)
                & ~Q(postmini_updated__in=["Đã cập nhật", "Đã cập nhật 1 dòng"])
            )
        )
    if selected_statuses:
        registrations = registrations.filter(gddb_status__in=selected_statuses)
    if query:
        registrations = registrations.filter(
            Q(contract_code__icontains=query)
            | Q(license_plate__icontains=query)
            | Q(chassis_number__icontains=query)
            | Q(engine_number__icontains=query)
            | Q(shop_name__icontains=query)
        )
    if date_from:
        registrations = registrations.filter(registered_at__date__gte=date_from)
    if date_to:
        registrations = registrations.filter(registered_at__date__lte=date_to)
    return registrations, selected_statuses, query, date_from, date_to


@login_required
@require_ui_permission("gddb_registration")
def gddb_registration_view(request):
    registrations, selected_statuses, query, date_from, date_to = _gddb_filtered_registrations(
        request, rollup_days=7
    )
    sort_param = request.GET.get("sort", "-created_at")
    if sort_param not in {"created_at", "-created_at"}:
        sort_param = "-created_at"
    registrations = registrations.select_related(
        "registered_by", "updated_by", "registered_identity"
    ).order_by(sort_param, "-registration_id")
    paginator = Paginator(registrations, 50)
    page_obj = paginator.get_page(request.GET.get("page"))
    page_query = request.GET.copy()
    page_query.pop("page", None)
    pagination_query_prefix = f"{page_query.urlencode()}&" if page_query else ""
    sort_query = request.GET.copy()
    sort_query.pop("page", None)
    sort_query.pop("sort", None)
    sort_query_prefix = f"{sort_query.urlencode()}&" if sort_query else ""
    pagination_range = paginator.get_elided_page_range(page_obj.number, on_each_side=2, on_ends=1)
    base_qs = CollateralRegistration.objects.filter(
        is_duplicate=False,
        created_at__gte=timezone.now() - timedelta(days=7),
    )
    pending_count = base_qs.filter(gddb_status=CollateralRegistrationStatus.PENDING).count()
    registered_count = base_qs.filter(gddb_status=CollateralRegistrationStatus.REGISTERED).count()
    not_registered_count = base_qs.filter(gddb_status=CollateralRegistrationStatus.NOT_REGISTERED).count()
    done_count = base_qs.filter(
        gddb_status=CollateralRegistrationStatus.REGISTERED,
        postmini_updated__in=["Đã cập nhật", "Đã cập nhật 1 dòng"],
    ).count()
    total_count = base_qs.count()
    active_tab = request.GET.get("tab", "list")
    allowed_tabs = {"list"}
    if _is_gddb_admin(request.user):
        allowed_tabs.update({"api_docs", "manual", "batches", "configuration"})
    if request.user.is_superuser:
        allowed_tabs.add("tokens")
    if active_tab not in allowed_tabs:
        if active_tab != "list":
            messages.error(request, "Bạn không có quyền truy cập chức năng này.")
        active_tab = "list"
    manual_batch = None
    manual_batch_id = request.GET.get("manual_batch_id")
    if manual_batch_id:
        manual_batch = CollateralRegistrationImportBatch.objects.filter(batch_id=manual_batch_id).first()
    manual_payload_draft = request.session.pop("gddb_manual_payload_draft", "") if active_tab == "manual" else ""
    batch_page_obj = None
    batch_pagination_range = []
    batch_pagination_query_prefix = ""
    batch_query = (request.GET.get("batch_q") or "").strip()
    batch_source = (request.GET.get("batch_source") or "").strip()
    batch_date_from = dateparse.parse_date(request.GET.get("batch_date_from") or "")
    batch_date_to = dateparse.parse_date(request.GET.get("batch_date_to") or "")
    if active_tab == "batches":
        batch_queryset = CollateralRegistrationImportBatch.objects.select_related("created_by")
        if batch_source == "manual":
            batch_queryset = batch_queryset.filter(source_type__startswith="manual")
        elif batch_source == "api":
            batch_queryset = batch_queryset.exclude(source_type__startswith="manual")
        if batch_date_from:
            batch_queryset = batch_queryset.filter(created_at__date__gte=batch_date_from)
        if batch_date_to:
            batch_queryset = batch_queryset.filter(created_at__date__lte=batch_date_to)
        if batch_query:
            batch_id_query = batch_query.removeprefix("#")
            batch_search = (
                Q(source_type__icontains=batch_query)
                | Q(source_url__icontains=batch_query)
                | Q(created_by__username__icontains=batch_query)
                | Q(created_by__first_name__icontains=batch_query)
                | Q(created_by__last_name__icontains=batch_query)
            )
            if batch_id_query.isdigit():
                batch_search |= Q(batch_id=int(batch_id_query))
            batch_queryset = batch_queryset.filter(batch_search)
        batch_paginator = Paginator(batch_queryset.order_by("-created_at", "-batch_id"), 50)
        batch_page_obj = batch_paginator.get_page(request.GET.get("batch_page"))
        batch_page_query = request.GET.copy()
        batch_page_query.pop("batch_page", None)
        batch_pagination_query_prefix = (
            f"{batch_page_query.urlencode()}&" if batch_page_query else ""
        )
        batch_pagination_range = batch_paginator.get_elided_page_range(
            batch_page_obj.number, on_each_side=2, on_ends=1
        )
        for batch_item in batch_page_obj:
            is_manual = (batch_item.source_type or "").startswith("manual")
            batch_item.source_channel = "manual" if is_manual else "api"
            batch_item.source_channel_label = "Manual submit" if is_manual else "API"
    api_tokens = CollateralRegistrationApiToken.objects.select_related("owner", "created_by", "revoked_by") if request.user.is_superuser else []
    new_api_token = request.session.pop("gddb_new_api_token", None) if request.user.is_superuser else None
    registration_identities = CollateralRegistrationExternalIdentity.objects.filter(is_active=True).order_by("external_code")
    shop_names = {item.shop_name.strip().casefold() for item in page_obj if item.shop_name and item.shop_name.strip()}
    suggested_by_shop = {}
    if shop_names:
        for shop in Shop.objects.filter(is_shop_active=True, for_borrow_only=False).select_related("default_gddb_identity"):
            normalized_name = (shop.shop_name or "").strip().casefold()
            if normalized_name in shop_names and shop.default_gddb_identity and shop.default_gddb_identity.is_active:
                suggested_by_shop.setdefault(normalized_name, shop.default_gddb_identity)
    for item in page_obj:
        item.suggested_identity = suggested_by_shop.get((item.shop_name or "").strip().casefold())

    configuration_identities = []
    configuration_shops = []
    pgd_query = (request.GET.get("pgd_q") or "").strip()
    if active_tab == "configuration":
        configuration_identities = CollateralRegistrationExternalIdentity.objects.order_by("external_code")
        configuration_shops = Shop.objects.filter(is_shop_active=True, for_borrow_only=False).select_related(
            "default_gddb_identity"
        )
        if pgd_query:
            configuration_shops = configuration_shops.filter(
                Q(shop_name__icontains=pgd_query) | Q(shop_code__icontains=pgd_query)
            )
        configuration_shops = configuration_shops.order_by("shop_name")
    token_owners = User.objects.filter(is_active=True).order_by("username") if request.user.is_superuser else []
    context = get_user_context(request.user)
    context.update({
        "page_obj": page_obj,
        "status_choices": CollateralRegistrationStatus.choices,
        "postmini_status_choices": GDDB_POSTMINI_STATUS_CHOICES,
        "non_registration_reason_choices": GDDB_NON_REGISTRATION_REASON_CHOICES,
        "registration_reason_choices": GDDB_REGISTRATION_REASON_CHOICES,
        "registration_identity_choices": registration_identities,
        "filters": {
            "status": selected_statuses[0] if len(selected_statuses) == 1 else "",
            "statuses": selected_statuses,
            "q": query,
            "date_from": date_from.isoformat() if date_from else "",
            "date_to": date_to.isoformat() if date_to else "",
        },
        "is_default_work_queue": "status_present" not in request.GET,
        "selected_status_options": [
            (value, label) for value, label in CollateralRegistrationStatus.choices if value in selected_statuses
        ],
        "pending_count": pending_count,
        "not_registered_count": not_registered_count,
        "registered_count": registered_count,
        "done_count": done_count,
        "processing_posmini_count": registered_count - done_count,
        "total_count": total_count,
        "active_tab": active_tab,
        "manual_batch": manual_batch,
        "manual_payload_draft": manual_payload_draft,
        "batch_page_obj": batch_page_obj,
        "batch_pagination_range": batch_pagination_range,
        "batch_pagination_query_prefix": batch_pagination_query_prefix,
        "batch_filters": {
            "q": batch_query,
            "source": batch_source,
            "date_from": batch_date_from.isoformat() if batch_date_from else "",
            "date_to": batch_date_to.isoformat() if batch_date_to else "",
        },
        "api_tokens": api_tokens,
        "new_api_token": new_api_token,
        "token_owners": token_owners,
        "configuration_identities": configuration_identities,
        "configuration_shops": configuration_shops,
        "pgd_query": pgd_query,
        "pagination_range": pagination_range,
        "pagination_query_prefix": pagination_query_prefix,
        "sort_query_prefix": sort_query_prefix,
        "sort_param": sort_param,
        "can_process_gddb": _is_gddb_checker(request.user),
        "can_export_gddb": _is_gddb_admin(request.user),
    })
    return render(request, "app_documents/app_gddb_registration_v2.html", context)


GDDB_INTAKE_FIELD_LABELS = {
    "external_ref": "ID external",
    "contract_code": "Mã hợp đồng",
    "license_plate": "Biển số xe",
    "chassis_number": "Số khung",
    "engine_number": "Số máy",
    "gddb_status": "Trạng thái GDĐB",
    "contract_status": "Trạng thái hợp đồng",
    "source_created_date": "Ngày tạo",
    "disbursement_date": "Ngày giải ngân",
    "shop_name": "Cửa hàng",
    "disbursement_source": "Nguồn giải ngân",
    "post_update_status": "Trạng thái sau cập nhật",
    "postmini_updated": "Cập nhật PosMini",
    "source_user": "User đăng ký",
    "registered_by_name": "User thực hiện đăng ký",
    "reason": "Lý do",
    "note": "Ghi chú",
    "previous_application_no": "Số đơn đăng ký trước đó",
    "previous_registration_date": "Ngày đăng ký trước đó",
    "it_ticket_code": "Mã ticket IT",
    "pgd_note": "Note cho PGD",
    "source_system": "Hệ thống nguồn",
}


def _parse_gddb_manual_payload(raw_payload):
    input_mode = "JSON"
    column_mapping = []
    if raw_payload.lstrip().startswith(("{", "[")):
        try:
            payload = json.loads(raw_payload)
        except json.JSONDecodeError as exc:
            raise ValueError(f"JSON không hợp lệ: {exc}") from exc

        if isinstance(payload, dict):
            if payload.get("excel_url") or payload.get("url"):
                raise ValueError("Submit manual không hỗ trợ excel_url; hãy dán nội dung file trực tiếp.")
            records = payload.get("records", [])
            source_type = payload.get("source_type") or "manual_ui"
            source_url = payload.get("source_url") or "gddb_manual_submit"
        else:
            records = payload
            source_type = "manual_ui"
            source_url = "gddb_manual_submit"
        if isinstance(records, list):
            source_columns = []
            for record in records[:20]:
                if not isinstance(record, dict):
                    continue
                for key in record:
                    if key not in source_columns:
                        source_columns.append(key)
            column_mapping = [
                {"source": key, "field": resolve_intake_field_name(key), "value_key": key}
                for key in source_columns
            ]
    else:
        try:
            records, input_mode, column_mapping = parse_pasted_tabular_records(raw_payload, include_mapping=True)
        except ValueError as exc:
            raise ValueError(f"Không đọc được dữ liệu: {exc}") from exc
        source_type = "manual_paste"
        source_url = "gddb_manual_paste"

    if not isinstance(records, list):
        raise ValueError("records phải là một danh sách.")
    if any(not isinstance(record, dict) for record in records):
        raise ValueError("Mỗi phần tử trong records phải là một object dữ liệu.")
    return records, source_type, source_url, input_mode, column_mapping


@login_required
@require_ui_permission("gddb_registration")
@require_http_methods(["POST"])
def gddb_manual_preview_view(request):
    if not _is_gddb_admin(request.user):
        return JsonResponse({"success": False, "error": "Chỉ Admin được xem trước dữ liệu GDĐB manual."}, status=403)
    raw_payload = (request.POST.get("manual_payload") or "").strip()
    if not raw_payload:
        return JsonResponse({"success": False, "error": "Vui lòng dán dữ liệu cần xem trước."}, status=400)
    try:
        records, _, _, input_mode, column_mapping = _parse_gddb_manual_payload(raw_payload)
    except ValueError as exc:
        return JsonResponse({"success": False, "error": str(exc)}, status=400)

    preview_columns = []
    preview_value_keys = []
    for mapping in column_mapping:
        field = mapping.get("field")
        preview_value_keys.append(mapping.get("value_key") or field or mapping.get("source"))
        preview_columns.append({
            "source": mapping.get("source") or "",
            "field": field or "",
            "label": GDDB_INTAKE_FIELD_LABELS.get(field, "Không sử dụng"),
            "ignored": not bool(field),
        })
    preview_rows = [
        [record.get(value_key, "") for value_key in preview_value_keys]
        for record in records[:5]
    ]
    return JsonResponse({
        "success": True,
        "input_mode": input_mode,
        "total_rows": len(records),
        "columns": preview_columns,
        "rows": preview_rows,
        "has_ignored_columns": any(column["ignored"] for column in preview_columns),
    }, encoder=DjangoJSONEncoder)


@login_required
@require_ui_permission("gddb_registration")
@require_http_methods(["POST"])
def gddb_manual_intake_view(request):
    if not _is_gddb_admin(request.user):
        messages.error(request, "Chỉ Admin được submit dữ liệu GDĐB manual.")
        return redirect("gddb_registration_v2")
    raw_payload = (request.POST.get("manual_payload") or "").strip()
    if not raw_payload:
        messages.error(request, "Vui lòng dán JSON hoặc dữ liệu copy từ Excel/Google Sheets.")
        return redirect(f"{reverse('gddb_registration_v2')}?tab=manual")

    try:
        records, source_type, source_url, input_mode, _ = _parse_gddb_manual_payload(raw_payload)
    except ValueError as exc:
        request.session["gddb_manual_payload_draft"] = raw_payload[:100000]
        messages.error(request, str(exc))
        return redirect(f"{reverse('gddb_registration_v2')}?tab=manual")

    batch = import_collateral_registrations(
        records,
        user=request.user,
        source_type=source_type,
        source_url=source_url,
    )
    messages.success(
        request,
        (
            "Đã submit GDĐB manual: "
            f"nhận dạng {input_mode}; "
            f"tổng {batch.total_rows}, tạo {batch.created_rows}, cập nhật {batch.updated_rows}, "
            f"bỏ qua {batch.skipped_rows}, trùng {batch.duplicate_rows}, lỗi {batch.error_rows}."
        ),
    )
    return redirect(f"{reverse('gddb_registration_v2')}?tab=manual&manual_batch_id={batch.batch_id}")


@csrf_exempt
@require_http_methods(["POST"])
def api_gddb_intake(request):
    authorized, token_owner = _gddb_intake_identity(request)
    if not authorized:
        return JsonResponse({"success": False, "error": "Unauthorized"}, status=403)
    try:
        payload = _json_body(request)
    except json.JSONDecodeError:
        return JsonResponse({"success": False, "error": "Payload JSON không hợp lệ."}, status=400)

    excel_url = payload.get("excel_url") or payload.get("url") if isinstance(payload, dict) else ""
    if excel_url:
        try:
            records = load_records_from_excel_url(excel_url)
        except Exception as exc:
            return JsonResponse({"success": False, "error": f"Không đọc được Excel URL: {exc}"}, status=400)
        source_type = "excel_url"
        source_url = excel_url
    else:
        records = payload.get("records", []) if isinstance(payload, dict) else payload
        source_type = payload.get("source_type", "api") if isinstance(payload, dict) else "api"
        source_url = payload.get("source_url", "") if isinstance(payload, dict) else ""

    if not isinstance(records, list):
        return JsonResponse({"success": False, "error": "records phải là một danh sách."}, status=400)

    batch = import_collateral_registrations(
        records,
        user=token_owner or (request.user if request.user.is_authenticated else None),
        source_type=source_type,
        source_url=source_url,
    )
    return JsonResponse({
        "success": True,
        "batch_id": batch.batch_id,
        "total_rows": batch.total_rows,
        "created_rows": batch.created_rows,
        "updated_rows": batch.updated_rows,
        "skipped_rows": batch.skipped_rows,
        "duplicate_rows": batch.duplicate_rows,
        "error_rows": batch.error_rows,
        "summary": batch.summary,
    })


@login_required
@require_ui_permission("gddb_registration")
@require_http_methods(["POST"])
def api_gddb_update(request, registration_id):
    if not _is_gddb_checker(request.user):
        return JsonResponse({"success": False, "error": "Chỉ Checker được xử lý giao dịch GDĐB."}, status=403)
    registration = get_object_or_404(CollateralRegistration, registration_id=registration_id, is_duplicate=False)
    try:
        payload = _json_body(request)
    except json.JSONDecodeError:
        return JsonResponse({"success": False, "error": "Payload JSON không hợp lệ."}, status=400)

    status = payload.get("gddb_status")
    if status not in dict(CollateralRegistrationStatus.choices):
        return JsonResponse({"success": False, "error": "Trạng thái giao dịch bảo đảm không hợp lệ."}, status=400)
    postmini_updated = payload.get("postmini_updated", registration.postmini_updated) or "Chưa cập nhật"
    if postmini_updated not in dict(GDDB_POSTMINI_STATUS_CHOICES):
        return JsonResponse({"success": False, "error": "Trạng thái PosMini không hợp lệ."}, status=400)
    identity_id = payload.get("registered_identity_id")
    registered_identity = None
    if identity_id:
        try:
            identity_id = int(identity_id)
        except (TypeError, ValueError):
            return JsonResponse({"success": False, "error": "Định danh đăng ký không hợp lệ."}, status=400)
        registered_identity = CollateralRegistrationExternalIdentity.objects.filter(
            identity_id=identity_id,
            is_active=True,
        ).first()
        if not registered_identity:
            return JsonResponse({"success": False, "error": "Định danh đăng ký không hợp lệ hoặc đã ngừng hoạt động."}, status=400)
    if status == CollateralRegistrationStatus.REGISTERED and not registered_identity:
        return JsonResponse({"success": False, "error": "Vui lòng xác nhận định danh đã dùng để đăng ký."}, status=400)
    reason = (payload.get("reason") or "").strip()
    if status == CollateralRegistrationStatus.NOT_REGISTERED:
        if reason not in GDDB_NON_REGISTRATION_REASON_CHOICES:
            return JsonResponse({"success": False, "error": "Vui lòng chọn lý do không đăng ký hợp lệ."}, status=400)
    elif status == CollateralRegistrationStatus.REGISTERED and reason and reason not in GDDB_REGISTRATION_REASON_CHOICES:
        return JsonResponse({"success": False, "error": "Lý do/loại đăng ký không hợp lệ."}, status=400)

    old_status = registration.gddb_status
    old_postmini_status = registration.postmini_updated or "Chưa cập nhật"
    registration.gddb_status = status
    registration.post_update_status = dict(CollateralRegistrationStatus.choices)[status]
    registration.note = payload.get("note", registration.note)
    registration.reason = reason
    registration.postmini_updated = postmini_updated
    registration.source_user = request.user.username
    registration.previous_application_no = payload.get("previous_application_no", registration.previous_application_no)
    registration.it_ticket_code = payload.get("it_ticket_code", registration.it_ticket_code)
    registration.pgd_note = payload.get("pgd_note", registration.pgd_note)
    registration.registered_identity = registered_identity
    registration.registered_by_name = registered_identity.external_code if registered_identity else ""
    registration.updated_by = request.user
    if status == CollateralRegistrationStatus.REGISTERED:
        registration.registered_by = request.user
        if old_status != CollateralRegistrationStatus.REGISTERED or not registration.registered_at:
            registration.registered_at = timezone.now()
    else:
        registration.registered_by = None
        registration.registered_at = None
        registration.registered_identity = None
        registration.registered_by_name = ""
        registration.postmini_updated = "Chưa cập nhật"
    registration.save()
    CollateralRegistrationLog.objects.create(
        registration=registration,
        action="status_update",
        from_status=old_status,
        to_status=status,
        note=registration.note,
        metadata={
            "reason": registration.reason,
            "previous_application_no": registration.previous_application_no,
            "it_ticket_code": registration.it_ticket_code,
            "pgd_note": registration.pgd_note,
            "postmini_updated": registration.postmini_updated,
            "source_user": registration.source_user,
            "registered_by_name": registration.registered_by_name,
            "registered_identity_id": registration.registered_identity_id,
            "from_postmini_status": old_postmini_status,
            "to_postmini_status": registration.postmini_updated,
        },
        created_by=request.user,
    )
    return JsonResponse({
        "success": True,
        "registration_id": registration.registration_id,
        "gddb_status": registration.gddb_status,
        "gddb_status_label": registration.get_gddb_status_display(),
        "registered_at": registration.registered_at,
        "source_user": registration.source_user,
        "registered_identity_id": registration.registered_identity_id,
        "registered_identity_code": registration.registered_by_name,
        "postmini_updated": registration.postmini_updated,
        "post_update_status": registration.post_update_status,
        "reason": registration.reason,
        "updated_by_username": request.user.username,
    }, encoder=DjangoJSONEncoder)


@login_required
@require_ui_permission("gddb_registration")
@require_http_methods(["POST"])
def api_gddb_note_update(request, registration_id):
    if not _is_gddb_checker(request.user):
        return JsonResponse(
            {"success": False, "error": "Chỉ Checker được cập nhật ghi chú GDĐB."},
            status=403,
        )
    registration = get_object_or_404(
        CollateralRegistration,
        registration_id=registration_id,
        is_duplicate=False,
    )
    try:
        payload = _json_body(request)
    except json.JSONDecodeError:
        return JsonResponse(
            {"success": False, "error": "Payload JSON không hợp lệ."}, status=400
        )

    note_value = payload.get("note", "")
    if not isinstance(note_value, str):
        return JsonResponse(
            {"success": False, "error": "Ghi chú không hợp lệ."}, status=400
        )
    note_value = note_value.strip()
    if len(note_value) > 5000:
        return JsonResponse(
            {"success": False, "error": "Ghi chú không được vượt quá 5.000 ký tự."},
            status=400,
        )

    old_note = registration.note or ""
    if old_note != note_value:
        registration.note = note_value or None
        registration.updated_by = request.user
        registration.save(update_fields=["note", "updated_by", "updated_at"])
        CollateralRegistrationLog.objects.create(
            registration=registration,
            action="note_update",
            from_status=registration.gddb_status,
            to_status=registration.gddb_status,
            note=note_value or None,
            metadata={"old_note": old_note, "new_note": note_value},
            created_by=request.user,
        )

    return JsonResponse({
        "success": True,
        "note": note_value,
        "updated_by_username": request.user.username,
    })


@login_required
@require_ui_permission("gddb_registration")
@require_http_methods(["POST"])
def api_gddb_postmini_update(request, registration_id):
    if not _is_gddb_checker(request.user):
        return JsonResponse({"success": False, "error": "Chỉ Checker được cập nhật PosMini."}, status=403)
    registration = get_object_or_404(CollateralRegistration, registration_id=registration_id, is_duplicate=False)
    if registration.gddb_status != CollateralRegistrationStatus.REGISTERED:
        return JsonResponse({"success": False, "error": "Cần xác nhận đăng ký GDĐB trước khi cập nhật PosMini."}, status=400)
    try:
        payload = _json_body(request)
    except json.JSONDecodeError:
        return JsonResponse({"success": False, "error": "Payload JSON không hợp lệ."}, status=400)
    postmini_status = payload.get("postmini_updated")
    if postmini_status not in dict(GDDB_POSTMINI_STATUS_CHOICES):
        return JsonResponse({"success": False, "error": "Trạng thái PosMini không hợp lệ."}, status=400)

    old_status = registration.postmini_updated or "Chưa cập nhật"
    registration.postmini_updated = postmini_status
    registration.updated_by = request.user
    registration.source_user = request.user.username
    registration.save(update_fields=["postmini_updated", "updated_by", "source_user", "updated_at"])
    CollateralRegistrationLog.objects.create(
        registration=registration,
        action="postmini_update",
        note=f"PosMini: {old_status} → {postmini_status}",
        metadata={"from_postmini_status": old_status, "to_postmini_status": postmini_status},
        created_by=request.user,
    )
    return JsonResponse({
        "success": True,
        "postmini_updated": postmini_status,
        "process_done": postmini_status != "Chưa cập nhật",
        "source_user": registration.source_user,
        "updated_by_username": request.user.username,
    })


@login_required
@require_ui_permission("gddb_registration")
def gddb_export_view(request):
    if not _is_gddb_admin(request.user):
        return HttpResponse("Bạn không có quyền xuất dữ liệu đối soát GDĐB.", status=403)

    period_type = (request.GET.get("period_type") or "").strip()
    export_from = export_to = None
    export_label = ""
    if period_type == "day":
        export_from = dateparse.parse_date(request.GET.get("export_day") or "")
        export_to = export_from
        export_label = export_from.strftime("%Y%m%d") if export_from else ""
    elif period_type == "month":
        try:
            export_from = datetime.strptime(request.GET.get("export_month") or "", "%Y-%m").date().replace(day=1)
            export_to = export_from.replace(day=calendar.monthrange(export_from.year, export_from.month)[1])
            export_label = export_from.strftime("%Y%m")
        except ValueError:
            export_from = export_to = None
    elif period_type == "year":
        try:
            export_year = int(request.GET.get("export_year") or "")
            if not 2000 <= export_year <= 2100:
                raise ValueError
            export_from = datetime(export_year, 1, 1).date()
            export_to = datetime(export_year, 12, 31).date()
            export_label = str(export_year)
        except (TypeError, ValueError):
            export_from = export_to = None
    elif period_type == "range":
        export_from = dateparse.parse_date(request.GET.get("export_from") or "")
        export_to = dateparse.parse_date(request.GET.get("export_to") or "")
        if export_from and export_to:
            export_label = f"{export_from:%Y%m%d}-{export_to:%Y%m%d}"

    if not export_from or not export_to or export_from > export_to:
        messages.error(request, "Vui lòng chọn khoảng thời gian xuất đối soát hợp lệ.")
        return redirect("gddb_registration_v2")

    registrations = CollateralRegistration.objects.filter(
        is_duplicate=False,
        registered_at__date__range=(export_from, export_to),
    ).select_related(
        "registered_by", "registered_identity"
    ).order_by("registered_at", "contract_code")
    headers = [
        "Mã hợp đồng",
        "Biển số xe",
        "Số khung",
        "Số máy",
        "Trạng thái GDĐB",
        "Trạng thái hợp đồng",
        "Ngày tạo",
        "Ngày giải ngân",
        "Cửa hàng",
        "Nguồn giải ngân",
        "Trạng thái cập nhật giao dịch bảo đảm",
        "Lý do",
        "Cập nhật PosMini",
        "User đăng ký",
        "User thực hiện đăng ký",
    ]
    workbook = Workbook()
    worksheet = workbook.active
    worksheet.title = "Doi soat GDDB"
    worksheet.append(headers)
    for cell in worksheet[1]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor="047857")
        cell.alignment = Alignment(horizontal="center", vertical="center")

    status_labels = dict(CollateralRegistrationStatus.choices)
    for item in registrations.iterator():
        worksheet.append([
            item.contract_code,
            item.license_plate or "",
            item.chassis_number or "",
            item.engine_number or "",
            status_labels.get(item.gddb_status, item.gddb_status),
            item.contract_status or "",
            item.source_created_date,
            item.disbursement_date,
            item.shop_name or "",
            item.disbursement_source or "",
            item.post_update_status or status_labels.get(item.gddb_status, item.gddb_status),
            item.reason or "",
            item.postmini_updated or "Chưa cập nhật",
            item.source_user or "",
            item.registered_identity.external_code if item.registered_identity else (item.registered_by_name or ""),
        ])
    for row in worksheet.iter_rows(min_row=2, min_col=7, max_col=8):
        for cell in row:
            cell.number_format = "dd/mm/yyyy"
    for index, header in enumerate(headers, start=1):
        worksheet.column_dimensions[get_column_letter(index)].width = min(max(len(header) + 4, 14), 32)
    worksheet.freeze_panes = "A2"
    worksheet.auto_filter.ref = worksheet.dimensions

    output = BytesIO()
    workbook.save(output)
    output.seek(0)
    filename = f"doi-soat-gddb-{export_label}.xlsx"
    response = HttpResponse(
        output.getvalue(),
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


@login_required
@require_ui_permission("gddb_registration")
@require_http_methods(["POST"])
def gddb_token_create_view(request):
    if not request.user.is_superuser:
        return HttpResponse("Chỉ Super Admin được quản lý token GDĐB.", status=403)
    name = (request.POST.get("name") or "").strip()
    owner = User.objects.filter(pk=request.POST.get("owner_id"), is_active=True).first()
    if not name or not owner:
        messages.error(request, "Vui lòng nhập tên token và gán người sở hữu đang hoạt động.")
        return redirect(f"{reverse('gddb_registration_v2')}?tab=tokens")

    raw_token = f"gddb_{secrets.token_urlsafe(32)}"
    CollateralRegistrationApiToken.objects.create(
        name=name,
        token_hash=hashlib.sha256(raw_token.encode("utf-8")).hexdigest(),
        token_prefix=raw_token[:12],
        owner=owner,
        created_by=request.user,
    )
    request.session["gddb_new_api_token"] = raw_token
    messages.success(request, "Đã tạo token. Hãy sao chép ngay vì token chỉ hiển thị một lần.")
    return redirect(f"{reverse('gddb_registration_v2')}?tab=tokens")


@login_required
@require_ui_permission("gddb_registration")
@require_http_methods(["POST"])
def gddb_token_revoke_view(request, token_id):
    if not request.user.is_superuser:
        return HttpResponse("Chỉ Super Admin được quản lý token GDĐB.", status=403)
    api_token = get_object_or_404(CollateralRegistrationApiToken, token_id=token_id)
    if api_token.is_active:
        api_token.is_active = False
        api_token.revoked_at = timezone.now()
        api_token.revoked_by = request.user
        api_token.save(update_fields=["is_active", "revoked_at", "revoked_by"])
        messages.success(request, f"Đã thu hồi token {api_token.name}.")
    return redirect(f"{reverse('gddb_registration_v2')}?tab=tokens")


@login_required
@require_ui_permission("gddb_registration")
@require_http_methods(["POST"])
def gddb_identity_create_view(request):
    if not _is_gddb_admin(request.user):
        return HttpResponse("Chỉ Admin được cấu hình định danh GDĐB.", status=403)
    external_code = (request.POST.get("external_code") or "").strip()
    display_name = (request.POST.get("display_name") or "").strip()
    if not external_code:
        messages.error(request, "Vui lòng nhập định danh external.")
    elif not re.fullmatch(r"[A-Za-z0-9._-]+", external_code):
        messages.error(request, "Định danh chỉ được chứa chữ, số, dấu chấm, gạch dưới hoặc gạch ngang.")
    elif CollateralRegistrationExternalIdentity.objects.filter(external_code__iexact=external_code).exists():
        messages.error(request, f"Định danh {external_code} đã tồn tại.")
    else:
        CollateralRegistrationExternalIdentity.objects.create(
            external_code=external_code,
            display_name=display_name or external_code,
            created_by=request.user,
            updated_by=request.user,
        )
        messages.success(request, f"Đã tạo định danh {external_code}.")
    return redirect(f"{reverse('gddb_registration_v2')}?tab=configuration")


@login_required
@require_ui_permission("gddb_registration")
@require_http_methods(["POST"])
def gddb_configuration_save_view(request):
    if not _is_gddb_admin(request.user):
        return HttpResponse("Chỉ Admin được cấu hình định danh GDĐB.", status=403)

    active_identity_ids = set(request.POST.getlist("active_identity"))
    with transaction.atomic():
        for identity in CollateralRegistrationExternalIdentity.objects.all():
            next_active = str(identity.identity_id) in active_identity_ids
            if identity.is_active != next_active:
                identity.is_active = next_active
                identity.updated_by = request.user
                identity.save(update_fields=["is_active", "updated_by", "updated_at"])

        valid_identities = {
            str(identity_id): identity_id
            for identity_id in CollateralRegistrationExternalIdentity.objects.filter(is_active=True).values_list(
                "identity_id", flat=True
            )
        }
        submitted_shop_ids = [
            key.removeprefix("shop_identity_")
            for key in request.POST
            if key.startswith("shop_identity_") and key.removeprefix("shop_identity_").isdigit()
        ]
        for shop in Shop.objects.filter(
            is_shop_active=True,
            for_borrow_only=False,
            shop_id__in=submitted_shop_ids,
        ):
            submitted_id = (request.POST.get(f"shop_identity_{shop.shop_id}") or "").strip()
            next_identity_id = valid_identities.get(submitted_id)
            if shop.default_gddb_identity_id != next_identity_id:
                shop.default_gddb_identity_id = next_identity_id
                shop.save(update_fields=["default_gddb_identity"])

    messages.success(request, "Đã lưu danh mục định danh và mapping mặc định theo PGD.")
    return redirect(f"{reverse('gddb_registration_v2')}?tab=configuration")


@login_required
@require_ui_permission("gddb_registration")
def gddb_shop_mapping_export_view(request):
    if not _is_gddb_admin(request.user):
        return HttpResponse("Chỉ Admin được xuất mapping định danh GDĐB.", status=403)

    workbook = Workbook()
    worksheet = workbook.active
    worksheet.title = "Mapping PGD"
    worksheet.append(["PGD", "Định danh"])
    for cell in worksheet[1]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor="047857")
        cell.alignment = Alignment(horizontal="center", vertical="center")

    shops = Shop.objects.filter(is_shop_active=True, for_borrow_only=False).select_related(
        "default_gddb_identity"
    ).order_by("shop_name")
    for shop in shops:
        worksheet.append([
            shop.shop_name,
            shop.default_gddb_identity.external_code
            if shop.default_gddb_identity and shop.default_gddb_identity.is_active
            else "",
        ])
        for cell in worksheet[worksheet.max_row]:
            cell.data_type = "s"
    worksheet.column_dimensions["A"].width = 42
    worksheet.column_dimensions["B"].width = 24
    worksheet.freeze_panes = "A2"
    worksheet.auto_filter.ref = worksheet.dimensions

    output = BytesIO()
    workbook.save(output)
    filename = f"mapping-pgd-dinh-danh-gddb-{_gddb_current_date():%Y%m%d}.xlsx"
    response = HttpResponse(
        output.getvalue(),
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


@login_required
@require_ui_permission("gddb_registration")
@require_http_methods(["POST"])
def gddb_shop_mapping_import_view(request):
    if not _is_gddb_admin(request.user):
        return HttpResponse("Chỉ Admin được import mapping định danh GDĐB.", status=403)

    uploaded_file = request.FILES.get("mapping_file")
    redirect_url = f"{reverse('gddb_registration_v2')}?tab=configuration"
    if not uploaded_file:
        messages.error(request, "Vui lòng chọn file Excel mapping.")
        return redirect(redirect_url)
    if not uploaded_file.name.lower().endswith(".xlsx"):
        messages.error(request, "File mapping phải có định dạng .xlsx.")
        return redirect(redirect_url)
    if uploaded_file.size > 5 * 1024 * 1024:
        messages.error(request, "File mapping không được vượt quá 5 MB.")
        return redirect(redirect_url)

    try:
        workbook = load_workbook(uploaded_file, read_only=True, data_only=True)
        worksheet = workbook.active
        header_values = next(worksheet.iter_rows(min_row=1, max_row=1, values_only=True), None)
        if header_values is None:
            raise ValueError("File Excel đang trống.")
        raw_headers = [str(value).strip() if value is not None else "" for value in header_values]
        while raw_headers and not raw_headers[-1]:
            raw_headers.pop()
        if [header.casefold() for header in raw_headers] != ["pgd", "định danh"]:
            raise ValueError("Dòng tiêu đề phải có đúng 2 cột: PGD và Định danh.")

        shop_candidates = {}
        for shop in Shop.objects.filter(is_shop_active=True, for_borrow_only=False):
            shop_candidates.setdefault(shop.shop_name.strip().casefold(), []).append(shop)
        identities = {
            identity.external_code.casefold(): identity
            for identity in CollateralRegistrationExternalIdentity.objects.filter(is_active=True)
        }

        errors = []
        pending_updates = []
        seen_shops = set()
        for row_number, values in enumerate(worksheet.iter_rows(min_row=2, values_only=True), start=2):
            pgd_name = str(values[0]).strip() if len(values) > 0 and values[0] is not None else ""
            identity_code = str(values[1]).strip() if len(values) > 1 and values[1] is not None else ""
            if not pgd_name and not identity_code:
                continue
            if not pgd_name:
                errors.append(f"Dòng {row_number}: thiếu PGD.")
                continue

            normalized_shop = pgd_name.casefold()
            if normalized_shop in seen_shops:
                errors.append(f"Dòng {row_number}: PGD '{pgd_name}' bị lặp trong file.")
                continue
            seen_shops.add(normalized_shop)
            candidates = shop_candidates.get(normalized_shop, [])
            if not candidates:
                errors.append(f"Dòng {row_number}: không tìm thấy PGD '{pgd_name}'.")
                continue
            if len(candidates) > 1:
                errors.append(f"Dòng {row_number}: có nhiều PGD cùng tên '{pgd_name}', không thể tự động mapping.")
                continue

            identity = None
            if identity_code:
                identity = identities.get(identity_code.casefold())
                if not identity:
                    errors.append(f"Dòng {row_number}: định danh '{identity_code}' không tồn tại hoặc đã ngừng dùng.")
                    continue
            shop = candidates[0]
            shop.default_gddb_identity = identity
            pending_updates.append(shop)

        if errors:
            for error in errors[:15]:
                messages.error(request, error)
            if len(errors) > 15:
                messages.error(request, f"Còn {len(errors) - 15} lỗi khác. Không có mapping nào được cập nhật.")
            return redirect(redirect_url)
        if not pending_updates:
            messages.error(request, "File không có dòng mapping nào để cập nhật.")
            return redirect(redirect_url)

        Shop.objects.bulk_update(pending_updates, ["default_gddb_identity"])
        mapped_count = sum(1 for shop in pending_updates if shop.default_gddb_identity_id)
        cleared_count = len(pending_updates) - mapped_count
        messages.success(
            request,
            f"Đã import {len(pending_updates)} PGD: mapping {mapped_count}, để trống {cleared_count}.",
        )
    except (ValueError, TypeError, KeyError, openpyxl.utils.exceptions.InvalidFileException) as exc:
        messages.error(request, f"Không đọc được file mapping: {exc}")
    except Exception as exc:
        logger.exception("GDDB shop mapping import failed")
        messages.error(request, f"Import mapping thất bại: {exc}")
    return redirect(redirect_url)


class CustomPasswordResetView(PasswordResetView):
    form_class = GapoPasswordResetForm
    email_template_name = 'registration/password_reset_email.html'
    subject_template_name = 'registration/password_reset_subject.txt'
    html_email_template_name = 'registration/password_reset_email.html'
    
    def form_valid(self, form):
        gapo_url = getattr(settings, 'GAPO_API_URL', '')
        gapo_api_key = getattr(settings, 'GAPO_BOT_API_KEY', '')
        gapo_bot_id = getattr(settings, 'GAPO_BOT_ID', '')
        if not (gapo_url and gapo_api_key and gapo_bot_id):
            messages.error(self.request, "Chưa cấu hình GAPO bot. Liên hệ quản trị.")
            return self.form_invalid(form)
        user = form.get_user()
        if not user:
            messages.error(self.request, "Không tìm thấy tài khoản phù hợp.")
            return self.form_invalid(form)
        try:
            self._send_gapo_reset(user, gapo_url, gapo_api_key, gapo_bot_id)
            messages.success(self.request, "Thông tin đã được gửi qua địa chỉ GAPO của bạn.")
            return HttpResponseRedirect(self.get_success_url())
        except ValueError as ve:
            messages.error(self.request, str(ve))
        except Exception as exc:
            logger.error("Gửi reset password qua GAPO thất bại", exc_info=exc)
            messages.error(self.request, "Gửi qua GAPO thất bại. Vui lòng thử lại sau.")
        return self.form_invalid(form)

    def _send_gapo_reset(self, user, gapo_url, gapo_api_key, gapo_bot_id):
        profile = getattr(user, "userprofile", None)
        gapo_user_id = getattr(profile, "gapo_user_id", None)
        if not gapo_user_id:
            raise ValueError(f"User {user.username} chưa có GAPO ID. Liên hệ admin để cập nhật.")
        uid = urlsafe_base64_encode(force_bytes(user.pk))
        token = self.token_generator.make_token(user)
        reset_path = reverse('password_reset_confirm', kwargs={'uidb64': uid, 'token': token})
        reset_url = self.request.build_absolute_uri(reset_path)
        payload = {
            "bot_id": gapo_bot_id,
            "receiver_id": int(gapo_user_id),
            "body": {
                "type": "text",
                "text": f"Bạn yêu cầu đặt lại mật khẩu. Nhấn vào liên kết sau để đặt lại: {reset_url}",
                "is_markdown_text": True
            },
        }
        headers = {
            "x-gapo-api-key": gapo_api_key,
            "Content-Type": "application/json",
        }
        print(payload)
        response = requests.post(gapo_url, json=payload, headers=headers, timeout=10)
        if response.status_code >= 400:
            print(response.text)
            raise ValueError(f"GAPO trả về lỗi {response.status_code}: {response.text}")
        
logger = logging.getLogger(__name__)


def _get_nested_gapo_value(payload, *paths):
    if not isinstance(payload, dict):
        return ""
    for path in paths:
        current = payload
        found = True
        for part in path:
            if not isinstance(current, dict) or part not in current:
                found = False
                break
            current = current[part]
        if found and current not in (None, "", [], {}):
            if isinstance(current, (dict, list)):
                return json.dumps(current, ensure_ascii=False)
            return str(current)
    return ""


def _extract_gapo_webhook_summary(payload):
    return {
        "event_type": _get_nested_gapo_value(
            payload,
            ("type",),
            ("event",),
            ("event_type",),
            ("data", "type"),
            ("data", "event"),
        ),
        "bot_id": _get_nested_gapo_value(
            payload,
            ("bot_id",),
            ("data", "bot_id"),
            ("bot", "id"),
            ("data", "bot", "id"),
        ),
        "message_id": _get_nested_gapo_value(
            payload,
            ("message_id",),
            ("data", "message_id"),
            ("message", "id"),
            ("data", "message", "id"),
        ),
        "thread_id": _get_nested_gapo_value(
            payload,
            ("thread_id",),
            ("data", "thread_id"),
            ("message", "thread_id"),
            ("data", "message", "thread_id"),
        ),
        "collab_id": _get_nested_gapo_value(
            payload,
            ("collab_id",),
            ("data", "collab_id"),
            ("message", "collab_id"),
            ("data", "message", "collab_id"),
        ),
        "sender_id": _get_nested_gapo_value(
            payload,
            ("sender_id",),
            ("data", "sender_id"),
            ("user_id",),
            ("data", "user_id"),
            ("sender", "id"),
            ("data", "sender", "id"),
            ("message", "sender_id"),
            ("data", "message", "sender_id"),
        ),
        "message_text": _get_nested_gapo_value(
            payload,
            ("text",),
            ("tmp_text",),
            ("message", "text"),
            ("message", "tmp_text"),
            ("data", "text"),
            ("data", "tmp_text"),
            ("body", "text"),
            ("data", "body", "text"),
            ("message", "body", "text"),
            ("data", "message", "text"),
            ("data", "message", "tmp_text"),
            ("data", "message", "body", "text"),
        ),
    }


def _build_gapo_webhook_headers(request):
    captured = {}
    for key, value in request.headers.items():
        key_lower = key.lower()
        if key_lower == "authorization":
            captured[key] = "[redacted]"
        elif key_lower == "x-gapo-webhook-secret":
            captured[key] = "[redacted]"
        elif key_lower.startswith("x-gapo") or key_lower in {
            "content-type",
            "user-agent",
            "x-forwarded-for",
            "x-real-ip",
        }:
            captured[key] = value
    return captured


@csrf_exempt
@require_http_methods(["GET", "POST"])
def gapo_webhook_poc_view(request):
    if request.method == "GET":
        return JsonResponse(
            {
                "ok": True,
                "message": "Gapo webhook POC is ready.",
                "post_url": request.build_absolute_uri(),
                "recent_events_url": request.build_absolute_uri(reverse("gapo_webhook_poc_events")),
            }
        )

    secret = getattr(settings, "GAPO_WEBHOOK_SECRET", "")
    if secret:
        token = request.headers.get("X-Gapo-Webhook-Secret") or request.headers.get("Authorization", "")
        if token.startswith("Bearer "):
            token = token.replace("Bearer ", "", 1)
        if token != secret:
            return JsonResponse({"ok": False, "error": "Invalid webhook secret."}, status=403)

    raw_body = request.body.decode("utf-8", errors="replace")
    is_json_valid = True
    payload = {}
    try:
        parsed_payload = json.loads(raw_body or "{}")
        if isinstance(parsed_payload, dict):
            payload = parsed_payload
        else:
            payload = {"_payload": parsed_payload}
    except json.JSONDecodeError:
        is_json_valid = False

    summary = _extract_gapo_webhook_summary(payload)
    event = GapoWebhookEvent.objects.create(
        event_type=summary["event_type"],
        bot_id=summary["bot_id"],
        message_id=summary["message_id"],
        thread_id=summary["thread_id"],
        collab_id=summary["collab_id"],
        sender_id=summary["sender_id"],
        message_text=summary["message_text"],
        http_method=request.method,
        request_path=request.path,
        remote_addr=(request.headers.get("X-Forwarded-For") or request.META.get("REMOTE_ADDR", "")).split(",")[0].strip(),
        headers=_build_gapo_webhook_headers(request),
        payload=payload,
        raw_body=raw_body,
        is_json_valid=is_json_valid,
    )
    return JsonResponse(
        {
            "ok": True,
            "stored": True,
            "event_id": event.id,
            "is_json_valid": is_json_valid,
            "summary": summary,
        }
    )


@login_required
@require_http_methods(["GET"])
def gapo_webhook_poc_events_view(request):
    events = list(
        GapoWebhookEvent.objects.values(
            "id",
            "created_at",
            "event_type",
            "bot_id",
            "message_id",
            "thread_id",
            "collab_id",
            "sender_id",
            "message_text",
            "is_json_valid",
        )[:20]
    )
    return JsonResponse({"ok": True, "count": len(events), "events": events}, encoder=DjangoJSONEncoder)

@login_required
def switch_region(request, region_id):
    user_profile = UserProfile.objects.get(user=request.user)  # Lấy UserProfile của user hiện tại
    try:
        # Tìm region dựa trên region_id từ URL và kiểm tra quyền truy cập
        selected_region = Region.objects.get(region_id=region_id)  # Lấy Region từ region_id
        # Cập nhật region trong UserProfile
        user_profile.region = selected_region
        user_profile.save()  # Lưu thay đổi vào database
        # Cập nhật region_id vào session
        request.session['region_id'] = selected_region.region_id
        messages.success(request, f"Bạn đã chuyển sang vùng {selected_region.region_name}")
    except Region.DoesNotExist:
        messages.error(request, "Vùng không tồn tại hoặc bạn không có quyền truy cập. Vui lòng thử lại.")

    return redirect(request.META.get('HTTP_REFERER', 'home'))  # Chuyển hướng lại trang trước đó hoặc về trang chủ

@login_required
def home_view(request): 
    # Get user context from the utility function
    user = request.user
    user_context = get_user_context(user)
    regions = Region.objects.all()
    context = {
        **user_context,
          'user': user,
           'regions':regions
          }
    return render(request, 'home.html', context)

def handle_400(request, exception):
    return render(request, '400.html', status=400)

def handle_500(request):
    return render(request, '500.html', status=500)

#---------------------CHECKING TRANSACTION---------------------
# view danh sách chứng từ
@login_required
def checking_transaction_view(request, template_name="app_documents/app_checkingtransaction.html", redirect_name="checking_transaction"):
    user = request.user
    user_context = get_user_context(user)
    documents_detail = DocumentsDetail.objects.none()  # Khởi tạo documents_detail là None 
    if not user_context['is_admin'] and not user_context['is_checker']:
        return redirect('home')
    else:
        #Handle GET requests từ form duyệt chứng từ 
        if request.method == 'GET':
            filters = {}
            choice_shop = request.GET.get('choice_shop')
            choice_loan_code = request.GET.get('choice_loan_code')
            choice_contract_code = request.GET.get('choice_contract_code')
            choice_user_duyet = request.GET.get('choice_user_duyet')
            choice_check_date = request.GET.get('filtercheckdate')
            choice_document_date = request.GET.get('filterdocumentdate')
            choice_document_status = request.GET.get('choicedocumentstatus')
            choice_check_status = request.GET.get('choicecheckstatus')
            choice_business_type = request.GET.get('choicebusinesstype')
            region_filter = AccessControls.get_filters_for_user(user)
            range_date= 15
            if choice_shop:
                try: 
                    if choice_shop.isdigit():
                        filters['shop_id__shop_id'] = choice_shop
                    else:
                        choice_shop = str(choice_shop).strip()
                        filters['shop_id__shop_name__iexact'] = choice_shop
                except ValueError:
                    choice_shop = str(choice_shop).strip()
                    filters['shop_id__shop_name__icontains'] = choice_shop
                if choice_user_duyet:
                    filters['lastest_checked_by__username__icontains'] = choice_user_duyet
                if choice_check_date:
                    date_range = choice_check_date.split(' to ')
                    if len(date_range) == 2:
                        # Trường hợp có cả ngày bắt đầu và kết thúc
                        check_date_start, check_date_end = date_range
                        check_date_start = datetime.strptime(check_date_start, "%Y-%m-%d").date()
                        check_date_end =  datetime.strptime(check_date_end, "%Y-%m-%d").date()
                        if (check_date_end - check_date_start).days > range_date:
                            messages.info(request, f'Chỉ cho phép xuất dữ liệu Ngày duyệt {range_date} ngày liên tục.')
                            check_date_end_short7 = check_date_start + timedelta(days=range_date)
                            filters['lastest_checked_date__date__range'] = [check_date_start, check_date_end_short7]
                        else:
                            filters['lastest_checked_date__date__range'] = [check_date_start, check_date_end]
                    elif len(date_range) == 1:
                        # Trường hợp chỉ có một ngày, xem xét nó là ngày bắt đầu và sử dụng cho cả hai ngày bắt đầu và kết thúc
                        check_date = datetime.strptime(date_range[0], "%Y-%m-%d").date()
                        filters['lastest_checked_date__date__range'] = [check_date, check_date]
                if choice_document_date:
                    date_parts = choice_document_date.split(' to ')
                    if len(date_parts) == 2:
                        document_date_start, document_date_end = date_parts
                        document_date_start =datetime.strptime(document_date_start, "%Y-%m-%d").date()
                        document_date_end = datetime.strptime(document_date_end, "%Y-%m-%d").date()
                        if (document_date_end - document_date_start).days > range_date:
                            messages.info(request, f'Chỉ cho phép xuất dữ liệu Ngày chứng từ {range_date} ngày liên tục.')
                            document_date_end_short7 = document_date_start + timedelta(days=range_date)
                            filters['documents_created_date__range'] = [document_date_start, document_date_end_short7]
                        else:
                            filters['documents_created_date__range'] = [document_date_start, document_date_end]
                    elif len(date_parts) == 1:
                        # Trường hợp chỉ có một ngày, xem xét nó là ngày bắt đầu và sử dụng cho cả hai ngày bắt đầu và kết thúc
                        create_date = datetime.strptime(date_parts[0], "%Y-%m-%d").date()
                        filters['documents_created_date__range'] = [create_date, create_date]
                if choice_document_status:
                    filters['document_status_id'] = choice_document_status   
                if choice_check_status:
                    filters['status_id'] = choice_check_status          
                if choice_business_type:
                    filters['business_type_id'] = choice_business_type
            if choice_loan_code:
                filters['loan_id__loan_code__icontains'] = choice_loan_code
            if choice_contract_code:
                filters['contract_id__contract_code__icontains'] = choice_contract_code
            if len(filters)==0:
                # Nếu không có bộ lọc nào được thiết lập thì lấy tất cả dữ liệu documents_detail
                documents_detail = DocumentsDetail.objects.none()
            #Lấy dữ liệu documents_detail dựa trên các bộ lọc đã thiết lập
            else:
                filters['business_type_id__allow_checking']=True
                # Lọc dữ liệu dựa trên role của user là checker thì chỉ lấy dữ liệu của region của user
                region_shop=AccessControls.filter_shop_region_based_on_role(user)
                filters.update(region_shop)
                documents_detail = DocumentsDetail.objects.filter(**filters).select_related('checkingadditional').order_by('documents_created_date', 'loan_id','document_type_id', 'contract_id').select_related('package_id')
            paginator = Paginator(documents_detail, 50)  # Show 50 documents per page
            page_number = request.GET.get('page')
            documents_detail = paginator.get_page(page_number)
            change_requests = ChangeRequest.objects.filter(document__in=documents_detail, status='pending')
            change_requests_map = {req.document_id: req for req in change_requests}   
        #Handle POST từ form duyệt chứng từ 
        if request.method == 'POST':
            if 'formcheck' :
                # Submit mới 
                documents_id_submit = request.POST.get('documents_id_submit')
                checking_status_submit = request.POST.get('checking_status_submit')
                lasted_checked_date_submit  = timezone.now()
                note_submit = request.POST.get('checking_note_submit')
                package_code_submit = request.POST.get('package_code_submit')
                # Submit cũ 
                checking_status_previous = request.POST.get('checking_status_previous')
                package_id_previous = request.POST.get('package_id_previous')
                # Save to database
                documents_detail_instance = DocumentsDetail.objects.filter(documents_id = documents_id_submit)     
                documents_detail_instance_log = DocumentsDetail.objects.get(documents_id = documents_id_submit)     
                # Kiểm tra status_id cũ có khác status_id mới không? Nếu khác thì lưu lại ở Documents_transaction_checking_change_log
                is_checkingstatus_changed = False
                message_success_content = ''
                if checking_status_submit:
                    if checking_status_submit != checking_status_previous:
                        is_checkingstatus_changed = True
                        # # Use the update() method to update all matching rows in the queryset
                        documents_detail_instance.update(
                                                    status_id = checking_status_submit, 
                                                    lastest_checked_date= lasted_checked_date_submit, 
                                                    lastest_checked_by = user)
                        # Log the change
                        if is_checkingstatus_changed:
                            checking_status_instance_log = CheckingTransactionStatus.objects.get(status_id=checking_status_submit) 
                            # documents_detail_instance.update(lastest_checked_date= lasted_checked_date_submit, lastest_checked_by = user) 
                            DocumentsTransactionChecking.objects.create(
                                        documents_id = documents_detail_instance_log,
                                        trans_created_date = lasted_checked_date_submit,
                                        trans_created_by=user,
                                        checking_status_id = checking_status_instance_log,
                                    )
                            message_success_content += f"Thay đổi trạng thái thành công cho chứng từ {documents_detail_instance_log.documents_code}\n" 
                            # Nếu trạng thái chứng từ thay đổi và trạng thái kiểm chứng từ cũ là hẹn bổ sung thì đánh dấu is_valid trong AdditionalChecking là False
                            if not checking_status_instance_log.is_request_additional:
                                CheckingAdditional.objects.filter(additional=documents_detail_instance_log).update(is_valid=False) 
                            # Nếu trạng thái chứng từ đổi thành hẹn bổ sung thì đánh dấu is_valid trong AdditionalChecking là True
                            if checking_status_instance_log.is_request_additional:
                                CheckingAdditional.objects.filter(additional=documents_detail_instance_log).update(is_valid=True)
                            # Chuyển trạng thái nếu chưa có trạng thái hoặc trạng thái là đã nhận thành đã duyệt  
                            if documents_detail_instance_log.document_status_id == None: 
                                documents_detail_instance.update(document_status_id = DocumentStatus.objects.get(documents_status_code='102'))
                            if documents_detail_instance_log.document_status_id == DocumentStatus.objects.get(documents_status_code='101'): 
                                documents_detail_instance.update(document_status_id =  DocumentStatus.objects.get(documents_status_code='102'))
                                # Cập nhật ghi chú 
                if note_submit:
                    document_detail_instance_get_note = documents_detail_instance_log.note
                    if note_submit != document_detail_instance_get_note :
                        documents_detail_instance.update(note = note_submit)
                        message_success_content += f"Thêm ghi chú thành công cho chứng từ {documents_detail_instance_log.documents_code}\n"               
                if package_code_submit:
                    try: 
                        if Package.objects.filter(package_code = package_code_submit).exists():
                            package_id = Package.objects.get(package_code = package_code_submit)
                            documents_detail_instance.update(package_id = package_id)
                            message_success_content += f"Gán thùng thành công cho chứng từ {documents_detail_instance_log.documents_code}\n" 
                            # Lưu lại log gán thùng chứng từ 
                            PackageDocumentHistory.objects.create(
                                document_id = documents_detail_instance_log,
                                package_id = package_id,
                                trans_created_date = timezone.now(),
                                trans_created_by = user
                            )
                        else:
                            noti_error = f"Thùng {package_code_submit} không tồn tại. Vui lòng chọn một mã thùng đã tồn tại"  
                            messages.add_message(request, messages.ERROR, noti_error)
                            return HttpResponseRedirect(request.META.get('HTTP_REFERER'))
                    except IntegrityError:
                        noti_error = f"Thùng {package_code_submit} không tồn tại. Vui lòng chọn một mã thùng đã tồn tại"  
                        messages.add_message(request, messages.ERROR, noti_error)
                        return HttpResponseRedirect(request.META.get('HTTP_REFERER'))
                if message_success_content !='':
                    messages.add_message(request, messages.SUCCESS, message_success_content)
                # Tạo dictionary chứa thông tin lọc từ dữ liệu POST
                filter_params = {
                    'choice_shop': request.POST.get('filter_choice_shop'),
                    'choice_loan_code': request.POST.get('filter_choice_loan_code'),
                    'choice_user_duyet': request.POST.get('filter_choice_user_duyet'),
                    'filtercheckdate': request.POST.get('filter_filtercheckdate'),
                    'filterdocumentdate': request.POST.get('filter_filterdocumentdate'),
                    'choicedocumentstatus': request.POST.get('filter_choicedocumentstatus'),
                    'choicecheckstatus': request.POST.get('filter_choicecheckstatus'),
                    'choicebusinesstype': request.POST.get('filter_choicebusinesstype'),
                    'page': request.POST.get('filter_page'),
                }
                # Chuyển về trang hiển thị dữ liệu với các thông số lọc đã thiết lập
                redirect_url = f"{reverse(redirect_name)}?{urlencode(filter_params)}"
                return HttpResponseRedirect(redirect_url)  
        # Build the query string without 'page' parameter
        query_string = '&'.join(f"{key}={value}" for key, value in request.GET.items() if key != 'page')
        user_by_role = AccessControls.get_users_based_on_role(user)
        drop_list_checking_status = CheckingTransactionStatus.objects.all() 
        drop_list_shops = Shop.objects.filter(**region_filter)
        drop_list_users = user_by_role
        drop_list_document_status = DocumentStatus.objects.all()
        drop_list_business_type = BusinessType.objects.all()
        drop_list_borrowing_status = BorrowingStatus.objects.all()
        drop_list_shops_borrow = Shop.objects.filter( for_borrow_only=True)
        regions = Region.objects.all()
        context = {
            # 'is_admin': is_admin,
            # 'is_shop_user': is_shop_user,
            # 'is_checker': is_checker,
            # 'is_risk': is_risk,
            # 'is_supervisor': is_supervisor,
            **user_context,
            'user': user,
            'documents_detail': documents_detail,
            'drop_list_checking_status': drop_list_checking_status,
            'drop_list_shops':drop_list_shops,
            'drop_list_users': drop_list_users, 
            'drop_list_document_status': drop_list_document_status,
            'drop_list_business_type': drop_list_business_type,
            'query_string': query_string,
            'regions':regions, 
            'change_requests_map':change_requests_map,
            'drop_list_borrowing_status': drop_list_borrowing_status,
            'drop_list_shops_borrow':drop_list_shops_borrow
        }
        context['query_string'] = query_string
        return render(request, template_name, context)

@login_required
def checking_transaction_view_v2(request):
    user = request.user
    user_context = get_user_context(user)
    documents_detail = DocumentsDetail.objects.none()
    if not user_context['is_admin'] and not user_context['is_checker']:
        return redirect('home')

    change_requests_map = {}
    if request.method == 'GET':
        filters = {}
        choice_shop = request.GET.get('choice_shop')
        choice_loan_code = request.GET.get('choice_loan_code')
        choice_contract_code = request.GET.get('choice_contract_code')
        choice_package_code = request.GET.get('filter_package', '').strip()
        choice_partner_package_code = request.GET.get('filter_partner_package', '').strip()
        choice_user_duyet = request.GET.get('choice_user_duyet')
        choice_check_date = request.GET.get('filtercheckdate')
        choice_document_date = request.GET.get('filterdocumentdate')
        choice_document_status = request.GET.get('choicedocumentstatus')
        choice_check_status = request.GET.get('choicecheckstatus')
        choice_business_type = request.GET.get('choicebusinesstype')
        sort_raw = request.GET.get('sort', '').strip()
        region_filter = AccessControls.get_filters_for_user(user)
        range_date = 15
        if choice_shop:
            try:
                if choice_shop.isdigit():
                    filters['shop_id__shop_id'] = choice_shop
                else:
                    choice_shop = str(choice_shop).strip()
                    filters['shop_id__shop_name__iexact'] = choice_shop
            except ValueError:
                choice_shop = str(choice_shop).strip()
                filters['shop_id__shop_name__icontains'] = choice_shop
            if choice_user_duyet:
                filters['lastest_checked_by__username__icontains'] = choice_user_duyet
            if choice_check_date:
                date_range = choice_check_date.split(' to ')
                if len(date_range) == 2:
                    check_date_start, check_date_end = date_range
                    check_date_start = datetime.strptime(check_date_start, "%Y-%m-%d").date()
                    check_date_end = datetime.strptime(check_date_end, "%Y-%m-%d").date()
                    if (check_date_end - check_date_start).days > range_date:
                        messages.info(request, f'Chỉ cho phép xuất dữ liệu Ngày duyệt {range_date} ngày liên tục.')
                        check_date_end_short7 = check_date_start + timedelta(days=range_date)
                        filters['lastest_checked_date__date__range'] = [check_date_start, check_date_end_short7]
                    else:
                        filters['lastest_checked_date__date__range'] = [check_date_start, check_date_end]
                elif len(date_range) == 1:
                    check_date = datetime.strptime(date_range[0], "%Y-%m-%d").date()
                    filters['lastest_checked_date__date__range'] = [check_date, check_date]
            if choice_document_date:
                date_parts = choice_document_date.split(' to ')
                if len(date_parts) == 2:
                    document_date_start, document_date_end = date_parts
                    document_date_start = datetime.strptime(document_date_start, "%Y-%m-%d").date()
                    document_date_end = datetime.strptime(document_date_end, "%Y-%m-%d").date()
                    if (document_date_end - document_date_start).days > range_date:
                        messages.info(request, f'Chỉ cho phép xuất dữ liệu Ngày chứng từ {range_date} ngày liên tục.')
                        document_date_end_short7 = document_date_start + timedelta(days=range_date)
                        filters['documents_created_date__range'] = [document_date_start, document_date_end_short7]
                    else:
                        filters['documents_created_date__range'] = [document_date_start, document_date_end]
                elif len(date_parts) == 1:
                    create_date = datetime.strptime(date_parts[0], "%Y-%m-%d").date()
                    filters['documents_created_date__range'] = [create_date, create_date]
            if choice_document_status:
                filters['document_status_id'] = choice_document_status
            if choice_check_status:
                filters['status_id'] = choice_check_status
            if choice_business_type:
                filters['business_type_id'] = choice_business_type
        if choice_loan_code:
            filters['loan_id__loan_code__icontains'] = choice_loan_code
        if choice_contract_code:
            filters['contract_id__contract_code__icontains'] = choice_contract_code
        if choice_package_code:
            filters['package_id__package_code__icontains'] = choice_package_code
        if choice_partner_package_code:
            filters['package_id__partnerpackage__partner_package_code__icontains'] = choice_partner_package_code
        if len(filters) == 0:
            documents_detail = DocumentsDetail.objects.none()
        else:
            filters['business_type_id__allow_checking'] = True
            region_shop = AccessControls.filter_shop_region_based_on_role(user)
            filters.update(region_shop)
            documents_detail = DocumentsDetail.objects.filter(**filters).select_related(
                'checkingadditional',
                'package_id',
                'package_id__partnerpackage',
                'package_id__partnerpackage__status_id',
                'shop_id',
                'loan_id',
                'loan_id__employee_id',
                'contract_id',
                'contract_id__employee_id',
                'folder_id',
                'folder_id__folder_type_id',
                'folder_id__folder_status_id',
                'document_type_id',
                'business_type_id',
                'document_status_id',
                'status_id',
                'lastest_checked_by',
            )
            default_doc_status = DocumentStatus.objects.filter(is_selectable=True).order_by('status_id').first()
            if default_doc_status:
                DocumentsDetail.objects.filter(
                    **filters,
                    document_status_id__isnull=True,
                    folder_id__folder_status_id__is_received=True,
                ).update(document_status_id=default_doc_status)
            if sort_raw:
                sort_map = {
                    'shop': 'shop_id__shop_name',
                    '-shop': '-shop_id__shop_name',
                    'document_date': 'documents_created_date',
                    '-document_date': '-documents_created_date',
                    'document_type': 'document_type_id__document_type_name',
                    '-document_type': '-document_type_id__document_type_name',
                    'business_type': 'business_type_id__business_type_name',
                    '-business_type': '-business_type_id__business_type_name',
                    'document_status': 'document_status_id__documents_status_name',
                    '-document_status': '-document_status_id__documents_status_name',
                    'checking_status': 'status_id__checking_status_name',
                    '-checking_status': '-status_id__checking_status_name',
                    'checking_date': 'lastest_checked_date',
                    '-checking_date': '-lastest_checked_date',
                    'checking_user': 'lastest_checked_by__username',
                    '-checking_user': '-lastest_checked_by__username',
                    'package_code': 'package_id__package_code',
                    '-package_code': '-package_id__package_code',
                }
                sort_parts = [p for p in sort_raw.split(',') if p]
                resolved_sorts = [sort_map.get(p) for p in sort_parts if sort_map.get(p)]
                if resolved_sorts:
                    documents_detail = documents_detail.order_by(*resolved_sorts)
                else:
                    documents_detail = documents_detail.order_by('documents_created_date', 'loan_id', 'contract_id', 'document_type_id')
            else:
                documents_detail = documents_detail.order_by('documents_created_date', 'loan_id', 'contract_id', 'document_type_id')

        paginator = Paginator(documents_detail, 50)
        page_number = request.GET.get('page')
        documents_detail = paginator.get_page(page_number)
        change_requests = ChangeRequest.objects.filter(document__in=documents_detail, status='pending')
        change_requests_map = {req.document_id: req for req in change_requests}

    if request.method == 'POST':
        is_ajax = request.headers.get('x-requested-with') == 'XMLHttpRequest'
        if 'formcheck':
            documents_id_submit = request.POST.get('documents_id_submit')
            checking_status_submit = request.POST.get('checking_status_submit')
            lasted_checked_date_submit = timezone.now()
            note_submit = request.POST.get('checking_note_submit')
            package_code_submit = request.POST.get('package_code_submit')
            checking_status_previous = request.POST.get('checking_status_previous')
            documents_detail_instance = DocumentsDetail.objects.filter(documents_id=documents_id_submit)
            documents_detail_instance_log = DocumentsDetail.objects.get(documents_id=documents_id_submit)
            is_checkingstatus_changed = False
            message_success_content = ''
            folder_received = bool(documents_detail_instance_log.folder_id and documents_detail_instance_log.folder_id.folder_status_id and documents_detail_instance_log.folder_id.folder_status_id.is_received)
            has_package = bool(documents_detail_instance_log.package_id and documents_detail_instance_log.package_id.package_code)
            if checking_status_submit:
                if not folder_received or not has_package:
                    error_msg = 'Chỉ duyệt chứng từ đã nhận và có mã thùng.'
                    if is_ajax:
                        return JsonResponse({'success': False, 'error': error_msg}, status=400)
                    messages.add_message(request, messages.ERROR, error_msg)
                    return HttpResponseRedirect(request.META.get('HTTP_REFERER'))
                checked_status = DocumentStatus.objects.filter(is_checked=True).order_by('status_id').first()
                if not checked_status:
                    error_msg = 'Chưa cấu hình trạng thái chứng từ đã duyệt.'
                    if is_ajax:
                        return JsonResponse({'success': False, 'error': error_msg}, status=400)
                    messages.add_message(request, messages.ERROR, error_msg)
                    return HttpResponseRedirect(request.META.get('HTTP_REFERER'))
                checking_status_instance_log = CheckingTransactionStatus.objects.get(status_id=checking_status_submit)
                if checking_status_submit != checking_status_previous:
                    is_checkingstatus_changed = True
                    documents_detail_instance.update(
                        status_id=checking_status_submit,
                        lastest_checked_date=lasted_checked_date_submit,
                        lastest_checked_by=user)
                    if is_checkingstatus_changed:
                        DocumentsTransactionChecking.objects.create(
                            documents_id=documents_detail_instance_log,
                            trans_created_date=lasted_checked_date_submit,
                            trans_created_by=user,
                            checking_status_id=checking_status_instance_log,
                        )
                        message_success_content += f"Thay đổi trạng thái thành công cho chứng từ {documents_detail_instance_log.documents_code}\n"
                        if documents_detail_instance_log.document_status_id is None or (
                            documents_detail_instance_log.document_status_id and documents_detail_instance_log.document_status_id.is_selectable
                        ):
                            documents_detail_instance.update(document_status_id=checked_status)
                if not checking_status_instance_log.is_request_additional:
                    CheckingAdditional.objects.filter(additional=documents_detail_instance_log).update(is_valid=False)
                if checking_status_instance_log.is_request_additional:
                    additional_date = request.POST.get('additional_date')
                    additional_note = request.POST.get('additional_note')
                    if not additional_date:
                        if is_ajax:
                            return JsonResponse({'success': False, 'error': 'Vui lòng chọn ngày hẹn bổ sung.'}, status=400)
                        messages.add_message(request, messages.ERROR, 'Vui lòng chọn ngày hẹn bổ sung.')
                        return HttpResponseRedirect(request.META.get('HTTP_REFERER'))
                    additional_obj, created = CheckingAdditional.objects.get_or_create(
                        additional=documents_detail_instance_log,
                        defaults={
                            'is_valid': True,
                            'additional_note': additional_note if additional_note else None,
                            'date_addition': additional_date,
                            'additional_created_by': user,
                        },
                    )
                    if not created:
                        CheckingAdditional.objects.filter(additional=documents_detail_instance_log).update(
                            is_valid=True,
                            additional_note=additional_note if additional_note else None,
                            date_addition=additional_date,
                            additional_updated_date=timezone.now(),
                        )
            if note_submit:
                document_detail_instance_get_note = documents_detail_instance_log.note
                if note_submit != document_detail_instance_get_note:
                    documents_detail_instance.update(note=note_submit)
                    message_success_content += f"Thêm ghi chú thành công cho chứng từ {documents_detail_instance_log.documents_code}\n"
            if package_code_submit:
                is_selectable = bool(documents_detail_instance_log.document_status_id and documents_detail_instance_log.document_status_id.is_selectable)
                is_checked = bool(documents_detail_instance_log.document_status_id and documents_detail_instance_log.document_status_id.is_checked)
                if (not is_selectable and not is_checked) or not folder_received:
                    error_msg = 'Chỉ đổi thùng khi chứng từ đã nhận và trạng thái cho phép.'
                    if is_ajax:
                        return JsonResponse({'success': False, 'error': error_msg}, status=400)
                    messages.add_message(request, messages.ERROR, error_msg)
                    return HttpResponseRedirect(request.META.get('HTTP_REFERER'))
                try:
                    if Package.objects.filter(package_code=package_code_submit).exists():
                        package_id = Package.objects.get(package_code=package_code_submit)
                        documents_detail_instance.update(package_id=package_id)
                        message_success_content += f"Gán thùng thành công cho chứng từ {documents_detail_instance_log.documents_code}\n"
                        PackageDocumentHistory.objects.create(
                            document_id=documents_detail_instance_log,
                            package_id=package_id,
                            trans_created_date=timezone.now(),
                            trans_created_by=user
                        )
                    else:
                        noti_error = f"Thùng {package_code_submit} không tồn tại. Vui lòng chọn một mã thùng đã tồn tại"
                        if is_ajax:
                            return JsonResponse({'success': False, 'error': noti_error}, status=400)
                        messages.add_message(request, messages.ERROR, noti_error)
                        return HttpResponseRedirect(request.META.get('HTTP_REFERER'))
                except IntegrityError:
                    noti_error = f"Thùng {package_code_submit} không tồn tại. Vui lòng chọn một mã thùng đã tồn tại"
                    if is_ajax:
                        return JsonResponse({'success': False, 'error': noti_error}, status=400)
                    messages.add_message(request, messages.ERROR, noti_error)
                    return HttpResponseRedirect(request.META.get('HTTP_REFERER'))
            if message_success_content != '' and not is_ajax:
                messages.add_message(request, messages.SUCCESS, message_success_content)
            if is_ajax:
                documents_detail_instance_log = DocumentsDetail.objects.select_related(
                    'status_id', 'lastest_checked_by', 'document_status_id'
                ).get(documents_id=documents_id_submit)
                checking_user_full = ''
                if documents_detail_instance_log.lastest_checked_by:
                    checking_user_full = f"{documents_detail_instance_log.lastest_checked_by.last_name} {documents_detail_instance_log.lastest_checked_by.first_name}".strip()
                return JsonResponse({
                    'success': True,
                    'checking_status_id': documents_detail_instance_log.status_id.status_id if documents_detail_instance_log.status_id else '',
                    'checking_status_name': documents_detail_instance_log.status_id.checking_status_name if documents_detail_instance_log.status_id else '',
                    'checking_date': documents_detail_instance_log.lastest_checked_date.strftime('%Y-%m-%d %H:%M') if documents_detail_instance_log.lastest_checked_date else '',
                    'checking_user': documents_detail_instance_log.lastest_checked_by.username if documents_detail_instance_log.lastest_checked_by else '',
                    'checking_user_full': checking_user_full,
                    'document_status_name': documents_detail_instance_log.document_status_id.documents_status_name if documents_detail_instance_log.document_status_id else '',
                    'document_status_color': documents_detail_instance_log.document_status_id.badge_color if documents_detail_instance_log.document_status_id else '',
                    'document_status_is_selectable': documents_detail_instance_log.document_status_id.is_selectable if documents_detail_instance_log.document_status_id else False,
                    'document_status_is_checked': documents_detail_instance_log.document_status_id.is_checked if documents_detail_instance_log.document_status_id else False,
                })
            filter_params = {
                'choice_shop': request.POST.get('filter_choice_shop'),
                'choice_loan_code': request.POST.get('filter_choice_loan_code'),
                'choice_user_duyet': request.POST.get('filter_choice_user_duyet'),
                'filtercheckdate': request.POST.get('filter_filtercheckdate'),
                'filterdocumentdate': request.POST.get('filter_filterdocumentdate'),
                'choicedocumentstatus': request.POST.get('filter_choicedocumentstatus'),
                'choicecheckstatus': request.POST.get('filter_choicecheckstatus'),
                'choicebusinesstype': request.POST.get('filter_choicebusinesstype'),
                'filter_package': request.POST.get('filter_package'),
                'filter_partner_package': request.POST.get('filter_partner_package'),
                'page': request.POST.get('filter_page'),
                'sort': request.POST.get('filter_sort'),
            }
            redirect_url = f"{reverse('checking_transaction_v2')}?{urlencode(filter_params)}"
            return HttpResponseRedirect(redirect_url)

    current = documents_detail.number if documents_detail else 1
    total_pages = documents_detail.paginator.num_pages if documents_detail else 1
    start_range = max(current - 2, 1)
    end_range = min(current + 2, total_pages)
    page_range_custom = list(range(1, min(2, total_pages) + 1))
    page_range_custom += list(range(start_range, end_range + 1))
    page_range_custom += list(range(max(total_pages - 1, 1), total_pages + 1))
    page_range_custom = sorted(set([p for p in page_range_custom if 1 <= p <= total_pages]))

    def base_field(part):
        return part.lstrip('-')

    sort_fields = ['shop', 'document_date', 'document_type', 'business_type', 'document_status', 'checking_status', 'checking_date', 'checking_user', 'package_code']
    sort_toggle = {}
    current_sort_parts = [p for p in request.GET.get('sort', '').split(',') if p]
    for f in sort_fields:
        current_dir = None
        for p in current_sort_parts:
            if base_field(p) == f:
                current_dir = p.startswith('-')
                break
        if current_dir is None:
            toggled = f
        elif current_dir is False:
            toggled = f'-{f}'
        else:
            toggled = f
        remaining = [p for p in current_sort_parts if base_field(p) != f]
        new_parts = [toggled] + remaining
        sort_toggle[f] = ','.join(new_parts)

    qs_no_page = request.GET.copy()
    qs_no_page.pop('page', None)
    qs_no_page.pop('sort', None)
    base_qs = qs_no_page.urlencode()

    query_string = '&'.join(f"{key}={value}" for key, value in request.GET.items() if key != 'page')
    user_by_role = AccessControls.get_users_based_on_role(user)
    drop_list_checking_status = CheckingTransactionStatus.objects.all()
    drop_list_shops = Shop.objects.filter(**region_filter)
    drop_list_users = user_by_role
    drop_list_document_status = DocumentStatus.objects.all()
    drop_list_business_type = BusinessType.objects.all()
    drop_list_borrowing_status = BorrowingStatus.objects.all()
    drop_list_shops_borrow = Shop.objects.filter(for_borrow_only=True)
    regions = Region.objects.all()
    context = {
        **user_context,
        'user': user,
        'documents_detail': documents_detail,
        'drop_list_checking_status': drop_list_checking_status,
        'drop_list_shops': drop_list_shops,
        'drop_list_users': drop_list_users,
        'drop_list_document_status': drop_list_document_status,
        'drop_list_business_type': drop_list_business_type,
        'query_string': query_string,
        'regions': regions,
        'change_requests_map': change_requests_map,
        'drop_list_borrowing_status': drop_list_borrowing_status,
        'drop_list_shops_borrow': drop_list_shops_borrow,
        'page_range_custom': page_range_custom,
        'base_qs': base_qs,
        'sort_param': request.GET.get('sort', ''),
        'sort_toggle': sort_toggle,
    }
    return render(request, "app_documents/app_checkingtransaction_v2.html", context)

# Lịch sử duyệt chứng từ
@login_required
def fetch_history(request, document_id):
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        history = DocumentsTransactionChecking.objects.filter(documents_id=document_id).values(
            'trans_created_date', 
            'trans_created_by__username', 
            'checking_status_id__checking_status_name'
            ).order_by('-trans_created_date')
        package_history = PackageDocumentHistory.objects.filter(document_id=document_id).values(
            'trans_created_date',
            'trans_created_by__username',
            'trans_created_by__first_name',
            'trans_created_by__last_name',
            'package_id__package_code'
            ).order_by('-trans_created_date')
        return JsonResponse({
            'checking_history': list(history),
            'package_history': list(package_history),
        })
    else:
        return JsonResponse({'error': 'Invalid request'}, status=400)
    
# Chứng từ hẹn bổ sung 
@login_required
def checking_additional_view(request, document_id):
    document = get_object_or_404(DocumentsDetail, pk=document_id)
    if request.method == 'POST':
        additional_note = request.POST.get('additional_note')
        date_addition = request.POST.get('date_addition')
        previous_check_status = request.POST.get('previous_check_status')
        additional_create_date = timezone.now()
        if additional_note or date_addition:
            try:
                # Try to create a new CheckingAdditional instance
                CheckingAdditional.objects.create(
                    additional=document,
                    additional_note=additional_note, 
                    date_addition=date_addition,
                    additional_created_date=additional_create_date, 
                    additional_created_by=request.user,
                    is_valid=True
                )
                messages.success(request, f'Hẹn bổ sung thành công cho chứng từ mã {document.documents_code}')  
                # Nếu user đã CheckingAdditional thành công thì chuyển trạng thái của checkingdocuments status_id thành trạng thái hẹn bổ sung
                additional_status = CheckingTransactionStatus.objects.filter(is_request_additional=True).order_by('status_id').first()
                if not additional_status:
                    messages.error(request, 'Chưa cấu hình trạng thái hẹn bổ sung.')
                    return HttpResponseRedirect(request.META.get('HTTP_REFERER'))
                already_documents_status_102 = DocumentStatus.objects.get(documents_status_code = '102') # Instance của trạng thái chứng từ đã duyệt
                DocumentsDetail.objects.filter(documents_id = document_id).update(
                                                                                status_id = additional_status.status_id ,
                                                                                document_status_id = already_documents_status_102.status_id,
                                                                                lastest_checked_date = timezone.now(),
                                                                                lastest_checked_by = request.user)
                # Nếu trạng thái hiện tại của chứng từ khác hẹn bổ sung thì có nghĩa là đang thay đổi trạng thái, từ đó log thay đổi.
                if previous_check_status != str(additional_status.status_id):
                    DocumentsTransactionChecking.objects.create(
                                        documents_id = document,
                                        trans_created_date = additional_create_date,
                                        trans_created_by=request.user,
                                        checking_status_id = additional_status,
                                        )
            except IntegrityError:
                # Handle the case where a CheckingAdditional instance already exists for this document
                existing_additional = CheckingAdditional.objects.get(additional=document)
                existing_additional.additional_note = additional_note
                existing_additional.date_addition = date_addition
                existing_additional.is_valid = True
                existing_additional.save()
                messages.info(request, 'Cập nhật dữ liệu hẹn chứng từ thành công')
                # Nếu user đã CheckingAdditional thành công thì chuyển trạng thái của checkingdocuments status_id thành trạng thái hẹn bổ sung
                additional_status = CheckingTransactionStatus.objects.filter(is_request_additional=True).order_by('status_id').first()
                if additional_status:
                    DocumentsDetail.objects.filter(documents_id = document_id).update(status_id = additional_status)
            # Redirect về trang trước đó
        return HttpResponseRedirect(request.META.get('HTTP_REFERER'))   # Redirect to the desired URL after handling the form submission
    return redirect('checking_transaction')  # Redirect if it's not a POST request or if something goes wrong

# Duyệt nhiều chứng từ
@login_required
def bulk_checking_document_view(request):
    try:
        data = json.loads(request.body)
        selected_items = data.get('selectedItems', [])
        selected_documents = [item.removeprefix('checkingitem') for item in selected_items]
        checking_note_submit = data.get('checking_note_submit')
        documents_status_choice = data.get('documents_status_choice')
        additional_bulk_date_choice = data.get('additional_bulk_date_choice')
        additional_bulk_note_choice = data.get('additional_bulk_note_choice')
        checking_time = timezone.now()
        user = request.user
        if not selected_items or not documents_status_choice:
            return JsonResponse({'success': False, 'error': 'Invalid data'})
        documents_status_choice_instance = CheckingTransactionStatus.objects.get(status_id=documents_status_choice)
        if documents_status_choice_instance.is_request_additional and not additional_bulk_date_choice:
            return JsonResponse({'success': False, 'error': 'Vui lòng chọn ngày hẹn bổ sung.'}, status=400)
        selected_qs = DocumentsDetail.objects.filter(documents_id__in=selected_documents).select_related(
            'loan_id',
            'contract_id',
            'folder_id',
            'folder_id__folder_status_id',
            'package_id',
        )
        checked_status = DocumentStatus.objects.filter(is_checked=True).order_by('status_id').first()
        if not checked_status:
            return JsonResponse({'success': False, 'error': 'Chưa cấu hình trạng thái chứng từ đã duyệt.'}, status=400)
        if selected_qs.count() != len(selected_documents):
            return JsonResponse({'success': False, 'error': 'Không tìm thấy đủ chứng từ đã chọn.'})
        group_keys = set()
        for doc in selected_qs:
            if not doc.package_id or not doc.package_id.package_code:
                return JsonResponse({'success': False, 'error': 'Chỉ duyệt chứng từ có mã thùng.'}, status=400)
        for doc in selected_qs:
            if getattr(doc, 'loan_id', None) and getattr(doc.loan_id, 'loan_code', None):
                group_keys.add(f"loan:{doc.loan_id.loan_code}")
            elif getattr(doc, 'contract_id', None) and getattr(doc.contract_id, 'contract_code', None):
                group_keys.add(f"contract:{doc.contract_id.contract_code}")
            else:
                group_keys.add(f"unknown:{doc.documents_id}")
        if len(group_keys) > 1:
            return JsonResponse({'success': False, 'error': 'Chỉ được duyệt nhiều chứng từ cùng HĐCC hoặc GNN.'}, status=400)
        try:
            with transaction.atomic():
                updated_rows = []
                for document_id in selected_documents:
                    documents_detail_instance = DocumentsDetail.objects.filter(documents_id=document_id)
                    documents_detail_instance_log = DocumentsDetail.objects.get(documents_id=document_id)
                    documents_detail_instance.update(
                        status_id = documents_status_choice_instance, 
                        document_status_id = checked_status,
                        lastest_checked_date= checking_time, 
                        note=checking_note_submit if checking_note_submit else None,
                        lastest_checked_by = user
                    )
                    DocumentsTransactionChecking.objects.create(
                        documents_id = documents_detail_instance_log,
                        trans_created_date = checking_time,
                        trans_created_by=user,
                        checking_status_id = documents_status_choice_instance,
                        )
                    #Tạo bổ sung cho chứng từ nếu trạng thái là hẹn bổ sung
                    if documents_status_choice_instance.is_request_additional:
                        CheckingAdditional.objects.create(
                            additional = documents_detail_instance_log, 
                            is_valid=True,
                            additional_note = additional_bulk_note_choice if additional_bulk_note_choice else None,
                            date_addition = additional_bulk_date_choice if additional_bulk_date_choice else None,
                            additional_created_date = checking_time,
                            additional_created_by = user
                            )
                    updated_doc = DocumentsDetail.objects.select_related(
                        'status_id', 'lastest_checked_by', 'document_status_id'
                    ).get(documents_id=document_id)
                    checking_user_full = ''
                    if updated_doc.lastest_checked_by:
                        checking_user_full = f"{updated_doc.lastest_checked_by.last_name} {updated_doc.lastest_checked_by.first_name}".strip()
                    updated_rows.append({
                        'documents_id': updated_doc.documents_id,
                        'checking_status_id': updated_doc.status_id.status_id if updated_doc.status_id else '',
                        'checking_status_name': updated_doc.status_id.checking_status_name if updated_doc.status_id else '',
                        'checking_date': updated_doc.lastest_checked_date.strftime('%Y-%m-%d %H:%M') if updated_doc.lastest_checked_date else '',
                        'checking_user': updated_doc.lastest_checked_by.username if updated_doc.lastest_checked_by else '',
                        'checking_user_full': checking_user_full,
                        'document_status_name': updated_doc.document_status_id.documents_status_name if updated_doc.document_status_id else '',
                        'document_status_color': updated_doc.document_status_id.badge_color if updated_doc.document_status_id else '',
                        'document_status_is_selectable': updated_doc.document_status_id.is_selectable if updated_doc.document_status_id else False,
                        'document_status_is_checked': updated_doc.document_status_id.is_checked if updated_doc.document_status_id else False,
                    })
                return JsonResponse({'success': True, 'updated': updated_rows})
        except Exception as e:
            # Không set messages cho JSON response để tránh tràn sang màn hình khác
            return JsonResponse({'success': False, 'error': 'Có lỗi xảy ra'} )
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})
        
# ADDITIONAL CHECKING TRANSACTION MANGAMENT
# Export to excel của checking management view
def export_to_excel(queryset):
    wb = Workbook()
    ws = wb.active
    ws.title = "Checking Additional"

    columns = [
        "STT", "Phòng giao dịch", "Ngày chứng từ", "Thông tin", "Loại chứng từ",
        "Loại quyển", "Ngày đến hạn bổ sung", "Người tạo bổ sung", "Trạng thái duyệt", "Thông tin duyệt", "Note bổ sung"
    ]
    ws.append(columns)
    header_fill = PatternFill(start_color='00833E', end_color='00833E', fill_type='solid')
    header_font = Font(bold=True, color="FFFFFF")

    for cell in ws[1]:  # ws[1] tương đương với hàng đầu tiên
        cell.fill = header_fill
        cell.font = header_font
    for index, additional in enumerate(queryset, start=1):
        row = [
            index,
            additional.additional.shop_id.shop_name,
            additional.additional.documents_created_date.strftime('%Y-%m-%d'),
            f"Mã HĐ: {additional.additional.loan_id.loan_code}\nTên KH: {additional.additional.loan_id.customer_name}",
            additional.additional.document_type_id.document_type_name,
            additional.additional.folder_id.folder_type_id.folder_type_name,
            additional.date_addition.strftime('%Y-%m-%d'),
            str(additional.additional_created_by),  # Chuyển đối tượng User thành chuỗi
            additional.additional.status_id.checking_status_name if additional.additional.status_id else "Chưa duyệt",
            f"{additional.additional.lastest_checked_date.strftime('%Y-%m-%d %H:%M') if additional.additional.lastest_checked_date else ''}\n{str(additional.additional.lastest_checked_by) if additional.additional.lastest_checked_by else ''}",
            additional.additional_note
        ]
        ws.append(row)
        # Thiết lập màu nền và font cho header

    response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Content-Disposition'] = 'attachment; filename=additional_checking.xlsx'
    wb.save(response)
    return response

# Additional checking management view
@login_required
def additional_management_view(request):
    user = request.user
    user_context = get_user_context(user)
    # is_admin = user.is_superuser
    # is_checker = user.groups.filter(name='checker').exists()
    region_filter = AccessControls.get_filters_for_user(user)
    # if not is_admin and not is_checker:
    if not user_context['is_admin'] and not user_context['is_checker']:
        messages.error(request, "Unauthorized access.")
        return redirect('home')
        # Only show valid additional checking records and order by date of addition and prefetch related additional and has date_addition in current month
    now = timezone.now()
    current_month = now.month
    current_year = now.year
    checking_additional = CheckingAdditional.objects.filter( is_valid=True,
                                                            date_addition__year=current_year,
                                                            date_addition__month=current_month
                                                           ).order_by('date_addition').prefetch_related('additional')
    # Filter Part
    if request.method == 'GET':
        filters = {}
        choice_shop = request.GET.get('choice_shop') 
        choice_folder_type = request.GET.get('choice_folder_type')
        filterdocumentdate = request.GET.get('filterdocumentdate')
        filteradditionaldate = request.GET.get('filteradditionaldate') 
        filtermonthdocumentdate = request.GET.get('filtermonthdocumentdate')
        if choice_shop:
            try:
                if choice_shop.isdigit():
                    filters['additional__shop_id__shop_id'] = choice_shop
                else:
                    choice_shop = str(choice_shop).strip()
                    filters['additional__shop_id__shop_name__iexact'] = choice_shop
            except ValueError:
                choice_shop = str(choice_shop).strip()
                filters['additional__shop_id__shop_name__icontains'] = choice_shop
        if choice_folder_type:
            filters['additional__folder_id__folder_type_id'] = choice_folder_type
        if filtermonthdocumentdate: 
            month_parts = filtermonthdocumentdate.split('.')
            if len(month_parts) == 2:
                doc_month, doc_year = month_parts
                filters['additional__documents_created_date__month'] = doc_month
                filters['additional__documents_created_date__year'] = doc_year
        if filterdocumentdate:
            date_parts = filterdocumentdate.split(' to ')
            if len(date_parts) == 2:
                document_date_start, document_date_end = date_parts
                filters['additional__documents_created_date__range'] = [datetime.strptime(document_date_start, "%Y-%m-%d").date(), 
                                                                        datetime.strptime(document_date_end, "%Y-%m-%d").date()]
            elif len(date_parts) == 1:
                create_date = datetime.strptime(date_parts[0], "%Y-%m-%d").date()
                filters['additional__documents_created_date__range'] = [create_date, create_date] 
        if filteradditionaldate:
            date_parts = filteradditionaldate.split(' to ')
            if len(date_parts) == 2:
                additional_date_start, additional_date_end = date_parts
                filters['date_addition__range'] = [datetime.strptime(additional_date_start, "%Y-%m-%d").date(), 
                                                    datetime.strptime(additional_date_end, "%Y-%m-%d").date()]
            elif len(date_parts) == 1:
                additional_date = datetime.strptime(date_parts[0], "%Y-%m-%d").date()
                filters['date_addition__range'] = [additional_date, additional_date]
       
        if len(filters)==0:
            checking_additional = checking_additional
        else:
            checking_additional = CheckingAdditional.objects.filter(**filters,is_valid=True).order_by('date_addition').prefetch_related('additional')
    # Check if export is requested
    if request.GET.get('export') == '1':
        return export_to_excel(checking_additional)
    paginator = Paginator(checking_additional, 50)  # Show 50 documents per page
    page_number = request.GET.get('page')
    checking_additional = paginator.get_page(page_number) 
    drop_list_folder_type = FolderType.objects.all()
    drop_list_shops = Shop.objects.filter(**region_filter)
    regions = Region.objects.all()
    context = {
        # 'is_admin': is_admin,
        # 'is_checker': is_checker,
        **user_context,
        'user': user,
        'now': now,
        'checking_additional': checking_additional,
        'drop_list_folder_type': drop_list_folder_type,
        'drop_list_shops': drop_list_shops,
        'regions' : regions
    }
    return render(request, 'app_documents/app_additional_management.html', context)

#-------------------FOLDER TRANSACTION -------------------
# Folder transaction view
@login_required
def receive_folder_view(request, template_name="app_documents/app_receivingtransaction.html", redirect_name="receiving_transaction"): 
    user = request.user 
    user_context = get_user_context(user)
    folder_detail = Folder.objects.none()  # Khởi tạo folder_detail là None 
    if not user_context['is_admin'] and not user_context['is_checker']:
        messages.error(request, "Unauthorized access.")
        return redirect('home')
    else:
        region_filter = AccessControls.get_filters_for_user(user)
        if request.method == 'GET':
            filters = {}
            choice_shop = request.GET.get('choice_shop')
            choice_user_nhan = request.GET.get('choice_user_nhan')
            choice_folder_type = request.GET.get('choice_folder_type')
            choice_folder_status = request.GET.get('choice_folder_status')
            choice_folder_date = request.GET.get('filter_folder_date')
            choice_folder_code = request.GET.get('choice_folder_code')
            choice_receive_date = request.GET.get('filter_receive_date')
            # choice_package_code = request.GET.get('package_code_submit') 
            filter_package = request.GET.get('filter_package')
            range_date = 15
            #Handle GET requests từ form nhận hồ sơ
            if choice_shop:
                try: 
                    if choice_shop.isdigit():
                        filters['shop_id__shop_id'] = choice_shop  
                    else:
                        choice_shop = str(choice_shop).strip()
                        filters['shop_id__shop_name__iexact'] = choice_shop
                        # filters shop theo region 
                except ValueError: 
                    # Tim kiếm gần giống: 
                    choice_shop = str(choice_shop).strip()
                    filters['shop_id__shop_name__icontains'] = choice_shop 
                if choice_user_nhan:
                    filters['lastest_received_by__username__icontains'] = choice_user_nhan
                if choice_folder_type:
                    filters['folder_type_id'] = choice_folder_type
                if choice_receive_date:
                    date_range = choice_receive_date.split(' to ')
                    if len(date_range) == 2:
                        # Trường hợp có cả ngày bắt đầu và kết thúc
                        receive_date_start, receive_date_end = date_range
                        receive_date_start = datetime.strptime(receive_date_start, "%Y-%m-%d").date()
                        receive_date_end = datetime.strptime(receive_date_end, "%Y-%m-%d").date()
                        if (receive_date_end - receive_date_start).days > range_date:
                            messages.info(request, f'Chỉ cho phép xuất dữ liệu Ngày nhận {range_date} ngày liên tục.')
                            receive_date_end_short7 = receive_date_start + timedelta(days=range_date)
                            filters['lastest_received_date__date__range'] = [receive_date_start, receive_date_end_short7]
                        else:
                            # Chỉ cho phép xuất dữ liệu 7 ngày liên tục, nếu lớn hơn thì cảnh báo info và xuất dữ liệu 7 ngày kể từ start
                            filters['lastest_received_date__date__range'] = [receive_date_start, receive_date_end]
                    elif len(date_range) == 1:
                        # Trường hợp chỉ có một ngày, xem xét nó là ngày bắt đầu và sử dụng cho cả hai ngày bắt đầu và kết thúc
                        receive_date = datetime.strptime(date_range[0], "%Y-%m-%d").date()
                        filters['lastest_received_date__date__range'] = [receive_date, receive_date]
                if choice_folder_date:
                    date_parts = choice_folder_date.split(' to ')
                    if len(date_parts) == 2:
                        # Trường hợp có cả ngày bắt đầu và kết thúc 
                        folder_date_start, folder_date_end = date_parts
                        folder_date_start = datetime.strptime(folder_date_start, "%Y-%m-%d").date() 
                        folder_date_end = datetime.strptime(folder_date_end, "%Y-%m-%d").date() 
                        if(folder_date_end - folder_date_start).days > 15:
                            messages.info(request, f'Chỉ cho phép xuất dữ liệu Ngày chứng từ {range_date} ngày liên tục.')
                            folder_date_end_short7 = folder_date_start + timedelta(days=7)
                            filters['folder_created_date__range'] = [folder_date_start, folder_date_end_short7]
                        else:
                            filters['folder_created_date__range'] = [folder_date_start, folder_date_end]
                    elif len(date_parts) == 1:
                        # Trường hợp chỉ có một ngày, xem xét nó là ngày bắt đầu và sử dụng cho cả hai ngày bắt đầu và kết thúc
                        create_date = datetime.strptime(date_parts[0], "%Y-%m-%d").date()
                        filters['folder_created_date__range'] = [create_date, create_date]         
                if choice_folder_status:
                    filters['folder_status_id'] = choice_folder_status         
            if choice_folder_code:
                filters['folder_code__icontains'] = choice_folder_code
            if filter_package:
                # Relate with 2 columns 
                if filter_package.startswith('CIMB') or filter_package.startswith('VH'):
                    filters['package_id__package_code'] = filter_package
                else:
                    filters['package_id__partnerpackage__partner_package_code'] = filter_package 
            if len(filters) == 0:
                # Nếu không có bộ lọc nào được thiết lập thì lấy tất cả dữ liệu documents_detail
                folder_detail = Folder.objects.none()
            #Lấy dữ liệu documents_detail dựa trên các bộ lọc đã thiết lập
            else:
                region_shop = AccessControls.filter_shop_region_based_on_role(user)
                filters.update(region_shop)
                folder_detail = Folder.objects.filter(**filters).prefetch_related('package_id').order_by('folder_created_date')
            # Sau khi có folder_detail dựa trên bộ lọc
            paginator = Paginator(folder_detail, 50)
            page_number = request.GET.get('page')
            folder_detail = paginator.get_page(page_number)
            # Lấy ChangeRequest liên quan đến từng folder (có status là 'pending')
            change_requests = ChangeRequest.objects.filter(folder__in=folder_detail, status='pending')
            change_requests_map = {req.folder_id: req for req in change_requests}     
        #Handle POST từ form nhận hồ sơ
        if request.method == 'POST':
            if 'formreceive' :
                # Submit mới 
                folder_id_submit = request.POST.get('folder_id_submit')
                folder_status_submit = request.POST.get('folder_status_submit')
                lasted_received_date_submit  = request.POST.get('filter_True_Lastest_Receive_Date')
                if lasted_received_date_submit == '':
                    lasted_received_date_submit = timezone.now()
                else:
                    # Nếu cần xử lý chuỗi thành datetime, hãy thực hiện tại đây
                    lasted_received_date_submit = parse_datetime(lasted_received_date_submit)
                note_submit = request.POST.get('folder_note_submit')
                choice_package_code = request.POST.get('package_code_submit')
                # Submit cũ 
                folder_status_previous = request.POST.get('folder_status_previous')
                folder_detail_instance = Folder.objects.filter(folder_id = folder_id_submit) 
                folder_detail_instance_log = Folder.objects.get(folder_id = folder_id_submit) 
                is_folderstatus_changed = False 
                messages_success_content = ''
                # Kiểm tra folder_status_id cũ có khác folder_status_id mới không? Nếu khác thì lưu lại ở Folders_transaction_receiving_change_log
                if folder_status_submit:
                    # Nếu trạng thái quyển submit khác với trạng thái quyển hiện tại thì cập nhật trạng thái mới.
                    if folder_status_submit != folder_status_previous:
                        if Package.objects.filter(package_code = choice_package_code).exists():
                            is_folderstatus_changed = True
                            folder_detail_instance.update(  folder_status_id = folder_status_submit, 
                                                            lastest_received_date= lasted_received_date_submit, 
                                                            lastest_received_by = user)
                            result_check = check_on_time(folder_detail_instance_log, lasted_received_date_submit)
                            messages.add_message(request, messages.INFO, result_check.get("message", "")) 
                            # Nếu trạng thái được thay đổi thì lưu lại log trong bảng FolderTransactionReceiving
                            if is_folderstatus_changed:
                                # Lấy ins của trạng thái quyển mới
                                folder_status_instance_log = FolderStatus.objects.get(folder_status_id=folder_status_submit) 
                                # Tạo log thay đổi trạng thái quyển
                                FoldersTransactionReceiving.objects.create(
                                    folder_id = folder_detail_instance_log, 
                                    trans_updated_date=lasted_received_date_submit,
                                    trans_created_by=user,
                                    folder_status_id = folder_status_instance_log
                                )
                                # Bắn message thành công
                                messages_success_content += f"Thay đổi trạng thái thành công cho quyển {folder_detail_instance_log.folder_code}\n" 
                # Nếu nhận được ghi chú thì kiểm tra ghi chú cũ có khác với ghi chú mới không? Nếu khác thì cập nhật ghi chú mới.                     
                if note_submit:
                    # Lấy ra ghi chú của quyển hiện tại
                    folder_detail_instance_get_note = Folder.objects.get(folder_id = folder_id_submit) 
                    if note_submit != folder_detail_instance_get_note.note : 
                        folder_detail_instance.update(note = note_submit)
                        # Bắn tin nhắn ghi chú thành công
                        messages_success_content += f"Thêm ghi chú thành công cho quyển {folder_detail_instance_get_note.folder_code}\n" 
                # Nếu nhận được mã thùng mới, kiểm tra xem mã thùng đã có trong hệ thống chưa? Nếu có trong hệ thống thì cho nhập, nếu không thì báo lỗi chưa có thùng
                if choice_package_code:
                    try: 
                        if Package.objects.filter(package_code = choice_package_code).exists():
                            create_package_time = timezone.now()
                            package_id = Package.objects.get(package_code = choice_package_code)
                            folder_detail_instance.update(package_id = package_id)
                            messages_success_content += f"Gán thùng thành công cho quyển {folder_detail_instance_log.folder_code}" 
                            PackageFolderHistory.objects.create(
                                folder_id = folder_detail_instance_log,
                                package_id = package_id,
                                trans_created_date = create_package_time,
                                trans_created_by = user
                            )
                            # Kiểm tra package_id tại documents_detail đã tồn tại folder_id chưa? Nếu chưa thì thêm vào package_id của folder tại package_id của documents_detail
                            if DocumentsDetail.objects.filter(folder_id = folder_id_submit).exists():
                                document_details = DocumentsDetail.objects.select_for_update().filter(folder_id = folder_id_submit)
                                with transaction.atomic():
                                    for document in document_details:
                                        document.package_id = package_id
                                        document.save()                    
                                        PackageDocumentHistory.objects.create(
                                            document_id = document,
                                            package_id = package_id,
                                            trans_created_date=create_package_time,
                                            trans_created_by=user )
                        # Nếu thùng không tồn tại thì thông báo lỗi
                        else:
                            noti_error = f"Thùng {choice_package_code} không tồn tại"  
                            messages.add_message(request, messages.ERROR, noti_error)
                            return HttpResponseRedirect(request.META.get('HTTP_REFERER'))
                    except IntegrityError: 
                        #Nếu thùng không tồn tại thì thông báo lỗi 
                        noti_error = f"Thùng {choice_package_code} không tồn tại" 
                        messages.add_message(request, messages.ERROR, noti_error) 
                        return HttpResponseRedirect(request.META.get('HTTP_REFERER'))
                if messages_success_content !='':
                    messages.add_message(request, messages.SUCCESS, messages_success_content) 
                # Tạo dictionary chứa thông tin lọc từ dữ liệu POST
                filter_params = {
                    'choice_shop': request.POST.get('filter_choice_shop'),
                    'choice_folder_code': request.POST.get('filter_choice_folder_code'),
                    'choice_user_nhan': request.POST.get('filter_choice_user_nhan'),
                    'filter_receive_date': request.POST.get('filter_choice_receive_date'),
                    'filter_folder_date': request.POST.get('filter_choice_folder_date'),
                    'choice_folder_type': request.POST.get('filter_choice_folder_type'),
                    'choice_folder_status': request.POST.get('filter_choice_folder_status'),
                    'page': request.POST.get('filter_page'),
                }
                # Chuyển về trang hiển thị dữ liệu với các thông số lọc đã thiết lập
                redirect_url = f"{reverse(redirect_name)}?{urlencode(filter_params)}"
                return HttpResponseRedirect(redirect_url)  
        user_by_role = AccessControls.get_users_based_on_role(user)
        query_string = '&'.join(f"{key}={value}" for key, value in request.GET.items() if key != 'page')
        drop_list_shops = Shop.objects.filter(**region_filter)
        drop_list_users = user_by_role
        drop_list_folder_type = FolderType.objects.all()
        drop_list_folder_status = FolderStatus.objects.all()
        drop_list_folder_status_received = FolderStatus.objects.filter(is_received=True)
        regions = Region.objects.all()
        context = {
            **user_context,
            'user': user,
            'folder_detail': folder_detail,
            'drop_list_shops': drop_list_shops,
            'drop_list_users': drop_list_users,
            'drop_list_folder_type': drop_list_folder_type,
            'drop_list_folder_status': drop_list_folder_status,
            'drop_list_folder_status_received': drop_list_folder_status_received,
            'regions': regions,
            'change_request':change_requests_map,
        }
        context['query_string'] = query_string
        return render(request, template_name, context)


@login_required
def receive_folder_view_v2(request):
    """
    Trang nhận chứng từ ver2 (UI mới, layout giống package-list).
    """
    user = request.user
    user_context = get_user_context(user)
    if not user_context['is_admin'] and not user_context['is_checker']:
        messages.error(request, "Unauthorized access.")
        return redirect('home')

    filters = {}
    choice_shop = request.GET.get('choice_shop', '').strip()
    choice_folder_code = request.GET.get('choice_folder_code', '').strip()
    choice_folder_status = request.GET.get('choice_folder_status', '').strip()
    choice_folder_type = request.GET.get('choice_folder_type', '').strip()
    choice_lastest_receiver = request.GET.get('choice_lastest_receiver', '').strip()
    choice_package_code = request.GET.get('filter_package', '').strip()
    choice_partner_package_code = request.GET.get('filter_partner_package', '').strip()
    choice_receive_date = request.GET.get('filter_receive_date', '').strip()
    choice_folder_date = request.GET.get('filter_folder_date', '').strip()
    sort_raw = request.GET.get('sort', '-folder_created_date').strip()

    range_date = 30  # giới hạn 30 ngày

    region_shop_filter = AccessControls.filter_shop_region_based_on_role(user)
    region_filter = AccessControls.get_filters_for_user(user)
    drop_list_shops = Shop.objects.filter(is_shop_active=True, for_borrow_only=False, **region_filter).order_by('shop_name')
    drop_list_folder_status = FolderStatus.objects.filter(is_valid=True).order_by('folder_status_name')
    drop_list_folder_status_received = FolderStatus.objects.filter(is_received=True, is_valid=True).order_by('folder_status_name')
    drop_list_folder_type = FolderType.objects.filter(is_valid=True).order_by('folder_type_name')
    drop_list_users = User.objects.filter(is_active=True).order_by('username')
    package_types = FolderType.objects.filter(is_valid=True).order_by('package_type', 'folder_type_name')
    partners_active = Partner.objects.filter(is_active=True).order_by('partner_name')
    partners_options_json = json.dumps(
        list(partners_active.values('partner_id', 'partner_name', 'partner_code', 'require_partner_selection', 'require_partner_code')),
        cls=DjangoJSONEncoder,
        ensure_ascii=False,
    )
    region_options_json = json.dumps(
        list(Region.objects.values('region_code', 'region_name')),
        cls=DjangoJSONEncoder,
        ensure_ascii=False,
    )
    issue_palette = ['#f59e0b', '#10b981', '#3b82f6', '#f97316', '#ec4899', '#8b5cf6', '#14b8a6', '#94a3b8']
    issue_types = FolderIssueType.objects.filter(is_active=True).order_by('sort_order', 'issue_type_name')
    issue_type_options = []
    for idx, issue in enumerate(issue_types):
        color = issue.badge_color or issue_palette[idx % len(issue_palette)]
        issue_type_options.append({
            'id': issue.issue_type_id,
            'name': issue.issue_type_name,
            'color': color,
            'is_no_issue': issue.is_no_issue,
        })
    issue_color_map = {opt['id']: opt['color'] for opt in issue_type_options}

    if choice_shop:
        if choice_shop.isdigit():
            filters['shop_id__shop_id'] = choice_shop
        else:
            filters['shop_id__shop_name__icontains'] = choice_shop
    if choice_folder_code:
        filters['folder_code__icontains'] = choice_folder_code
    if choice_folder_status:
        filters['folder_status_id'] = choice_folder_status
    if choice_folder_type:
        filters['folder_type_id'] = choice_folder_type
    if choice_lastest_receiver:
        filters['lastest_received_by__username__icontains'] = choice_lastest_receiver
    if choice_package_code:
        filters['package_id__package_code__icontains'] = choice_package_code
    if choice_partner_package_code:
        filters['package_id__partnerpackage__partner_package_code__icontains'] = choice_partner_package_code

    def _apply_date_range(input_str, field_lookup):
        if not input_str:
            return
        date_parts = input_str.split(' to ')
        if len(date_parts) == 2:
            start = datetime.strptime(date_parts[0], "%Y-%m-%d").date()
            end = datetime.strptime(date_parts[1], "%Y-%m-%d").date()
            if (end - start).days > range_date:
                messages.info(request, f"Chỉ cho phép tìm trong tối đa {range_date} ngày.")
                end = start + timedelta(days=range_date)
            filters[field_lookup] = [start, end]
        elif len(date_parts) == 1 and date_parts[0]:
            single = datetime.strptime(date_parts[0], "%Y-%m-%d").date()
            filters[field_lookup] = [single, single]

    _apply_date_range(choice_receive_date, 'lastest_received_date__date__range')
    _apply_date_range(choice_folder_date, 'folder_created_date__range')

    if len(filters) == 0:
        folder_detail_qs = Folder.objects.none()
    else:
        filters.update(region_shop_filter)

        sort_map = {
            'folder_code': 'folder_code',
            '-folder_code': '-folder_code',
            'shop': 'shop_id__shop_name',
            '-shop': '-shop_id__shop_name',
            'folder_type': 'folder_type_id__folder_type_name',
            '-folder_type': '-folder_type_id__folder_type_name',
            'folder_created_date': 'folder_created_date',
            '-folder_created_date': '-folder_created_date',
            'lastest_received_date': 'lastest_received_date',
            '-lastest_received_date': '-lastest_received_date',
            'folder_status': 'folder_status_id__folder_status_name',
            '-folder_status': '-folder_status_id__folder_status_name',
            'is_original': 'is_original',
            '-is_original': '-is_original',
        }
        sort_fields_map = {
            'folder_code': 'folder_code',
            '-folder_code': '-folder_code',
            'shop': 'shop_id__shop_name',
            '-shop': '-shop_id__shop_name',
            'folder_type': 'folder_type_id__folder_type_name',
            '-folder_type': '-folder_type_id__folder_type_name',
            'folder_created_date': 'folder_created_date',
            '-folder_created_date': '-folder_created_date',
            'lastest_received_date': 'lastest_received_date',
            '-lastest_received_date': '-lastest_received_date',
            'folder_status': 'folder_status_id__folder_status_name',
            '-folder_status': '-folder_status_id__folder_status_name',
            'is_original': 'is_original',
            '-is_original': '-is_original',
        }

        sort_parts = [p for p in sort_raw.split(',') if p]
        resolved_sorts = [sort_fields_map.get(p) for p in sort_parts if sort_fields_map.get(p)]
        if not resolved_sorts:
            resolved_sorts = ['-folder_created_date']

        folder_detail_qs = Folder.objects.filter(**filters).select_related(
            'shop_id', 'folder_type_id', 'folder_status_id', 'lastest_received_by', 'package_id'
        ).order_by(*resolved_sorts)

    paginator = Paginator(folder_detail_qs, 25)
    page_number = request.GET.get('page')
    folder_detail = paginator.get_page(page_number)
    folder_ids = [f.folder_id for f in folder_detail] if folder_detail else []
    folder_issues_map = {}
    if folder_ids:
        for issue in FolderIssue.objects.select_related('issue_type').filter(folder_id__in=folder_ids):
            issue_type = issue.issue_type
            color = issue_color_map.get(issue_type.issue_type_id, issue_type.badge_color or issue_palette[0])
            folder_issues_map.setdefault(str(issue.folder_id), []).append({
                'id': issue_type.issue_type_id,
                'name': issue_type.issue_type_name,
                'color': color,
                'is_no_issue': issue_type.is_no_issue,
            })

    current = folder_detail.number if folder_detail else 1
    total_pages = paginator.num_pages if paginator else 1
    start_range = max(current - 2, 1)
    end_range = min(current + 2, total_pages)
    page_range_custom = list(range(1, min(2, total_pages) + 1))
    page_range_custom += list(range(start_range, end_range + 1))
    page_range_custom += list(range(max(total_pages - 1, 1), total_pages + 1))
    page_range_custom = sorted(set([p for p in page_range_custom if 1 <= p <= total_pages]))

    # sort toggle map for template
    def base_field(part):
        return part.lstrip('-')

    sort_fields = ['folder_code', 'shop', 'folder_type', 'folder_created_date', 'lastest_received_date', 'folder_status', 'is_original']
    sort_toggle = {}
    current_sort_parts = [p for p in sort_raw.split(',') if p]
    for f in sort_fields:
        current_dir = None
        for p in current_sort_parts:
            if base_field(p) == f:
                current_dir = p.startswith('-')
                break
        if current_dir is None:
            toggled = f
        elif current_dir is False:
            toggled = f'-{f}'
        else:
            toggled = f
        remaining = [p for p in current_sort_parts if base_field(p) != f]
        new_parts = [toggled] + remaining
        sort_toggle[f] = ','.join(new_parts)

    qs_no_page = request.GET.copy()
    qs_no_page.pop('page', None)
    qs_no_page.pop('sort', None)
    base_qs = qs_no_page.urlencode()

    context = {
        **user_context,
        'user': user,
        'folder_detail': folder_detail,
        'drop_list_shops': drop_list_shops,
        'drop_list_folder_status': drop_list_folder_status,
        'drop_list_folder_status_received': drop_list_folder_status_received,
        'drop_list_folder_type': drop_list_folder_type,
        'drop_list_users': drop_list_users,
        'paginator': paginator,
        'page_range_custom': page_range_custom,
        'sort_param': sort_raw,
        'sort_toggle': sort_toggle,
        'base_qs': base_qs,
        'package_types': package_types,
        'partners_active': partners_active,
        'partners_options_json': partners_options_json,
        'region_options_json': region_options_json,
        'issue_type_options': issue_type_options,
        'issue_types_json': json.dumps(issue_type_options, cls=DjangoJSONEncoder, ensure_ascii=False),
        'folder_issues_json': json.dumps(folder_issues_map, cls=DjangoJSONEncoder, ensure_ascii=False),
        'filters': {
            'choice_shop': choice_shop,
            'choice_folder_code': choice_folder_code,
            'choice_folder_status': choice_folder_status,
            'choice_folder_type': choice_folder_type,
            'choice_lastest_receiver': choice_lastest_receiver,
            'filter_receive_date': choice_receive_date,
            'filter_folder_date': choice_folder_date,
            'filter_package': choice_package_code,
        }
    }
    return render(request, "app_documents/app_document_receiving_v2.html", context)


def _folder_appointment_payload(folder):
    return {
        'active': folder.folder_appointment,
        'appointment_date': folder.folder_appointment_date.isoformat() if folder.folder_appointment_date else '',
        'reason': folder.folder_appointment_reason or '',
        'created_at': folder.folder_appointment_created_at,
        'created_by': folder.folder_appointment_created_by.username if folder.folder_appointment_created_by else '',
        'updated_at': folder.folder_appointment_updated_at,
        'resolved_at': folder.folder_appointment_resolved_at,
        'resolved_by': folder.folder_appointment_resolved_by.username if folder.folder_appointment_resolved_by else '',
    }


def _resolve_folder_appointment(folder, user, received_at, *, source):
    if not folder.folder_appointment:
        return False
    folder.folder_appointment = False
    folder.folder_appointment_resolved_at = timezone.now()
    folder.folder_appointment_resolved_by = user
    folder.folder_appointment_updated_at = timezone.now()
    folder.save(update_fields=[
        'folder_appointment',
        'folder_appointment_resolved_at',
        'folder_appointment_resolved_by',
        'folder_appointment_updated_at',
    ])
    FolderAppointmentLog.objects.create(
        folder=folder,
        action=FolderAppointmentLog.ACTION_RECEIVED,
        appointment_date=folder.folder_appointment_date,
        reason=folder.folder_appointment_reason,
        actor=user,
        metadata={
            'received_at': received_at.isoformat() if hasattr(received_at, 'isoformat') else str(received_at or ''),
            'source': source,
        },
    )
    return True


@login_required
@require_http_methods(["GET", "POST"])
def api_folder_appointment_v2(request, folder_id):
    user_context = get_user_context(request.user)
    if not user_context['is_admin'] and not user_context['is_checker']:
        return JsonResponse({'success': False, 'error': 'Unauthorized access.'}, status=403)

    appointment_scope = AccessControls.filter_shop_region_based_on_role(request.user)
    folder = get_object_or_404(
        Folder.objects.filter(**appointment_scope).select_related(
            'folder_status_id',
            'folder_appointment_created_by',
            'folder_appointment_resolved_by',
        ),
        folder_id=folder_id,
    )
    if request.method == "GET":
        logs = list(folder.appointment_logs.select_related('actor').order_by('-event_at')[:30])
        return JsonResponse({
            'success': True,
            'appointment': _folder_appointment_payload(folder),
            'is_received': bool(folder.folder_status_id and folder.folder_status_id.is_received),
            'logs': [
                {
                    'action': log.action,
                    'action_label': log.get_action_display(),
                    'appointment_date': log.appointment_date.isoformat() if log.appointment_date else '',
                    'reason': log.reason or '',
                    'event_at': log.event_at,
                    'actor': log.actor.username if log.actor else '',
                    'metadata': log.metadata,
                }
                for log in logs
            ],
        }, encoder=DjangoJSONEncoder)

    try:
        payload = _json_body(request)
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'Payload JSON không hợp lệ.'}, status=400)
    action = (payload.get('action') or 'schedule').strip()
    now = timezone.now()

    with transaction.atomic():
        folder = Folder.objects.select_for_update().filter(**appointment_scope).get(folder_id=folder_id)
        if action == 'cancel':
            if not folder.folder_appointment:
                return JsonResponse({'success': False, 'error': 'Quyển hiện không có lịch hẹn đang hoạt động.'}, status=400)
            folder.folder_appointment = False
            folder.folder_appointment_resolved_at = now
            folder.folder_appointment_resolved_by = request.user
            folder.folder_appointment_updated_at = now
            folder.save(update_fields=[
                'folder_appointment',
                'folder_appointment_resolved_at',
                'folder_appointment_resolved_by',
                'folder_appointment_updated_at',
            ])
            FolderAppointmentLog.objects.create(
                folder=folder,
                action=FolderAppointmentLog.ACTION_CANCELLED,
                appointment_date=folder.folder_appointment_date,
                reason=folder.folder_appointment_reason,
                actor=request.user,
            )
        elif action == 'schedule':
            if folder.folder_status_id and folder.folder_status_id.is_received:
                return JsonResponse({'success': False, 'error': 'Quyển đã được nhận, không thể tạo lịch hẹn mới.'}, status=400)
            appointment_date = dateparse.parse_date(payload.get('appointment_date') or '')
            reason = (payload.get('reason') or '').strip()
            if not appointment_date:
                return JsonResponse({'success': False, 'error': 'Vui lòng chọn ngày hẹn nhận quyển.'}, status=400)
            if appointment_date < _gddb_current_date():
                return JsonResponse({'success': False, 'error': 'Ngày hẹn không được nhỏ hơn ngày hiện tại.'}, status=400)
            if not reason:
                return JsonResponse({'success': False, 'error': 'Vui lòng nhập lý do hẹn nhận quyển.'}, status=400)
            if len(reason) > 2000:
                return JsonResponse({'success': False, 'error': 'Lý do không được vượt quá 2.000 ký tự.'}, status=400)

            was_active = folder.folder_appointment
            old_date = folder.folder_appointment_date
            old_reason = folder.folder_appointment_reason or ''
            folder.folder_appointment = True
            folder.folder_appointment_date = appointment_date
            folder.folder_appointment_reason = reason
            folder.folder_appointment_updated_at = now
            folder.folder_appointment_resolved_at = None
            folder.folder_appointment_resolved_by = None
            if not was_active:
                folder.folder_appointment_created_at = now
                folder.folder_appointment_created_by = request.user
            folder.save(update_fields=[
                'folder_appointment',
                'folder_appointment_date',
                'folder_appointment_reason',
                'folder_appointment_created_at',
                'folder_appointment_created_by',
                'folder_appointment_updated_at',
                'folder_appointment_resolved_at',
                'folder_appointment_resolved_by',
            ])
            FolderAppointmentLog.objects.create(
                folder=folder,
                action=(
                    FolderAppointmentLog.ACTION_RESCHEDULED
                    if was_active
                    else FolderAppointmentLog.ACTION_SCHEDULED
                ),
                appointment_date=appointment_date,
                reason=reason,
                actor=request.user,
                metadata={
                    'previous_appointment_date': old_date.isoformat() if old_date else '',
                    'previous_reason': old_reason,
                },
            )
        else:
            return JsonResponse({'success': False, 'error': 'Thao tác lịch hẹn không hợp lệ.'}, status=400)

    folder.refresh_from_db()
    return JsonResponse({
        'success': True,
        'message': 'Đã lưu lịch hẹn nhận quyển.' if action == 'schedule' else 'Đã hủy lịch hẹn nhận quyển.',
        'appointment': _folder_appointment_payload(folder),
    }, encoder=DjangoJSONEncoder)


def _folder_appointment_status_label(folder):
    if folder.folder_appointment:
        return 'Đang hẹn'
    if folder.folder_status_id and folder.folder_status_id.is_received:
        return 'Đã nhận'
    if folder.folder_appointment_resolved_at:
        return 'Đã đóng lịch hẹn'
    return 'Chưa hẹn'


def _parse_folder_appointment_export_period(request):
    period_type = (request.GET.get('period_type') or '').strip()
    date_from = date_to = None
    label = ''
    if period_type == 'day':
        date_from = dateparse.parse_date(request.GET.get('export_day') or '')
        date_to = date_from
        label = date_from.strftime('%Y%m%d') if date_from else ''
    elif period_type == 'month':
        try:
            date_from = datetime.strptime(request.GET.get('export_month') or '', '%Y-%m').date().replace(day=1)
            date_to = date_from.replace(day=calendar.monthrange(date_from.year, date_from.month)[1])
            label = date_from.strftime('%Y%m')
        except ValueError:
            date_from = date_to = None
    elif period_type == 'year':
        try:
            year = int(request.GET.get('export_year') or '')
            if not 2000 <= year <= 2100:
                raise ValueError
            date_from = datetime(year, 1, 1).date()
            date_to = datetime(year, 12, 31).date()
            label = str(year)
        except (TypeError, ValueError):
            date_from = date_to = None
    elif period_type == 'range':
        date_from = dateparse.parse_date(request.GET.get('export_from') or '')
        date_to = dateparse.parse_date(request.GET.get('export_to') or '')
        if date_from and date_to:
            label = f'{date_from:%Y%m%d}-{date_to:%Y%m%d}'
    if not date_from or not date_to or date_from > date_to:
        raise ValueError('Vui lòng chọn khoảng ngày hẹn hợp lệ.')
    return date_from, date_to, label


@login_required
def folder_appointment_report_view(request):
    if not _is_gddb_admin(request.user):
        return HttpResponse('Chỉ Admin được xem báo cáo hẹn nhận quyển.', status=403)
    query = (request.GET.get('q') or '').strip()
    status = (request.GET.get('status') or '').strip()
    appointments = Folder.objects.filter(folder_appointment_date__isnull=False).select_related(
        'folder_type_id',
        'shop_id',
        'folder_status_id',
        'folder_appointment_created_by',
        'folder_appointment_resolved_by',
        'lastest_received_by',
    )
    if query:
        appointments = appointments.filter(
            Q(folder_code__icontains=query)
            | Q(shop_id__shop_name__icontains=query)
            | Q(shop_id__shop_code__icontains=query)
        )
    if status == 'active':
        appointments = appointments.filter(folder_appointment=True)
    elif status == 'resolved':
        appointments = appointments.filter(folder_appointment=False, folder_appointment_resolved_at__isnull=False)
    appointments = appointments.order_by('folder_appointment_date', 'shop_id__shop_name', 'folder_code')
    paginator = Paginator(appointments, 50)
    page_obj = paginator.get_page(request.GET.get('page'))
    page_query = request.GET.copy()
    page_query.pop('page', None)
    context = get_user_context(request.user)
    context.update({
        'page_obj': page_obj,
        'query': query,
        'status_filter': status,
        'page_query_prefix': f'{page_query.urlencode()}&' if page_query else '',
        'total_count': Folder.objects.filter(folder_appointment_date__isnull=False).count(),
        'active_count': Folder.objects.filter(folder_appointment=True).count(),
        'resolved_count': Folder.objects.filter(
            folder_appointment=False,
            folder_appointment_resolved_at__isnull=False,
        ).count(),
    })
    for folder in page_obj:
        folder.appointment_status_label = _folder_appointment_status_label(folder)
    return render(request, 'app_documents/app_folder_appointment_report_v2.html', context)


@login_required
def folder_appointment_export_view(request):
    if not _is_gddb_admin(request.user):
        return HttpResponse('Chỉ Admin được xuất báo cáo hẹn nhận quyển.', status=403)
    try:
        date_from, date_to, label = _parse_folder_appointment_export_period(request)
    except ValueError as exc:
        messages.error(request, str(exc))
        return redirect('folder_appointment_report_v2')

    appointments = Folder.objects.filter(
        folder_appointment_date__range=(date_from, date_to),
    ).select_related(
        'folder_type_id',
        'shop_id',
        'folder_status_id',
        'folder_appointment_created_by',
        'folder_appointment_resolved_by',
        'lastest_received_by',
    ).order_by('folder_appointment_date', 'shop_id__shop_name', 'folder_code')
    headers = [
        'Mã quyển',
        'Loại quyển',
        'Phòng giao dịch',
        'Ngày quyển',
        'Ngày hẹn nhận',
        'Lý do hẹn',
        'Trạng thái hẹn',
        'Trạng thái quyển',
        'Loại bản',
        'Trạng thái lỗi',
        'Đúng/trễ hạn',
        'Ngày nhận thực tế',
        'Người tạo hẹn',
        'Thời gian tạo hẹn',
        'Người hoàn tất hẹn',
        'Thời gian hoàn tất hẹn',
        'Người nhận quyển',
        'Ghi chú quyển',
    ]
    workbook = Workbook()
    worksheet = workbook.active
    worksheet.title = 'Hen nhan quyen'
    worksheet.append(headers)
    for cell in worksheet[1]:
        cell.font = Font(bold=True, color='FFFFFF')
        cell.fill = PatternFill('solid', fgColor='047857')
        cell.alignment = Alignment(horizontal='center', vertical='center')

    for folder in appointments.iterator():
        timing_status = 'Đúng hạn' if folder.is_on_time else ('Trễ hạn' if folder.is_late else '')
        worksheet.append([
            folder.folder_code,
            folder.folder_type_id.folder_type_name if folder.folder_type_id else '',
            folder.shop_id.shop_name if folder.shop_id else '',
            folder.folder_created_date,
            folder.folder_appointment_date,
            folder.folder_appointment_reason or '',
            _folder_appointment_status_label(folder),
            folder.folder_status_id.folder_status_name if folder.folder_status_id else '',
            'Bản gốc' if folder.is_original else 'Bản bổ sung',
            'Có lỗi' if folder.is_issue else ('Không lỗi' if folder.is_issue is False else ''),
            timing_status,
            folder.lastest_received_date,
            folder.folder_appointment_created_by.username if folder.folder_appointment_created_by else '',
            folder.folder_appointment_created_at,
            folder.folder_appointment_resolved_by.username if folder.folder_appointment_resolved_by else '',
            folder.folder_appointment_resolved_at,
            folder.lastest_received_by.username if folder.lastest_received_by else '',
            folder.note or '',
        ])
    for row in worksheet.iter_rows(min_row=2):
        for column_index in (4, 5):
            row[column_index - 1].number_format = 'dd/mm/yyyy'
        for column_index in (12, 14, 16):
            cell = row[column_index - 1]
            if cell.value and timezone.is_aware(cell.value):
                cell.value = timezone.localtime(cell.value).replace(tzinfo=None)
            cell.number_format = 'dd/mm/yyyy hh:mm'
    for index, header in enumerate(headers, start=1):
        worksheet.column_dimensions[get_column_letter(index)].width = min(max(len(header) + 4, 14), 40)
    worksheet.freeze_panes = 'A2'
    worksheet.auto_filter.ref = worksheet.dimensions

    output = BytesIO()
    workbook.save(output)
    response = HttpResponse(
        output.getvalue(),
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    )
    response['Content-Disposition'] = f'attachment; filename="hen-nhan-quyen-{label}.xlsx"'
    return response


@login_required
def api_receive_folder_update_v2(request):
    user_context = get_user_context(request.user)
    if not user_context['is_admin'] and not user_context['is_checker']:
        return JsonResponse({'error': 'Unauthorized access.'}, status=403)
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)

    try:
        payload = json.loads(request.body.decode() or "{}")
    except json.JSONDecodeError:
        payload = {}

    folder_id = payload.get('folder_id')
    folder_status_id = payload.get('folder_status_id')
    package_code = (payload.get('package_code') or "").strip()
    received_date_raw = (payload.get('received_date') or "").strip()
    redirect_url = payload.get('redirect_url') or request.META.get('HTTP_REFERER') or reverse('receiving_transaction_v2')
    issue_type_ids = _normalize_issue_type_ids(payload.get('issue_type_ids') or [])

    if not folder_id or not folder_status_id:
        return JsonResponse({'error': 'Thiếu thông tin quyển hoặc trạng thái.'}, status=400)
    if not package_code:
        return JsonResponse({'error': 'Vui lòng nhập mã thùng nhận.'}, status=400)

    received_dt = None
    if received_date_raw:
        received_dt = parse_datetime(received_date_raw)
        if received_dt is None:
            for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d"):
                try:
                    received_dt = datetime.strptime(received_date_raw, fmt)
                    break
                except ValueError:
                    continue
    if received_dt is None:
        received_dt = timezone.now()
    if timezone.is_naive(received_dt):
        received_dt = timezone.make_aware(received_dt, timezone.get_current_timezone())

    try:
        with transaction.atomic():
            folder = Folder.objects.select_for_update().get(folder_id=folder_id)
            package = Package.objects.select_related('package_type').get(package_code=package_code)
            folder_status = FolderStatus.objects.get(folder_status_id=folder_status_id)
            issue_types, issue_error = _get_valid_issue_types(issue_type_ids)
            if issue_error:
                return JsonResponse({'error': issue_error}, status=400)

            folder_pkg_type = (folder.folder_type_id.package_type if folder.folder_type_id else None)
            package_pkg_type = (package.package_type.package_type if package.package_type else None)
            if not folder_pkg_type or not package_pkg_type:
                return JsonResponse({'error': 'Thiếu thông tin loại thùng/loại quyển.'}, status=400)
            if str(folder_pkg_type).strip().upper() != str(package_pkg_type).strip().upper():
                return JsonResponse({'error': 'Mã thùng không khớp loại quyển.'}, status=400)

            status_changed = folder.folder_status_id_id != folder_status.folder_status_id

            folder.folder_status_id = folder_status
            folder.lastest_received_date = received_dt
            folder.lastest_received_by = request.user
            folder.package_id = package
            folder.save(update_fields=[
                'folder_status_id',
                'lastest_received_date',
                'lastest_received_by',
                'package_id',
            ])
            if folder_status.is_received:
                _resolve_folder_appointment(
                    folder,
                    request.user,
                    received_dt,
                    source='receive_v2_single',
                )

            check_result = check_on_time(folder, received_dt)

            if status_changed:
                FoldersTransactionReceiving.objects.create(
                    folder_id=folder,
                    trans_updated_date=received_dt,
                    trans_created_by=request.user,
                    folder_status_id=folder_status,
                )

            receive_time = timezone.now()
            PackageFolderHistory.objects.create(
                folder_id=folder,
                package_id=package,
                trans_created_date=receive_time,
                trans_created_by=request.user,
            )

            document_details = DocumentsDetail.objects.select_for_update().filter(folder_id=folder.folder_id)
            for document in document_details:
                if document.package_id_id != package.package_id:
                    document.package_id = package
                    document.save(update_fields=['package_id'])
                PackageDocumentHistory.objects.create(
                    document_id=document,
                    package_id=package,
                    trans_created_date=receive_time,
                    trans_created_by=request.user,
                )
            _replace_folder_issues(folder, issue_types, request.user)

    except Folder.DoesNotExist:
        return JsonResponse({'error': 'Không tìm thấy quyển chứng từ.'}, status=404)
    except Package.DoesNotExist:
        return JsonResponse({'error': 'Mã thùng không tồn tại.'}, status=404)
    except FolderStatus.DoesNotExist:
        return JsonResponse({'error': 'Trạng thái không tồn tại.'}, status=404)
    except Exception as exc:
        return JsonResponse({'error': f'Lỗi xử lý: {exc}'}, status=500)

    message = f"Nhận quyển {folder.folder_code} thành công."
    return JsonResponse({
        'success': True,
        'message': message,
        'status_name': folder_status.folder_status_name,
        'received_date': received_dt.strftime('%Y-%m-%d %H:%M'),
        'user': request.user.username,
        'is_on_time': folder.is_on_time,
        'is_late': folder.is_late,
        'check_message': check_result.get('message', ''),
        'redirect_url': redirect_url,
    })


@login_required
def api_folder_note_v2(request, folder_id):
    user_context = get_user_context(request.user)
    if not user_context['is_admin'] and not user_context['is_checker']:
        return JsonResponse({'error': 'Unauthorized access.'}, status=403)
    if request.method != "POST":
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    folder = get_object_or_404(Folder, pk=folder_id)
    try:
        payload = json.loads(request.body.decode() or "{}")
    except json.JSONDecodeError:
        payload = {}
    note_val = payload.get("note")
    note_clean = note_val.strip() if isinstance(note_val, str) else ""
    folder.note = note_clean or None
    folder.save(update_fields=["note"])
    return JsonResponse({"success": True, "note": folder.note or ""})

@login_required
@require_http_methods(["POST"])
def api_document_note_v2(request, document_id):
    user_context = get_user_context(request.user)
    if not user_context['is_admin'] and not user_context['is_checker']:
        return JsonResponse({'error': 'Unauthorized access.'}, status=403)
    try:
        payload = json.loads(request.body.decode() or "{}")
    except json.JSONDecodeError:
        payload = {}
    note_val = payload.get("note")
    note_clean = note_val.strip() if isinstance(note_val, str) else ""
    document = get_object_or_404(DocumentsDetail, documents_id=document_id)
    document.note = note_clean or None
    document.save(update_fields=["note"])
    return JsonResponse({"success": True, "note": document.note or ""})

# Lịch sử nhận quyển chứng từ
@login_required
def fetch_history_receiving(request, folder_id):
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        history = FoldersTransactionReceiving.objects.filter(folder_id=folder_id).values(
            'trans_created_date',
            'trans_created_by__username',
            'folder_status_id__folder_status_name'
        )
        return JsonResponse(list(history), safe=False)


@login_required
def fetch_history_receiving_v2(request, folder_id):
    user_context = get_user_context(request.user)
    if not user_context['is_admin'] and not user_context['is_checker']:
        return JsonResponse({'error': 'Unauthorized access.'}, status=403)
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        folder_history = FoldersTransactionReceiving.objects.filter(folder_id=folder_id).values(
            'trans_created_date',
            'trans_created_by__username',
            'folder_status_id__folder_status_name'
        )
        package_history = PackageFolderHistory.objects.filter(folder_id=folder_id).values(
            'trans_created_date',
            'trans_created_by__username',
            'package_id__package_code'
        )
        return JsonResponse({
            'folder_history': list(folder_history),
            'package_history': list(package_history),
        })
    return JsonResponse({'error': 'Bad request'}, status=400)

# Nhận nhiều quyển 1 lần Bulk Receive
@login_required
def bulk_receive_folder_view(request):
    try:
        data = json.loads(request.body)
        # From JS
        selected_items = data.get('selectedItems', [])
        selected_folder = [item.removeprefix('checkingitem') for item in selected_items]
        package_choice = data.get('package_choice')
        folder_status_choice = data.get('folder_status_choice')
        folder_note_choice = data.get('folder_note_choice')
        issue_type_ids = _normalize_issue_type_ids(data.get('issue_type_ids') or [])
        require_issue_types = bool(data.get('require_issue_types'))
        lasted_received_date_submit  = data.get('trueLastestReceiveDate')
        if lasted_received_date_submit == '':
            lasted_received_date_submit = timezone.now()
        else:
            lasted_received_date_submit = parse_datetime(lasted_received_date_submit)
        receive_time = timezone.now()
        user = request.user 
        try: 
            if not selected_folder:
                return JsonResponse({'success': False, 'error': 'Vui lòng chọn ít nhất một quyển.'})
            if not package_choice:
                return JsonResponse({'success': False, 'error': 'Vui lòng nhập mã thùng.'})
            if not folder_status_choice:
                return JsonResponse({'success': False, 'error': 'Vui lòng chọn trạng thái nhận.'})
            issue_types = []
            if issue_type_ids:
                issue_types, issue_error = _get_valid_issue_types(issue_type_ids)
                if issue_error:
                    return JsonResponse({'success': False, 'error': issue_error})
            elif require_issue_types:
                return JsonResponse({'success': False, 'error': 'Vui lòng chọn ít nhất 1 trạng thái lỗi.'})

            package_id_instance = Package.objects.select_related('package_type').get(package_code=package_choice)
            folder_status_instance = FolderStatus.objects.get(folder_status_id=folder_status_choice)
            package_type_code = (package_id_instance.package_type.package_type if package_id_instance.package_type else None)
            if not package_type_code:
                return JsonResponse({'success': False, 'error': 'Không xác định được loại thùng của mã thùng.'})

            folders = Folder.objects.select_related('folder_type_id').filter(folder_id__in=selected_folder)
            if folders.count() != len(selected_folder):
                return JsonResponse({'success': False, 'error': 'Có quyển không tồn tại, vui lòng tải lại.'})

            mismatched = []
            for folder in folders:
                folder_pkg_type = folder.folder_type_id.package_type if folder.folder_type_id else None
                if not folder_pkg_type or str(folder_pkg_type).strip().upper() != str(package_type_code).strip().upper():
                    mismatched.append(folder.folder_code)

            if mismatched:
                preview = ', '.join(mismatched[:5])
                suffix = '...' if len(mismatched) > 5 else ''
                return JsonResponse({'success': False, 'error': f'Mã thùng không khớp loại quyển: {preview}{suffix}'})

            with transaction.atomic():
                for folder in folders:
                    # Cập nhật trạng thái quyển chứng từ
                    folder.folder_status_id = folder_status_instance
                    folder.package_id = package_id_instance
                    folder.lastest_received_date = lasted_received_date_submit
                    folder.lastest_received_by = user
                    folder.note = folder_note_choice
                    folder.save()
                    if folder_status_instance.is_received:
                        _resolve_folder_appointment(
                            folder,
                            user,
                            lasted_received_date_submit,
                            source='receive_v2_bulk',
                        )
                    # Gọi hàm `check_on_time` để kiểm tra và cập nhật trạng thái đúng/trễ hạn
                    check_on_time(folder,lasted_received_date_submit)
                    # Tạo log nhận quyển chứng từ
                    FoldersTransactionReceiving.objects.create(
                        folder_id=folder,
                        trans_updated_date=lasted_received_date_submit,
                        trans_created_by=user,
                        folder_status_id=folder.folder_status_id
                    )
                    # Tạo log gán thùng cho quyển chứng từ 
                    PackageFolderHistory.objects.create(
                        folder_id=folder,
                        package_id=folder.package_id,
                        trans_created_date=receive_time,
                        trans_created_by=user)
                    document_details = DocumentsDetail.objects.select_for_update().filter(folder_id = folder.folder_id)
                    for document in document_details:
                        document.package_id = package_id_instance
                        document.save() 
                        # Sau khi gán thùng cho chứng từ thì tạo log gán thùng cho chứng từ
                        PackageDocumentHistory.objects.create(
                            document_id = document,
                            package_id = package_id_instance,
                            trans_created_date=receive_time,
                            trans_created_by=user )
                    if issue_types:
                        _replace_folder_issues(folder, issue_types, user)
                # Không set messages cho JSON response để tránh tràn sang màn hình khác
        except Package.DoesNotExist:
            return JsonResponse({'success': False, 'error': 'Mã thùng không tồn tại.'})
        except FolderStatus.DoesNotExist:
            return JsonResponse({'success': False, 'error': 'Trạng thái nhận không tồn tại.'})
        except IntegrityError:
            messages.error(request, 'sys001-Có lỗi xảy ra khi xử lý dữ liệu. Vui lòng thử lại sau!')
            return JsonResponse({'success': False, 'error': 'sys001-Có lỗi xảy ra khi xử lý dữ liệu. Vui lòng thử lại sau!'})           
        return JsonResponse({'success': True})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})

# Tạo quyển bổ sung 
@login_required
def receiving_additional_view(request, folder_id): 
    folder = get_object_or_404(Folder, pk=folder_id)
    user = request.user
    if request.method == 'POST': 
        if 'form-additional-folder' :
            choice_additional_folder_note = request.POST.get('additional_folder_note_submit') #Ghi chú bổ sung 
            choice_additional_folder_status = request.POST.get('additional_folder_status_submit') # Trạng thái quyển bổ sung 
            choice_additional_package_code = request.POST.get('additional_package_code_submit') # Thùng bổ sung
            folder_code_additional = request.POST.get('filter_choice_folder_code') #Folder.objects.get(folder_id = folder_id).folder_code 
            lasted_received_date_submit  = request.POST.get('filter_True_Lastest_Receive_Date')
            if lasted_received_date_submit == '':
                lasted_received_date_submit = timezone.now()
            else:
                # Nếu cần xử lý chuỗi thành datetime, hãy thực hiện tại đây
                lasted_received_date_submit = parse_datetime(lasted_received_date_submit)
            # Hàm tạo quyển bổ sung bằng cách đếm xem có bao nhiêu quyển bổ sung đã được tạo ra từ quyển gốc
            count_folder_additional = Folder.objects.filter(folder_code__contains = folder_code_additional).count()
            # Tạo kí tự quyển bổ sung. 
            folder_code_additional = folder_code_additional + f'-{count_folder_additional}'
            # Tạo dictionary chứa thông tin lọc từ dữ liệu POST
            filter_params = {
                'choice_shop': request.POST.get('filter_choice_shop', ''),
            }
            redirect_name = request.POST.get('redirect_name', 'receiving_transaction')
            if not choice_additional_package_code or not choice_additional_folder_status:
                messages.error(request, 'Vui lòng chọn thùng và trạng thái cho quyển bổ sung.')
                return HttpResponseRedirect(request.META.get('HTTP_REFERER'))
            
            # Nếu thùng không tồn tại thì thông báo lỗi 
            if not Package.objects.filter(package_code=choice_additional_package_code).exists() :
                messages.error(request, 'Thùng không tồn tại. Vui lòng tạo 1 thùng mới.')
                return HttpResponseRedirect(request.META.get('HTTP_REFERER'))
                
            if not FolderStatus.objects.filter(folder_status_id=choice_additional_folder_status).exists():
                messages.error(request, 'Trạng thái không tồn tại. Vui lòng chọn trạng thái khác.')
                return HttpResponseRedirect(request.META.get('HTTP_REFERER'))   

            try : 
                created_date = timezone.now()   
                folder_status_id_found = FolderStatus.objects.get(folder_status_id=choice_additional_folder_status)
                package_id_found = Package.objects.get(package_code=choice_additional_package_code)        
                # Try to create a new CheckingAdditional instance
                folder_aditional_instance = Folder.objects.create(
                    folder_code=folder_code_additional,
                    shop_id=folder.shop_id,
                    folder_type_id=folder.folder_type_id,
                    folder_status_id=folder_status_id_found,
                    manager_id=folder.manager_id,
                    folder_created_date=folder.folder_created_date,
                    note = choice_additional_folder_note if choice_additional_folder_note else None,
                    package_id=package_id_found,
                    lastest_received_date = lasted_received_date_submit,
                    lastest_received_by = user,
                    is_original=False,
                    is_issue=folder.is_issue,
                )
                message_of_success_additional = f'Tạo quyển bổ sung thành công. Quyển bổ sung có mã quyển: {folder_code_additional}' 
                
                FoldersTransactionReceiving.objects.create(
                    folder_id = folder_aditional_instance , 
                    trans_updated_date = lasted_received_date_submit, 
                    trans_created_by = user,
                    folder_status_id = folder_status_id_found
                )
                PackageFolderHistory.objects.create(
                    folder_id = folder_aditional_instance,
                    package_id = package_id_found,
                    trans_created_date = created_date,
                    trans_created_by = user)
                
                messages.success(request, message_of_success_additional)  
                redirect_url = f"{reverse(redirect_name)}?{urlencode(filter_params)}"
                return HttpResponseRedirect(redirect_url)  
            except IntegrityError:
                # Redirect về trang trước đó
                return HttpResponseRedirect(request.META.get('HTTP_REFERER'))   # Redirect to the desired URL after handling the form submission
    return redirect('receiving_transaction')  # Redirect if it's not a POST request or if something goes wrong

#------------------- PACKAGE -------------------------------
# Export to excel packages function 
def export_packages_view(queryset):
    # Tạo file Excel mới
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Packages"
    # Tạo tiêu đề cho các cột
    columns = ['STT', 'id' ,'Mã thùng F88', 'Mã thùng F88 Cũ', 'Mã thùng Đối tác', 'Đối tác','Người tạo', 'Ngày tạo', 'Loại thùng', 'Trạng thái thùng', 'Khu vực' ]
    ws.append(columns)
    # Thêm dữ liệu vào file Excel
    for index, package in enumerate(queryset, start=1):
        partner_package = getattr(package, 'partnerpackage', None)
        ws.append([
            index,
            package.package_id,
            package.package_code,
            package.package_code_old or '',
            partner_package.partner_package_code if partner_package else '',
            partner_package.partner_name if partner_package else '',
            package.created_by.username, 
            package.created_date.strftime('%Y-%m-%d') if package.created_date else '',
            package.package_type.folder_type_name if package.package_type else '',
            partner_package.status_id.package_status_name if partner_package and partner_package.status_id else '',
            package.region_id.region_name if package.region_id else ''
        ])
    # Tạo response để gửi file Excel về cho client
    response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Content-Disposition'] = f'attachment; filename=Packages_{timezone.now().strftime("%Y%m%d_%H%M%S")}.xlsx'
    
    wb.save(response)
    return response
# Package management 
@login_required
def package_management_view(request):
    user = request.user 
    user_context = get_user_context(user)
    if not user_context['is_admin'] and not user_context['is_checker']:
        messages.error(request, "Unauthorized access.")
        return redirect('home')
    package_list = Package.objects.none()
    if request.method == 'GET':
        filters = {}
        choice_package = request.GET.get('choice_package')
        choice_partner_package = request.GET.get('choice_partner_package')
        choice_package_old = request.GET.get('choice_package_old')
        filterpackagestatus = request.GET.get('filterpackagestatus')
        filterregion = request.GET.get('filterregion')  
        choice_user_tao_thung = request.GET.get('choice_user_tao_thung')
        filter_empty_package = request.GET.get('filter_empty_package')
        
        if choice_package:
            filters['package_code__iexact'] = choice_package
        if choice_partner_package:
            filters['partnerpackage__partner_package_code__iexact'] = choice_partner_package
        if choice_package_old:
            filters['package_code_old__icontains'] = choice_package_old    
        if filterpackagestatus:
            filters['partnerpackage__status_id'] = filterpackagestatus
        if choice_user_tao_thung: 
            filters['created_by__username'] = choice_user_tao_thung.lower()
        if filterregion:
            filters['created_by__userprofile__region__region_id'] = filterregion
        if filter_empty_package == '1':
            filters['folder__isnull'] = True
        
        base_queryset = Package.objects.select_related('partnerpackage', 'package_type', 'region_id').annotate(folder_count=Count('folder', distinct=True)).order_by('-created_date')
        if len(filters)   == 0:
            package_list = base_queryset
        else : 
            package_list = base_queryset.filter(**filters)

        # Check if export to Excel is requested
        if request.GET.get('export') == '1':
            return export_packages_view(package_list)

        paginator = Paginator(package_list, 50)  # Show 50 documents per page
        page_number = request.GET.get('page')
        package_list = paginator.get_page(page_number)
        # filter_params = {
        #     'choice_package' :  request.GET.get('choice_package'),
        #     'choice_partner_package' : request.GET.get('choice_partner_package') ,
        #     'choice_package_old' : request.GET.get('choice_package_old'),
        #     'filterpackagestatus' : request.GET.get('filterpackagestatus'),
        #     'filterregion' : request.GET.get('filterregion')  ,
        #     'choice_user_tao_thung' : request.GET.get('choice_user_tao_thung'),
        # }
    user_by_role = AccessControls.get_users_based_on_role(user)
    region_by_role = AccessControls.get_regions_based_on_role(user)
    partnerpackage_status = PartnerPackageStatus.objects.all()
    partnerpackage_list = PartnerPackage.objects.all()
    partners = Partner.objects.filter(is_active=True).order_by('partner_name')
    partners_require_selection = partners.filter(require_partner_selection=True).exists()
    droplist_users =  user_by_role #User.objects.filter()
    droplist_regions = region_by_role ##Region.objects.filter()
    query_string = '&'.join(f"{key}={value}" for key, value in request.GET.items() if key != 'page')
    context = {
        **user_context,
        'package_list': package_list,
        'user': user,
        'partnerpackage_status': partnerpackage_status,
        'partnerpackage_list': partnerpackage_list,
        'droplist_users': droplist_users,
        'droplist_regions': droplist_regions,
        'partners': partners,
        'partners_require_selection': partners_require_selection,
     }
    context['query_string'] = query_string
    return render(request, 'app_documents/app_package_management.html', context )

@login_required
def package_list_management_view(request):
    user = request.user
    user_context = get_user_context(user)
    if not user_context['is_admin'] and not user_context['is_checker']:
        messages.error(request, "Unauthorized access.")
        return redirect('home')

    search_term = request.GET.get('package_search', '').strip()
    status_filter = request.GET.get('status_id', '').strip()
    created_from = request.GET.get('created_from', '').strip()
    created_to = request.GET.get('created_to', '').strip()

    def _parse_input_date(val):
        if not val:
            return None
        try:
            return datetime.strptime(val, "%d/%m/%Y").date()
        except ValueError:
            return dateparse.parse_date(val)

    filters = Q()
    if search_term:
        filters &= (
            Q(package_code__icontains=search_term) |
            Q(package_code_old__icontains=search_term) |
            Q(partnerpackage__partner_package_code__icontains=search_term)
        )
    if status_filter:
        filters &= Q(partnerpackage__status_id=status_filter)
    start_date = _parse_input_date(created_from)
    end_date = _parse_input_date(created_to)
    if start_date:
        filters &= Q(created_date__date__gte=start_date)
    if end_date:
        filters &= Q(created_date__date__lte=end_date)

    base_queryset = Package.objects.select_related('partnerpackage', 'package_type', 'region_id').annotate(
        folder_count=Count('folder', distinct=True),
        shop_count=Count('folder__shop_id', distinct=True)
    ).order_by('-created_date')

    has_filters = bool(filters.children)
    filtered_queryset = base_queryset.filter(filters) if has_filters else base_queryset

    packages_queryset = filtered_queryset

    default_in_status = PartnerPackageStatus.objects.filter(is_in_warehouse=True).first()

    def build_status_payload(status_obj):
        if status_obj:
            color = status_obj.badge_color
            if not color:
                if status_obj.is_released:
                    color = '#DC2626'
                elif status_obj.is_backed:
                    color = '#D97706'
                elif status_obj.is_in_warehouse:
                    color = '#047857'
                else:
                    color = '#E5E7EB'
            return {
                'id': status_obj.status_id,
                'name': status_obj.package_status_name,
                'color': color,
                'isReleased': status_obj.is_released,
                'isBacked': status_obj.is_backed,
                'isInWarehouse': status_obj.is_in_warehouse,
            }
        if default_in_status:
            return {
                'id': default_in_status.status_id,
                'name': default_in_status.package_status_name,
                'color': default_in_status.badge_color or '#047857',
                'isReleased': default_in_status.is_released,
                'isBacked': default_in_status.is_backed,
                'isInWarehouse': default_in_status.is_in_warehouse,
            }
        return {
            'id': None,
            'name': 'Trong kho',
            'color': '#047857',
            'isReleased': False,
            'isBacked': False,
            'isInWarehouse': True,
        }

    packages_data = []
    for package in packages_queryset:
        partner_package = getattr(package, 'partnerpackage', None)
        status = partner_package.status_id if partner_package else None
        status_payload = build_status_payload(status)
        region_name = package.region_id.region_name if package.region_id else 'Chưa cập nhật'
        package_type = package.package_type.folder_type_name if package.package_type else 'Loại thùng'
        partner_name_display = ''
        if partner_package:
            partner_name_display = partner_package.partner.partner_name if partner_package.partner else partner_package.partner_name or ''
        partner_color = ''
        if partner_package and partner_package.partner and partner_package.partner.badge_color:
            partner_color = partner_package.partner.badge_color
        package_type_color = package.package_type.badge_color if package.package_type and package.package_type.badge_color else ''

        packages_data.append({
            'id': package.package_id,
            'packageCode': package.package_code,
            'packageCodeOld': package.package_code_old or '',
            'partnerPackageCode': partner_package.partner_package_code if partner_package else '',
            'partnerName': partner_name_display,
            'partnerId': partner_package.partner.partner_id if partner_package and partner_package.partner else None,
            'partnerColor': partner_color,
            'createdDate': package.created_date.strftime('%Y-%m-%d') if package.created_date else '',
            'status': status_payload,
            'packageType': package_type,
            'packageTypeColor': package_type_color,
            'regionName': region_name,
            'folderCount': getattr(package, 'folder_count', 0),
            'shopCount': getattr(package, 'shop_count', 0),
            'note': package.note or '',
            'createdBy': package.created_by.get_full_name() or package.created_by.username if package.created_by else '',
        })

    statuses = PartnerPackageStatus.objects.all().order_by('package_status_name')
    status_options_json = json.dumps(
        list(statuses.values('status_id', 'package_status_name', 'badge_color')),
        cls=DjangoJSONEncoder,
        ensure_ascii=False,
    )
    package_types = FolderType.objects.filter(is_valid=True).order_by('package_type', 'folder_type_name')
    partners_active = Partner.objects.filter(is_active=True).order_by('partner_name')
    partners_options_json = json.dumps(
        list(partners_active.values('partner_id', 'partner_name', 'partner_code', 'require_partner_selection', 'require_partner_code')),
        cls=DjangoJSONEncoder,
        ensure_ascii=False,
    )
    region_options_json = json.dumps(
        list(Region.objects.values('region_code', 'region_name')),
        cls=DjangoJSONEncoder,
        ensure_ascii=False,
    )
    folder_type_options_json = json.dumps(
        list(package_types.values('folder_type_code', 'folder_type_name', 'package_type')),
        cls=DjangoJSONEncoder,
        ensure_ascii=False,
    )

    context = {
        **user_context,
        'packages_json': json.dumps(packages_data, cls=DjangoJSONEncoder, ensure_ascii=False),
        'filters_json': json.dumps({
            'package_search': search_term,
            'status_id': status_filter,
            'created_from': created_from,
            'created_to': created_to,
        }, cls=DjangoJSONEncoder, ensure_ascii=False),
        'status_options_json': status_options_json,
        'package_types': package_types,
        'partners_active': partners_active,
        'partners_options_json': partners_options_json,
        'region_options_json': region_options_json,
        'folder_type_options_json': folder_type_options_json,
    }
    return render(request, 'app_documents/app_package_list_v2.html', context)


@login_required
def export_package_list_v2(request):
    user = request.user
    user_context = get_user_context(user)
    if not user_context['is_admin'] and not user_context['is_checker']:
        messages.error(request, "Unauthorized access.")
        return redirect('home')

    search_term = request.GET.get('package_search', '').strip()
    status_filter = request.GET.get('status_id', '').strip()
    created_from = request.GET.get('created_from', '').strip()
    created_to = request.GET.get('created_to', '').strip()

    def _parse_input_date(val):
        if not val:
            return None
        try:
            return datetime.strptime(val, "%d/%m/%Y").date()
        except ValueError:
            return dateparse.parse_date(val)

    filters = Q()
    if search_term:
        filters &= (
            Q(package_code__icontains=search_term) |
            Q(package_code_old__icontains=search_term) |
            Q(partnerpackage__partner_package_code__icontains=search_term)
        )
    if status_filter:
        filters &= Q(partnerpackage__status_id=status_filter)
    start_date = _parse_input_date(created_from)
    end_date = _parse_input_date(created_to)
    if start_date:
        filters &= Q(created_date__date__gte=start_date)
    if end_date:
        filters &= Q(created_date__date__lte=end_date)

    queryset = Package.objects.select_related(
        'partnerpackage',
        'partnerpackage__partner',
        'partnerpackage__status_id',
        'package_type',
        'region_id',
        'created_by',
    ).order_by('-created_date')

    if filters.children:
        queryset = queryset.filter(filters)

    return export_packages_view(queryset)


@login_required
def api_package_partner(request, package_id):
    user_context = get_user_context(request.user)
    if not user_context['is_admin'] and not user_context['is_checker']:
        return JsonResponse({'error': 'Unauthorized access.'}, status=403)
    if request.method != "POST":
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    try:
        payload = json.loads(request.body.decode() or "{}")
    except json.JSONDecodeError:
        payload = {}
    partner_id = payload.get("partner_id")
    partner_package_code_submit = (payload.get("partner_package_code") or "").strip()
    status_id_submit = payload.get("status_id")
    pkg = get_object_or_404(Package, pk=package_id)
    partner_obj = None
    if partner_id:
        partner_obj = Partner.objects.filter(pk=partner_id).first()
        if not partner_obj:
            return JsonResponse({'error': 'Partner not found.'}, status=400)
        if partner_obj.require_partner_code and not partner_package_code_submit:
            return JsonResponse({'error': f'Đối tác {partner_obj.partner_name} yêu cầu nhập mã thùng đối tác.'}, status=400)

    partner_package_code_value = partner_package_code_submit or None
    if partner_package_code_value and PartnerPackage.objects.exclude(package_id=pkg).filter(partner_package_code=partner_package_code_value).exists():
        return JsonResponse({'error': f'Mã thùng đối tác {partner_package_code_value} đã tồn tại.'}, status=400)

    status_obj = None
    if status_id_submit:
        status_obj = PartnerPackageStatus.objects.filter(pk=status_id_submit).first()
        if not status_obj:
            return JsonResponse({'error': 'Trạng thái không hợp lệ.'}, status=400)

    default_in_status = PartnerPackageStatus.objects.filter(is_in_warehouse=True).first()

    def build_status_payload(status_obj):
        if status_obj:
            color = status_obj.badge_color
            if not color:
                if status_obj.is_released:
                    color = '#DC2626'
                elif status_obj.is_backed:
                    color = '#D97706'
                elif status_obj.is_in_warehouse:
                    color = '#047857'
                else:
                    color = '#E5E7EB'
            return {
                'id': status_obj.status_id,
                'name': status_obj.package_status_name,
                'color': color,
                'isReleased': status_obj.is_released,
                'isBacked': status_obj.is_backed,
                'isInWarehouse': status_obj.is_in_warehouse,
            }
        if default_in_status:
            return {
                'id': default_in_status.status_id,
                'name': default_in_status.package_status_name,
                'color': default_in_status.badge_color or '#047857',
                'isReleased': default_in_status.is_released,
                'isBacked': default_in_status.is_backed,
                'isInWarehouse': default_in_status.is_in_warehouse,
            }
        return {
            'id': None,
            'name': 'Trong kho',
            'color': '#047857',
            'isReleased': False,
            'isBacked': False,
            'isInWarehouse': True,
        }

    partner_pkg, _ = PartnerPackage.objects.get_or_create(
        package_id=pkg,
        defaults={
            "created_date": timezone.now(),
            "created_by": request.user,
        },
    )
    old_partner = partner_pkg.partner
    old_partner_name = partner_pkg.partner_name
    old_code = partner_pkg.partner_package_code
    old_status = partner_pkg.status_id

    # Chặn cập nhật mã đối tác nếu đã release
    if old_status and old_status.is_released:
        if partner_package_code_value and partner_package_code_value != old_code:
            return JsonResponse({'error': 'Thùng đã ở trạng thái released, không được cập nhật mã thùng đối tác.'}, status=400)

    # Kiểm tra quyền đổi trạng thái nếu đã release/backed
    if status_obj and old_status and (old_status.is_released or old_status.is_backed) and not user_context['is_admin']:
        if old_status.status_id != status_obj.status_id:
            return JsonResponse({'error': 'Chỉ Admin được đổi trạng thái khi thùng đã ở trạng thái released/backed.'}, status=403)

    # Kiểm tra flow trạng thái hợp lệ
    def allow_transition(current, new):
        if not new:
            return True
        if not current or current.is_in_warehouse:
            return new.is_released or new.is_in_warehouse
        if current.is_released:
            return new.is_released or new.is_backed
        if current.is_backed:
            return new.is_backed or new.is_released
        return True

    if status_obj and not allow_transition(old_status, status_obj):
        return JsonResponse({'error': 'Không hợp lệ: chỉ cho phép luồng in_warehouse -> released -> backed -> released.'}, status=400)

    partner_pkg.partner = partner_obj
    partner_pkg.partner_name = partner_obj.partner_name if partner_obj else None
    partner_pkg.partner_package_code = partner_package_code_value
    if status_obj:
        partner_pkg.status_id = status_obj
    elif not partner_pkg.status_id and default_in_status:
        partner_pkg.status_id = default_in_status
    if not partner_pkg.created_date:
        partner_pkg.created_date = timezone.now()
    partner_pkg.updated_date = timezone.now()
    partner_pkg.save()

    def log_history(action, old_val, new_val):
        if (old_val or '') == (new_val or ''):
            return None
        return PartnerPackageHistory.objects.create(
            package=pkg,
            action=action,
            old_value=old_val or '',
            new_value=new_val or '',
            created_by=request.user,
        )

    log_history('partner_change', old_partner_name or getattr(old_partner, 'partner_name', None), partner_pkg.partner_name)
    log_history('partner_code_change', old_code, partner_pkg.partner_package_code)
    log_history('status_change', old_status.package_status_name if old_status else None, partner_pkg.status_id.package_status_name if partner_pkg.status_id else None)

    current_status = partner_pkg.status_id
    status_payload = build_status_payload(current_status)

    history_qs = PartnerPackageHistory.objects.filter(package=pkg).select_related('created_by').order_by('-created_at')[:20]
    history_payload = []
    for h in history_qs:
        history_payload.append({
            'action': h.action,
            'oldValue': h.old_value or '',
            'newValue': h.new_value or '',
            'user': h.created_by.get_full_name() or h.created_by.username if h.created_by else '',
            'date': h.created_at.strftime('%Y-%m-%d %H:%M'),
        })

    return JsonResponse({
        'status': 'ok',
        'partner_id': partner_obj.partner_id if partner_obj else None,
        'partner_name': partner_obj.partner_name if partner_obj else '',
        'partner_package_code': partner_pkg.partner_package_code or '',
        'status_obj': status_payload,
        'history': history_payload,
    })


@login_required
def api_package_note(request, package_id):
    user_context = get_user_context(request.user)
    if not user_context['is_admin'] and not user_context['is_checker']:
        return JsonResponse({'error': 'Unauthorized access.'}, status=403)
    if request.method != "POST":
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    pkg = get_object_or_404(Package, pk=package_id)
    try:
        payload = json.loads(request.body.decode() or "{}")
    except json.JSONDecodeError:
        payload = {}
    note_val = payload.get("note")
    note_clean = note_val.strip() if isinstance(note_val, str) else ""
    pkg.note = note_clean or None
    pkg.updated_date = timezone.now()
    pkg.save(update_fields=["note", "updated_date"])
    return JsonResponse({"success": True, "note": pkg.note or ""})


@login_required
def package_list_detail_view(request, package_id):
    user = request.user
    user_context = get_user_context(user)
    if not user_context['is_admin'] and not user_context['is_checker']:
        return JsonResponse({'error': 'Unauthorized access.'}, status=403)

    package = get_object_or_404(
        Package.objects.select_related('partnerpackage', 'package_type', 'region_id'),
        pk=package_id
    )

    documents_prefetch = Prefetch(
        'documentsdetail_set',
        queryset=DocumentsDetail.objects.select_related('document_status_id', 'document_type_id', 'loan_id', 'contract_id').order_by('documents_created_date')
    )
    folders_prefetch = Prefetch(
        'folder_set',
        queryset=Folder.objects.select_related('shop_id', 'folder_type_id', 'folder_status_id').prefetch_related(documents_prefetch).order_by('shop_id__shop_name', 'folder_created_date')
    )
    package = Package.objects.select_related('partnerpackage', 'package_type', 'region_id').prefetch_related(folders_prefetch).get(pk=package_id)

    partner_package = getattr(package, 'partnerpackage', None)
    status = partner_package.status_id if partner_package else None
    default_in_status = PartnerPackageStatus.objects.filter(is_in_warehouse=True).first()

    def build_status_payload(status_obj):
        if status_obj:
            color = status_obj.badge_color
            if not color:
                if status_obj.is_released:
                    color = '#DC2626'
                elif status_obj.is_backed:
                    color = '#D97706'
                elif status_obj.is_in_warehouse:
                    color = '#047857'
                else:
                    color = '#E5E7EB'
            return {
                'name': status_obj.package_status_name,
                'color': color,
                'id': status_obj.status_id,
                'isReleased': status_obj.is_released,
                'isBacked': status_obj.is_backed,
                'isInWarehouse': status_obj.is_in_warehouse,
            }
        if default_in_status:
            return {
                'name': default_in_status.package_status_name,
                'color': default_in_status.badge_color or '#047857',
                'id': default_in_status.status_id,
                'isReleased': default_in_status.is_released,
                'isBacked': default_in_status.is_backed,
                'isInWarehouse': default_in_status.is_in_warehouse,
            }
        return {
            'name': 'Trong kho',
            'color': '#047857',
            'id': None,
            'isReleased': False,
            'isBacked': False,
            'isInWarehouse': True,
        }
    status_payload = build_status_payload(status)
    region_name = package.region_id.region_name if package.region_id else 'Chưa cập nhật'
    package_type = package.package_type.folder_type_name if package.package_type else 'Loại thùng'
    partner_name_display = ''
    if partner_package:
        partner_name_display = partner_package.partner.partner_name if partner_package.partner else partner_package.partner_name or ''
    partner_color = ''
    if partner_package and partner_package.partner and partner_package.partner.badge_color:
        partner_color = partner_package.partner.badge_color
    package_type_color = package.package_type.badge_color if package.package_type and package.package_type.badge_color else ''
    created_by_name = package.created_by.get_full_name() or package.created_by.username if package.created_by else ''

    shop_groups = {}
    for folder in getattr(package, 'folder_set', []).all():
        shop = folder.shop_id
        shop_name = shop.shop_name if shop else 'PGD chưa rõ'
        shop_code = shop.shop_code if shop else ''
        key = f"{shop_name}-{shop_code}"
        if key not in shop_groups:
            shop_groups[key] = {
                'shopName': shop_name,
                'shopCode': shop_code,
                'count': 0,
                'folders': []
            }
        shop_groups[key]['count'] += 1
        documents_iterable = folder.documentsdetail_set.select_related('document_status_id', 'document_type_id', 'loan_id', 'contract_id').all()
        docs_payload = []
        for doc in documents_iterable:
            doc_type = doc.document_type_id.document_type_name if doc.document_type_id else ''
            doc_status = doc.document_status_id.documents_status_name if doc.document_status_id else '---'
            contract_code = doc.contract_id.contract_code if doc.contract_id else ''
            loan_code = doc.loan_id.loan_code if doc.loan_id else ''
            docs_payload.append({
                'code': doc.documents_code,
                'type': doc_type,
                'createdDate': doc.documents_created_date.strftime('%Y-%m-%d') if doc.documents_created_date else '',
                'status': doc_status,
                'refCode': contract_code or loan_code or '',
            })

        shop_groups[key]['folders'].append({
            'folderCode': folder.folder_code,
            'typeLabel': 'Gốc' if folder.is_original else 'Bổ sung',
            'createdDate': folder.folder_created_date.strftime('%Y-%m-%d') if folder.folder_created_date else '',
            'folderStatus': folder.folder_status_id.folder_status_name if getattr(folder, 'folder_status_id', None) else '---',
            'documents': docs_payload,
        })

    detail_payload = {
        'id': package.package_id,
        'packageCode': package.package_code,
        'packageCodeOld': package.package_code_old or '',
        'partnerPackageCode': partner_package.partner_package_code if partner_package else '',
        'partnerName': partner_name_display,
        'partnerId': partner_package.partner.partner_id if partner_package and partner_package.partner else None,
        'partnerColor': partner_color,
        'createdDate': package.created_date.strftime('%Y-%m-%d') if package.created_date else '',
        'createdBy': created_by_name,
        'status': status_payload,
        'packageType': package_type,
        'packageTypeColor': package_type_color,
        'regionName': region_name,
        'folderCount': getattr(package, 'folder_set', []).count(),
        'shopCount': len(shop_groups.keys()),
        'foldersByShop': list(shop_groups.values()),
        'note': package.note or '',
        'history': [],
    }
    history_qs = PartnerPackageHistory.objects.filter(package=package).select_related('created_by').order_by('-created_at')[:20]
    detail_payload['history'] = [
        {
            'action': h.action,
            'oldValue': h.old_value or '',
            'newValue': h.new_value or '',
            'user': h.created_by.get_full_name() or h.created_by.username if h.created_by else '',
            'date': h.created_at.strftime('%Y-%m-%d %H:%M'),
        }
        for h in history_qs
    ]
    return JsonResponse(detail_payload, safe=False)

# Package management edit view
@login_required
def edit_package_view(request, package_id):
    user = request.user
    user_context = get_user_context(user)
    if not user_context['is_admin'] and not user_context['is_checker']:
        return JsonResponse({'error': 'Unauthorized access.'}, status=403)
    package = get_object_or_404(Package, pk=package_id)
    partners_qs = Partner.objects.filter(is_active=True)
    partners_require_selection = partners_qs.filter(require_partner_selection=True).exists()
    if request.method == 'POST':
        partner_package_code_submit = request.POST.get('partner_code_choice', '').strip()
        partner_id_choice = request.POST.get('partner_id_choice')
        old_package_code_choice = request.POST.get('old_package_code_choice')
        date_action = timezone.now()

        partner_instance = None
        if partner_id_choice:
            partner_instance = partners_qs.filter(partner_id=partner_id_choice).first()
            if not partner_instance:
                return JsonResponse({'error': 'Đối tác không tồn tại hoặc đã bị vô hiệu.'}, status=400)
        elif partners_require_selection and partners_qs.exists():
            return JsonResponse({'error': 'Vui lòng chọn đối tác lưu trữ.'}, status=400)
        if partner_instance and partner_instance.require_partner_code and not partner_package_code_submit:
            return JsonResponse({'error': f'Đối tác {partner_instance.partner_name} yêu cầu nhập mã thùng đối tác.'}, status=400)
        if partner_package_code_submit and PartnerPackage.objects.exclude(package_id=package).filter(partner_package_code=partner_package_code_submit).exists():
            return JsonResponse({'error': f'Mã thùng đối tác {partner_package_code_submit} đã tồn tại.'}, status=400)
        
        partner_package_code_value = partner_package_code_submit or None
        try:
            partner_package = PartnerPackage.objects.get(package_id=package)
        except PartnerPackage.DoesNotExist:
            partner_package = None

        if partner_instance:
            if partner_package:
                has_changes = (
                    partner_package.partner_package_code != partner_package_code_value or
                    partner_package.partner_id != (partner_instance.partner_id if partner_instance else None)
                )
                if has_changes:
                    partner_package.partner_package_code = partner_package_code_value
                    partner_package.partner_name = partner_instance.partner_code
                    partner_package.partner = partner_instance
                    partner_package.updated_date = date_action
                    partner_package.save()
                else:
                    return JsonResponse({'message': 'No changes detected.'})
            else:
                default_status = PartnerPackageStatus.objects.get(status_id=1)
                PartnerPackage.objects.create(
                    package_id=package,
                    partner_package_code=partner_package_code_value,
                    partner_name=partner_instance.partner_code,
                    partner=partner_instance,
                    created_date=date_action,
                    created_by=user,
                    status_id=default_status
                )
        else:
            # No partner selected, remove existing relation if exists
            if partner_package:
                partner_package.delete()
        
        if old_package_code_choice and old_package_code_choice != package.package_code_old:
            package.package_code_old = old_package_code_choice
            package.updated_date = date_action
            package.save()
        
        return JsonResponse({'message': f'Package {package.package_code} updated successfully.', 'package_id': package.package_id})
    return JsonResponse({'error': 'Invalid request method.'}, status=405)

# Function điều kiện validate định dạng mã thùng
def validate_package_code(value, user):
    package_pattern = r'^(CIMB|NH|VH)-(\d{6})-([A-Za-z0-9]{1})(\d{2})$'
    match = re.match(package_pattern, value)
    profile = UserProfile.objects.get(user=user)
    region_code_user = (profile.region.region_code or "").upper()
    if not match:
        return {
            'is_valid': False,
            'error': "Tên thùng phải tuân thủ định dạng '{FOLDER_TYPE}-{yyMMdd}-{region_code}{bb}' (ví dụ: VH-241001-M01)."
        }
    prefix_part, date_part, region_part, sequence_part = match.groups()
    if not (1 <= int(sequence_part) <= 99):
        return {'is_valid': False, 'error': "Số thứ tự bb phải từ 01-99."}
    if prefix_part.upper() not in ['CIMB', 'NH', 'VH']:
        return {'is_valid': False, 'error': "FOLDER_TYPE phải là CIMB/NH/VH."}
    if region_code_user and region_part.upper() != region_code_user[:1]:
        return {'is_valid': False, 'error': f"Bạn là vùng {region_code_user}, vui lòng dùng mã vùng {region_code_user[:1]} trong package_code."}
    existing_codes = Package.objects.filter(package_code__startswith=f'{prefix_part}-{date_part}-{region_part}')
    if existing_codes.exists():
        last_sequence = max(int(code.package_code.split('-')[-1][1:]) for code in existing_codes)
        if int(sequence_part) <= last_sequence:
            return {'is_valid': False, 'error': "Thùng với số thứ tự này đã tồn tại. Vui lòng tạo số thứ tự cao hơn."}
    if Package.objects.filter(package_code=value).exists():
        return {'is_valid': False, 'error': "Thùng đã tồn tại trong hệ thống. Vui lòng nhập lại."}
    return {'is_valid': True}


def validate_package_code_v2(value, selected_region_code=None):
    """
    Cú pháp mới: {FolderType}-{yymmdd}-{a}{bb}
    FolderType: lấy theo package_type của FolderType (VD: VH/NH/CIMB, mở rộng được).
    yymmdd: ngày tạo thùng.
    a: mã vùng/kho người dùng chọn.
    bb: số thứ tự 2 chữ số, không trùng, max 99.
    """
    code = (value or "").strip().upper()
    pattern = r'^([A-Z0-9]{2,10})-(\d{6})-([A-Z0-9]{1})(\d{2})$'
    match = re.match(pattern, code)
    if not match:
        return {'is_valid': False, 'error': "Mã thùng phải theo định dạng {FolderType}-yymmdd-aBB (ví dụ: VH-241231-M01)."}

    folder_type_part, date_part, region_part, seq_part = match.groups()

    folder_type_obj = FolderType.objects.filter(package_type__iexact=folder_type_part, is_valid=True).first()
    if not folder_type_obj:
        return {'is_valid': False, 'error': "Loại thùng không hợp lệ. Vui lòng chọn loại trong danh sách."}

    try:
        created_date = datetime.strptime(date_part, "%y%m%d").date()
    except ValueError:
        return {'is_valid': False, 'error': "Ngày trong mã thùng không hợp lệ (yymmdd)."}

    try:
        seq_int = int(seq_part)
    except ValueError:
        return {'is_valid': False, 'error': "Số thứ tự BB phải là số."}
    if not (1 <= seq_int <= 99):
        return {'is_valid': False, 'error': "Số thứ tự BB phải từ 01-99."}

    region_char = region_part.upper()
    if selected_region_code:
        selected_region_char = selected_region_code.strip().upper()[:1]
        if region_char != selected_region_char:
            return {'is_valid': False, 'error': f"Mã kho (a) phải khớp vùng đang chọn: {selected_region_char}."}

    prefix = f"{folder_type_part.upper()}-{date_part}-{region_char}"
    existing_qs = Package.objects.filter(package_code__istartswith=prefix)
    if existing_qs.filter(package_code__iexact=code).exists():
        return {'is_valid': False, 'error': "Mã thùng đã tồn tại."}

    max_seq = 0
    for pkg in existing_qs:
        tail = pkg.package_code.rsplit('-', 1)[-1]
        if not tail:
            continue
        tail_region = tail[:1].upper()
        tail_seq = tail[1:]
        if tail_region != region_char:
            continue
        try:
            tail_seq_int = int(tail_seq)
            if tail_seq_int > max_seq:
                max_seq = tail_seq_int
        except ValueError:
            continue

    next_suggested = max_seq + 1 if max_seq < 99 else None
    if seq_int <= max_seq:
        msg = f"Số thứ tự đã dùng đến {max_seq:02d} cho {prefix}."
        if next_suggested and next_suggested <= 99:
            msg += f" Gợi ý: dùng {next_suggested:02d}."
        return {'is_valid': False, 'error': msg, 'next_suggested_sequence': next_suggested}

    return {
        'is_valid': True,
        'normalized_code': code,
        'folder_type': folder_type_obj,
        'created_date': created_date,
        'region_part': region_char,
        'next_suggested_sequence': next_suggested,
    }

# View cho phép tạo thùng mới
@login_required
def create_package_view(request, user_id):
    user= User.objects.get(pk=user_id)
    user_context = get_user_context(request.user)
    user_profiles = UserProfile.objects.get(user=user)
    package_type = FolderType.objects.filter(is_valid=True)
    regions = Region.objects.all()
    partners_qs = Partner.objects.filter(is_active=True).order_by('partner_name')
    partners_require_selection = partners_qs.filter(require_partner_selection=True).exists()
    context = {
        'employee_code': user_profiles.employee_code,
        'region_code': user_profiles.region.region_code,
        **user_context,
        'user': user,
        'user_profiles': user_profiles,
        'package_types': package_type,
        'regions' : regions,
        'partners': partners_qs,
        'partners_require_selection': partners_require_selection,
        }
    if not user_context['is_admin'] and not user_context['is_checker']:
        messages.error(request, "Bạn không có quyền truy cập trang này.")
        return redirect('home')
    if request.method == 'POST':
        package_code_submit = request.POST.get('package_code_submit')
        partner_package_code_submit = request.POST.get('partner_package_code_choice', '').strip()
        partner_id_submit = request.POST.get('partner_id_choice')
        package_type_submit = request.POST.get('package_type_choice')
        package_region_submit = request.POST.get('region_choice')
        partner_instance = None
        if partner_id_submit:
            try:
                partner_instance = partners_qs.get(partner_id=partner_id_submit)
            except Partner.DoesNotExist:
                return JsonResponse({'success': False, 'message': 'Đối tác không tồn tại hoặc đã bị vô hiệu.'}, status=400)
        elif partners_require_selection and partners_qs.exists():
            return JsonResponse({'success': False, 'message': 'Vui lòng chọn đối tác lưu trữ.'}, status=400)
        if partner_instance and partner_instance.require_partner_code and not partner_package_code_submit:
            return JsonResponse({'success': False, 'message': f'Đối tác {partner_instance.partner_name} yêu cầu nhập mã thùng đối tác.'}, status=400)
        if partner_package_code_submit and PartnerPackage.objects.filter(partner_package_code=partner_package_code_submit).exists():
            return JsonResponse({'success': False, 'message': f'Mã thùng đối tác {partner_package_code_submit} đã tồn tại trong hệ thống.'}, status=400)
        if not partner_instance and partners_qs.exists():
            return JsonResponse({'success': False, 'message': 'Vui lòng chọn đối tác lưu trữ.'}, status=400)
        # Validate package code using the custom validation function
        validation_result = validate_package_code(package_code_submit, user)
        if not validation_result['is_valid']:
            return JsonResponse({'success': False, 'message': validation_result['error']}, status=400)
        # Save new package
        package = Package.objects.create(
            package_code=package_code_submit,
            package_type= FolderType.objects.get(package_type=package_type_submit),
            created_by=request.user,
            region_id =  Region.objects.get(region_code=package_region_submit) 
        )
        partner_package = None
        if partner_instance:
            partner_status_instance_1 = PartnerPackageStatus.objects.get(status_id=1)  # Assuming status_id=1 means 'newly created'
            partner_package = PartnerPackage.objects.create(
                package_id=package,
                partner_package_code=partner_package_code_submit or None,
                partner_name=partner_instance.partner_code,
                partner=partner_instance,
                created_date=timezone.now(),
                status_id=partner_status_instance_1,
                created_by=request.user
            )
        payload = {
            'package_id': model_to_dict(package),
            'partner_package': model_to_dict(partner_package) if partner_package else None,
            'success': True,
            'message': 'Tạo thùng mới thành công.'
            }
        return JsonResponse(payload, status=200)
    
    return render(request, 'app_documents/app_create_package.html', context)

# View GEN số thứ tự tiếp theo cho thùng mới
@login_required
def get_next_package_sequence(request):
    base_code = request.GET.get('baseCode')
    if not base_code:
        return JsonResponse({'success': False, 'message': 'Base code is required.'})
    try:
        existing_codes = Package.objects.filter(package_code__startswith=base_code)
        max_sequence = 0
        for package in existing_codes:
            try:
                sequence = int(package.package_code.split('-')[-1][1:])
                max_sequence = max(max_sequence, sequence)
            except (ValueError, IndexError) as e:
                logger.error(f"Error parsing sequence from package code {package.package_code}: {e}")
                continue
        
        next_sequence = max_sequence + 1
        if next_sequence >= 100:
            return JsonResponse({'success': False, 'message': 'No available sequences left.'})
        
        return JsonResponse({'success': True, 'nextSequence': f"{next_sequence:02d}"})
    except Exception as e:
        logger.error("Failed to fetch package sequence", exc_info=True)
        return JsonResponse({'success': False, 'message': 'Server error when fetching sequence number.'})

@login_required
def api_package_create_v2(request):
    """
    Endpoint tạo thùng v2 qua JSON body, dùng validate_package_code_v2.
    Body mẫu:
    {
      "package_code": "VH-241231-M01",
      "region_code": "M",   # 1 ký tự vùng/kho người chọn
      "partner_id": 123,    # optional
      "partner_package_code": "CRN-001",  # optional
      "folder_type_id": 5   # optional, để cross-check với package_code
    }
    """
    user_context = get_user_context(request.user)
    if not user_context['is_admin'] and not user_context['is_checker']:
        return JsonResponse({'error': 'Unauthorized access.'}, status=403)
    if request.method != "POST":
        return JsonResponse({'error': 'Method not allowed'}, status=405)

    try:
        payload = json.loads(request.body.decode() or "{}")
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON payload.'}, status=400)

    package_code = (payload.get('package_code') or '').strip()
    region_code = (payload.get('region_code') or '').strip()
    partner_id = payload.get('partner_id')
    partner_package_code = (payload.get('partner_package_code') or '').strip() or None
    folder_type_id = payload.get('folder_type_id')

    validation = validate_package_code_v2(package_code, selected_region_code=region_code)
    if not validation.get('is_valid'):
        resp = {'error': validation.get('error', 'Validation failed.')}
        if validation.get('next_suggested_sequence'):
            resp['next_suggested_sequence'] = validation['next_suggested_sequence']
        return JsonResponse(resp, status=400)

    folder_type_obj = validation['folder_type']
    if folder_type_id and str(folder_type_id) != str(folder_type_obj.folder_type_id):
        return JsonResponse({'error': 'Loại thùng ở mã và lựa chọn không khớp.'}, status=400)

    region_obj = None
    if region_code:
        region_obj = Region.objects.filter(region_code__iexact=region_code[:1]).first()
        if not region_obj:
            return JsonResponse({'error': f"Mã vùng {region_code} không tồn tại."}, status=400)

    partner_obj = None
    if partner_id:
        try:
            partner_obj = Partner.objects.get(partner_id=partner_id, is_active=True)
        except Partner.DoesNotExist:
            return JsonResponse({'error': 'Đối tác không tồn tại hoặc đã bị vô hiệu.'}, status=400)

    if partner_package_code and PartnerPackage.objects.filter(partner_package_code=partner_package_code).exists():
        return JsonResponse({'error': f'Mã thùng đối tác {partner_package_code} đã tồn tại trong hệ thống.'}, status=400)

    default_status = PartnerPackageStatus.objects.filter(is_in_warehouse=True).first() or PartnerPackageStatus.objects.filter(status_id=1).first()

    try:
        with transaction.atomic():
            created_dt = timezone.make_aware(datetime.combine(validation['created_date'], datetime.min.time()))
            package = Package.objects.create(
                package_code=validation['normalized_code'],
                package_type=folder_type_obj,
                created_by=request.user,
                region_id=region_obj,
                created_date=created_dt,
            )
            partner_package = None
            if partner_obj or partner_package_code:
                partner_package = PartnerPackage.objects.create(
                    package_id=package,
                    partner_package_code=partner_package_code,
                    partner_name=partner_obj.partner_code if partner_obj else None,
                    partner=partner_obj,
                    created_date=timezone.now(),
                    status_id=default_status,
                    created_by=request.user,
                )
    except Exception as e:
        logger.error("api_package_create_v2 failed", exc_info=True)
        return JsonResponse({'error': f'Lỗi hệ thống: {str(e)}'}, status=500)

    return JsonResponse({
        'success': True,
        'package': {
            'id': package.package_id,
            'package_code': package.package_code,
            'package_type': folder_type_obj.package_type,
            'folder_type_id': folder_type_obj.folder_type_id,
            'region': region_obj.region_code if region_obj else None,
        },
        'partner_package': {
            'id': partner_package.pk,
            'partner_package_code': partner_package.partner_package_code,
            'partner_id': partner_obj.partner_id if partner_obj else None,
        } if partner_package else None,
        'next_suggested_sequence': validation.get('next_suggested_sequence'),
    }, status=200)

# View cho phép xóa thùng  
@login_required
def clear_package_view(request, folder_id): 
    ''' Xóa thùng của quyển chứng từ 
    Chỉ cho phép xóa thùng trong ngày hiện tại.
    So sánh ngày hiện tại với ngày gán thùng vào quyển chứng từ (Folder) 
    Ngày gán quyển chứng từ trong bảng TransactionReceiving 
    ''' 
    if request.method == 'POST':
        data = json.loads(request.body)
        package_id = data.get('package_id_submit')
        if package_id:
            today = timezone.now().date() 
            # Kiểm tra trong quyển chứng từ đã được duyệt chưa? 
            if DocumentsDetail.objects.filter(folder_id=folder_id,document_status_id__documents_status_code = '102').exists(): 
                return JsonResponse({'success': False, 'message': 'Quyển chứng từ đã có chứng từ được duyệt, Không được gỡ thùng khỏi quyển chứng từ.'})
            # Kiểm tra ngày gán thùng lớn nhất vào quyển chứng từ 
            if FoldersTransactionReceiving.objects.filter(folder_id=folder_id, trans_created_date__date = today).exists(): 
                Folder.objects.filter(folder_id=folder_id).update(package_id=None)
                DocumentsDetail.objects.filter(folder_id=folder_id).update(package_id=None)
                Folder.objects.filter(folder_id=folder_id).update(
                        lastest_received_date=None
                    ,   lastest_received_by=None
                    ,   folder_status_id= FolderStatus.objects.get( is_not_received_yet = True )
                    ,   is_on_time = None 
                    ,   is_late = None 
                    ,   note = None)
                return JsonResponse({'success': True, 'message': 'Xóa thùng thành công.'})
            else:
                return JsonResponse({'success': False, 'message': 'Đã quá thời hạn xóa thùng. Liên hệ admin'})
        else:
            return JsonResponse({'success': False, 'message': 'Không tìm thấy thùng cần xóa.'})
    return JsonResponse({'success': False, 'message': 'Invalid request.'})

# View kiểm tra thùng F88
@login_required
def check_package_view(request):
    package_code = request.GET.get('user_entering_package_code', '').strip()
    # First, check if the package code matches the required format
    package_pattern = r'^(VH|CIMB)-(\d{6})-(\d)(\d{2})$'
    if not re.match(package_pattern, package_code):
        return JsonResponse({
            'is_valid_package': False,
            'error_message': "Định dạng thùng phải đúng template 'TYPE-yymmdd-axx'. Với TYPE là loại thùng.\nyymmdd: là năm-tháng-ngày-hiện tại.\na sẽ là mã vùng của bạn\nxx phải là chữ số thứ tự từ 01-99"
            'package_exists'
        })
    # Then, check if the package code already exists in the database
    package_exists = Package.objects.filter(package_code=package_code).exists()
    if package_exists:
        partner_package_status_noneligible = PartnerPackage.objects.filter( package_id__package_code = package_code , status_id__status_id = 2).exists()
        return JsonResponse({
            'is_valid_package': False,
            'error_message': f'Thùng {package_code} đã tồn tại trong hệ thống. Vui lòng nhập mã khác.',
            'package_exists' : package_exists,
            'partner_package_status_noneligible': partner_package_status_noneligible
        })
    # If both checks pass, the package code is considered valid
    return JsonResponse({
        'is_valid_package': True,
        'error_message': '',
        'package_exists' : package_exists 
        })

# View kiểm tra thùng Đối tác
@login_required 
def check_partner_package_view(request): 
    partner_package_code = request.GET.get('user_entering_partner_package_code', '').strip() 
    package_partner_exists = PartnerPackage.objects.filter(partner_package_code=partner_package_code).exists()
    if package_partner_exists:
        return JsonResponse({
            'error_message': f'Thùng {partner_package_code} đã tồn tại trong hệ thống. Vui lòng nhập mã khác.',
            'package_partner_exists' : package_partner_exists
        })
    return JsonResponse({ 
        'error_message': '',
        'package_partner_exists' : package_partner_exists
    })

# View chuyển trạng thái thùng đối tác 
@login_required
def change_partnerpackage_status(request, package_id):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            new_partnerpackage_status_id = data.get('new_partnerpackage_status')

            if not new_partnerpackage_status_id:
                return JsonResponse({'success': False, 'error': 'Trạng thái mới không hợp lệ.'}, status=400)

            partnerpackage = get_object_or_404(PartnerPackage, package_id_id=package_id)
            new_status = get_object_or_404(PartnerPackageStatus, pk=new_partnerpackage_status_id)
            partnerpackage.status_id = new_status
            partnerpackage.save()
            return JsonResponse({'success': True})
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)}, status=500)
    else:
        return JsonResponse({'success': False, 'error': 'Yêu cầu không hợp lệ.'}, status=400)
# ----------------- BULK PACKAGE (validate + save) -----------------
def _parse_date_safe(val):
    if pd.isna(val):
        return None
    parsed = pd.to_datetime(val, errors="coerce")
    if pd.isna(parsed):
        return None
    return parsed.date()


def _normalize_col_name(value):
    if value is None:
        return ""
    text = str(value).strip().lower()
    text = re.sub(r"\s+", "_", text)
    return text


def _base_col_name(value):
    base = _normalize_col_name(value)
    return re.sub(r"\.\d+$", "", base)


def _pick_date_columns(columns):
    day_cols = [c for c in columns if _base_col_name(c) in ("ngay", "ngày", "day")]
    month_cols = [c for c in columns if _base_col_name(c) in ("thang", "tháng", "month")]
    year_cols = [c for c in columns if _base_col_name(c) in ("nam", "năm", "year")]

    def _pick_by_hint(cols, hint):
        for col in cols:
            base = _normalize_col_name(col)
            if hint in base:
                return col
        return None

    receive_day = _pick_by_hint(day_cols, "nhan") or (day_cols[0] if len(day_cols) >= 1 else None)
    receive_month = _pick_by_hint(month_cols, "nhan") or (month_cols[0] if len(month_cols) >= 1 else None)
    receive_year = _pick_by_hint(year_cols, "nhan") or (year_cols[0] if len(year_cols) >= 1 else None)

    folder_day = _pick_by_hint(day_cols, "phat_sinh")
    folder_month = _pick_by_hint(month_cols, "phat_sinh")
    folder_year = _pick_by_hint(year_cols, "phat_sinh")

    if not folder_day and len(day_cols) >= 2:
        folder_day = day_cols[1]
    if not folder_month and len(month_cols) >= 2:
        folder_month = month_cols[1]
    if not folder_year and len(year_cols) >= 2:
        folder_year = year_cols[1]

    return {
        "receive_day": receive_day,
        "receive_month": receive_month,
        "receive_year": receive_year,
        "folder_day": folder_day,
        "folder_month": folder_month,
        "folder_year": folder_year,
    }


def _build_date(day_val, month_val, year_val):
    try:
        if pd.isna(day_val) or pd.isna(month_val) or pd.isna(year_val):
            return None
        day = int(day_val)
        month = int(month_val)
        year = int(year_val)
        return datetime(year, month, day).date()
    except Exception:
        return None


def _resolve_shop_by_pgd(pgd_value):
    if pd.isna(pgd_value):
        return None, "Thiếu PGD."
    raw = str(pgd_value).strip()
    if not raw:
        return None, "Thiếu PGD."
    code = raw.split()[0].strip()
    if not code:
        return None, "PGD không hợp lệ."
    candidates = Shop.objects.filter(shop_name__icontains=code)
    if not candidates.exists():
        return None, f"PGD '{raw}' không tồn tại."
    if candidates.count() == 1:
        return candidates.first(), ""
    exact = candidates.filter(shop_name__iexact=raw)
    if exact.count() == 1:
        return exact.first(), ""
    return None, f"PGD '{raw}' trùng lặp, không xác định được."


def _validate_offline_receiving(df, uploader, upload_filename=""):
    df = df.rename(columns={c: c for c in df.columns})
    columns = list(df.columns)
    date_cols = _pick_date_columns(columns)

    pgd_col = None
    for col in columns:
        base = _base_col_name(col)
        if base in ("pgd", "phong_giao_dich", "phong_giaodich"):
            pgd_col = col
            break

    folder_type_col = None
    for col in columns:
        base = _base_col_name(col)
        if base in ("folder_type", "foldertype", "folder_type_code", "foldertype_code"):
            folder_type_col = col
            break

    package_col = None
    for col in columns:
        base = _base_col_name(col)
        if base in ("ma_thung_f88", "ma_thung", "package_code", "ma_thung_f88"):
            package_col = col
            break

    user_col = None
    for col in columns:
        base = _base_col_name(col)
        if base in ("nhan_su", "nhan_sự", "username", "nhan_vien", "nhân_sự"):
            user_col = col
            break

    if not all([date_cols["receive_day"], date_cols["receive_month"], date_cols["receive_year"]]):
        raise ValidationError("Thiếu cột ngày/tháng/năm nhận.")
    if not all([date_cols["folder_day"], date_cols["folder_month"], date_cols["folder_year"]]):
        raise ValidationError("Thiếu cột ngày/tháng/năm phát sinh.")
    if not pgd_col:
        raise ValidationError("Thiếu cột PGD.")
    if not folder_type_col:
        raise ValidationError("Thiếu cột Folder type (folder_type_code).")
    if not package_col:
        raise ValidationError("Thiếu cột Mã thùng F88.")
    if not user_col:
        raise ValidationError("Thiếu cột Nhân sự (username).")

    folder_type_map = {ft.folder_type_code.upper(): ft for ft in FolderType.objects.filter(is_valid=True) if ft.folder_type_code}
    region_map = {r.region_code.upper(): r for r in Region.objects.all()}
    status_received = FolderStatus.objects.filter(is_received=True).first()
    if not status_received:
        raise ValidationError("Chưa cấu hình trạng thái nhận.")

    package_pattern = re.compile(r"^(?P<type>[A-Za-z0-9]+)-(?P<date>\d{6})-(?P<region>[A-Za-z0-9])(?P<seq>\d{2})$")

    result_rows = []
    valid_rows = []
    package_cache = {}

    for idx, row in df.iterrows():
        errors = []
        warnings = []

        receive_date = _build_date(
            row.get(date_cols["receive_day"]),
            row.get(date_cols["receive_month"]),
            row.get(date_cols["receive_year"]),
        )
        folder_date = _build_date(
            row.get(date_cols["folder_day"]),
            row.get(date_cols["folder_month"]),
            row.get(date_cols["folder_year"]),
        )

        if not receive_date:
            errors.append("Ngày nhận không hợp lệ.")
        if not folder_date:
            errors.append("Ngày phát sinh không hợp lệ.")

        shop, shop_error = _resolve_shop_by_pgd(row.get(pgd_col))
        if shop_error:
            errors.append(shop_error)

        folder_type_code = str(row.get(folder_type_col)).strip() if not pd.isna(row.get(folder_type_col)) else ""
        folder_type_obj = folder_type_map.get(folder_type_code.upper()) if folder_type_code else None
        if not folder_type_obj:
            errors.append(f"Folder type '{folder_type_code}' không tồn tại.")

        username = str(row.get(user_col)).strip() if not pd.isna(row.get(user_col)) else ""
        receiver = User.objects.filter(username=username).first() if username else None
        if not receiver:
            errors.append(f"Nhân sự '{username}' không tồn tại.")

        package_code = str(row.get(package_col)).strip() if not pd.isna(row.get(package_col)) else ""
        package_obj = None
        package_region = None
        if not package_code:
            errors.append("Thiếu mã thùng F88.")
        else:
            match = package_pattern.match(package_code)
            if not match:
                errors.append("Mã thùng F88 không đúng định dạng.")
            else:
                pkg_type = match.group("type").upper()
                region_part = match.group("region").upper()
                if folder_type_obj and folder_type_obj.folder_type_code and pkg_type != folder_type_obj.folder_type_code.upper():
                    errors.append("Mã thùng không khớp folder_type_code.")
                package_region = region_map.get(region_part)

            if package_code in package_cache:
                package_obj = package_cache[package_code]
            else:
                package_obj = Package.objects.filter(package_code=package_code).first()
                if package_obj:
                    package_cache[package_code] = package_obj

        folder_obj = None
        fallback_used = False
        if shop and folder_type_obj and folder_date:
            qs = Folder.objects.filter(
                shop_id=shop,
                folder_type_id=folder_type_obj,
                folder_created_date=folder_date,
            )
            if qs.count() == 1:
                folder_obj = qs.first()
            elif qs.count() == 0:
                fallback_qs = Folder.objects.filter(shop_id=shop, folder_type_id=folder_type_obj)
                if fallback_qs.count() == 1:
                    folder_obj = fallback_qs.first()
                    fallback_used = True
                    warnings.append("Không tìm thấy đúng ngày phát sinh, fallback toàn bộ theo PGD + loại quyển.")
                elif fallback_qs.count() == 0:
                    errors.append("Không tìm thấy quyển theo PGD + loại quyển.")
                else:
                    errors.append("Có nhiều quyển theo PGD + loại quyển, không thể fallback.")
            else:
                errors.append("Có nhiều quyển theo PGD + ngày phát sinh + loại quyển.")

        status = "valid" if not errors else "invalid"
        if not errors:
            valid_rows.append(
                {
                    "folder": folder_obj,
                    "receiver": receiver,
                    "receive_date": receive_date,
                    "folder_date": folder_date,
                    "folder_type": folder_type_obj,
                    "shop": shop,
                    "package_code": package_code,
                    "package_region": package_region,
                    "package": package_obj,
                    "fallback_used": fallback_used,
                }
            )

        result_rows.append(
            {
                "row": idx + 2,
                "pgd": str(row.get(pgd_col)).strip() if not pd.isna(row.get(pgd_col)) else "",
                "folder_type_code": folder_type_code,
                "username": username,
                "package_code": package_code,
                "receive_date": receive_date.strftime("%Y-%m-%d") if receive_date else "",
                "folder_date": folder_date.strftime("%Y-%m-%d") if folder_date else "",
                "status": status,
                "warning": "; ".join(warnings),
                "error": "; ".join(errors),
            }
        )

    return result_rows, valid_rows, status_received


def _validate_bulk_packages(df, user, user_context, upload_filename=""):
    def _clean_str(val):
        if pd.isna(val):
            return ""
        return str(val).strip()

    required_cols = [
        "package_code",
        "package_type",
        "region_code",
        "partner_code",
        "partner_package_code",
        "created_date",
        "note",
        "username",
    ]
    df = df.rename(columns={c: c.strip().lower() for c in df.columns})
    rename_map = {
        "folder_type": "package_type",
        "folder_typeid": "package_type",
        "package_type_code": "package_type",
        "region": "region_code",
        "partner": "partner_code",
        "partner_code": "partner_code",
        "partner_package": "partner_package_code",
        "partner_packagecode": "partner_package_code",
        "created": "created_date",
        "created_at": "created_date",
        "creator": "username",
    }
    for src, dst in rename_map.items():
        if src in df.columns and dst not in df.columns:
            df = df.rename(columns={src: dst})
    missing = [col for col in required_cols if col not in df.columns]
    if missing:
        raise ValidationError(f"Thiếu cột: {', '.join(missing)}")

    pattern = re.compile(r"^(CIMB|NH|VH)-(\d{6})-([A-Za-z0-9]{1})(\d{2})$")
    region_map = {r.region_code.upper(): r for r in Region.objects.all()}
    folder_types = list(FolderType.objects.filter(is_valid=True))
    folder_type_by_package = {}
    for ft in folder_types:
        key = (ft.package_type or "").upper()
        if key not in folder_type_by_package:
            folder_type_by_package[key] = []
        folder_type_by_package[key].append(ft)
    partner_map = {p.partner_code.upper(): p for p in Partner.objects.filter(is_active=True)}

    seen_package = set()
    seen_partner_pkg = set()

    result_rows = []
    valid_rows = []

    for idx, row in df.iterrows():
        errors = []
        raw_code = _clean_str(row.get("package_code"))
        package_type_val = _clean_str(row.get("package_type"))
        region_code = _clean_str(row.get("region_code"))
        partner_code = _clean_str(row.get("partner_code"))
        partner_pkg_code = _clean_str(row.get("partner_package_code"))
        created_date_val = _parse_date_safe(row.get("created_date"))
        note_val_raw = row.get("note")
        username_val = _clean_str(row.get("username"))

        match = pattern.match(raw_code)
        if not raw_code:
            errors.append("Thiếu package_code.")
        elif not match:
            errors.append("package_code không đúng format {FOLDER_TYPE}-{yyMMdd}-{region}{bb}.")
        else:
            prefix, ymd, region_in_code, seq = match.groups()
            if package_type_val and prefix.upper() != package_type_val.upper():
                errors.append("package_code không khớp package_type.")
            if region_code and region_in_code.upper() != region_code.upper():
                errors.append("package_code không khớp region_code.")
            if seq == "00":
                errors.append("Số thứ tự bb phải từ 01-99.")

        folder_type_obj = None
        resolved_folder_type_code = ""
        if package_type_val:
            ft_list = folder_type_by_package.get(package_type_val.upper(), [])
            if not ft_list:
                errors.append(f"package_type '{package_type_val}' không tồn tại.")
            elif len(ft_list) > 1:
                errors.append(
                    f"package_type '{package_type_val}' mapping nhiều folder_type_code: "
                    f"{', '.join([ft.folder_type_code for ft in ft_list if ft.folder_type_code])}. "
                    "Vui lòng cấu hình/chuẩn hóa để duy nhất."
                )
            else:
                folder_type_obj = ft_list[0]
                resolved_folder_type_code = folder_type_obj.folder_type_code or ""

        region_obj = None
        if region_code:
            region_obj = region_map.get(region_code.upper())
            if not region_obj:
                errors.append(f"region_code '{region_code}' không tồn tại.")

        partner_obj = None
        if partner_code:
            partner_obj = partner_map.get(partner_code.upper())
            if not partner_obj:
                errors.append(f"partner_code '{partner_code}' không tồn tại.")

        if partner_pkg_code:
            if partner_pkg_code in seen_partner_pkg:
                errors.append(f"partner_package_code '{partner_pkg_code}' trùng trong file.")
            if PartnerPackage.objects.filter(partner_package_code=partner_pkg_code).exists():
                errors.append(f"partner_package_code '{partner_pkg_code}' đã tồn tại.")

        if raw_code:
            if raw_code in seen_package:
                errors.append(f"package_code '{raw_code}' trùng trong file.")
            if Package.objects.filter(package_code=raw_code).exists():
                errors.append(f"package_code '{raw_code}' đã tồn tại.")

        if partner_obj and partner_obj.require_partner_code and not partner_pkg_code:
            errors.append(f"Đối tác {partner_obj.partner_name} yêu cầu partner_package_code.")

        creator = user
        used_creator = user.username
        if user_context.get("is_admin"):
            if username_val:
                creator = User.objects.filter(username=username_val).first()
                if not creator:
                    errors.append(f"username '{username_val}' không tồn tại.")
                else:
                    used_creator = creator.username
            else:
                creator = user
                used_creator = user.username
        else:
            # Non-admin: ignore provided username, always use uploader
            creator = user
            used_creator = user.username

        if created_date_val:
            try:
                created_dt = datetime.combine(created_date_val, datetime.min.time())
                if timezone.is_naive(created_dt):
                    created_dt = timezone.make_aware(created_dt, timezone.get_current_timezone())
            except Exception:
                errors.append("created_date không hợp lệ.")
        else:
            created_dt = timezone.now()

        if pd.isna(note_val_raw) or str(note_val_raw).strip() == "":
            note_val = f"Dữ liệu được bởi file {upload_filename}, được upload bởi {user.username}."
        else:
            note_val = str(note_val_raw).strip()

        status = "valid" if not errors else "invalid"
        if not errors:
            seen_package.add(raw_code)
            if partner_pkg_code:
                seen_partner_pkg.add(partner_pkg_code)
            valid_rows.append(
                {
                    "package_code": raw_code,
                    "folder_type": folder_type_obj,
                    "region": region_obj,
                    "partner": partner_obj,
                    "partner_package_code": partner_pkg_code or None,
                    "created_dt": created_dt,
                    "note": note_val,
                    "creator": creator,
                }
            )

        result_rows.append(
            {
                "package_code": raw_code,
                "package_type": package_type_val,
                "resolved_folder_type_code": resolved_folder_type_code,
                "region_code": region_code,
                "partner_code": partner_code,
                "partner_package_code": partner_pkg_code,
                "created_date": created_date_val.strftime("%Y-%m-%d") if created_date_val else "",
                "note": note_val,
                "username": username_val,
                "used_username": used_creator,
                "status": status,
                "error": "; ".join(errors),
            }
        )

    return result_rows, valid_rows


@login_required
@require_http_methods(["POST"])
def package_bulk_validate(request):
    file = request.FILES.get("file")
    if not file:
        return JsonResponse({"error": "Thiếu file upload."}, status=400)
    if file.size > 30 * 1024 * 1024:
        return JsonResponse({"error": "File vượt quá 30MB."}, status=400)
    try:
        df = pd.read_excel(file, sheet_name="Template")
    except Exception as exc:
        return JsonResponse({"error": f"Lỗi đọc file: {exc}"}, status=400)

    try:
        user_context = get_user_context(request.user)
        result_rows, _ = _validate_bulk_packages(df, request.user, user_context, upload_filename=file.name)
    except Exception as exc:
        return JsonResponse({"error": str(exc)}, status=400)

    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        pd.DataFrame(result_rows).to_excel(writer, sheet_name="Result", index=False)
    output.seek(0)
    resp = HttpResponse(
        output.read(),
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    resp["Content-Disposition"] = 'attachment; filename="bulk_package_validate_result.xlsx"'
    return resp


@login_required
@require_http_methods(["POST"])
def package_bulk_save(request):
    file = request.FILES.get("file")
    if not file:
        return JsonResponse({"error": "Thiếu file upload."}, status=400)
    if file.size > 30 * 1024 * 1024:
        return JsonResponse({"error": "File vượt quá 30MB."}, status=400)
    try:
        df = pd.read_excel(file, sheet_name="Template")
    except Exception as exc:
        return JsonResponse({"error": f"Lỗi đọc file: {exc}"}, status=400)

    user_context = get_user_context(request.user)
    try:
        result_rows, valid_rows = _validate_bulk_packages(df, request.user, user_context, upload_filename=file.name)
    except Exception as exc:
        return JsonResponse({"error": str(exc)}, status=400)

    invalid_count = len([r for r in result_rows if r["status"] == "invalid"])
    if invalid_count > 0:
        output = BytesIO()
        with pd.ExcelWriter(output, engine="openpyxl") as writer:
            pd.DataFrame(result_rows).to_excel(writer, sheet_name="Result", index=False)
        output.seek(0)
        resp = HttpResponse(
            output.read(),
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        resp["Content-Disposition"] = 'attachment; filename="bulk_package_save_errors.xlsx"'
        return resp

    created = 0
    partner_created = 0
    default_status = PartnerPackageStatus.objects.filter(is_in_warehouse=True).first() or PartnerPackageStatus.objects.first()
    with transaction.atomic():
        for entry in valid_rows:
            package = Package.objects.create(
                package_code=entry["package_code"],
                package_type=entry["folder_type"],
                created_by=entry["creator"],
                region_id=entry["region"],
                created_date=entry["created_dt"],
            )
            created += 1
            if entry["partner"] or entry["partner_package_code"]:
                PartnerPackage.objects.create(
                    package_id=package,
                    partner_package_code=entry["partner_package_code"],
                    partner=entry["partner"],
                    partner_name=entry["partner"].partner_code if entry["partner"] else None,
                    created_date=entry["created_dt"],
                    updated_date=entry["created_dt"],
                    status_id=default_status,
                    created_by=entry["creator"],
                )
                partner_created += 1
    return JsonResponse(
        {
            "success": True,
            "created_packages": created,
            "created_partnerpackages": partner_created,
        }
    )


def _load_receiving_import_df(file):
    try:
        df = pd.read_excel(file, header=1)
    except Exception:
        df = pd.read_excel(file)
    if df is None or df.empty:
        raise ValidationError("File không có dữ liệu.")
    return df


@login_required
@require_ui_permission('receiving_import_v2')
def receiving_import_v2(request):
    user_context = get_user_context(request.user)
    return render(request, 'app_documents/app_receiving_import_v2.html', {**user_context})


@login_required
@require_ui_permission('receiving_import_v2')
@require_http_methods(["POST"])
def receiving_import_validate(request):
    file = request.FILES.get("file")
    if not file:
        return JsonResponse({"error": "Thiếu file upload."}, status=400)
    if file.size > 30 * 1024 * 1024:
        return JsonResponse({"error": "File vượt quá 30MB."}, status=400)
    try:
        df = _load_receiving_import_df(file)
        result_rows, _, _ = _validate_offline_receiving(df, request.user, upload_filename=file.name)
    except Exception as exc:
        return JsonResponse({"error": str(exc)}, status=400)

    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        pd.DataFrame(result_rows).to_excel(writer, sheet_name="Result", index=False)
    output.seek(0)
    resp = HttpResponse(
        output.read(),
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    resp["Content-Disposition"] = 'attachment; filename="receiving_import_validate_result.xlsx"'
    return resp


@login_required
@require_ui_permission('receiving_import_v2')
@require_http_methods(["POST"])
def receiving_import_save(request):
    file = request.FILES.get("file")
    if not file:
        return JsonResponse({"error": "Thiếu file upload."}, status=400)
    if file.size > 30 * 1024 * 1024:
        return JsonResponse({"error": "File vượt quá 30MB."}, status=400)
    try:
        df = _load_receiving_import_df(file)
        result_rows, valid_rows, status_received = _validate_offline_receiving(df, request.user, upload_filename=file.name)
    except Exception as exc:
        return JsonResponse({"error": str(exc)}, status=400)

    invalid_count = len([r for r in result_rows if r["status"] == "invalid"])
    if invalid_count > 0:
        output = BytesIO()
        with pd.ExcelWriter(output, engine="openpyxl") as writer:
            pd.DataFrame(result_rows).to_excel(writer, sheet_name="Result", index=False)
        output.seek(0)
        resp = HttpResponse(
            output.read(),
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        resp["Content-Disposition"] = 'attachment; filename="receiving_import_errors.xlsx"'
        return resp

    created_packages = 0
    updated_folders = 0
    fallback_used = 0
    package_cache = {}

    with transaction.atomic():
        for entry in valid_rows:
            folder = entry["folder"]
            receiver = entry["receiver"]
            receive_date = entry["receive_date"]
            package_code = entry["package_code"]
            folder_type = entry["folder_type"]
            package_region = entry["package_region"]
            package_obj = entry["package"]
            if entry.get("fallback_used"):
                fallback_used += 1

            if not package_obj:
                package_obj = package_cache.get(package_code)
            if not package_obj:
                package_obj = Package.objects.filter(package_code=package_code).first()
            if not package_obj:
                created_dt = datetime.combine(receive_date, datetime.min.time())
                if timezone.is_naive(created_dt):
                    created_dt = timezone.make_aware(created_dt, timezone.get_current_timezone())
                package_obj = Package.objects.create(
                    package_code=package_code,
                    package_type=folder_type,
                    created_by=receiver,
                    created_date=created_dt,
                    region_id=package_region,
                )
                created_packages += 1
            package_cache[package_code] = package_obj

            received_dt = datetime.combine(receive_date, datetime.min.time())
            if timezone.is_naive(received_dt):
                received_dt = timezone.make_aware(received_dt, timezone.get_current_timezone())

            folder.lastest_received_date = received_dt
            folder.lastest_received_by = receiver
            folder.folder_status_id = status_received
            folder.package_id = package_obj
            folder.save(update_fields=['lastest_received_date', 'lastest_received_by', 'folder_status_id', 'package_id'])
            if status_received.is_received:
                _resolve_folder_appointment(
                    folder,
                    receiver,
                    received_dt,
                    source='receive_v2_import',
                )
            updated_folders += 1

            check_on_time(folder, received_dt)

            FoldersTransactionReceiving.objects.create(
                folder_id=folder,
                trans_updated_date=received_dt,
                trans_created_by=receiver,
                folder_status_id=status_received,
            )

            PackageFolderHistory.objects.create(
                folder_id=folder,
                package_id=package_obj,
                trans_created_date=received_dt,
                trans_created_by=receiver,
            )

            documents = DocumentsDetail.objects.select_for_update().filter(folder_id=folder.folder_id)
            for document in documents:
                document.package_id = package_obj
                document.save(update_fields=['package_id'])
                PackageDocumentHistory.objects.create(
                    document_id=document,
                    package_id=package_obj,
                    trans_created_date=received_dt,
                    trans_created_by=receiver,
                )

    return JsonResponse(
        {
            "success": True,
            "updated_folders": updated_folders,
            "created_packages": created_packages,
            "fallback_used": fallback_used,
        }
    )

# Tạo thùng nhiều từ file Excel
@login_required
def import_packages_view(request):
    if request.method == 'POST' and request.FILES.get('filePackage'):
        excel_file = request.FILES['filePackage']
        try:
            df = pd.read_excel(excel_file)
            user_created = request.user
            partners_qs = Partner.objects.filter(is_active=True)
            partners_require_selection = partners_qs.filter(require_partner_selection=True).exists()
            with transaction.atomic():
                for index, row in df.iterrows():
                    new_package_code_raw = row['newPackageCode']
                    old_package_code = row['oldPackageCode']
                    partner_package_code = row['partnerPackageCode']
                    partner_name_value = row['partnerName']
                    package_type_name = row['packageType']
                    partner_package_status = row['partnerPackageStatus']
                    package_region = row['packageRegion']
                    if pd.isna(new_package_code_raw):
                        raise transaction.TransactionManagementError("Missing package code in import file.")
                    new_package_code = str(new_package_code_raw).strip()
                    partner_package_code_value = None if pd.isna(partner_package_code) or str(partner_package_code).strip() == '' else str(partner_package_code).strip()
                    partner_name_value = None if pd.isna(partner_name_value) or str(partner_name_value).strip() == '' else str(partner_name_value).strip()
                   
                    # Validate package type by matching with FolderType's package_type
                    try:
                        package_type = FolderType.objects.get(package_type=package_type_name)
                    except FolderType.DoesNotExist:
                        messages.error(request, f"Loại thùng hàng '{package_type_name}' không tồn tại.")
                        raise transaction.TransactionManagementError(f"Loại thùng hàng '{package_type_name}' không tồn tại.")
            
                    # Validate package code
                    validation_result = validate_package_code(new_package_code, user_created)
                    if not validation_result['is_valid']:
                        messages.error(request, validation_result['error'])
                        raise transaction.TransactionManagementError(validation_result['error'])
                    # Create or update Package
                    package, created = Package.objects.update_or_create(
                        package_code=new_package_code,
                        package_type= package_type,
                        created_by= user_created,
                        package_code_old= old_package_code,
                        updated_date= timezone.now(),
                        region_id= Region.objects.get(region_code = package_region )
                    )
                    # Create or update PartnerPackage
                    partner_instance = None
                    if partner_name_value:
                        partner_instance = partners_qs.filter(partner_code__iexact=partner_name_value).first()
                        if not partner_instance:
                            partner_instance = partners_qs.filter(partner_name__iexact=partner_name_value).first()
                    if not partner_instance and partners_require_selection and partners_qs.exists():
                        raise transaction.TransactionManagementError(f"Vui lòng cấu hình và chọn đối tác hợp lệ cho thùng {new_package_code}.")
                    if partner_instance and partner_instance.require_partner_code and not partner_package_code_value:
                        raise transaction.TransactionManagementError(f"Đối tác {partner_instance.partner_name} yêu cầu mã thùng đối tác cho thùng {new_package_code}.")
                    if partner_package_code_value and PartnerPackage.objects.exclude(package_id=package).filter(partner_package_code=partner_package_code_value).exists():
                        raise transaction.TransactionManagementError(f"Mã thùng đối tác {partner_package_code_value} đã tồn tại.")
                    if partner_instance or partner_package_code_value:
                        if partner_package_status: 
                            status = PartnerPackageStatus.objects.get(status_id=partner_package_status)  
                        else: 
                            status = PartnerPackageStatus.objects.get(status_id=1)  # Assuming status_id=1 is the default
                        PartnerPackage.objects.update_or_create(
                            package_id=package,
                            defaults={
                                'partner_package_code': partner_package_code_value,
                                'partner_name': partner_instance.partner_code if partner_instance else partner_name_value,
                                'partner': partner_instance,
                                'created_date': timezone.now(),
                                'created_by': request.user,
                                'status_id': status,
                                'updated_date': timezone.now(),
                            }
                        )        
            messages.success(request, "Tải lên và xử lý dữ liệu thành công.")
            return redirect('package_management_view')
        except Exception as e:
            messages.error(request, f"Đã xảy ra lỗi trong quá trình tải lên: {e}")
            # Rollback will happen automatically due to atomic
    return redirect('package_management')

#---------------DASHBOARD-------------------------

@login_required
def documents_dashboard (request):
     # Get user context from the utility function
    user = request.user
    user_context = get_user_context(user)
    if not user_context.get("is_admin"):
        messages.error(request, "Bạn không có quyền truy cập dashboard.")
        return redirect("home")

    # Thời gian lọc
    start_date_str = request.GET.get("start_date")
    end_date_str = request.GET.get("end_date")
    checker_user_id = request.GET.get("checker_user")
    heatmap_mode = request.GET.get("heatmap_mode", "hour")

    start_date, end_date = parse_dates(start_date_str, end_date_str)
    metrics = get_dashboard_metrics(start_date, end_date, checker_user_id, heatmap_mode)

    context = {
        **user_context,
        "user": user,
        "start_date": start_date.strftime("%Y-%m-%d"),
        "end_date": end_date.strftime("%Y-%m-%d"),
        "approved_contracts": metrics["approved_contracts"],
        "first_time_contracts": metrics["first_time_contracts"],
        "total_actions": metrics["total_actions"],
        "active_checkers_count": metrics["active_checkers_count"],
        "avg_actions_per_day": metrics["avg_actions_per_day"],
        "total_reject_actions": metrics["total_reject_actions"],
        "reject_rate": metrics["reject_rate"],
        "approval_rate": metrics["approval_rate"],
        "checker_user_id": checker_user_id or "",
        "drop_checkers": metrics["drop_checkers"],
        "heatmap_list": metrics["heatmap_list"],
        "ranking": metrics["ranking"],
        "status_breakdown": metrics["status_breakdown"],
        "heatmap_mode": heatmap_mode,
    }
    return render(request, 'app_documents/app_dashboard.html', context)

@login_required
def folder_received_dashboard(request):
    user = request.user
    user_context = get_user_context(user)
    if not user_context.get("is_admin"):
        messages.error(request, "Bạn không có quyền truy cập báo cáo này.")
        return redirect("home")

    start_date_str = request.GET.get("start_date")
    end_date_str = request.GET.get("end_date")
    start_date, end_date = parse_dates(start_date_str, end_date_str)
    metrics = get_folder_received_metrics(start_date, end_date)

    context = {
        **user_context,
        "user": user,
        "start_date": start_date.strftime("%Y-%m-%d"),
        "end_date": end_date.strftime("%Y-%m-%d"),
        "folder_received_count": metrics["folder_received_count"],
    }
    return render(request, "app_documents/app_dashboard_folder.html", context)


@login_required
def document_kpi_dashboard_v2(request):
    user = request.user
    user_context = get_user_context(user)
    if not user_context.get("is_admin"):
        messages.error(request, "Bạn không có quyền truy cập dashboard.")
        return redirect("home")

    tab = request.GET.get("tab", "receive")
    start_date_str = request.GET.get("start_date")
    end_date_str = request.GET.get("end_date")
    month_str = request.GET.get("month")
    folder_type_id = request.GET.get("folder_type_id")

    kpi_defaults = [
        {"code": "on_time_rate", "name": "KPI nhận đúng hạn", "target_rate": 90.0},
        {"code": "late_rate", "name": "KPI nhận trễ hạn", "target_rate": 90.0},
        {"code": "not_received_rate", "name": "KPI chưa nhận", "target_rate": 90.0},
    ]
    default_codes = [item["code"] for item in kpi_defaults]
    settings_by_code = {
        item.metric_code: item
        for item in DocumentKpiSetting.objects.filter(metric_code__in=default_codes)
    }
    for item in kpi_defaults:
        setting = settings_by_code.get(item["code"])
        if not setting:
            setting = DocumentKpiSetting.objects.create(
                metric_code=item["code"],
                metric_name=item["name"],
                target_rate=item["target_rate"],
                updated_by=user,
            )
            settings_by_code[item["code"]] = setting
        elif not setting.metric_name:
            setting.metric_name = item["name"]
            setting.updated_by = user
            setting.save(update_fields=["metric_name", "updated_by"])

    if request.method == "POST" and tab == "config":
        action = request.POST.get("action")
        if action == "update_kpi":
            for setting in DocumentKpiSetting.objects.filter(metric_code__in=default_codes):
                raw_value = request.POST.get(f"target_rate_{setting.metric_code}")
                if raw_value is None:
                    continue
                try:
                    new_rate = float(raw_value)
                except (TypeError, ValueError):
                    continue
                if new_rate != float(setting.target_rate):
                    setting.target_rate = new_rate
                    setting.updated_by = user
                    setting.save(update_fields=["target_rate", "updated_by", "updated_at"])
            messages.success(request, "Đã cập nhật KPI.")
        return redirect(f"{reverse('document_kpi_v2')}?tab=config")

    kpi_settings = [settings_by_code[code] for code in default_codes if code in settings_by_code]
    kpi_targets = {
        setting.metric_code: float(setting.target_rate)
        for setting in kpi_settings
        if setting.is_active
    }
    for item in kpi_defaults:
        kpi_targets.setdefault(item["code"], item["target_rate"])
    kpi_labels = {item["code"]: item["name"] for item in kpi_defaults}
    kpi_on_time_warn = max(kpi_targets.get("on_time_rate", 90.0) - 5, 0)

    today = timezone.now().date()
    if month_str:
        try:
            year, month = [int(part) for part in month_str.split("-")]
            last_day = calendar.monthrange(year, month)[1]
            start_date = datetime(year, month, 1).date()
            end_date = datetime(year, month, last_day).date()
        except (ValueError, IndexError):
            start_date, end_date = parse_dates(start_date_str, end_date_str)
    else:
        start_date, end_date = parse_dates(start_date_str, end_date_str)

    start_date = start_date or today.replace(day=1)
    end_date = end_date or today

    base_qs = Folder.objects.select_related('shop_id', 'shop_id__region_id', 'folder_type_id', 'folder_status_id').filter(
        folder_created_date__range=[start_date, end_date]
    )
    if folder_type_id and folder_type_id.isdigit():
        base_qs = base_qs.filter(folder_type_id=folder_type_id)

    receiving_qs = base_qs.filter(is_original=True, is_issue=True)
    on_time_count = receiving_qs.filter(is_on_time=True).count()
    late_count = receiving_qs.filter(is_late=True).count()
    received_count = receiving_qs.filter(folder_status_id__is_received=True).count()
    not_received_issue_original_count = receiving_qs.filter(
        folder_status_id__is_not_received_yet=True
    ).count()
    total_count = received_count + not_received_issue_original_count
    base_total_count = base_qs.count()
    total_original_count = base_qs.filter(is_original=True).count()
    total_issue_count = base_qs.filter(is_issue=True).count()

    def safe_rate(part, total):
        return round((part / total) * 100, 2) if total else 0.0

    on_time_rate_all = safe_rate(on_time_count, received_count)
    late_rate_all = safe_rate(late_count, received_count)
    issue_original_total = total_count
    not_received_rate_all = safe_rate(not_received_issue_original_count, issue_original_total)
    original_rate_all = safe_rate(total_original_count, base_total_count)
    issue_rate_all = safe_rate(total_issue_count, base_total_count)

    ratio_qs = receiving_qs
    ratio_denominator = ratio_qs.filter(lastest_received_date__isnull=False).count()
    ratio_numerator = ratio_qs.filter(is_on_time=True).count()
    ratio_percent = round((ratio_numerator / ratio_denominator) * 100, 2) if ratio_denominator else 0.0

    by_shop = receiving_qs.values('shop_id__shop_name').annotate(
        total=Count('folder_id'),
        on_time=Count('folder_id', filter=Q(is_on_time=True)),
        late=Count('folder_id', filter=Q(is_late=True)),
        not_received=Count('folder_id', filter=Q(folder_status_id__is_not_received_yet=True) | Q(lastest_received_date__isnull=True)),
    ).order_by('-total')

    shop_rows = []
    for row in by_shop:
        total = row['total'] or 0
        on_time = row['on_time'] or 0
        ratio = round((on_time / total) * 100, 2) if total else 0.0
        late_rate = round(((row['late'] or 0) / total) * 100, 2) if total else 0.0
        not_received_rate = round(((row['not_received'] or 0) / total) * 100, 2) if total else 0.0
        shop_rows.append({
            'shop_name': row['shop_id__shop_name'] or 'Không xác định',
            'total': total,
            'on_time': on_time,
            'late': row['late'] or 0,
            'not_received': row['not_received'] or 0,
            'ratio': ratio,
            'on_time_rate': ratio,
            'late_rate': late_rate,
            'not_received_rate': not_received_rate,
        })
    shops_top = sorted(shop_rows, key=lambda x: (-x['ratio'], -x['total']))[:10]
    shops_bottom = sorted(shop_rows, key=lambda x: (x['ratio'], x['total']))[:10]
    shops_combined = []
    shop_seen = set()
    for row in shops_top + shops_bottom:
        if row['shop_name'] in shop_seen:
            continue
        shop_seen.add(row['shop_name'])
        shops_combined.append(row)

    by_region_manager = receiving_qs.values(
        'manager_id__regionManager__regionManager_id',
        'manager_id__regionManager__regionManager_name',
        'manager_id__regionManager__regionManager_code',
    ).annotate(
        total=Count('folder_id'),
        on_time=Count('folder_id', filter=Q(is_on_time=True)),
        late=Count('folder_id', filter=Q(is_late=True)),
        not_received=Count('folder_id', filter=Q(folder_status_id__is_not_received_yet=True) | Q(lastest_received_date__isnull=True)),
    ).order_by('-total')

    region_map = {}
    area_lookup = {}
    for row in by_region_manager:
        total = row['total'] or 0
        on_time = row['on_time'] or 0
        ratio = round((on_time / total) * 100, 2) if total else 0.0
        region_id = row['manager_id__regionManager__regionManager_id'] or 'none'
        region_map[region_id] = {
            'id': region_id,
            'name': row['manager_id__regionManager__regionManager_name'] or 'Chưa phân vùng',
            'code': row['manager_id__regionManager__regionManager_code'] or '',
            'total': total,
            'on_time': on_time,
            'late': row['late'] or 0,
            'not_received': row['not_received'] or 0,
            'ratio': ratio,
            'areas': [],
        }

    by_area_manager = receiving_qs.values(
        'manager_id__regionManager__regionManager_id',
        'manager_id__regionManager__regionManager_name',
        'manager_id__regionManager__regionManager_code',
        'manager_id__areaManager__areaManager_id',
        'manager_id__areaManager__areaManager_name',
        'manager_id__areaManager__areaManager_code',
    ).annotate(
        total=Count('folder_id'),
        on_time=Count('folder_id', filter=Q(is_on_time=True)),
        late=Count('folder_id', filter=Q(is_late=True)),
        not_received=Count('folder_id', filter=Q(folder_status_id__is_not_received_yet=True) | Q(lastest_received_date__isnull=True)),
    ).order_by('-total')

    for row in by_area_manager:
        total = row['total'] or 0
        on_time = row['on_time'] or 0
        ratio = round((on_time / total) * 100, 2) if total else 0.0
        region_id = row['manager_id__regionManager__regionManager_id'] or 'none'
        area_id = row['manager_id__areaManager__areaManager_id'] or ''
        if region_id not in region_map:
            region_map[region_id] = {
                'id': region_id,
                'name': row['manager_id__regionManager__regionManager_name'] or 'Chưa phân vùng',
                'code': row['manager_id__regionManager__regionManager_code'] or '',
                'total': 0,
                'on_time': 0,
                'late': 0,
                'not_received': 0,
                'ratio': 0.0,
                'areas': [],
            }
        area_entry = {
            'id': area_id,
            'uid': f"{region_id}_{area_id or 'none'}",
            'name': row['manager_id__areaManager__areaManager_name'] or 'Chưa phân khu vực',
            'code': row['manager_id__areaManager__areaManager_code'] or '',
            'total': total,
            'on_time': on_time,
            'late': row['late'] or 0,
            'not_received': row['not_received'] or 0,
            'ratio': ratio,
            'shops': [],
        }
        region_map[region_id]['areas'].append(area_entry)
        area_lookup[(region_id, area_id)] = area_entry

    by_shop_area = receiving_qs.values(
        'manager_id__regionManager__regionManager_id',
        'manager_id__areaManager__areaManager_id',
        'shop_id',
        'shop_id__shop_name',
        'shop_id__shop_code',
    ).annotate(
        total=Count('folder_id'),
        on_time=Count('folder_id', filter=Q(is_on_time=True)),
        late=Count('folder_id', filter=Q(is_late=True)),
        not_received=Count('folder_id', filter=Q(folder_status_id__is_not_received_yet=True) | Q(lastest_received_date__isnull=True)),
    ).order_by('-total')

    for row in by_shop_area:
        total = row['total'] or 0
        on_time = row['on_time'] or 0
        late = row['late'] or 0
        not_received = row['not_received'] or 0
        ratio = round((on_time / total) * 100, 2) if total else 0.0
        late_rate = round((late / total) * 100, 2) if total else 0.0
        not_received_rate = round((not_received / total) * 100, 2) if total else 0.0
        region_id = row['manager_id__regionManager__regionManager_id'] or 'none'
        area_id = row['manager_id__areaManager__areaManager_id'] or ''
        if region_id not in region_map:
            region_map[region_id] = {
                'id': region_id,
                'name': 'Chưa phân vùng',
                'code': '',
                'total': 0,
                'on_time': 0,
                'late': 0,
                'not_received': 0,
                'ratio': 0.0,
                'areas': [],
            }
        area_entry = area_lookup.get((region_id, area_id))
        if not area_entry:
            area_entry = {
                'id': area_id,
                'uid': f"{region_id}_{area_id or 'none'}",
                'name': 'Chưa phân khu vực',
                'code': '',
                'total': 0,
                'on_time': 0,
                'late': 0,
                'not_received': 0,
                'ratio': 0.0,
                'shops': [],
            }
            region_map[region_id]['areas'].append(area_entry)
            area_lookup[(region_id, area_id)] = area_entry
        area_entry['shops'].append({
            'id': row['shop_id'],
            'name': row['shop_id__shop_name'] or 'Không xác định',
            'code': row['shop_id__shop_code'] or '',
            'total': total,
            'on_time': on_time,
            'late': late,
            'not_received': not_received,
            'on_time_rate': ratio,
            'late_rate': late_rate,
            'not_received_rate': not_received_rate,
        })

    for area_entry in area_lookup.values():
        area_entry['shops'] = sorted(area_entry['shops'], key=lambda x: (-x['total'], x['name']))

    for region in region_map.values():
        region['areas'] = sorted(region['areas'], key=lambda x: (x['ratio'], -x['total'], x['name']))
    region_area_rows = sorted(region_map.values(), key=lambda x: (x['ratio'], -x['total'], x['name']))

    by_month = receiving_qs.annotate(month=TruncMonth('folder_created_date')).values('month').annotate(
        total=Count('folder_id'),
        on_time=Count('folder_id', filter=Q(is_on_time=True)),
        late=Count('folder_id', filter=Q(is_late=True)),
        not_received=Count('folder_id', filter=Q(folder_status_id__is_not_received_yet=True) | Q(lastest_received_date__isnull=True)),
    ).order_by('month')

    month_rows = []
    month_chart_rows = []
    prev_month = None
    def change_pct(current, previous):
        if previous in (None, 0):
            return None
        return round(((current - previous) / previous) * 100, 2)
    for row in by_month:
        label = row['month'].strftime('%Y-%m') if row['month'] else ''
        total = row['total'] or 0
        on_time = row['on_time'] or 0
        late = row['late'] or 0
        not_received = row['not_received'] or 0
        month_rows.append({
            'month': label,
            'total': total,
            'on_time': on_time,
            'late': late,
            'not_received': not_received,
            'total_change_pct': change_pct(total, prev_month['total'] if prev_month else None),
            'on_time_change_pct': change_pct(on_time, prev_month['on_time'] if prev_month else None),
            'late_change_pct': change_pct(late, prev_month['late'] if prev_month else None),
            'not_received_change_pct': change_pct(not_received, prev_month['not_received'] if prev_month else None),
        })
        prev_month = {
            'total': total,
            'on_time': on_time,
            'late': late,
            'not_received': not_received,
        }
        if total:
            month_chart_rows.append({
                'month': label,
                'on_time_rate': round((on_time / total) * 100, 2),
                'late_rate': round((late / total) * 100, 2),
                'not_received_rate': round((not_received / total) * 100, 2),
            })
        else:
            month_chart_rows.append({
                'month': label,
                'on_time_rate': 0.0,
                'late_rate': 0.0,
                'not_received_rate': 0.0,
            })

    borrow_base_qs = BorrowingDocument.objects.select_related(
        'borrow_status_id',
        'borrower',
        'documents_id',
        'documents_id__loan_id',
        'documents_id__contract_id',
    ).filter(borrow_date__range=[start_date, end_date])

    borrow_total_count = borrow_base_qs.count()
    borrow_active_qs = borrow_base_qs.filter(borrow_status_id__flag_is_borrowing=True)
    borrow_returned_qs = borrow_base_qs.filter(borrow_status_id__flag_return=True)
    borrow_lost_qs = borrow_base_qs.filter(borrow_status_id__flag_is_lost=True)
    borrow_active_count = borrow_active_qs.count()
    borrow_returned_count = borrow_returned_qs.count()
    borrow_lost_count = borrow_lost_qs.count()
    borrow_overdue_count = borrow_active_qs.filter(appointment_date__lt=today).count()
    borrow_overdue_rate = safe_rate(borrow_overdue_count, borrow_active_count)

    borrow_on_time_count = borrow_returned_qs.filter(
        return_date__isnull=False,
        appointment_date__isnull=False,
        return_date__lte=F('appointment_date'),
    ).count()
    borrow_late_count = borrow_returned_qs.filter(
        return_date__isnull=False,
        appointment_date__isnull=False,
        return_date__gt=F('appointment_date'),
    ).count()
    borrow_on_time_rate = safe_rate(borrow_on_time_count, borrow_total_count)

    borrow_pending_request_qs = BorrowRequest.objects.filter(
        status__in=[BorrowRequestStatus.HANDED_OVER, BorrowRequestStatus.PARTIALLY_RETURNED],
    )
    borrow_pending_request_qs = borrow_pending_request_qs.filter(
        created_at__date__range=[start_date, end_date]
    )
    borrow_pending_request_count = borrow_pending_request_qs.count()

    borrow_by_borrower_raw = borrow_base_qs.values('borrower__shop_name').annotate(
        total=Count('borrow_id'),
        on_time=Count('borrow_id', filter=Q(
            borrow_status_id__flag_return=True,
            return_date__isnull=False,
            appointment_date__isnull=False,
            return_date__lte=F('appointment_date'),
        )),
        late=Count('borrow_id', filter=Q(
            borrow_status_id__flag_return=True,
            return_date__isnull=False,
            appointment_date__isnull=False,
            return_date__gt=F('appointment_date'),
        )),
        active=Count('borrow_id', filter=Q(borrow_status_id__flag_is_borrowing=True)),
        overdue=Count('borrow_id', filter=Q(borrow_status_id__flag_is_borrowing=True, appointment_date__lt=today)),
        loan_count=Count('documents_id__loan_id', distinct=True),
        contract_count=Count('documents_id__contract_id', distinct=True),
    ).order_by('-total')

    borrow_by_borrower = []
    for row in borrow_by_borrower_raw:
        total = row['total'] or 0
        overdue_rate = safe_rate(row['overdue'] or 0, row['active'] or 0)
        borrow_by_borrower.append({
            'borrower': row['borrower__shop_name'] or 'Không xác định',
            'total': total,
            'on_time': row['on_time'] or 0,
            'late': row['late'] or 0,
            'active': row['active'] or 0,
            'overdue': row['overdue'] or 0,
            'overdue_rate': overdue_rate,
            'loan_count': row['loan_count'] or 0,
            'contract_count': row['contract_count'] or 0,
        })

    borrow_pivot_raw = borrow_base_qs.annotate(
        month=TruncMonth('borrow_date')
    ).values('borrower__shop_name', 'month').annotate(
        total=Count('borrow_id'),
        on_time=Count('borrow_id', filter=Q(
            borrow_status_id__flag_return=True,
            return_date__isnull=False,
            appointment_date__isnull=False,
            return_date__lte=F('appointment_date'),
        )),
        late=Count('borrow_id', filter=Q(
            borrow_status_id__flag_return=True,
            return_date__isnull=False,
            appointment_date__isnull=False,
            return_date__gt=F('appointment_date'),
        )),
    ).order_by('borrower__shop_name', 'month')

    borrow_pivot_rows = []
    for row in borrow_pivot_raw:
        month_label = row['month'].strftime('%Y-%m') if row['month'] else ''
        borrow_pivot_rows.append({
            'borrower': row['borrower__shop_name'] or 'Không xác định',
            'month': month_label,
            'total': row['total'] or 0,
            'on_time': row['on_time'] or 0,
            'late': row['late'] or 0,
        })

    borrow_month_rows = []
    borrow_month_chart_rows = []
    prev_borrow = None
    for row in borrow_base_qs.annotate(month=TruncMonth('borrow_date')).values('month').annotate(
        total=Count('borrow_id'),
        on_time=Count('borrow_id', filter=Q(
            borrow_status_id__flag_return=True,
            return_date__isnull=False,
            appointment_date__isnull=False,
            return_date__lte=F('appointment_date'),
        )),
        late=Count('borrow_id', filter=Q(
            borrow_status_id__flag_return=True,
            return_date__isnull=False,
            appointment_date__isnull=False,
            return_date__gt=F('appointment_date'),
        )),
        overdue=Count('borrow_id', filter=Q(
            borrow_status_id__flag_is_borrowing=True,
            appointment_date__lt=today,
        )),
    ).order_by('month'):
        label = row['month'].strftime('%Y-%m') if row['month'] else ''
        total = row['total'] or 0
        on_time = row['on_time'] or 0
        late = row['late'] or 0
        overdue = row['overdue'] or 0
        borrow_month_rows.append({
            'month': label,
            'total': total,
            'on_time': on_time,
            'late': late,
            'overdue': overdue,
            'total_change_pct': change_pct(total, prev_borrow['total'] if prev_borrow else None),
            'on_time_change_pct': change_pct(on_time, prev_borrow['on_time'] if prev_borrow else None),
            'late_change_pct': change_pct(late, prev_borrow['late'] if prev_borrow else None),
            'overdue_change_pct': change_pct(overdue, prev_borrow['overdue'] if prev_borrow else None),
        })
        prev_borrow = {'total': total, 'on_time': on_time, 'late': late, 'overdue': overdue}
        if total:
            borrow_month_chart_rows.append({
                'month': label,
                'on_time_rate': round((on_time / total) * 100, 2),
                'late_rate': round((late / total) * 100, 2),
                'overdue_rate': round((overdue / total) * 100, 2),
            })
        else:
            borrow_month_chart_rows.append({
                'month': label,
                'on_time_rate': 0.0,
                'late_rate': 0.0,
                'overdue_rate': 0.0,
            })

    borrow_late_rows = []
    for row in borrow_returned_qs.filter(
        return_date__isnull=False,
        appointment_date__isnull=False,
        return_date__gt=F('appointment_date'),
    ).select_related('borrower', 'documents_id', 'documents_id__loan_id', 'documents_id__contract_id').order_by('-return_date')[:200]:
        borrow_late_rows.append({
            'borrower': row.borrower.shop_name if row.borrower else 'Không xác định',
            'note': row.note or '',
            'documents_code': row.documents_id.documents_code if row.documents_id else '',
            'contract_code': row.documents_id.contract_id.contract_code if row.documents_id and row.documents_id.contract_id else '',
            'loan_code': row.documents_id.loan_id.loan_code if row.documents_id and row.documents_id.loan_id else '',
            'appointment_date': row.appointment_date,
            'return_date': row.return_date,
        })

    borrow_detail_rows = []
    for row in borrow_base_qs.select_related(
        'borrower', 'documents_id', 'documents_id__loan_id', 'documents_id__contract_id', 'borrow_status_id'
    ).order_by('-borrow_date')[:300]:
        on_time = False
        late = False
        if row.return_date and row.appointment_date:
            on_time = row.return_date <= row.appointment_date
            late = row.return_date > row.appointment_date
        borrow_detail_rows.append({
            'borrower': row.borrower.shop_name if row.borrower else 'Không xác định',
            'documents_code': row.documents_id.documents_code if row.documents_id else '',
            'contract_code': row.documents_id.contract_id.contract_code if row.documents_id and row.documents_id.contract_id else '',
            'loan_code': row.documents_id.loan_id.loan_code if row.documents_id and row.documents_id.loan_id else '',
            'borrow_date': row.borrow_date,
            'appointment_date': row.appointment_date,
            'return_date': row.return_date,
            'status': row.borrow_status_id.borrow_status_name if row.borrow_status_id else '',
            'note': row.note or '',
            'on_time': on_time,
            'late': late,
        })

    def build_productivity_payload(start_date, end_date):
        daily_qs = UserPresenceDaily.objects.filter(work_date__range=[start_date, end_date])
        total_minutes = daily_qs.aggregate(total=Sum('total_active_minutes')).get('total') or 0
        active_users = daily_qs.values('user_id').distinct().count()
        active_days = daily_qs.values('work_date').distinct().count()
        summary = {
            'total_minutes': int(total_minutes),
            'total_hours': round(total_minutes / 60, 2) if total_minutes else 0,
            'active_users': active_users,
            'active_days': active_days,
            'avg_minutes_per_user': round(total_minutes / active_users, 1) if active_users else 0,
            'avg_minutes_per_day': round(total_minutes / active_days, 1) if active_days else 0,
            'peak_hour': None,
            'peak_minutes': 0,
        }
        users = list(
            daily_qs.select_related('user')
            .values('user__username', 'user__first_name', 'user__last_name', 'user__userprofile__department')
            .annotate(
                total_minutes=Sum('total_active_minutes'),
                active_days=Count('work_date', distinct=True),
            )
            .order_by('-total_minutes')
        )

        hourly_qs = UserPresenceHourly.objects.filter(work_date__range=[start_date, end_date]).values('hour').annotate(
            total_seconds=Sum('active_seconds'),
            user_count=Count('user', distinct=True),
        ).order_by('hour')
        hour_map = {row['hour']: row for row in hourly_qs}
        hours = []
        for hour in range(24):
            row = hour_map.get(hour, {})
            minutes = int((row.get('total_seconds') or 0) // 60)
            hours.append({
                'hour': hour,
                'minutes': minutes,
                'user_count': row.get('user_count') or 0,
            })
        if hours:
            peak_row = max(hours, key=lambda x: x['minutes'])
            summary['peak_hour'] = peak_row['hour']
            summary['peak_minutes'] = peak_row['minutes']

        group_qs = UserPresenceHourly.objects.filter(work_date__range=[start_date, end_date]).values(
            'user__userprofile__department', 'hour'
        ).annotate(total_seconds=Sum('active_seconds')).order_by('user__userprofile__department', 'hour')
        group_map = {}
        for row in group_qs:
            group_name = row['user__userprofile__department'] or 'Không xác định'
            group_map.setdefault(group_name, {h: 0 for h in range(24)})
            group_map[group_name][row['hour']] = int((row['total_seconds'] or 0) // 60)
        heatmap_rows = []
        max_minutes = 0
        for group_name, hour_dict in group_map.items():
            for h in range(24):
                max_minutes = max(max_minutes, hour_dict.get(h, 0))
        for group_name, hour_dict in group_map.items():
            cells = []
            for h in range(24):
                minutes = hour_dict.get(h, 0)
                if minutes == 0 or max_minutes == 0:
                    opacity = 0
                else:
                    opacity = round(0.15 + (minutes / max_minutes) * 0.65, 2)
                cells.append({'minutes': minutes, 'opacity': opacity})
            heatmap_rows.append({'group': group_name, 'cells': cells})
        heatmap_rows = sorted(heatmap_rows, key=lambda x: x['group'])

        top_hours = sorted(hours, key=lambda x: x['minutes'], reverse=True)[:5]
        bottom_hours = sorted(hours, key=lambda x: x['minutes'])[:5]

        return summary, users, hours, top_hours, bottom_hours, heatmap_rows

    productivity_summary = {
        'total_minutes': 0,
        'total_hours': 0,
        'active_users': 0,
        'active_days': 0,
        'avg_minutes_per_user': 0,
        'avg_minutes_per_day': 0,
        'peak_hour': None,
        'peak_minutes': 0,
    }
    productivity_users = []
    productivity_hours = []
    productivity_top_hours = []
    productivity_bottom_hours = []
    productivity_heatmap_rows = []
    productivity_suggestions = []
    productivity_hour_labels = list(range(24))

    if tab == 'productivity':
        (
            productivity_summary,
            productivity_users_all,
            productivity_hours,
            productivity_top_hours,
            productivity_bottom_hours,
            productivity_heatmap_rows,
        ) = build_productivity_payload(start_date, end_date)
        productivity_users = productivity_users_all[:10]
        active_window = [row for row in productivity_hours if 7 <= row['hour'] <= 20]
        productivity_top_hours = sorted(active_window, key=lambda x: x['minutes'], reverse=True)[:5]
        productivity_bottom_hours = sorted(active_window, key=lambda x: x['minutes'])[:5]

    context = {
        **user_context,
        'user': user,
        'active_tab': tab,
        'tab_qs': urlencode({k: v for k, v in request.GET.items() if k != 'tab'}),
        'start_date': start_date.strftime("%Y-%m-%d"),
        'end_date': end_date.strftime("%Y-%m-%d"),
        'month': month_str or '',
        'folder_type_id': folder_type_id or '',
        'filter_folder_types': FolderType.objects.filter(is_valid=True).order_by('folder_type_name'),
        'kpi_settings': kpi_settings,
        'kpi_targets': kpi_targets,
        'kpi_labels': kpi_labels,
        'kpi_on_time_warn': kpi_on_time_warn,
        'on_time_count': on_time_count,
        'late_count': late_count,
        'not_received_count': not_received_issue_original_count,
        'total_count': total_count,
        'received_count': received_count,
        'issue_original_total': issue_original_total,
        'ratio_percent': ratio_percent,
        'ratio_numerator': ratio_numerator,
        'ratio_denominator': ratio_denominator,
        'shops_breakdown': shops_combined,
        'region_area_breakdown': region_area_rows,
        'months_breakdown': month_rows,
        'months_chart_json': json.dumps(month_chart_rows, cls=DjangoJSONEncoder, ensure_ascii=False),
        'borrow_months_chart_json': json.dumps(borrow_month_chart_rows, cls=DjangoJSONEncoder, ensure_ascii=False),
        'total_original_count': total_original_count,
        'total_issue_count': total_issue_count,
        'on_time_rate_all': on_time_rate_all,
        'late_rate_all': late_rate_all,
        'not_received_rate_all': not_received_rate_all,
        'original_rate_all': original_rate_all,
        'issue_rate_all': issue_rate_all,
        'borrow_total_count': borrow_total_count,
        'borrow_active_count': borrow_active_count,
        'borrow_returned_count': borrow_returned_count,
        'borrow_lost_count': borrow_lost_count,
        'borrow_overdue_count': borrow_overdue_count,
        'borrow_overdue_rate': borrow_overdue_rate,
        'borrow_on_time_count': borrow_on_time_count,
        'borrow_late_count': borrow_late_count,
        'borrow_on_time_rate': borrow_on_time_rate,
        'borrow_pending_request_count': borrow_pending_request_count,
        'borrow_by_borrower': borrow_by_borrower,
        'borrow_pivot_rows': borrow_pivot_rows,
        'borrow_months_breakdown': borrow_month_rows,
        'borrow_late_rows': borrow_late_rows,
        'borrow_detail_rows': borrow_detail_rows,
        'productivity_summary': productivity_summary,
        'productivity_users': productivity_users,
        'productivity_hours_json': json.dumps(productivity_hours, cls=DjangoJSONEncoder, ensure_ascii=False),
        'productivity_top_hours': productivity_top_hours,
        'productivity_bottom_hours': productivity_bottom_hours,
        'productivity_heatmap_rows': productivity_heatmap_rows,
        'productivity_suggestions': productivity_suggestions,
        'productivity_hour_labels': productivity_hour_labels,
    }
    return render(request, "app_documents/app_document_kpi_v2.html", context)


@login_required
def export_productivity_report(request):
    user = request.user
    user_context = get_user_context(user)
    if not user_context.get("is_admin"):
        messages.error(request, "Bạn không có quyền truy cập dữ liệu.")
        return redirect("document_kpi_v2")

    start_date_str = request.GET.get("start_date")
    end_date_str = request.GET.get("end_date")
    month_str = request.GET.get("month")
    fmt = request.GET.get("format", "xlsx").lower()

    today = timezone.now().date()
    if month_str:
        try:
            year, month = [int(part) for part in month_str.split("-")]
            last_day = calendar.monthrange(year, month)[1]
            start_date = datetime(year, month, 1).date()
            end_date = datetime(year, month, last_day).date()
        except (ValueError, IndexError):
            start_date, end_date = parse_dates(start_date_str, end_date_str)
    else:
        start_date, end_date = parse_dates(start_date_str, end_date_str)
    start_date = start_date or today.replace(day=1)
    end_date = end_date or today

    daily_qs = UserPresenceDaily.objects.filter(work_date__range=[start_date, end_date])
    user_rows = list(
        daily_qs.select_related('user')
        .values('user__username', 'user__first_name', 'user__last_name', 'user__userprofile__department')
        .annotate(
            total_minutes=Sum('total_active_minutes'),
            active_days=Count('work_date', distinct=True),
        )
        .order_by('-total_minutes')
    )
    for row in user_rows:
        row['full_name'] = f"{row.get('user__last_name') or ''} {row.get('user__first_name') or ''}".strip() or row.get('user__username')
        row['department'] = row.get('user__userprofile__department') or 'Không xác định'
        row['total_hours'] = round((row.get('total_minutes') or 0) / 60, 2)

    hourly_qs = UserPresenceHourly.objects.filter(work_date__range=[start_date, end_date]).values('hour').annotate(
        total_seconds=Sum('active_seconds'),
        user_count=Count('user', distinct=True),
    ).order_by('hour')
    hourly_map = {row['hour']: row for row in hourly_qs}
    hourly_rows = []
    for hour in range(24):
        row = hourly_map.get(hour, {})
        minutes = int((row.get('total_seconds') or 0) // 60)
        hourly_rows.append({
            'hour': hour,
            'total_minutes': minutes,
            'user_count': row.get('user_count') or 0,
        })

    if fmt == "csv":
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="productivity_report.csv"'
        writer = csv.writer(response)
        writer.writerow(['username', 'full_name', 'department', 'total_minutes', 'total_hours', 'active_days'])
        for row in user_rows:
            writer.writerow([
                row.get('user__username'),
                row.get('full_name'),
                row.get('department'),
                row.get('total_minutes') or 0,
                row.get('total_hours') or 0,
                row.get('active_days') or 0,
            ])
        return response

    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        pd.DataFrame(user_rows).rename(columns={
            'user__username': 'username',
            'full_name': 'full_name',
            'department': 'department',
            'total_minutes': 'total_minutes',
            'total_hours': 'total_hours',
            'active_days': 'active_days',
        })[['username', 'full_name', 'department', 'total_minutes', 'total_hours', 'active_days']].to_excel(
            writer, sheet_name="Summary", index=False
        )
        pd.DataFrame(hourly_rows).to_excel(writer, sheet_name="Hourly", index=False)
    output.seek(0)
    resp = HttpResponse(
        output.read(),
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    resp["Content-Disposition"] = 'attachment; filename="productivity_report.xlsx"'
    return resp

@login_required
def export_kpi_shop_detail(request):
    user = request.user
    user_context = get_user_context(user)
    if not user_context.get("is_admin"):
        messages.error(request, "Bạn không có quyền truy cập dữ liệu.")
        return redirect("home")

    shop_id = request.GET.get("shop_id")
    if not shop_id or not shop_id.isdigit():
        messages.error(request, "Thiếu phòng giao dịch.")
        return redirect("document_kpi_v2")

    start_date_str = request.GET.get("start_date")
    end_date_str = request.GET.get("end_date")
    month_str = request.GET.get("month")
    folder_type_id = request.GET.get("folder_type_id")

    today = timezone.now().date()
    if month_str:
        try:
            year, month = [int(part) for part in month_str.split("-")]
            last_day = calendar.monthrange(year, month)[1]
            start_date = datetime(year, month, 1).date()
            end_date = datetime(year, month, last_day).date()
        except (ValueError, IndexError):
            start_date, end_date = parse_dates(start_date_str, end_date_str)
    else:
        start_date, end_date = parse_dates(start_date_str, end_date_str)

    start_date = start_date or today.replace(day=1)
    end_date = end_date or today

    qs = Folder.objects.select_related(
        'shop_id',
        'folder_type_id',
        'folder_status_id',
        'manager_id__regionManager',
        'manager_id__areaManager',
    ).filter(
        shop_id=shop_id,
        is_original=True,
        is_issue=True,
        folder_created_date__range=[start_date, end_date],
    ).order_by('folder_created_date')

    if folder_type_id and folder_type_id.isdigit():
        qs = qs.filter(folder_type_id=folder_type_id)

    response = HttpResponse(content_type="text/csv; charset=utf-8")
    filename = f"pgd_detail_{shop_id}_{start_date}_{end_date}.csv"
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    response.write("\ufeff")

    writer = csv.writer(response)
    writer.writerow([
        "Phòng giao dịch",
        "Ngày phát sinh quyển",
        "Loại quyển",
        "Tình trạng đúng hạn",
        "Tình trạng trễ hạn",
        "Tình trạng chưa nhận",
        "Ngày nhận (nếu có)",
        "Khu vực",
        "Vùng",
    ])

    for folder in qs.iterator():
        shop_name = folder.shop_id.shop_name if folder.shop_id else "Không xác định"
        folder_type = folder.folder_type_id.folder_type_name if folder.folder_type_id else ""
        on_time = "Có" if folder.is_on_time else "Không"
        late = "Có" if folder.is_late else "Không"
        not_received = "Có" if folder.folder_status_id and folder.folder_status_id.is_not_received_yet else "Không"
        received_date = folder.lastest_received_date.date().isoformat() if folder.lastest_received_date else ""
        area_name = ""
        region_name = ""
        if folder.manager_id:
            if folder.manager_id.areaManager:
                area_name = folder.manager_id.areaManager.areaManager_name or ""
            if folder.manager_id.regionManager:
                region_name = folder.manager_id.regionManager.regionManager_name or ""
        writer.writerow([
            shop_name,
            folder.folder_created_date.isoformat(),
            folder_type,
            on_time,
            late,
            not_received,
            received_date,
            area_name,
            region_name,
        ])

    return response

@login_required
def gapo_schedule_view(request):
    user = request.user
    user_context = get_user_context(user)
    if not user_context.get("is_admin"):
        messages.error(request, "Bạn không có quyền truy cập tính năng này.")
        return redirect("home")

    if request.method == "POST" and request.POST.get("action"):
        action = request.POST.get("action")
        schedule_id = request.POST.get("schedule_id")
        try:
            schedule = GapoScheduledMessage.objects.get(pk=schedule_id)
        except GapoScheduledMessage.DoesNotExist:
            messages.error(request, "Không tìm thấy lịch gửi.")
            return redirect("gapo_schedule")
        now = timezone.now()
        if action == "retry":
            schedule.status = GapoScheduledMessage.Status.PENDING
            schedule.last_error = None
            schedule.save(update_fields=["status", "last_error", "updated_at"])
            eta = schedule.schedule_at if schedule.schedule_at > now else None
            send_gapo_scheduled_message.apply_async(args=[schedule.id], eta=eta)
            messages.success(request, "Đã retry lịch gửi.")
        elif action == "resend_now":
            schedule.status = GapoScheduledMessage.Status.PENDING
            schedule.last_error = None
            schedule.schedule_at = now
            schedule.save(update_fields=["status", "last_error", "schedule_at", "updated_at"])
            send_gapo_scheduled_message.apply_async(args=[schedule.id])
            messages.success(request, "Đã gửi lại ngay.")
        else:
            messages.error(request, "Hành động không hợp lệ.")
        return redirect("gapo_schedule")

    if request.method == "POST" and not request.POST.get("action"):
        form = GapoScheduleForm(request.POST)
        if form.is_valid():
            schedule = form.save(commit=False)
            schedule.created_by = user
            schedule.save()
            send_gapo_scheduled_message.apply_async(args=[schedule.id], eta=schedule.schedule_at)
            messages.success(request, "Đã lên lịch gửi tin GAPO.")
            return redirect("gapo_schedule")
    else:
        form = GapoScheduleForm()

    schedules = GapoScheduledMessage.objects.order_by("-created_at")[:20]
    context = {
        **user_context,
        "user": user,
        "form": form,
        "schedules": schedules,
    }
    return render(request, "app_documents/app_gapo_schedule.html", context)


@login_required
@require_http_methods(["POST"])
def gapo_ai_generate_view(request):
    user_context = get_user_context(request.user)
    if not user_context.get("is_admin"):
        return JsonResponse({"error": "Bạn không có quyền sử dụng AI soạn tin nhắn."}, status=403)

    try:
        payload = json.loads(request.body.decode("utf-8"))
    except json.JSONDecodeError:
        payload = {}
    base_text = (payload.get("text") or "").strip()
    style = (payload.get("style") or "formal").strip()

    if not base_text:
        return JsonResponse({"error": "Vui lòng nhập nội dung gốc để AI xử lý."}, status=400)

    api_key = getattr(settings, "GEMINI_API_KEY", "") or os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        return JsonResponse({"error": "Chưa cấu hình khóa API cho AI."}, status=500)

    hint = AI_STYLE_HINTS.get(style, "")
    prompt = f"{hint}\nYêu cầu: viết tin nhắn ngắn gọn, rõ ràng bằng tiếng Việt dựa trên nội dung: \"{base_text}\". Trả về đúng phần nội dung tin nhắn."
    request_body = {"contents": [{"parts": [{"text": prompt}]}]}

    try:
        resp = requests.post(
            "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent",
            headers={"Content-Type": "application/json", "X-goog-api-key": api_key},
            json=request_body,
            timeout=10,
        )
        resp.raise_for_status()
        candidates = resp.json().get("candidates", [])
        draft = ""
        if candidates:
            parts = candidates[0].get("content", {}).get("parts", [])
            draft = "".join(part.get("text", "") for part in parts)
        if not draft:
            return JsonResponse({"error": "AI không trả về nội dung. Thử lại sau."}, status=502)
        return JsonResponse({"draft": draft})
    except requests.RequestException as exc:
        logger.error("GAPO AI draft failed", exc_info=exc)
        return JsonResponse({"error": "Gọi AI thất bại. Vui lòng thử lại."}, status=502)

def export_excel_folder_fail(request):
    documents_created_date = request.GET.get('filterfoldermonth', None) 
    # Split mm.YYYY into YYYYmm 
    documents_created_date_month, documents_created_date_year = str(documents_created_date).split(".")
    folder_month = documents_created_date_year+documents_created_date_month
    
    if documents_created_date is None:
        return JsonResponse({'error': 'Missing documents_created_date parameter'}, status=400)
    
    query = f'''WITH folder_fail AS ( 
        SELECT 
            folder_code,
            folder_id,
            folder_created_date,
            qlkv_name,
            qlv_name,
            shop_name,
            foltype.folder_type_name,
            region.region_name
        FROM "f_FolderDetail" folder
        LEFT JOIN "d_Shops" shop ON shop.shop_id = folder.shop_id
        LEFT JOIN "d_Manager" man ON man.manager_id = folder.manager_id 
        LEFT JOIN "d_FolderType" foltype ON foltype.folder_type_id = folder.folder_type_id 
        LEFT JOIN "d_Region" region ON region.region_id = shop.region_id
        WHERE 
            folder.is_issue = true 
            AND folder.is_original = true 
            AND to_char(folder_created_date, 'yyyymm') = '{folder_month}' 
            AND lastest_received_date IS NULL 
    )
    SELECT 
        folder_fail.*,
        loan.loan_code,
        loan.customer_code,
        loan.customer_name,
        loan.employee_code,
        loan.employee_name,
        doctype.document_type_name,
        bus.business_type_name
    FROM "f_DocumentsDetail" doc 
    RIGHT JOIN folder_fail ON doc.folder_id = folder_fail.folder_id
    LEFT JOIN "d_DocumentType" doctype ON doctype.document_type_id = doc.document_type_id 
    LEFT JOIN "d_LoanDetail" loan ON loan.loan_id = doc.loan_id 
    LEFT JOIN "d_BusinessType" bus ON bus.business_type_id = doc.business_type_id 
    WHERE to_char(doc.documents_created_date, 'yyyymm') = '{folder_month}' '''
    with connection.cursor() as cursor:
        cursor.execute(query)
        columns = [col[0] for col in cursor.description]
        results = cursor.fetchall()

    if not results:
        return JsonResponse({'error': 'No data found for the given date'}, status=404)
        
    # Create an Excel workbook and add a worksheet
    wb = Workbook()
    ws = wb.active
    ws.title = "Folder Fail Data"
    
    # Write column headers
    for col_num, column_title in enumerate(columns, 1):
        cell = ws.cell(row=1, column=col_num)
        cell.value = column_title
    
    # Write data rows
    for row_num, row_data in enumerate(results, 2):
        for col_num, cell_value in enumerate(row_data, 1):
            cell = ws.cell(row=row_num, column=col_num)
            cell.value = cell_value
    
    # Create a response object
    response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Content-Disposition'] = f'attachment; filename=folder_fail_data_{folder_month}.xlsx'
    
    # Save the workbook to the response
    wb.save(response)
    
    return response

@login_required
def historical_folder_view(request):
    user = request.user
    user_context = get_user_context(user)
   
    if not user_context['is_admin'] and not user_context['is_checker']:
        return redirect('home')
    filters = {}
    # Lấy giá trị từ các bộ lọc
    choice_shop = request.GET.get('choice_shop')
    choice_folder_code = request.GET.get('choice_folder_code')
    choice_folder_type = request.GET.get('choice_folder_type')
    choice_folder_status = request.GET.get('choice_folder_status')
    filter_package = request.GET.get('filter_package')
    # Áp dụng các bộ lọc nếu có
    if choice_shop:
        filters['shop_id__shop_name__icontains'] = choice_shop
    if choice_folder_code:
        filters['folder_code__icontains'] = choice_folder_code
    if choice_folder_type:
        filters['folder_type_id'] = choice_folder_type
    if choice_folder_status:
        filters['folder_status_id'] = choice_folder_status
    if filter_package:
        filters['package_id__package_code__icontains'] = filter_package

    # Lọc dữ liệu từ HistoricalFolder theo các bộ lọc
    folder_detail = HistoricalFolder.objects.filter(**filters).order_by('folder_created_date')
    # Phân trang kết quả
    paginator = Paginator(folder_detail, 50)
    page_number = request.GET.get('page')
    folder_detail = paginator.get_page(page_number)
    # Chuẩn bị các dữ liệu cho template
    context = {
        **user_context,
        'user': user,
        'folder_detail': folder_detail,
        'drop_list_shops': Shop.objects.all(),
        'drop_list_folder_type': FolderType.objects.all(),
        'drop_list_folder_status': FolderStatus.objects.all(),
    }
    return render(request, 'app_documents/app_historical_folder.html', context)

@login_required
def historical_documents_view(request):
    user = request.user
    user_context = get_user_context(user)
   
    if not user_context['is_admin'] and not user_context['is_checker']:
        return redirect('home')
    
    filters = {}
    # Lấy giá trị từ các bộ lọc
    choice_shop = request.GET.get('choice_shop')
    choice_documents_code = request.GET.get('choice_documents_code')
    choice_document_type = request.GET.get('choice_document_type')
    choice_business_type = request.GET.get('choice_business_type')
    filter_package = request.GET.get('filter_package')
    
    # Áp dụng các bộ lọc nếu có
    if choice_shop:
        filters['shop_id__shop_name__icontains'] = choice_shop
    if choice_documents_code:
        filters['documents_code__icontains'] = choice_documents_code
    if choice_document_type:
        filters['document_type_name__icontains'] = choice_document_type
    if choice_business_type:
        filters['business_type_name__icontains'] = choice_business_type
    if filter_package:
        filters['package_id__package_code__icontains'] = filter_package

    # Lọc dữ liệu từ HistoricalDocuments theo các bộ lọc
    documents_detail = HistoricalDocuments.objects.filter(**filters).order_by('archived_at')
    
    # Phân trang kết quả
    paginator = Paginator(documents_detail, 50)
    page_number = request.GET.get('page')
    documents_detail = paginator.get_page(page_number)
    
    # Chuẩn bị các dữ liệu cho template
    context = {
        **user_context,
        'user': user,
        'documents_detail': documents_detail,
        'drop_list_shops': Shop.objects.all(),
        'drop_list_document_type': DocumentType.objects.all(),
        'drop_list_business_type': BusinessType.objects.all(),
    }
    return render(request, 'app_documents/app_historical_document.html', context)

# Yêu cầu thay đổi các quyển chứng từ nhận sai
@login_required
def request_change_folder_view(request, folder_id):
    """Người dùng đề xuất thay đổi thông tin của Folder"""
    if request.method == 'POST':
        folder = Folder.objects.get(folder_id=folder_id)
        if not folder:
            return JsonResponse({'success': False, 'message': 'Không tìm thấy quyển chứng từ.'})
        note = request.POST.get('note', '')
        # Tạo bản ghi yêu cầu thay đổi cho folder
        ChangeRequest.objects.create(
            folder=folder,
            user=request.user,
            request_type='folder',
            note=note
        )
        return JsonResponse({'success': True, 'message': 'Đã gửi đề xuất thay đổi cho admin.'})
    return JsonResponse({'success': False, 'message': 'Invalid request.'})

# Yêu cầu thay đổi các chứng từ duyệt sai
@login_required
def request_change_document_view(request, document_id):
    """Người dùng đề xuất thay đổi thông tin của DocumentsDetail"""
    if request.method == 'POST':
        document = DocumentsDetail.objects.get(documents_id=document_id)
        if not document:
            return JsonResponse({'success': False, 'message': 'Không tìm thấy chứng từ.'})
        note = request.POST.get('note', '')
        # Tạo bản ghi yêu cầu thay đổi cho document
        ChangeRequest.objects.create(
            document=document,
            user=request.user,
            request_type='document',
            note=note
        )
        return JsonResponse({'success': True, 'message': 'Đã gửi đề xuất thay đổi cho admin.'})
    return JsonResponse({'success': False, 'message': 'Invalid request.'})


# Borrow request helpers
def _borrow_request_log(borrow_request, action, from_status=None, to_status=None, user=None, item=None, note=None, meta=None):
    BorrowRequestLog.objects.create(
        borrow_request=borrow_request,
        item=item,
        action=action,
        from_status=from_status,
        to_status=to_status,
        note=note,
        meta=meta,
        created_by=user,
    )


def _refresh_borrow_request_status(borrow_request):
    items = list(borrow_request.items.all())
    if not items:
        if borrow_request.status != BorrowRequestStatus.PENDING:
            borrow_request.status = BorrowRequestStatus.PENDING
            borrow_request.save(update_fields=['status'])
        return

    statuses = {item.status for item in items}
    if statuses.issubset({BorrowRequestItemStatus.RETURNED, BorrowRequestItemStatus.LOST, BorrowRequestItemStatus.CANCELLED}):
        borrow_request.status = BorrowRequestStatus.RETURNED
    elif BorrowRequestItemStatus.HANDED_OVER in statuses or BorrowRequestItemStatus.RETURNED in statuses or BorrowRequestItemStatus.LOST in statuses:
        if BorrowRequestItemStatus.ASSIGNED in statuses or BorrowRequestItemStatus.PENDING in statuses:
            borrow_request.status = BorrowRequestStatus.PARTIALLY_RETURNED
        else:
            borrow_request.status = BorrowRequestStatus.HANDED_OVER
    elif statuses.issubset({BorrowRequestItemStatus.ASSIGNED, BorrowRequestItemStatus.PENDING}):
        borrow_request.status = BorrowRequestStatus.ASSIGNED
    else:
        borrow_request.status = BorrowRequestStatus.PARTIALLY_RETURNED

    borrow_request.save(update_fields=['status'])


def _has_missing_document_checking_status(document):
    checking_status = getattr(document, 'status_id', None)
    checking_status_type = getattr(checking_status, 'checking_status_type', None)
    return bool(checking_status_type and checking_status_type.is_missing_document)


def _get_borrow_contact_recipient(recipient_id):
    if not recipient_id or not str(recipient_id).isdigit():
        return None
    return (
        AdmParcelRecipientCatalog.objects.filter(
            pk=int(recipient_id),
            import_batch__is_current=True,
            is_active_member=True,
        )
        .only(
            'id',
            'full_name',
            'employee_code',
            'gapo_user_id',
            'email',
            'phone_number',
        )
        .first()
    )


def _get_borrower_for_contact_recipient(recipient):
    department_name = (getattr(recipient, 'department_name', '') or '').strip()
    if not department_name:
        return None
    return Shop.objects.filter(for_borrow_only=True, shop_name__iexact=department_name).first()


def _apply_borrow_contact_snapshot(borrow_request, recipient, contact_email=None, contact_phone=None):
    if recipient:
        borrow_request.contact_recipient = recipient
        borrow_request.contact_name = recipient.full_name or None
        borrow_request.contact_employee_code = recipient.employee_code or None
        borrow_request.contact_gapo_user_id = recipient.gapo_user_id or None
        borrow_request.contact_email = recipient.email or ((contact_email or '').strip() or None)
        borrow_request.contact_phone = recipient.phone_number or ((contact_phone or '').strip() or None)
    else:
        borrow_request.contact_recipient = None
        borrow_request.contact_name = None
        borrow_request.contact_employee_code = None
        borrow_request.contact_gapo_user_id = None
        borrow_request.contact_email = (contact_email or '').strip() or None
        borrow_request.contact_phone = (contact_phone or '').strip() or None


@login_required
def borrow_contact_recipient_search(request):
    user_context = get_user_context(request.user)
    if not user_context['is_admin'] and not user_context['is_checker']:
        return JsonResponse({'results': []}, status=403)

    current_batch = (
        AdmParcelRecipientImportBatch.objects.filter(is_current=True)
        .order_by('-created_at')
        .first()
    )
    if not current_batch:
        return JsonResponse({'results': []})

    query = (request.GET.get('q') or '').strip()
    selected_id = (request.GET.get('selected_id') or '').strip()
    queryset = current_batch.recipients.filter(is_active_member=True)
    if selected_id.isdigit():
        queryset = queryset.filter(pk=int(selected_id))
    else:
        if not query:
            return JsonResponse({'results': []})
        phone_query = ''.join(ch for ch in query if ch.isdigit())
        looks_like_phone = phone_query and all(ch.isdigit() or ch in ' +-.()' for ch in query)
        if looks_like_phone:
            queryset = queryset.filter(phone_number_normalized=phone_query)
        else:
            queryset = queryset.filter(
                Q(full_name__icontains=query)
                | Q(employee_code__icontains=query)
                | Q(email__icontains=query)
            )

    recipients = list(queryset.order_by('full_name', 'employee_code')[:20])
    department_names = {
        (recipient.department_name or '').strip().lower()
        for recipient in recipients
        if (recipient.department_name or '').strip()
    }
    borrower_by_department = {
        (shop.shop_name or '').strip().lower(): shop
        for shop in Shop.objects.filter(for_borrow_only=True, shop_name__isnull=False)
        if (shop.shop_name or '').strip().lower() in department_names
    }
    results = []
    for recipient in recipients:
        borrower = borrower_by_department.get((recipient.department_name or '').strip().lower())
        label = ' - '.join(
            part
            for part in [
                recipient.full_name,
                recipient.employee_code,
                recipient.department_name,
            ]
            if part
        )
        results.append({
            'id': recipient.id,
            'full_name': recipient.full_name,
            'employee_code': recipient.employee_code,
            'department_name': recipient.department_name,
            'gapo_user_id': recipient.gapo_user_id,
            'phone_number': recipient.phone_number,
            'email': recipient.email,
            'borrower_id': borrower.shop_id if borrower else '',
            'borrower_name': borrower.shop_name if borrower else '',
            'label': label,
        })
    return JsonResponse({'results': results})


#BORROW
@login_required
def borrow_request_management_v2(request):
    user = request.user
    user_context = get_user_context(user)
    if not user_context['is_admin'] and not user_context['is_checker']:
        return redirect('home')

    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'create':
            borrower_id = request.POST.get('borrower_id')
            reference_code = request.POST.get('reference_code')
            needed_date = request.POST.get('needed_date')
            appointment_date = request.POST.get('appointment_date')
            ticket_code = request.POST.get('ticket_code')
            contact_email = request.POST.get('contact_email')
            contact_phone = request.POST.get('contact_phone')
            contact_recipient = _get_borrow_contact_recipient(request.POST.get('contact_recipient_id'))
            note = request.POST.get('note')
            if not borrower_id or not needed_date:
                messages.error(request, 'Vui lòng nhập phòng ban và ngày cần.')
                return HttpResponseRedirect(request.META.get('HTTP_REFERER'))
            borrower = Shop.objects.filter(shop_id=borrower_id).first()
            if not borrower:
                messages.error(request, 'Không tìm thấy phòng ban.')
                return HttpResponseRedirect(request.META.get('HTTP_REFERER'))
            try:
                needed_date_value = datetime.strptime(needed_date, "%Y-%m-%d").date()
            except ValueError:
                messages.error(request, 'Ngày cần không hợp lệ.')
                return HttpResponseRedirect(request.META.get('HTTP_REFERER'))
            appointment_date_value = None
            if appointment_date:
                try:
                    appointment_date_value = datetime.strptime(appointment_date, "%Y-%m-%d").date()
                except ValueError:
                    messages.error(request, 'Ngày hẹn trả không hợp lệ.')
                    return HttpResponseRedirect(request.META.get('HTTP_REFERER'))
            new_request = BorrowRequest(
                borrower=_get_borrower_for_contact_recipient(contact_recipient) or borrower,
                requester=user,
                reference_code=reference_code or None,
                needed_date=needed_date_value,
                appointment_date=appointment_date_value,
                ticket_code=ticket_code or None,
                note=note or None,
                status=BorrowRequestStatus.PENDING,
                created_by=user,
                updated_by=user,
            )
            _apply_borrow_contact_snapshot(new_request, contact_recipient, contact_email, contact_phone)
            new_request.save()
            _borrow_request_log(new_request, 'create', None, BorrowRequestStatus.PENDING, user=user)
            return redirect('borrow_request_detail_v2', request_id=new_request.request_id)

    filters = {}
    choice_borrower = (request.GET.get('borrower') or '').strip()
    choice_status = (request.GET.get('status') or '').strip()
    choice_ticket = (request.GET.get('ticket') or '').strip()
    choice_needed_date = (request.GET.get('needed_date') or '').strip()

    if choice_borrower:
        if choice_borrower.isdigit():
            filters['borrower__shop_id'] = choice_borrower
        else:
            filters['borrower__shop_name__icontains'] = choice_borrower
    if choice_status:
        filters['status'] = choice_status
    else:
        filters['status__in'] = [
            BorrowRequestStatus.PENDING,
            BorrowRequestStatus.ASSIGNED,
            BorrowRequestStatus.CANCELLED,
            BorrowRequestStatus.REJECTED,
        ]
    if choice_ticket:
        filters['ticket_code__icontains'] = choice_ticket
    if choice_needed_date:
        date_parts = choice_needed_date.split(' to ')
        if len(date_parts) == 2:
            start_date = datetime.strptime(date_parts[0], "%Y-%m-%d").date()
            end_date = datetime.strptime(date_parts[1], "%Y-%m-%d").date()
            filters['needed_date__range'] = [start_date, end_date]
        elif len(date_parts) == 1:
            single_date = datetime.strptime(date_parts[0], "%Y-%m-%d").date()
            filters['needed_date__range'] = [single_date, single_date]

    qs = BorrowRequest.objects.select_related('borrower', 'requester').prefetch_related('items').annotate(items_count=Count('items')).order_by('-created_at')
    if filters:
        qs = qs.filter(**filters)

    paginator = Paginator(qs, 25)
    page_number = request.GET.get('page')
    borrow_requests = paginator.get_page(page_number)
    today = timezone.now().date()
    for req in borrow_requests:
        overdue_count = 0
        for item in req.items.all():
            if item.status in (BorrowRequestItemStatus.RETURNED, BorrowRequestItemStatus.CANCELLED):
                continue
            due_date = item.appointment_date or req.appointment_date
            if due_date and due_date < today:
                overdue_count += 1
        req.overdue_count = overdue_count

    current = borrow_requests.number if borrow_requests else 1
    total_pages = borrow_requests.paginator.num_pages if borrow_requests else 1
    start_range = max(current - 2, 1)
    end_range = min(current + 2, total_pages)
    page_range_custom = list(range(1, min(2, total_pages) + 1))
    page_range_custom += list(range(start_range, end_range + 1))
    page_range_custom += list(range(max(total_pages - 1, 1), total_pages + 1))
    page_range_custom = sorted(set([p for p in page_range_custom if 1 <= p <= total_pages]))

    qs_no_page = request.GET.copy()
    qs_no_page.pop('page', None)
    base_qs = qs_no_page.urlencode()

    context = {
        **user_context,
        'user': user,
        'borrow_requests': borrow_requests,
        'page_range_custom': page_range_custom,
        'base_qs': base_qs,
        'drop_list_shops': Shop.objects.filter(for_borrow_only=True).order_by('shop_name'),
        'drop_list_request_status': BorrowRequestStatus.choices,
        'is_request_work_queue': not bool(choice_status),
        'filters': {
            'borrower': choice_borrower,
            'status': choice_status,
            'ticket': choice_ticket,
            'needed_date': choice_needed_date,
        },
    }
    return render(request, 'app_documents/app_borrow_request_v2.html', context)


@login_required
def borrow_request_detail_v2(request, request_id):
    user = request.user
    user_context = get_user_context(user)
    if not user_context['is_admin'] and not user_context['is_checker']:
        return redirect('home')

    borrow_request = get_object_or_404(BorrowRequest, request_id=request_id)
    items = borrow_request.items.select_related('documents_id', 'legacy_borrowing').order_by('-created_at')
    has_assigned_items = items.filter(documents_id__isnull=False).exists()
    has_handover_items = items.filter(
        status=BorrowRequestItemStatus.ASSIGNED,
        documents_id__isnull=False,
    ).exists()
    has_handed_over_items = items.filter(
        Q(status__in=[
            BorrowRequestItemStatus.HANDED_OVER,
            BorrowRequestItemStatus.RETURNED,
            BorrowRequestItemStatus.LOST,
        ]) | Q(legacy_borrowing__isnull=False)
    ).exists()
    can_update_request = not has_handed_over_items
    logs = borrow_request.logs.select_related('created_by', 'item').order_by('-created_at')
    status_labels = dict(BorrowRequestStatus.choices)
    status_flow = [
        BorrowRequestStatus.PENDING,
        BorrowRequestStatus.ASSIGNED,
        BorrowRequestStatus.HANDED_OVER,
        BorrowRequestStatus.PARTIALLY_RETURNED,
        BorrowRequestStatus.RETURNED,
        BorrowRequestStatus.CANCELLED,
        BorrowRequestStatus.REJECTED,
    ]
    logs_by_status = {}
    for log in logs:
        status_key = log.to_status or log.from_status or 'unknown'
        logs_by_status.setdefault(status_key, []).append(log)
    log_steps = []
    for status_code in status_flow:
        if status_code in logs_by_status:
            log_steps.append({
                'code': status_code,
                'label': status_labels.get(status_code, status_code),
                'logs': logs_by_status[status_code],
            })
    for status_code, status_logs in logs_by_status.items():
        if status_code in status_flow:
            continue
        log_steps.append({
            'code': status_code,
            'label': status_labels.get(status_code, status_code),
            'logs': status_logs,
        })
    preview_key = (request.GET.get('preview_key') or '').strip()
    preview_rows = []
    preview_error = None

    if preview_key:
        loan_id = LoanDetail.objects.filter(loan_code=preview_key).values_list('loan_id', flat=True).first()
        contract_id = ContractDetail.objects.filter(contract_code=preview_key).values_list('contract_id', flat=True).first()
        document_filter = Q()
        if loan_id:
            document_filter |= Q(loan_id_id=loan_id)
        if contract_id:
            document_filter |= Q(contract_id_id=contract_id)

        documents = []
        if document_filter:
            documents = list(
                DocumentsDetail.objects.select_related(
                    'shop_id',
                    'document_type_id',
                    'business_type_id',
                    'folder_id',
                    'status_id',
                    'status_id__checking_status_type',
                    'document_status_id',
                    'package_id',
                ).filter(document_filter).order_by('documents_created_date', 'documents_id')[:200]
            )
        if not documents:
            preview_error = 'Không tìm thấy chứng từ theo contract_code hoặc loan_code.'
        else:
            doc_ids = [doc.documents_id for doc in documents]
            active_borrow_ids = set(
                BorrowingDocument.objects.filter(
                    documents_id__in=doc_ids,
                    borrow_status_id__flag_return=False,
                ).values_list('documents_id', flat=True)
            )
            assigned_ids = set(
                BorrowRequestItem.objects.filter(
                    borrow_request=borrow_request,
                    documents_id__in=doc_ids,
                ).values_list('documents_id', flat=True)
            )
            for doc in documents:
                reasons = []
                doc_status = doc.document_status_id
                if not doc_status or not doc_status.is_checked:
                    reasons.append('Chưa duyệt')
                if _has_missing_document_checking_status(doc):
                    reasons.append('Thiếu chứng từ')
                if doc_status and doc_status.is_borrow:
                    reasons.append('Đang mượn')
                if doc.documents_id in active_borrow_ids:
                    reasons.append('Đang có giao dịch mượn')
                if doc.documents_id in assigned_ids:
                    reasons.append('Đã gán trong yêu cầu')
                preview_rows.append({
                    'doc': doc,
                    'eligible': not reasons,
                    'reason': ', '.join(reasons),
                })

    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'add_item':
            document_code = (request.POST.get('documents_code') or '').strip()
            if not document_code:
                messages.error(request, 'Vui lòng nhập mã chứng từ.')
                return HttpResponseRedirect(request.META.get('HTTP_REFERER'))
            try:
                document = DocumentsDetail.objects.select_related(
                    'document_status_id',
                    'status_id__checking_status_type',
                ).get(documents_code=document_code)
            except DocumentsDetail.DoesNotExist:
                messages.error(request, 'Không tìm thấy chứng từ.')
                return HttpResponseRedirect(request.META.get('HTTP_REFERER'))
            if document.document_status_id and document.document_status_id.is_borrow:
                messages.error(request, 'Chứng từ đang được mượn.')
                return HttpResponseRedirect(request.META.get('HTTP_REFERER'))
            if not document.document_status_id or not document.document_status_id.is_checked:
                messages.error(request, 'Chứng từ chưa ở trạng thái đã duyệt.')
                return HttpResponseRedirect(request.META.get('HTTP_REFERER'))
            if _has_missing_document_checking_status(document):
                messages.error(request, 'Chứng từ có trạng thái duyệt thiếu chứng từ, không thể mượn.')
                return HttpResponseRedirect(request.META.get('HTTP_REFERER'))
            active_borrow = BorrowingDocument.objects.filter(documents_id=document, borrow_status_id__flag_return=False).exists()
            if active_borrow:
                messages.error(request, 'Chứng từ đang có giao dịch mượn.')
                return HttpResponseRedirect(request.META.get('HTTP_REFERER'))
            item = BorrowRequestItem.objects.create(
                borrow_request=borrow_request,
                documents_id=document,
                appointment_date=borrow_request.appointment_date,
                status=BorrowRequestItemStatus.ASSIGNED,
                created_by=user,
                updated_by=user,
            )
            _borrow_request_log(borrow_request, 'assign_document', borrow_request.status, BorrowRequestStatus.ASSIGNED, user=user, item=item, meta={'documents_id': document.documents_id})
            _refresh_borrow_request_status(borrow_request)
            return HttpResponseRedirect(request.META.get('HTTP_REFERER'))

        if action == 'assign_selected':
            selected_ids = request.POST.getlist('document_ids')
            if not selected_ids:
                messages.error(request, 'Vui lòng chọn chứng từ để gán.')
                return HttpResponseRedirect(request.META.get('HTTP_REFERER'))
            documents = DocumentsDetail.objects.select_related(
                'document_status_id',
                'status_id__checking_status_type',
            ).filter(documents_id__in=selected_ids)
            active_borrow_ids = set(
                BorrowingDocument.objects.filter(
                    documents_id__in=selected_ids,
                    borrow_status_id__flag_return=False,
                ).values_list('documents_id', flat=True)
            )
            existing_ids = set(
                BorrowRequestItem.objects.filter(
                    borrow_request=borrow_request,
                    documents_id__in=selected_ids,
                ).values_list('documents_id', flat=True)
            )
            added_count = 0
            skipped = []
            for doc in documents:
                doc_status = doc.document_status_id
                if doc.documents_id in existing_ids:
                    skipped.append(doc.documents_code)
                    continue
                if not doc_status or not doc_status.is_checked:
                    skipped.append(doc.documents_code)
                    continue
                if _has_missing_document_checking_status(doc):
                    skipped.append(doc.documents_code)
                    continue
                if doc_status.is_borrow or doc.documents_id in active_borrow_ids:
                    skipped.append(doc.documents_code)
                    continue
                item = BorrowRequestItem.objects.create(
                    borrow_request=borrow_request,
                    documents_id=doc,
                    appointment_date=borrow_request.appointment_date,
                    status=BorrowRequestItemStatus.ASSIGNED,
                    created_by=user,
                    updated_by=user,
                )
                _borrow_request_log(borrow_request, 'assign_document', borrow_request.status, BorrowRequestStatus.ASSIGNED, user=user, item=item, meta={'documents_id': doc.documents_id})
                added_count += 1
            if added_count:
                _refresh_borrow_request_status(borrow_request)
                messages.success(request, f'Đã gán {added_count} chứng từ.')
            if skipped:
                messages.warning(request, f'Bỏ qua {len(skipped)} chứng từ không hợp lệ hoặc đã gán.')
            return HttpResponseRedirect(request.META.get('HTTP_REFERER'))

        if action == 'handover':
            items_to_handover = borrow_request.items.select_related(
                'documents_id__document_status_id',
                'documents_id__status_id__checking_status_type',
            ).filter(status=BorrowRequestItemStatus.ASSIGNED, documents_id__isnull=False)
            if not items_to_handover.exists():
                messages.error(request, 'Không có chứng từ để bàn giao.')
                return HttpResponseRedirect(request.META.get('HTTP_REFERER'))
            missing_document_codes = [
                item.documents_id.documents_code
                for item in items_to_handover
                if _has_missing_document_checking_status(item.documents_id)
            ]
            if missing_document_codes:
                messages.error(
                    request,
                    f'Không thể bàn giao {len(missing_document_codes)} chứng từ có trạng thái duyệt thiếu chứng từ.',
                )
                return HttpResponseRedirect(request.META.get('HTTP_REFERER'))
            borrow_status = BorrowingStatus.objects.filter(flag_is_borrowing=True).first()
            if not borrow_status:
                messages.error(request, 'Không tìm thấy trạng thái mượn.')
                return HttpResponseRedirect(request.META.get('HTTP_REFERER'))
            document_status_borrow = DocumentStatus.objects.filter(is_borrow=True).first()
            if not document_status_borrow:
                messages.error(request, 'Không tìm thấy trạng thái chứng từ đang mượn.')
                return HttpResponseRedirect(request.META.get('HTTP_REFERER'))
            for item in items_to_handover:
                legacy = BorrowingDocument.objects.create(
                    documents_id=item.documents_id,
                    borrow_date=timezone.now().date(),
                    appointment_date=item.appointment_date or borrow_request.appointment_date,
                    lender=user,
                    borrower=borrow_request.borrower,
                    borrower_detail=borrow_request.contact_name,
                    ticket_code=borrow_request.ticket_code,
                    note=borrow_request.note,
                    borrow_status_id=borrow_status,
                )
                DocumentsDetail.objects.filter(documents_id=item.documents_id.documents_id).update(
                    document_status_id=document_status_borrow,
                    package_id=None,
                )
                item.legacy_borrowing = legacy
                item.status = BorrowRequestItemStatus.HANDED_OVER
                item.handed_over_date = timezone.now()
                item.updated_by = user
                item.save(update_fields=['legacy_borrowing', 'status', 'handed_over_date', 'updated_by', 'updated_at'])
                _borrow_request_log(borrow_request, 'handover', BorrowRequestStatus.ASSIGNED, BorrowRequestStatus.HANDED_OVER, user=user, item=item)
            _refresh_borrow_request_status(borrow_request)
            messages.success(request, 'Đã bàn giao chứng từ.')
            return HttpResponseRedirect(request.META.get('HTTP_REFERER'))

        if action == 'return_item':
            item_id = request.POST.get('item_id')
            item = get_object_or_404(BorrowRequestItem, item_id=item_id, borrow_request=borrow_request)
            return_status = BorrowingStatus.objects.filter(flag_return=True).first()
            checked_status = DocumentStatus.objects.filter(is_checked=True).first()
            if item.legacy_borrowing and return_status:
                item.legacy_borrowing.borrow_status_id = return_status
                item.legacy_borrowing.return_date = timezone.now().date()
                item.legacy_borrowing.save(update_fields=['borrow_status_id', 'return_date'])
            if item.documents_id and checked_status:
                DocumentsDetail.objects.filter(documents_id=item.documents_id.documents_id).update(document_status_id=checked_status)
            item.status = BorrowRequestItemStatus.RETURNED
            item.return_date = timezone.now()
            item.updated_by = user
            item.save(update_fields=['status', 'return_date', 'updated_by', 'updated_at'])
            _borrow_request_log(borrow_request, 'return', BorrowRequestStatus.HANDED_OVER, BorrowRequestStatus.RETURNED, user=user, item=item)
            _refresh_borrow_request_status(borrow_request)
            messages.success(request, 'Đã hoàn trả chứng từ.')
            return HttpResponseRedirect(request.META.get('HTTP_REFERER'))

        if action == 'lost_item':
            item_id = request.POST.get('item_id')
            item = get_object_or_404(BorrowRequestItem, item_id=item_id, borrow_request=borrow_request)
            lost_status = BorrowingStatus.objects.filter(flag_is_lost=True).first()
            doc_lost_status = DocumentStatus.objects.filter(is_lost=True).first()
            if item.legacy_borrowing and lost_status:
                item.legacy_borrowing.borrow_status_id = lost_status
                item.legacy_borrowing.save(update_fields=['borrow_status_id'])
            if item.documents_id and doc_lost_status:
                DocumentsDetail.objects.filter(documents_id=item.documents_id.documents_id).update(document_status_id=doc_lost_status)
            item.status = BorrowRequestItemStatus.LOST
            item.updated_by = user
            item.save(update_fields=['status', 'updated_by', 'updated_at'])
            _borrow_request_log(borrow_request, 'lost', BorrowRequestStatus.HANDED_OVER, BorrowRequestStatus.PARTIALLY_RETURNED, user=user, item=item)
            _refresh_borrow_request_status(borrow_request)
            messages.success(request, 'Đã cập nhật báo mất.')
            return HttpResponseRedirect(request.META.get('HTTP_REFERER'))

        if action == 'cancel_request':
            if has_assigned_items:
                messages.error(request, 'Phiếu đã có chứng từ, không thể hủy.')
                return HttpResponseRedirect(request.META.get('HTTP_REFERER'))
            from_status = borrow_request.status
            borrow_request.status = BorrowRequestStatus.CANCELLED
            borrow_request.updated_by = user
            borrow_request.save(update_fields=['status', 'updated_by', 'updated_at'])
            _borrow_request_log(borrow_request, 'cancel', from_status, BorrowRequestStatus.CANCELLED, user=user)
            messages.success(request, 'Đã hủy yêu cầu.')
            return HttpResponseRedirect(request.META.get('HTTP_REFERER'))

        if action == 'update_request':
            if not can_update_request:
                messages.error(request, 'Phiếu đã bàn giao chứng từ, không thể cập nhật thông tin yêu cầu.')
                return HttpResponseRedirect(request.META.get('HTTP_REFERER'))

            borrower_id = request.POST.get('borrower_id')
            needed_date = request.POST.get('needed_date')
            appointment_date = request.POST.get('appointment_date')
            contact_recipient = _get_borrow_contact_recipient(request.POST.get('contact_recipient_id'))

            borrower = Shop.objects.filter(shop_id=borrower_id, for_borrow_only=True).first()
            if not borrower:
                messages.error(request, 'Phòng ban mượn không hợp lệ.')
                return HttpResponseRedirect(request.META.get('HTTP_REFERER'))
            try:
                borrow_request.needed_date = datetime.strptime(needed_date, "%Y-%m-%d").date()
            except (TypeError, ValueError):
                messages.error(request, 'Ngày mượn không hợp lệ.')
                return HttpResponseRedirect(request.META.get('HTTP_REFERER'))
            if appointment_date:
                try:
                    borrow_request.appointment_date = datetime.strptime(appointment_date, "%Y-%m-%d").date()
                except ValueError:
                    messages.error(request, 'Ngày hẹn trả không hợp lệ.')
                    return HttpResponseRedirect(request.META.get('HTTP_REFERER'))
            else:
                borrow_request.appointment_date = None

            borrow_request.borrower = _get_borrower_for_contact_recipient(contact_recipient) or borrower
            borrow_request.reference_code = (request.POST.get('reference_code') or '').strip() or None
            borrow_request.ticket_code = (request.POST.get('ticket_code') or '').strip() or None
            _apply_borrow_contact_snapshot(
                borrow_request,
                contact_recipient,
                request.POST.get('contact_email'),
                request.POST.get('contact_phone'),
            )
            borrow_request.note = (request.POST.get('note') or '').strip() or None
            borrow_request.updated_by = user
            borrow_request.save(update_fields=[
                'borrower',
                'contact_recipient',
                'contact_name',
                'contact_employee_code',
                'contact_gapo_user_id',
                'needed_date',
                'appointment_date',
                'reference_code',
                'ticket_code',
                'contact_email',
                'contact_phone',
                'note',
                'updated_by',
                'updated_at',
            ])
            borrow_request.items.filter(
                status=BorrowRequestItemStatus.ASSIGNED,
                legacy_borrowing__isnull=True,
            ).update(appointment_date=borrow_request.appointment_date, updated_by_id=user.pk, updated_at=timezone.now())
            _borrow_request_log(borrow_request, 'update', borrow_request.status, borrow_request.status, user=user)
            messages.success(request, 'Đã cập nhật yêu cầu.')
            return HttpResponseRedirect(request.META.get('HTTP_REFERER'))

        if action == 'update_item_appointment':
            if not can_update_request:
                messages.error(request, 'Phiếu đã bàn giao chứng từ, không thể cập nhật ngày hẹn trả.')
                return HttpResponseRedirect(request.META.get('HTTP_REFERER'))
            item_id = request.POST.get('item_id')
            appointment_date = request.POST.get('appointment_date')
            if not item_id or not appointment_date:
                messages.error(request, 'Vui lòng chọn ngày hẹn trả.')
                return HttpResponseRedirect(request.META.get('HTTP_REFERER'))
            item = get_object_or_404(BorrowRequestItem, item_id=item_id, borrow_request=borrow_request)
            if item.status != BorrowRequestItemStatus.ASSIGNED or item.legacy_borrowing_id:
                messages.error(request, 'Chứng từ đã bàn giao, không thể cập nhật ngày hẹn trả.')
                return HttpResponseRedirect(request.META.get('HTTP_REFERER'))
            try:
                appointment_date_value = datetime.strptime(appointment_date, "%Y-%m-%d").date()
            except ValueError:
                messages.error(request, 'Ngày hẹn trả không hợp lệ.')
                return HttpResponseRedirect(request.META.get('HTTP_REFERER'))
            item.appointment_date = appointment_date_value
            item.updated_by = user
            item.save(update_fields=['appointment_date', 'updated_by', 'updated_at'])
            if item.legacy_borrowing:
                item.legacy_borrowing.appointment_date = appointment_date_value
                item.legacy_borrowing.save(update_fields=['appointment_date'])
            _borrow_request_log(
                borrow_request,
                'Cập nhật hẹn trả',
                borrow_request.status,
                borrow_request.status,
                user=user,
                item=item,
                note=f'Hẹn trả: {appointment_date_value.strftime("%Y-%m-%d")}',
            )
            messages.success(request, 'Đã cập nhật ngày hẹn trả.')
            return HttpResponseRedirect(request.META.get('HTTP_REFERER'))

    context = {
        **user_context,
        'user': user,
        'borrow_request': borrow_request,
        'items': items,
        'has_assigned_items': has_assigned_items,
        'has_handover_items': has_handover_items,
        'can_update_request': can_update_request,
        'logs': logs,
        'log_steps': log_steps,
        'preview_key': preview_key,
        'preview_rows': preview_rows,
        'preview_error': preview_error,
        'drop_list_shops': Shop.objects.filter(for_borrow_only=True).order_by('shop_name'),
        'status_choices': BorrowRequestStatus.choices,
    }
    return render(request, 'app_documents/app_borrow_request_detail_v2.html', context)


@csrf_exempt
def api_borrow_request_create(request):
    api_key_setting = getattr(settings, 'BORROW_REQUEST_API_KEY', '') or os.environ.get('BORROW_REQUEST_API_KEY', '')
    if not api_key_setting:
        return JsonResponse({'success': False, 'error': 'API key not configured.'}, status=503)
    client_key = (
        request.headers.get('X-API-KEY')
        or request.headers.get('X-Api-Key')
        or request.headers.get('x-api-key')
        or request.META.get('HTTP_X_API_KEY')
    )
    if not client_key or not secrets.compare_digest(client_key, api_key_setting):
        return JsonResponse({'success': False, 'error': 'Unauthorized'}, status=401)
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Invalid request'}, status=400)
    try:
        data = json.loads(request.body)
    except Exception:
        data = request.POST
    borrower_id = data.get('borrower_id')
    needed_date = data.get('needed_date')
    appointment_date = data.get('appointment_date')
    reference_code = data.get('reference_code')
    ticket_code = data.get('ticket_code')
    contact_email = data.get('contact_email')
    contact_phone = data.get('contact_phone')
    contact_recipient = _get_borrow_contact_recipient(data.get('contact_recipient_id'))
    note = data.get('note')
    source_system = data.get('source_system')
    external_ref = data.get('external_ref')
    if not borrower_id or not needed_date:
        return JsonResponse({'success': False, 'error': 'borrower_id and needed_date are required.'}, status=400)
    borrower = Shop.objects.filter(shop_id=borrower_id).first()
    if not borrower:
        return JsonResponse({'success': False, 'error': 'Borrower not found.'}, status=404)
    user = request.user if request.user.is_authenticated else None
    borrow_request = BorrowRequest(
        borrower=_get_borrower_for_contact_recipient(contact_recipient) or borrower,
        requester=user,
        reference_code=reference_code or None,
        needed_date=needed_date,
        appointment_date=appointment_date or None,
        ticket_code=ticket_code or None,
        note=note or None,
        status=BorrowRequestStatus.PENDING,
        source_system=source_system or None,
        external_ref=external_ref or None,
        created_by=user,
        updated_by=user,
    )
    _apply_borrow_contact_snapshot(borrow_request, contact_recipient, contact_email, contact_phone)
    borrow_request.save()
    _borrow_request_log(borrow_request, 'create', None, BorrowRequestStatus.PENDING, user=user, meta={'source_system': source_system, 'external_ref': external_ref})
    return JsonResponse({'success': True, 'request_id': borrow_request.request_id})


@login_required
@require_http_methods(["POST"])
def api_user_heartbeat(request):
    now = timezone.now()
    work_date = now.date()
    active_gap = getattr(settings, 'USER_PRESENCE_ACTIVE_GAP', 120)
    presence, created = UserPresenceDaily.objects.get_or_create(
        user=request.user,
        work_date=work_date,
        defaults={'last_seen_at': now, 'first_seen_at': now},
    )
    if not created and presence.last_seen_at:
        delta = (now - presence.last_seen_at).total_seconds()
        if 0 < delta <= active_gap:
            presence.total_active_seconds += int(delta)
    if not presence.first_seen_at:
        presence.first_seen_at = now
    presence.last_seen_at = now
    presence.total_active_minutes = int(presence.total_active_seconds // 60)
    presence.save(update_fields=['first_seen_at', 'last_seen_at', 'total_active_seconds', 'total_active_minutes', 'updated_at'])

    hour_bucket = now.hour
    hourly, created_hourly = UserPresenceHourly.objects.get_or_create(
        user=request.user,
        work_date=work_date,
        hour=hour_bucket,
        defaults={'first_seen_at': now, 'last_seen_at': now},
    )
    if not created_hourly and hourly.last_seen_at:
        delta = (now - hourly.last_seen_at).total_seconds()
        if 0 < delta <= active_gap:
            hourly.active_seconds += int(delta)
    if not hourly.first_seen_at:
        hourly.first_seen_at = now
    hourly.last_seen_at = now
    hourly.save(update_fields=['first_seen_at', 'last_seen_at', 'active_seconds', 'updated_at'])
    return JsonResponse({'success': True})


@login_required
def online_users_view(request):
    user = request.user
    user_context = get_user_context(user)
    if not user_context['is_admin']:
        return redirect('home')

    now = timezone.now()
    online_window = getattr(settings, 'USER_PRESENCE_ONLINE_WINDOW', 300)
    cutoff = now - timedelta(seconds=online_window)
    today = now.date()
    presences = list(UserPresenceDaily.objects.select_related('user').filter(work_date=today).order_by('-last_seen_at'))
    for presence in presences:
        presence.is_online = bool(presence.last_seen_at and presence.last_seen_at >= cutoff)
        presence.total_hours = round((presence.total_active_seconds or 0) / 3600, 2)
        if presence.last_seen_at:
            presence.idle_minutes = int((now - presence.last_seen_at).total_seconds() // 60)
        else:
            presence.idle_minutes = None
    max_active_seconds = max([p.total_active_seconds or 0 for p in presences], default=0)
    for presence in presences:
        if max_active_seconds:
            presence.activity_pct = round((presence.total_active_seconds or 0) * 100 / max_active_seconds, 1)
        else:
            presence.activity_pct = 0
    total_count = len(presences)
    online_count = sum(1 for p in presences if p.is_online)
    total_hours_sum = round(sum((p.total_active_seconds or 0) for p in presences) / 3600, 2)
    online_ratio = round((online_count / total_count) * 100, 1) if total_count else 0
    offline_ratio = round(((total_count - online_count) / total_count) * 100, 1) if total_count else 0
    context = {
        **user_context,
        'presences': presences,
        'cutoff': cutoff,
        'today': today,
        'total_count': total_count,
        'online_count': online_count,
        'offline_count': total_count - online_count,
        'total_hours_sum': total_hours_sum,
        'max_active_seconds': max_active_seconds,
        'online_ratio': online_ratio,
        'offline_ratio': offline_ratio,
    }
    return render(request, 'app_documents/app_online_users_v2.html', context)

@login_required
def borrow_document_management_v2(request):
    user = request.user
    user_context = get_user_context(user)
    if not user_context['is_admin'] and not user_context['is_checker']:
        return redirect('home')

    filters = {}
    choice_document_code = (request.GET.get('document_code') or '').strip()
    choice_borrower = (request.GET.get('borrower') or '').strip()
    choice_status = (request.GET.get('borrow_status') or '').strip()

    if choice_document_code:
        filters['documents_id__documents_code__icontains'] = choice_document_code
    if choice_borrower:
        if choice_borrower.isdigit():
            filters['borrower__shop_id'] = choice_borrower
        else:
            filters['borrower__shop_name__icontains'] = choice_borrower
    if choice_status:
        filters['borrow_status_id'] = choice_status

    request_item_qs = BorrowRequestItem.objects.select_related('borrow_request').order_by('-created_at')
    borrow_qs = BorrowingDocument.objects.select_related(
        'documents_id',
        'documents_id__loan_id',
        'documents_id__contract_id',
        'borrower',
        'borrow_status_id',
        'lender',
    ).prefetch_related(
        Prefetch('request_items', queryset=request_item_qs, to_attr='linked_request_items')
    ).order_by('-borrow_date', '-borrow_id')
    if filters:
        borrow_qs = borrow_qs.filter(**filters)

    paginator = Paginator(borrow_qs, 25)
    page_number = request.GET.get('page')
    borrow_list = paginator.get_page(page_number)
    for borrow in borrow_list:
        linked_items = getattr(borrow, 'linked_request_items', [])
        borrow.request_item = linked_items[0] if linked_items else None
        borrow.borrow_request = borrow.request_item.borrow_request if borrow.request_item else None

    current = borrow_list.number if borrow_list else 1
    total_pages = paginator.num_pages if paginator else 1
    start_range = max(current - 2, 1)
    end_range = min(current + 2, total_pages)
    page_range_custom = list(range(1, min(2, total_pages) + 1))
    page_range_custom += list(range(start_range, end_range + 1))
    page_range_custom += list(range(max(total_pages - 1, 1), total_pages + 1))
    page_range_custom = sorted(set([p for p in page_range_custom if 1 <= p <= total_pages]))

    qs_no_page = request.GET.copy()
    qs_no_page.pop('page', None)
    base_qs = qs_no_page.urlencode()

    context = {
        **user_context,
        'user': user,
        'borrow_list': borrow_list,
        'page_range_custom': page_range_custom,
        'paginator': paginator,
        'base_qs': base_qs,
        'drop_list_shops': Shop.objects.filter(for_borrow_only=True).order_by('shop_name'),
        'drop_list_borrowing_status': BorrowingStatus.objects.all().order_by('borrow_status_name'),
        'filters': {
            'document_code': choice_document_code,
            'borrower': choice_borrower,
            'borrow_status': choice_status,
        },
    }
    return render(request, 'app_documents/app_borrow_document_v2.html', context)


@login_required
def request_borrow_document_view(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            document_id = data.get('document_id')
            borrower_id = data.get('borrower_id')
            borrow_date = data.get('borrow_date')
            ticket_code = data.get('ticket_code')
            appointment_date = data.get('appointment_date')
            borrower_detail = data.get('borrower_detail')
            note = data.get('note')
            # Kiểm tra chứng từ có tồn tại không
            try:
                documents = DocumentsDetail.objects.select_related(
                    'document_status_id',
                    'status_id__checking_status_type',
                ).get(documents_id=document_id)
            except DocumentsDetail.DoesNotExist:
                return JsonResponse({"success": False, "message": "Chứng từ không tồn tại."}, status=404)
            if not documents.document_status_id or not documents.document_status_id.is_checked:
                return JsonResponse({"success": False, "message": "Chứng từ chưa ở trạng thái đã duyệt."}, status=400)
            if _has_missing_document_checking_status(documents):
                return JsonResponse({"success": False, "message": "Chứng từ có trạng thái duyệt thiếu chứng từ, không thể mượn."}, status=400)
            # Kiểm tra phòng ban có tồn tại không
            try:
                borrower = Shop.objects.get(shop_id=borrower_id)
            except Shop.DoesNotExist:
                return JsonResponse({"success": False, "message": "Phòng ban không tồn tại."}, status=404)
            # Kiểm tra trạng thái mượn có tồn tại không
            try:
                borrow_status = BorrowingStatus.objects.get(flag_is_borrowing=True)
            except BorrowingStatus.DoesNotExist:
                return JsonResponse({"success": False, "message": "Không tìm thấy trạng thái mượn."}, status=404)
            # Kiểm tra xem có bản ghi mượn nào chưa trả hay không
            borrow_document = BorrowingDocument.objects.filter(
                documents_id=document_id,
                borrow_status_id__flag_return=False
            ).first()
            # Nếu chưa có chứng từ mượn, thì tạo 1 transaction mượn chứng từ
            if not borrow_document:
                # Tạo mới bản ghi BorrowingDocument
                BorrowingDocument.objects.create(
                    documents_id=documents,
                    borrow_date=borrow_date,
                    appointment_date=appointment_date,
                    lender=request.user,
                    borrower=borrower,
                    borrower_detail = borrower_detail ,
                    ticket_code= ticket_code,
                    note=note,
                    borrow_status_id=borrow_status
                )
                # Cập nhật trạng thái của chứng từ thành trạng thái có `is_borrow=True` đang mượn. 
                document_status = DocumentStatus.objects.get(is_borrow=True)
                if document_status:
                    documents.document_status_id = document_status
                    documents.save()
            else:
                # Cập nhật bản ghi mượn hiện tại nếu đã tồn tại mà chưa trả
                JsonResponse({'success': True, 'message': 'Chứng từ này đang cho mượn rồi. Vui lòng kiểm tra lại'})
            return JsonResponse({'success': True, 'message': 'Cho mượn chứng từ thành công.'})
        except Exception as e:
            return JsonResponse({"success": False, "message": f"Lỗi: {str(e)}"}, status=400)
    return JsonResponse({"success": False, "message": "Phương thức không hợp lệ."}, status=400)

@login_required
def manage_borrow_document(request, document_id, action):
    if request.method == 'POST':  # Chỉ chấp nhận POST requests
        # Lấy document dựa trên document_id
        document = get_object_or_404(DocumentsDetail, documents_id=document_id)
        # Lấy borrow record gần nhất cho document này với trạng thái đang mượn
        borrow_record_active = BorrowingDocument.objects.filter(documents_id=document, borrow_status_id__flag_is_borrowing=True).first()
        try: 
            data = json.loads(request.body) 
            return_date = data.get('return_date') 
            if return_date == '': 
                return_date = datetime.now()
        except Exception as e:
            return_date = datetime.now()
            return JsonResponse({"success": False, "message": f"Lỗi: {str(e)}"}, status=400)
        
        if borrow_record_active:
            if action == 'return':
                # Cập nhật trạng thái document và borrow record khi hoàn trả
                document_status = DocumentStatus.objects.get(is_checked=True)  # Lấy trạng thái "Đã duyệt"
                if document_status:
                    document.document_status_id = document_status
                    document.save()
                # Lấy trạng thái "Đã trả" của borrow record
                borrow_status = BorrowingStatus.objects.get(flag_return=True) 
                if borrow_status:
                    borrow_record_active.borrow_status_id = borrow_status
                    borrow_record_active.return_date = return_date
                    borrow_record_active.save()
            elif action == 'lost':
                # Cập nhật trạng thái document và borrow record khi báo mất
                document_status = DocumentStatus.objects.get(is_lost=True)  # Lấy trạng thái "Đã mất"
                if document_status:
                    document.document_status_id = document_status
                    document.save()
                # Lấy trạng thái "Đã mất" của borrow record
                borrow_status = BorrowingStatus.objects.get(flag_is_lost=True) 
                if borrow_status:
                    borrow_record_active.borrow_status_id = borrow_status
                    borrow_record_active.save()
            else:
                return JsonResponse({'status': 'error', 'message': 'Invalid action'}, status=400)
            return JsonResponse({'status': 'Thao tác thành công?'})
    return JsonResponse({'status': 'error', 'message': 'Không tìm thấy chứng từ mượn, hỏi Admin!'}, status=400)
    return JsonResponse({'status': 'error', 'message': 'Invalid request method'}, status=400)


@login_required
def user_profile_v2_view(request):
    profile, _ = UserProfile.objects.get_or_create(
        user=request.user,
        defaults={'department': 'Chưa cập nhật'},
    )
    user_context = get_user_context(request.user)

    if request.method == 'POST':
        date_of_birth_raw = request.POST.get('date_of_birth', '').strip()
        avatar_file = request.FILES.get('avatar')
        remove_avatar = request.POST.get('remove_avatar') == '1'

        profile.date_of_birth = dateparse.parse_date(date_of_birth_raw) if date_of_birth_raw else None

        if remove_avatar and profile.avatar:
            profile.avatar.delete(save=False)
            profile.avatar = None

        if avatar_file:
            if profile.avatar:
                profile.avatar.delete(save=False)
            profile.avatar = avatar_file

        profile.save(update_fields=['date_of_birth', 'avatar'])
        messages.success(request, 'Đã cập nhật thông tin cá nhân.')
        return redirect('user_profile_v2')

    context = {
        **user_context,
        'profile': profile,
    }
    return render(request, 'app_documents/user_profile_v2.html', context)


@login_required
def ui_permission_v2_view(request):
    user_context = get_user_context(request.user)
    is_admin = user_context.get('is_admin') or user_context.get('is_super_admin')
    if not is_admin:
        messages.error(request, 'Bạn không có quyền truy cập.')
        return redirect('home')

    ensure_ui_screens()
    roles = [{'key': code, 'label': label} for code, label in ROLE_CODES]
    screens = list(UiScreen.objects.filter(is_active=True).order_by('screen_group', 'screen_name'))

    if request.method == 'POST':
        for screen in screens:
            for role in roles:
                checkbox = f"perm_{screen.screen_key}_{role['key']}"
                can_view = request.POST.get(checkbox) == '1'
                UiPermission.objects.update_or_create(
                    screen=screen,
                    role_code=role['key'],
                    defaults={'can_view': can_view, 'updated_by': request.user},
                )
        messages.success(request, 'Đã lưu phân quyền UI.')
        return redirect('ui_permission_v2')

    permissions = UiPermission.objects.filter(screen__in=screens)
    permission_map = {}
    for perm in permissions:
        permission_map.setdefault(perm.screen.screen_key, {})[perm.role_code] = perm.can_view

    context = {
        **user_context,
        'roles': roles,
        'screens': screens,
        'permission_map': permission_map,
    }
    return render(request, 'app_documents/ui_permission_v2.html', context)
