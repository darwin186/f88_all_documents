import csv
import os
import uuid
from datetime import datetime, date
from io import BytesIO
from functools import wraps

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.paginator import EmptyPage, PageNotAnInteger, Paginator
from django.db import IntegrityError, transaction, models
from django.db.models import F
from django.db.models import Count, Q, Max
from django.db.models.functions import TruncDay, ExtractYear
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.conf import settings
from django.http import JsonResponse
from django.core.files.base import ContentFile

from openpyxl import Workbook
from openpyxl import load_workbook

from app_documents.models import Shop, Region

from .forms import (
    AdmAdministrativeDocumentForm,
    AdmAdministrativeDocumentUpdateForm,
    AdmPaperDocumentForm,
    AdmDocumentTypeForm,
    AdmContentTypeForm,
    AdmSignerRoleForm,
    AdmDocumentStatusForm,
    AdmCompanyForm,
    AdmDepartmentForm,
    AdmPaperTypeForm,
    AdmCourierCompanyForm,
)
from .models import (
    AdmAdministrativeDocument,
    AdmCompany,
    AdmContentType,
    AdmCourierCompany,
    AdmDepartment,
    AdmDocumentStatus,
    AdmDocumentType,
    AdmDocumentAttachment,
    AdmDocumentCounter,
    AdmPaperCounter,
    AdmPaperDocument,
    AdmPaperType,
    AdmSignerRole,
    AdmAdministrativeDocumentHistory,
    AdmDepartment,
)
from .services import allocate_running_number, allocate_paper_running_number


def _has_admin_docs_access(user) -> bool:
    allowed_groups = ["administrative staff", "adminpaper"]
    is_checker = user.groups.filter(name="checker").exists()
    if getattr(user, "is_superuser", False):
        return True
    # Block checkers even if they are added to admin groups
    if is_checker:
        return False
    return user.groups.filter(name__in=allowed_groups).exists()


def _create_attachment_version(document, user, uploaded_file=None, link=None, note=None):
    """Create a new attachment version (file or link) for a document."""
    if not uploaded_file and not link:
        return None

    def _clone_upload(file_obj):
        if not file_obj:
            return None
        try:
            # If temp file disappeared (e.g., container cleanup), clone into memory
            if hasattr(file_obj, "temporary_file_path"):
                path = file_obj.temporary_file_path()
                if not os.path.exists(path):
                    data = file_obj.read()
                    return ContentFile(data, name=getattr(file_obj, "name", "upload"))
            file_obj.seek(0)
            return file_obj
        except Exception:
            try:
                data = file_obj.read()
                return ContentFile(data, name=getattr(file_obj, "name", "upload"))
            except Exception:
                return file_obj

    uploaded_file = _clone_upload(uploaded_file)

    current_max = (
        document.attachments.aggregate(max_version=Max("version")).get("max_version")
        or 0
    )
    new_version = current_max + 1
    document.attachments.filter(is_latest=True).update(is_latest=False)
    attachment = AdmDocumentAttachment.objects.create(
        document=document,
        version=new_version,
        file=uploaded_file if uploaded_file else None,
        original_name=getattr(uploaded_file, "name", None),
        link=link or None,
        is_latest=True,
        is_deleted=False,
        created_by=user,
        note=note,
    )
    if uploaded_file:
        # keep compatibility field pointing to latest file
        document.attachment = attachment.file
        document.save(update_fields=["attachment"])
    return attachment


def _parse_paper_rows(ws, request_user):
    """Parse worksheet for paper import. Return (errors, rows_data)."""
    headers = [
        "số hiệu (để trống nếu muốn hệ thống sinh)",
        "loại giấy",
        "miền",
        "phòng giao dịch",
        "phòng ban nội bộ",
        "người phụ trách",
        "nội dung",
        "đơn vị cpn",
        "mã vận đơn",
        "tình trạng",
        "ghi chú",
        "ngày tạo (yyyy-mm-dd)",
    ]
    header_row = [str(cell.value).strip().lower() if cell.value else "" for cell in next(ws.iter_rows(max_row=1))]
    if header_row != headers:
        return ["Header không đúng định dạng mẫu, vui lòng tải file mẫu mới nhất."], []

    paper_type_map = {p.name.lower(): p for p in AdmPaperType.objects.all()}
    shop_map = {s.shop_name.lower(): s for s in Shop.objects.all()}
    dept_map = {d.name.lower(): d for d in AdmDepartment.objects.all()}
    courier_map = {c.name.lower(): c for c in AdmCourierCompany.objects.all()}
    region_map = {r.region_name.lower(): r for r in Region.objects.all()}

    today = timezone.localdate() if settings.USE_TZ else date.today()

    errors = []
    rows_data = []

    for idx, row in enumerate(ws.iter_rows(min_row=2), start=2):
        values = [cell.value for cell in row]
        (
            number_full,
            paper_type_name,
            region,
            requested_dept_name,
            internal_dept_name,
            responsible,
            summary,
            courier_name,
            tracking_code,
            status_text,
            note,
            created_str,
        ) = values

        row_errors = []

        pt_key = str(paper_type_name).strip().lower() if paper_type_name else ""
        paper_type = paper_type_map.get(pt_key)
        if not paper_type:
            row_errors.append("Loại giấy không hợp lệ/để trống.")

        region_val = str(region).strip() if region else ""
        region_obj = None
        if not region_val:
            row_errors.append("Miền không được để trống.")
        else:
            region_obj = region_map.get(region_val.lower())
            if not region_obj:
                row_errors.append(f"Miền '{region_val}' không tồn tại.")

        requested_dept = None
        if requested_dept_name:
            requested_dept = shop_map.get(str(requested_dept_name).strip().lower())
            if not requested_dept:
                row_errors.append(f"Phòng giao dịch '{requested_dept_name}' không tồn tại.")

        internal_dept = None
        if internal_dept_name:
            internal_dept = dept_map.get(str(internal_dept_name).strip().lower())
            if not internal_dept:
                row_errors.append(f"Phòng ban nội bộ '{internal_dept_name}' không tồn tại.")

        if not requested_dept and not internal_dept:
            row_errors.append("Cần chọn Phòng giao dịch hoặc Phòng ban nội bộ (có thể chọn cả hai).")

        courier = None
        if courier_name:
            courier = courier_map.get(str(courier_name).strip().lower())
            if not courier:
                row_errors.append(f"Đơn vị CPN '{courier_name}' không tồn tại.")

        try:
            created_date = (
                datetime.strptime(str(created_str), "%Y-%m-%d").date() if created_str else today
            )
        except ValueError:
            row_errors.append("Ngày tạo không đúng định dạng yyyy-mm-dd.")

        summary_text = str(summary).strip() if summary else ""
        if not summary_text:
            row_errors.append("Nội dung không được để trống.")

        if row_errors:
            errors.append(f"Dòng {idx}: " + "; ".join(row_errors))
            continue

        rows_data.append(
            {
                "paper_type_id": paper_type.id,
                "paper_type_code": paper_type.code,
                "region": region_val,
                "requested_dept_id": requested_dept.pk if requested_dept else None,
                "internal_dept_id": internal_dept.id if internal_dept else None,
                "responsible": str(responsible).strip()
                if responsible
                else (request_user.get_full_name() or request_user.username),
                "summary": summary_text,
                "courier_id": courier.id if courier else None,
                "tracking_code": str(tracking_code).strip() if tracking_code else None,
                "status": str(status_text).strip() if status_text else "",
                "note": str(note).strip() if note else "",
                "created_date": created_date,
                "number_full": str(number_full).strip() if number_full else None,
            }
        )

    return errors, rows_data


def admin_staff_required(view_func):
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        if not request.user.is_authenticated:
            raise PermissionDenied
        if _has_admin_docs_access(request.user):
            return view_func(request, *args, **kwargs)
        messages.error(request, "Bạn không có quyền truy cập mục này.")
        return render(request, "403.html", status=403)

    return _wrapped


def _parse_filters(request):
    tz = timezone.get_current_timezone()
    today = timezone.now().astimezone(tz)

    start_date = request.GET.get("start_date")
    end_date = request.GET.get("end_date")
    month = request.GET.get("month")
    year = request.GET.get("year")
    company_id = request.GET.get("company")
    doc_type_id = request.GET.get("doc_type")
    department_id = request.GET.get("department")

    def parse_date_str(value):
        for fmt in ("%d/%m/%Y", "%Y-%m-%d"):
            try:
                return datetime.strptime(value, fmt).replace(tzinfo=tz)
            except (TypeError, ValueError):
                continue
        raise ValueError

    if month and year:
        try:
            m = int(month)
            y = int(year)
            start = datetime(y, m, 1, tzinfo=tz)
            if m == 12:
                end = datetime(y + 1, 1, 1, tzinfo=tz)
            else:
                end = datetime(y, m + 1, 1, tzinfo=tz)
            period_label = f"{m:02d}/{y}"
        except ValueError:
            start = today.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            if today.month == 12:
                end = start.replace(year=today.year + 1, month=1)
            else:
                end = start.replace(month=today.month + 1)
            period_label = today.strftime("%m/%Y")
    elif start_date or end_date:
        def parse_d(value, default):
            if not value:
                return default
            parsed = parse_date_str(value)
            return parsed

        default_start = today.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        default_end = default_start.replace(
            month=today.month + 1 if today.month < 12 else 1,
            year=today.year + 1 if today.month == 12 else today.year,
        )
        start = parse_d(start_date, default_start)
        end = parse_d(end_date, default_end)
        period_label = f"{start.strftime('%d/%m/%Y')} - {end.strftime('%d/%m/%Y')}"
    else:
        start = today.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        if today.month == 12:
            end = start.replace(year=today.year + 1, month=1)
        else:
            end = start.replace(month=today.month + 1)
        period_label = today.strftime("%m/%Y")

    selections = {
        "company": company_id or "",
        "doc_type": doc_type_id or "",
        "department": department_id or "",
        "start_date": start_date or "",
        "end_date": end_date or "",
        "month": month or "",
        "year": year or "",
        "period_label": period_label,
    }
    return start, end, selections


def _apply_filters(qs, start, end, selections):
    qs = qs.filter(created_at__gte=start, created_at__lt=end)
    if selections["company"]:
        qs = qs.filter(issuing_company_id=selections["company"])
    if selections["doc_type"]:
        qs = qs.filter(doc_type_id=selections["doc_type"])
    if selections["department"]:
        qs = qs.filter(issuing_department_id=selections["department"])
    return qs


@login_required
@admin_staff_required
def dashboard(request):
    start, end, sel = _parse_filters(request)

    base_qs = AdmAdministrativeDocument.objects.all()
    filtered_qs = _apply_filters(base_qs, start, end, sel)

    by_company = (
        filtered_qs.values("issuing_company__name")
        .annotate(total=Count("id"))
        .order_by("issuing_company__name")
    )
    company_labels = [row["issuing_company__name"] or "(Unknown)" for row in by_company]
    company_counts = [row["total"] for row in by_company]

    issued_qs = _apply_filters(
        AdmAdministrativeDocument.objects.filter(
            status__code=AdmDocumentStatus.CODE_ISSUED
        ),
        start,
        end,
        sel,
    )
    issued_total = issued_qs.count()

    issued_daily = (
        issued_qs.annotate(day=TruncDay("created_at"))
        .values("day")
        .annotate(total=Count("id"))
        .order_by("day")
    )
    daily_labels = [row["day"].strftime("%d/%m") for row in issued_daily]
    daily_counts = [row["total"] for row in issued_daily]

    # Ban hành theo tháng / công ty (12 tháng gần nhất)
    if settings.USE_TZ:
        today = timezone.localtime(timezone.now()).date()
    else:
        today = date.today()
    months = []
    for offset in range(11, -1, -1):
        y = today.year
        m = today.month - offset
        while m <= 0:
            m += 12
            y -= 1
        months.append(date(y, m, 1))

    from django.db.models.functions import TruncMonth

    issued_last_year = AdmAdministrativeDocument.objects.filter(
        status__code=AdmDocumentStatus.CODE_ISSUED,
        created_at__gte=months[0],
        created_at__lt=(
            date(months[-1].year + (1 if months[-1].month == 12 else 0),
                 1 if months[-1].month == 12 else months[-1].month + 1,
                 1)
        ),
    )
    monthly_rows = (
        issued_last_year.annotate(period=TruncMonth("created_at"))
        .values("period", "issuing_company__name")
        .annotate(total=Count("id"))
    )
    month_index = {dt: idx for idx, dt in enumerate(months)}
    company_names = sorted(
        {row["issuing_company__name"] or "(Unknown)" for row in monthly_rows}
    )
    monthly_series = {name: [0] * len(months) for name in company_names}
    for row in monthly_rows:
        period_date = row["period"].date()
        idx = month_index.get(period_date)
        if idx is not None:
            monthly_series[row["issuing_company__name"] or "(Unknown)"][idx] = row[
                "total"
            ]

    monthly_company_series = [
        {"label": name, "data": monthly_series[name]} for name in company_names
    ]
    monthly_company_labels = [f"{m.month:02d}/{m.year}" for m in months]

    companies = AdmCompany.objects.all().order_by("name")
    doc_types = AdmDocumentType.objects.all().order_by("name")
    departments = (
        AdmDepartment.objects.select_related("company").all().order_by("name")
    )

    paper_department = request.GET.get("paper_department")
    paper_departments = AdmPaperDocument.objects.select_related("requested_department").values_list(
        "requested_department__shop_id", "requested_department__shop_name"
    ).distinct()
    paper_department_choices = [
        {"id": dept_id, "name": dept_name}
        for dept_id, dept_name in paper_departments
        if dept_id
    ]

    paper_queryset = AdmPaperDocument.objects.filter(
        created_at__gte=start, created_at__lt=end, is_deleted=False
    )
    if paper_department:
        paper_queryset = paper_queryset.filter(requested_department_id=paper_department)

    paper_type_counts = (
        paper_queryset.values("paper_type__name")
        .annotate(total=Count("id"))
        .order_by("paper_type__name")
    )
    papers_total = paper_queryset.count()
    paper_labels = [row["paper_type__name"] or "Khác" for row in paper_type_counts]
    paper_counts = [row["total"] for row in paper_type_counts]

    context = {
        "company_labels": company_labels,
        "company_counts": company_counts,
        "issued_total": issued_total,
        "daily_labels": daily_labels,
        "daily_counts": daily_counts,
        "monthly_company_labels": monthly_company_labels,
        "monthly_company_series": monthly_company_series,
        "month_label": sel["period_label"],
        "companies": companies,
        "doc_types": doc_types,
        "departments": departments,
        "paper_departments": paper_department_choices,
        "paper_department_selected": paper_department or "",
        "sel": sel,
        "start_date_value": sel["start_date"],
        "end_date_value": sel["end_date"],
        "months_range": list(range(1, 13)),
        "has_admin_docs_access": _has_admin_docs_access(request.user),
        "paper_labels": paper_labels,
        "paper_counts": paper_counts,
        "papers_total": papers_total,
        "STATUS_DRAFT": AdmDocumentStatus.CODE_DRAFT,
        "STATUS_PENDING": AdmDocumentStatus.CODE_PENDING,
        "STATUS_ISSUED": AdmDocumentStatus.CODE_ISSUED,
        "STATUS_EXPIRED": AdmDocumentStatus.CODE_EXPIRED,
    }
    return render(request, "admindocuments/dashboard.html", context)


@login_required
@admin_staff_required
def dashboard_export(request):
    start, end, sel = _parse_filters(request)
    qs = _apply_filters(
        AdmAdministrativeDocument.objects.select_related(
            "doc_type",
            "signer_role",
            "status",
            "issuing_company",
            "issuing_department",
        ),
        start,
        end,
        sel,
    )

    filename = f"adm_dashboard_export_{start.strftime('%Y%m%d')}_{end.strftime('%Y%m%d')}.csv"
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'

    writer = csv.writer(response)
    writer.writerow(
        [
            "Document No",
            "Title",
            "Company",
            "Department",
            "Doc Type",
            "Status",
            "Created At",
            "Signer Role",
            "Reference",
            "Ticket Code",
        ]
    )
    for d in qs.order_by("-created_at"):
        writer.writerow(
            [
                d.document_number_full,
                d.title,
                getattr(d.issuing_company, "name", ""),
                getattr(d.issuing_department, "name", ""),
                getattr(d.doc_type, "name", ""),
                getattr(d.status, "name", ""),
                d.created_at.strftime("%Y-%m-%d %H:%M:%S"),
                getattr(d.signer_role, "title", ""),
                d.reference_number or "",
                d.ticket_code or "",
            ]
        )
    return response


@login_required
@admin_staff_required
def document_list(request):
    query = request.GET.get("q", "").strip()
    company_filter = request.GET.get("company")
    content_type_filter = request.GET.get("ctype")
    doc_type_filter = request.GET.get("dtype")
    start_date = request.GET.get("start_date")
    end_date = request.GET.get("end_date")
    sort = request.GET.get("sort", "created")
    direction = request.GET.get("dir", "desc")
    new_doc_id = request.GET.get("new")

    sort_map = {
        "number": "document_number_full",
        "title": "title",
        "type": "doc_type__name",
        "status": "status__code",
        "company": "issuing_company__name",
        "issue": "issue_date",
        "effective": "effective_date",
        "expiry": "expiry_date",
        "created": "created_at",
    }
    order_field = sort_map.get(sort, "created_at")
    if direction == "desc":
        order_field = f"-{order_field}"

    documents_qs = AdmAdministrativeDocument.objects.select_related(
        "doc_type", "signer_role", "status", "issuing_company"
    ).filter(is_void=False)
    if query:
        documents_qs = documents_qs.filter(
            Q(title__icontains=query) | Q(document_number_full__icontains=query)
        )
    if company_filter:
        documents_qs = documents_qs.filter(issuing_company_id=company_filter)
    if content_type_filter:
        documents_qs = documents_qs.filter(content_type_id=content_type_filter)
    if doc_type_filter:
        documents_qs = documents_qs.filter(doc_type_id=doc_type_filter)
    def _parse_dt(value):
        if not value:
            return None
        for fmt in ("%d/%m/%Y", "%Y-%m-%d"):
            try:
                return datetime.strptime(value, fmt).date()
            except (TypeError, ValueError):
                continue
        return None
    sd = _parse_dt(start_date)
    ed = _parse_dt(end_date)
    if not sd and not ed:
        today = timezone.localdate() if settings.USE_TZ else date.today()
        sd = date(today.year, 1, 1)
        ed = date(today.year, 12, 31)
    if sd:
        documents_qs = documents_qs.filter(created_at__date__gte=sd)
    if ed:
        documents_qs = documents_qs.filter(created_at__date__lte=ed)
    documents_qs = documents_qs.order_by(order_field)

    page = request.GET.get("page", "1")
    paginator = Paginator(documents_qs, 25)
    try:
        documents = paginator.page(page)
    except PageNotAnInteger:
        documents = paginator.page(1)
    except EmptyPage:
        documents = paginator.page(paginator.num_pages)

    form = AdmAdministrativeDocumentForm()
    doc_types = AdmDocumentType.objects.all().order_by("name")
    content_types = AdmContentType.objects.all().order_by("name")
    signer_roles = AdmSignerRole.objects.all().order_by("title")
    statuses = AdmDocumentStatus.objects.all().order_by("name")
    companies = AdmCompany.objects.all().order_by("name")
    departments = (
        AdmDepartment.objects.select_related("company").all().order_by("name")
    )
    reference_docs = AdmAdministrativeDocument.objects.all().order_by("-created_at")
    ref_prefill_id = request.GET.get("ref", "")
    default_status = AdmDocumentStatus.objects.filter(
        code=AdmDocumentStatus.CODE_DRAFT
    ).first()

    return render(
        request,
        "admindocuments/document_list.html",
        {
            "documents": documents,
            "paginator": paginator,
            "page_obj": documents,
            "is_paginated": paginator.num_pages > 1,
            "sort": sort,
            "dir": direction,
            "q": query,
            "active_company_id": company_filter or "",
            "form": form,
            "doc_types": doc_types,
            "content_types": content_types,
            "signer_roles": signer_roles,
            "statuses": statuses,
            "companies": companies,
            "departments": departments,
            "default_status": default_status,
            "has_admin_docs_access": _has_admin_docs_access(request.user),
            "STATUS_DRAFT": AdmDocumentStatus.CODE_DRAFT,
            "STATUS_PENDING": AdmDocumentStatus.CODE_PENDING,
            "STATUS_ISSUED": AdmDocumentStatus.CODE_ISSUED,
            "STATUS_EXPIRED": AdmDocumentStatus.CODE_EXPIRED,
            "new_doc_id": new_doc_id or "",
            "active_content_type_id": content_type_filter or "",
            "active_doc_type_id": doc_type_filter or "",
            "reference_docs": reference_docs,
            "ref_prefill_id": ref_prefill_id,
            "start_date": start_date or "",
            "end_date": end_date or "",
        },
    )


@login_required
@admin_staff_required
def document_list_export(request):
    query = request.GET.get("q", "").strip()
    company_filter = request.GET.get("company")
    content_type_filter = request.GET.get("ctype")
    doc_type_filter = request.GET.get("dtype")
    start_date = request.GET.get("start_date")
    end_date = request.GET.get("end_date")
    sort = request.GET.get("sort", "created")
    direction = request.GET.get("dir", "desc")

    sort_map = {
        "number": "document_number_full",
        "title": "title",
        "type": "doc_type__name",
        "status": "status__code",
        "company": "issuing_company__name",
        "issue": "issue_date",
        "effective": "effective_date",
        "expiry": "expiry_date",
        "created": "created_at",
    }
    order_field = sort_map.get(sort, "created_at")
    if direction == "desc":
        order_field = f"-{order_field}"

    documents_qs = AdmAdministrativeDocument.objects.select_related(
        "doc_type", "signer_role", "status", "issuing_company", "issuing_department"
    ).filter(is_void=False)
    if query:
        documents_qs = documents_qs.filter(
            Q(title__icontains=query) | Q(document_number_full__icontains=query)
        )
    if company_filter:
        documents_qs = documents_qs.filter(issuing_company_id=company_filter)
    if content_type_filter:
        documents_qs = documents_qs.filter(content_type_id=content_type_filter)
    if doc_type_filter:
        documents_qs = documents_qs.filter(doc_type_id=doc_type_filter)
    def _parse_date(value):
        if not value:
            return None
        for fmt in ("%d/%m/%Y", "%Y-%m-%d"):
            try:
                return datetime.strptime(value, fmt).date()
            except (TypeError, ValueError):
                continue
        return None

    sd = _parse_date(start_date)
    ed = _parse_date(end_date)
    if not sd and not ed:
        today = timezone.localdate() if settings.USE_TZ else date.today()
        sd = date(today.year, 1, 1)
        ed = date(today.year, 12, 31)
    if sd:
        documents_qs = documents_qs.filter(created_at__date__gte=sd)
    if ed:
        documents_qs = documents_qs.filter(created_at__date__lte=ed)
    documents_qs = documents_qs.order_by(order_field)

    wb = Workbook()
    ws = wb.active
    ws.title = "Danh sách văn bản"
    headers = [
        "STT",
        "Số hiệu",
        "Tên văn bản",
        "Loại văn bản",
        "Loại nội dung",
        "Trạng thái",
        "Công ty ban hành",
        "Phòng ban ban hành",
        "Người ký",
        "Số hiệu tham chiếu",
        "Tham chiếu tới",
        "Ngày ban hành",
        "Ngày hiệu lực",
        "Ngày hết hiệu lực",
        "Mã ticket",
        "Người tạo",
        "Ngày tạo",
        "Ghi chú",
    ]
    ws.append(headers)
    for idx, d in enumerate(documents_qs, start=1):
        ws.append(
            [
                idx,
                d.document_number_full,
                d.title,
                d.doc_type.name if d.doc_type_id else "",
                d.content_type.name if d.content_type_id else "",
                d.status.name if d.status_id else "",
                d.issuing_company.name if d.issuing_company_id else "",
                d.issuing_department.name if d.issuing_department_id else "",
                d.signer_role.title if d.signer_role_id else "",
                d.reference_number or "",
                d.reference_document.document_number_full
                if d.reference_document_id
                else "",
                d.issue_date.strftime("%d/%m/%Y") if d.issue_date else "",
                d.effective_date.strftime("%d/%m/%Y") if d.effective_date else "",
                d.expiry_date.strftime("%d/%m/%Y") if d.expiry_date else "",
                d.ticket_code or "",
                d.created_by.get_full_name() if d.created_by_id else "",
                d.created_at.astimezone(timezone.get_current_timezone()).strftime(
                    "%d/%m/%Y %H:%M"
                )
                if d.created_at
                else "",
                d.note or "",
            ]
        )

    buffer = BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    now_str = date.today().strftime("%Y%m%d")
    filename = f"danhsachvanbanhanhchin_{now_str}.xlsx"
    response = HttpResponse(
        buffer.getvalue(),
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


@login_required
@admin_staff_required
def paper_document_list(request):
    selected_type = request.GET.get("paper_type", "")
    query = request.GET.get("q", "").strip()
    sort = request.GET.get("sort", "created")
    direction = request.GET.get("dir", "desc")
    edit_id = request.GET.get("edit")

    sort_map = {
        "code": "document_number_full",
        "running": "running_number",
        "type": "paper_type__name",
        "region": "region",
        "responsible": "responsible_person",
        "department": "requested_department__shop_name",
        "ticket": "ticket_code",
        "status": "status",
        "created": "created_at",
    }
    order_field = sort_map.get(sort, "created_at")
    if direction == "desc":
        order_field = f"-{order_field}"

    documents_qs = AdmPaperDocument.objects.select_related(
        "requested_department", "paper_type", "courier_company"
    ).filter(is_deleted=False)
    if query:
        documents_qs = documents_qs.filter(
            Q(document_number_full__icontains=query)
            | Q(courier_tracking_code__icontains=query)
        )
    documents_qs = documents_qs.order_by(order_field)
    paper_types = AdmPaperType.objects.filter(is_active=True).order_by("name")
    if selected_type:
        documents_qs = documents_qs.filter(paper_type_id=selected_type)

    edit_instance = None
    if edit_id:
        edit_instance = AdmPaperDocument.objects.filter(pk=edit_id).first()

    if request.method == "POST":
        edit_target_id = request.POST.get("edit_id")
        edit_instance = (
            AdmPaperDocument.objects.filter(pk=edit_target_id).first()
            if edit_target_id
            else None
        )
        form = AdmPaperDocumentForm(request.POST, instance=edit_instance)
        if form.is_valid():
            paper_doc = form.save(commit=False)
            if edit_instance:
                paper_doc.updated_by = request.user
                paper_doc.save()
                messages.success(request, "Cập nhật giấy tờ thành công.")
            else:
                paper_doc.created_by = request.user
                full_name = (request.user.get_full_name() or "").strip()
                paper_doc.responsible_person = full_name if full_name else request.user.username
                attempts = 0
                saved = False
                while attempts < 3 and not saved:
                    attempts += 1
                    try:
                        with transaction.atomic():
                            year_now = timezone.now().year
                            running_number, doc_num = allocate_paper_running_number(
                                paper_doc.paper_type_id, paper_doc.paper_type.code, year_now
                            )
                            paper_doc.running_number = running_number
                            paper_doc.document_number_full = doc_num
                            paper_doc.save()
                        saved = True
                    except IntegrityError:
                        if attempts >= 3:
                            messages.error(
                                request,
                                "Không thể sinh số hiệu duy nhất, vui lòng thử lại.",
                            )
                            return redirect("admindocuments:paper_document_list")
                        continue
                # Spotlight newly created paper
                new_ids = request.session.get("paper_new_ids", [])
                new_nums = request.session.get("paper_new_numbers", [])
                new_ids.append(paper_doc.id)
                new_nums.append(paper_doc.document_number_full)
                request.session["paper_new_ids"] = new_ids
                request.session["paper_new_numbers"] = new_nums
                request.session.modified = True
                messages.success(
                    request,
                    f"Tạo giấy tờ thành công: {paper_doc.document_number_full}",
                )
            params = request.GET.copy()
            redirect_url = reverse("admindocuments:paper_document_list")
            if params:
                params.pop("edit", None)
                redirect_url += f"?{params.urlencode()}"
            return redirect(redirect_url)
        errors_str = []
        for field, errs in form.errors.items():
            label = form.fields.get(field).label if field in form.fields else field
            errors_str.append(f"{label}: {', '.join(errs)}")
        if errors_str:
            messages.error(request, "Dữ liệu không hợp lệ: " + " | ".join(errors_str))
        else:
            messages.error(request, "Dữ liệu không hợp lệ, vui lòng kiểm tra lại.")
    form = AdmPaperDocumentForm(instance=edit_instance)

    total_by_type = {
        row["paper_type"]: row["total"]
        for row in AdmPaperDocument.objects.filter(is_deleted=False)
        .values("paper_type")
        .annotate(total=Count("id"))
    }
    paper_type_tabs = [
        {"id": p.pk, "name": p.name, "total": total_by_type.get(p.pk, 0)} for p in paper_types
    ]
    paginator = Paginator(documents_qs, 25)
    page_number = request.GET.get("page", "1")
    try:
        documents = paginator.page(page_number)
    except PageNotAnInteger:
        documents = paginator.page(1)
    except EmptyPage:
        documents = paginator.page(paginator.num_pages)

    request_departments = form.fields["requested_department"].queryset
    requested_department_initial = ""
    if edit_instance and getattr(edit_instance, "requested_department_id", None):
        requested_department_initial = str(edit_instance.requested_department_id)
    edit_department_initial = ""
    if edit_instance and getattr(edit_instance, "department_id", None):
        edit_department_initial = str(edit_instance.department_id)

    new_ids = request.session.pop("paper_new_ids", [])
    new_numbers = request.session.pop("paper_new_numbers", [])

    context = {
        "documents": documents,
        "form": form,
        "paper_types": paper_type_tabs,
        "selected_type": selected_type,
        "sort": sort,
        "dir": direction,
        "paginator": paginator,
        "edit_id": edit_id or "",
        "paper_request_departments": request_departments,
        "edit_requested_department_id": requested_department_initial,
        "edit_department_id": edit_department_initial,
        "internal_departments": AdmDepartment.objects.select_related("company").all().order_by("name"),
        "new_ids": new_ids,
        "new_numbers": new_numbers,
    }
    return render(request, "admindocuments/paper_document_list.html", context)


@login_required
@admin_staff_required
def paper_document_detail(request, doc_id: int):
    paper_doc = get_object_or_404(
        AdmPaperDocument.objects.select_related(
            "paper_type", "requested_department", "courier_company", "department"
        ),
        pk=doc_id,
        is_deleted=False,
    )
    as_drawer = request.GET.get("drawer") == "1"
    if request.method == "POST":
        form = AdmPaperDocumentForm(request.POST, instance=paper_doc)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.updated_by = request.user
            obj.save()
            messages.success(request, "Cập nhật giấy tờ thành công.")
            return redirect("admindocuments:paper_document_detail", doc_id=doc_id)
        errors_str = []
        for field, errs in form.errors.items():
            label = form.fields.get(field).label if field in form.fields else field
            errors_str.append(f"{label}: {', '.join(errs)}")
        if errors_str:
            messages.error(request, "Dữ liệu không hợp lệ: " + " | ".join(errors_str))
        else:
            messages.error(request, "Dữ liệu không hợp lệ, vui lòng kiểm tra lại.")
    else:
        form = AdmPaperDocumentForm(instance=paper_doc)

    template_name = (
        "admindocuments/paper_document_detail_drawer.html"
        if as_drawer
        else "admindocuments/paper_document_detail.html"
    )
    return render(
        request,
        template_name,
        {
            "doc": paper_doc,
            "form": form,
            "paper_request_departments": Shop.objects.all().order_by("shop_name"),
            "internal_departments": AdmDepartment.objects.select_related("company")
            .all()
            .order_by("name"),
        },
    )


@login_required
@admin_staff_required
def paper_document_hide(request, doc_id: int):
    if request.method != "POST":
        return redirect("admindocuments:paper_document_list")
    paper_doc = get_object_or_404(AdmPaperDocument, pk=doc_id, is_deleted=False)
    paper_doc.document_number_full = f"{paper_doc.document_number_full}#VOID#{uuid.uuid4().hex[:6]}"
    paper_doc.is_deleted = True
    paper_doc.deleted_at = timezone.now()
    paper_doc.save(update_fields=["document_number_full", "is_deleted", "deleted_at"])
    messages.success(request, "Đã ẩn giấy và thu hồi số hiệu.")
    return redirect("admindocuments:paper_document_list")


@login_required
@admin_staff_required
def paper_document_import(request):
    if request.method != "POST" or "file" not in request.FILES:
        messages.error(request, "Vui lòng chọn file .xlsx để tải lên.")
        return redirect("admindocuments:paper_document_list")

    upload = request.FILES["file"]
    try:
        wb = load_workbook(upload)
        ws = wb.active
    except Exception:
        messages.error(request, "File không hợp lệ hoặc không thể đọc.")
        return redirect("admindocuments:paper_document_list")

    errors, rows_data = _parse_paper_rows(ws, request.user)
    if errors:
        messages.error(request, "Không nhập dữ liệu. Lỗi:\n" + "\n".join(errors))
        return redirect("admindocuments:paper_document_list")

    created_count = 0
    with transaction.atomic():
        for item in rows_data:
            year_now = item["created_date"].year
            running_number, document_number_full = allocate_paper_running_number(
                item["paper_type_id"], item["paper_type_code"], year_now
            )
            obj = AdmPaperDocument(
                paper_type_id=item["paper_type_id"],
                running_number=running_number,
                region=item["region"],
                requested_department_id=item["requested_dept_id"],
                department_id=item["internal_dept_id"],
                responsible_person=item["responsible"],
                document_number_full=document_number_full,
                summary=item["summary"],
                courier_company_id=item["courier_id"],
                courier_tracking_code=item["tracking_code"],
                status=item["status"],
                note=item["note"],
                created_by=request.user,
                created_at=datetime.combine(item["created_date"], datetime.min.time()).replace(
                    tzinfo=timezone.get_current_timezone()
                ),
            )
            obj.save()
            created_count += 1

    messages.success(request, f"Đã nhập {created_count} dòng thành công.")
    return redirect("admindocuments:paper_document_list")

@login_required
@admin_staff_required
def paper_document_template(request):
    """Generate Excel template for paper documents import."""
    wb = Workbook()
    ws = wb.active
    ws.title = "Template"
    headers = [
        "Số hiệu (để trống nếu muốn hệ thống sinh)",
        "Loại giấy",
        "Miền",
        "Phòng giao dịch",
        "Phòng ban nội bộ",
        "Người phụ trách",
        "Nội dung",
        "Đơn vị CPN",
        "Mã vận đơn",
        "Tình trạng",
        "Ghi chú",
        "Ngày tạo (yyyy-mm-dd)",
    ]
    ws.append(headers)

    sample = AdmPaperDocument.objects.select_related(
        "paper_type", "requested_department", "department", "courier_company"
    ).order_by("-created_at").first()
    if sample:
        ws.append(
            [
                "",
                sample.paper_type.name if sample.paper_type_id else "",
                sample.region or "",
                sample.requested_department.shop_name if sample.requested_department_id else "",
                sample.department.name if sample.department_id else "",
                sample.responsible_person or "",
                sample.summary or "",
                sample.courier_company.name if sample.courier_company_id else "",
                sample.courier_tracking_code or "",
                sample.status or "",
                sample.note or "",
                sample.created_at.date().isoformat(),
            ]
        )
    else:
        ws.append(
            [
                "",
                "Công văn",
                "Miền Bắc",
                "PGD Hà Nội",
                "Phòng Kế toán",
                "Nguyễn Văn A",
                "Nội dung ví dụ",
                "VNPost",
                "ABC123456",
                "Đang chờ",
                "Ghi chú ví dụ",
                date.today().isoformat(),
            ]
        )
    stream = BytesIO()
    wb.save(stream)
    stream.seek(0)
    response = HttpResponse(
        stream.getvalue(),
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    response[
        "Content-Disposition"
    ] = 'attachment; filename="paper_document_template.xlsx"'
    return response


@login_required
@admin_staff_required
def paper_document_import_url(request):
    if request.method != "POST":
        return JsonResponse({"error": "Method not allowed"}, status=405)
    if "file" not in request.FILES:
        return JsonResponse({"error": "Thiếu file .xlsx"}, status=400)
    upload = request.FILES["file"]
    try:
        wb = load_workbook(upload)
        ws = wb.active
    except Exception:
        return JsonResponse({"error": "File không hợp lệ hoặc không thể đọc."}, status=400)

    errors, rows_data = _parse_paper_rows(ws, request.user)
    if errors:
        return JsonResponse({"error": "Lỗi dữ liệu", "details": errors}, status=400)

    token = uuid.uuid4().hex
    serialized = []
    for item in rows_data:
        s = item.copy()
        s["created_date"] = s["created_date"].isoformat()
        serialized.append(s)
    request.session[f"paper_import_{token}"] = serialized
    request.session.modified = True
    return JsonResponse({"status": "ok", "token": token, "rows": len(rows_data)})


@login_required
@admin_staff_required
def paper_document_import_commit(request):
    if request.method != "POST":
        return JsonResponse({"error": "Method not allowed"}, status=405)
    token = request.POST.get("token")
    if not token:
        return JsonResponse({"error": "Thiếu token"}, status=400)
    rows_data = request.session.get(f"paper_import_{token}")
    if not rows_data:
        return JsonResponse({"error": "Token không hợp lệ hoặc đã hết hạn"}, status=400)

    created_count = 0
    created_ids = []
    created_numbers = []
    with transaction.atomic():
        for item in rows_data:
            created_date = datetime.fromisoformat(item["created_date"]).date()
            year_now = created_date.year
            running_number, document_number_full = allocate_paper_running_number(
                item["paper_type_id"], item["paper_type_code"], year_now
            )
            obj = AdmPaperDocument(
                paper_type_id=item["paper_type_id"],
                running_number=running_number,
                region=item["region"],
                requested_department_id=item["requested_dept_id"],
                department_id=item["internal_dept_id"],
                responsible_person=item["responsible"],
                document_number_full=document_number_full,
                summary=item["summary"],
                courier_company_id=item["courier_id"],
                courier_tracking_code=item["tracking_code"],
                status=item["status"],
                note=item["note"],
                created_by=request.user,
                created_at=datetime.combine(created_date, datetime.min.time()).replace(
                    tzinfo=timezone.get_current_timezone()
                ),
            )
            obj.save()
            created_count += 1
            created_ids.append(obj.id)
            created_numbers.append(document_number_full)
    try:
        del request.session[f"paper_import_{token}"]
        request.session.modified = True
    except KeyError:
        pass
    if created_ids:
        request.session["paper_new_ids"] = created_ids
        request.session["paper_new_numbers"] = created_numbers
        request.session.modified = True
    return JsonResponse({"status": "ok", "created": created_count})


@login_required
@admin_staff_required
def document_counter_manage(request):
    doc_types = AdmDocumentType.objects.all().order_by("name")
    companies = AdmCompany.objects.all().order_by("name")
    paper_types = AdmPaperType.objects.all().order_by("name")
    year_now = timezone.now().year
    active_tab = request.GET.get("tab", "admin")

    if request.method == "POST" and request.POST.get("target", "admin") == "admin":
        doc_type_id = request.POST.get("doc_type")
        company_id = request.POST.get("company")
        year = request.POST.get("year") or year_now
        next_number = request.POST.get("next_number")

        try:
            year = int(year)
            next_number = int(next_number)
        except (TypeError, ValueError):
            messages.error(request, "Năm và số tiếp theo phải là số.")
            return redirect("admindocuments:admindocuments_counters")

        if not doc_type_id or not company_id:
            messages.error(request, "Vui lòng chọn đủ loại văn bản và công ty.")
            return redirect("admindocuments:admindocuments_counters")

        used_qs = AdmAdministrativeDocument.objects.filter(
            doc_type_id=doc_type_id,
            issuing_company_id=company_id,
            created_at__year=year,
            is_void=False,
        )
        max_used = used_qs.aggregate(mx=Max("running_number"))["mx"] or 0
        exists_number = used_qs.filter(running_number=next_number).exists()
        if exists_number:
            messages.error(
                request,
                f"Số {next_number} đã được sử dụng (đã dùng tới {max_used}).",
            )
            return redirect("admindocuments:admindocuments_counters")

        counter, _ = AdmDocumentCounter.objects.get_or_create(
            doc_type_id=doc_type_id, company_id=company_id, year=year, defaults={"next_number": next_number}
        )
        if not _:
            counter.next_number = next_number
            counter.save(update_fields=["next_number", "updated_at"])
        dt_name = doc_types.filter(pk=doc_type_id).first()
        dt_name = dt_name.name if dt_name else doc_type_id
        comp_name = companies.filter(pk=company_id).first()
        comp_code = comp_name.code if comp_name else company_id
        messages.success(request, f"Cập nhật số tiếp theo cho '{dt_name}' - {comp_code} năm {year} -> {next_number}.")
        return redirect("admindocuments:admindocuments_counters")

    # prepare tracking
    used_map = {
        (row["doc_type_id"], row["issuing_company_id"], row["created_year"]): {
            "used_max": row["used_max"],
            "total": row["total"],
        }
        for row in AdmAdministrativeDocument.objects.filter(is_void=False)
        .values("doc_type_id", "issuing_company_id", created_year=ExtractYear("created_at"))
        .annotate(used_max=Max("running_number"), total=Count("id"))
    }

    counters = AdmDocumentCounter.objects.select_related("doc_type", "company").order_by(
        "-year", "doc_type__name", "company__name"
    )
    counter_rows = []
    for c in counters:
            key = (c.doc_type_id, c.company_id, c.year)
            used_info = used_map.get(key, {"used_max": 0, "total": 0})
            gap_from = (used_info["used_max"] or 0) + 1
            counter_rows.append(
                {
                "doc_type": c.doc_type,
                "doc_type_id": c.doc_type_id,
                "company": c.company,
                "company_id": c.company_id,
                "year": c.year,
                "next_number": c.next_number,
                "used_max": used_info["used_max"] or 0,
                "total": used_info["total"] or 0,
                "gap_from": gap_from,
                }
            )
    # Paper counter update
    if request.method == "POST" and request.POST.get("target") == "paper":
        paper_type_id = request.POST.get("paper_type")
        year = request.POST.get("year") or year_now
        next_number = request.POST.get("next_number")
        try:
            year = int(year)
            next_number = int(next_number)
        except (TypeError, ValueError):
            messages.error(request, "Năm và số tiếp theo phải là số.")
            return redirect("admindocuments:admindocuments_counters")
        if not paper_type_id:
            messages.error(request, "Vui lòng chọn loại giấy.")
            return redirect("admindocuments:admindocuments_counters")
        exists_active = AdmPaperDocument.objects.filter(
            paper_type_id=paper_type_id,
            created_at__year=year,
            is_deleted=False,
            running_number=next_number,
        ).exists()
        if exists_active:
            messages.error(request, f"Số {next_number} đã được sử dụng cho giấy này.")
            return redirect("admindocuments:admindocuments_counters")
        counter, created = AdmPaperCounter.objects.get_or_create(
            paper_type_id=paper_type_id,
            year=year,
            defaults={"next_number": next_number},
        )
        if not created:
            counter.next_number = next_number
            counter.save(update_fields=["next_number", "updated_at"])
        pt_name = paper_types.filter(pk=paper_type_id).first()
        pt_name = pt_name.name if pt_name else paper_type_id
        messages.success(request, f"Cập nhật số tiếp theo cho giấy '{pt_name}' năm {year} -> {next_number}.")
        return redirect(f"{reverse('admindocuments:admindocuments_counters')}?tab=paper")

    # Paper counters display
    paper_rows = []
    paper_years = (
        AdmPaperDocument.objects.values_list("created_at__year", flat=True).distinct()
    )
    years_set = set(y for y in paper_years if y)
    years_set.add(year_now)
    for pt in paper_types:
        for y in sorted(years_set):
            active_qs = AdmPaperDocument.objects.filter(
                paper_type_id=pt.id, created_at__year=y, is_deleted=False
            )
            void_qs = AdmPaperDocument.objects.filter(
                paper_type_id=pt.id, created_at__year=y, is_deleted=True
            )
            active_numbers = list(active_qs.values_list("running_number", flat=True))
            void_numbers = list(void_qs.values_list("running_number", flat=True))
            if not active_numbers and not void_numbers:
                continue
            active_numbers_sorted = sorted([n for n in active_numbers if n])
            candidate = 1
            for n in active_numbers_sorted:
                if n and n > candidate:
                    break
                candidate = (n or candidate) + 1
            counter = AdmPaperCounter.objects.filter(paper_type_id=pt.id, year=y).first()
            if counter and counter.next_number and counter.next_number > candidate:
                candidate = counter.next_number
            used_max = active_numbers_sorted[-1] if active_numbers_sorted else 0
            paper_rows.append(
                {
                    "paper_type": pt,
                    "paper_type_id": pt.id,
                    "year": y,
                    "used_max": used_max,
                    "next_number": candidate,
                    "gap_from": candidate,
                    "total": len(active_numbers_sorted),
                    "void_count": len([n for n in void_numbers if n]),
                    "counter": counter,
                }
            )

    return render(
        request,
        "admindocuments/document_counters.html",
        {
            "doc_types": doc_types,
            "companies": companies,
            "paper_types": paper_types,
            "year_now": year_now,
            "counters": counter_rows,
            "paper_counters": paper_rows,
            "active_tab": active_tab,
        },
    )


@login_required
@admin_staff_required
def document_counter_visual(request):
    doc_types = AdmDocumentType.objects.all().order_by("name")
    companies = AdmCompany.objects.all().order_by("name")
    year_now = timezone.now().year

    def _safe_int(val, default=None):
        try:
            return int(val)
        except (TypeError, ValueError):
            return default

    doc_type_id = _safe_int(request.GET.get("doc_type"))
    company_id = _safe_int(request.GET.get("company"))
    year = _safe_int(request.GET.get("year"), year_now)

    used_numbers = set()
    void_numbers = set()
    counter_next = None
    max_number = 0

    if doc_type_id and company_id:
        docs = AdmAdministrativeDocument.objects.filter(
            doc_type_id=doc_type_id,
            issuing_company_id=company_id,
            created_at__year=year,
        ).values_list("running_number", "is_void")
        for rn, is_void in docs:
            if rn is None:
                continue
            if is_void:
                void_numbers.add(rn)
            else:
                used_numbers.add(rn)
        counter = AdmDocumentCounter.objects.filter(
            doc_type_id=doc_type_id, company_id=company_id, year=year
        ).first()
        if counter:
            counter_next = counter.next_number or 1
            max_number = max(max_number, (counter_next or 1) - 1)
        if used_numbers or void_numbers:
            max_number = max(max_number, max(used_numbers | void_numbers))
        if max_number == 0 and counter_next:
            max_number = (counter_next or 1) - 1

    years_set = {year_now}
    years_set.update(
        AdmDocumentCounter.objects.values_list("year", flat=True).distinct()
    )
    years_set.update(
        AdmAdministrativeDocument.objects.annotate(y=ExtractYear("created_at")).values_list("y", flat=True).distinct()
    )
    years = sorted({y for y in years_set if y}, reverse=True)
    context = {
        "doc_types": doc_types,
        "companies": companies,
        "year_now": year_now,
        "selected_doc_type": doc_type_id or "",
        "selected_company": company_id or "",
        "selected_year": year,
        "used_numbers": sorted(list(used_numbers)),
        "void_numbers": sorted(list(void_numbers)),
        "max_number": max_number,
        "counter_next": counter_next,
        "years": years,
        "numbers": list(range(1, max_number + 1)) if max_number else [],
    }
    if request.GET.get("partial") == "1":
        return render(request, "admindocuments/document_counter_visual_partial.html", context)
    return render(request, "admindocuments/document_counter_visual.html", context)


@login_required
@admin_staff_required
def paper_counter_visual(request):
    paper_type_id = request.GET.get("paper_type")
    year_now = timezone.now().year
    try:
        year = int(request.GET.get("year", year_now))
    except (TypeError, ValueError):
        year = year_now

    used_numbers = set()
    void_numbers = set()
    max_number = 0
    next_number = 1

    if paper_type_id:
        active_qs = AdmPaperDocument.objects.filter(
            paper_type_id=paper_type_id, created_at__year=year, is_deleted=False
        )
        void_qs = AdmPaperDocument.objects.filter(
            paper_type_id=paper_type_id, created_at__year=year, is_deleted=True
        )
        used_numbers.update([n for n in active_qs.values_list("running_number", flat=True) if n])
        void_numbers.update([n for n in void_qs.values_list("running_number", flat=True) if n])
        if used_numbers or void_numbers:
            max_number = max(used_numbers | void_numbers)
        if max_number == 0:
            max_number = len(used_numbers)

        # compute next_number (gap fill)
        existing = sorted(list(used_numbers))
        candidate = 1
        for n in existing:
            if n > candidate:
                break
            candidate = n + 1
        counter = AdmPaperCounter.objects.filter(paper_type_id=paper_type_id, year=year).first()
        if counter and counter.next_number and counter.next_number > candidate:
            candidate = counter.next_number
        next_number = candidate
        if max_number:
            max_number = max(max_number, next_number)

    numbers = list(range(1, max_number + 1)) if max_number else []
    return render(
        request,
        "admindocuments/paper_counter_visual_partial.html",
        {
            "used_numbers": used_numbers,
            "void_numbers": void_numbers,
            "max_number": max_number,
            "next_number": next_number,
            "numbers": numbers,
        },
    )


@login_required
@admin_staff_required
def master_data(request):
    form_classes = {
        "doc_type": (AdmDocumentTypeForm, "Loại văn bản"),
        "content_type": (AdmContentTypeForm, "Loại nội dung"),
        "signer_role": (AdmSignerRoleForm, "Chức danh người ký"),
        "status": (AdmDocumentStatusForm, "Trạng thái văn bản"),
        "company": (AdmCompanyForm, "Công ty"),
        "department": (AdmDepartmentForm, "Phòng ban"),
        "paper_type": (AdmPaperTypeForm, "Loại giấy (paper)"),
        "courier": (AdmCourierCompanyForm, "Đơn vị chuyển phát"),
    }
    perm_map = {
        "doc_type": "app_admindocuments.add_admdocumenttype",
        "content_type": "app_admindocuments.add_admcontenttype",
        "signer_role": "app_admindocuments.add_admsignerrole",
        "status": "app_admindocuments.add_admdocumentstatus",
        "company": "app_admindocuments.add_admcompany",
        "department": "app_admindocuments.add_admdepartment",
        "paper_type": "app_admindocuments.add_admpapertype",
        "courier": "app_admindocuments.add_admcouriercompany",
    }
    forms_map = {key: cls() for key, (cls, _) in form_classes.items()}

    if request.method == "POST":
        form_key = request.POST.get("form_name")
        form_entry = form_classes.get(form_key)
        if not form_entry:
            messages.error(request, "Form không hợp lệ.")
            return redirect("admindocuments:master_data")
        form_cls, label = form_entry
        required_perm = perm_map.get(form_key)
        if required_perm and not request.user.has_perm(required_perm):
            messages.error(request, "Bạn không có quyền thêm %s." % label.lower())
            return redirect(f"{reverse('admindocuments:master_data')}#{form_key}")
        bound_form = form_cls(request.POST)
        forms_map[form_key] = bound_form
        if bound_form.is_valid():
            obj = bound_form.save(commit=False)
            if hasattr(obj, "created_by"):
                obj.created_by = request.user
            if hasattr(obj, "updated_by"):
                obj.updated_by = request.user
            obj.save()
            messages.success(request, f"Đã thêm {label.lower()}.")
            return redirect(f"{reverse('admindocuments:master_data')}#{form_key}")
        messages.error(request, "Dữ liệu không hợp lệ, vui lòng kiểm tra lại.")

    # Ensure dropdowns ordered nicely
    if "department" in forms_map:
        forms_map["department"].fields["company"].queryset = AdmCompany.objects.order_by("name")

    context = {
        "doc_types": AdmDocumentType.objects.all().order_by("name"),
        "content_types": AdmContentType.objects.all().order_by("name"),
        "signer_roles": AdmSignerRole.objects.all().order_by("title"),
        "statuses": AdmDocumentStatus.objects.all().order_by("name"),
        "companies": AdmCompany.objects.all().order_by("name"),
        "departments": AdmDepartment.objects.select_related("company").all().order_by(
            "company__code", "name"
        ),
        "paper_types": AdmPaperType.objects.all().order_by("name"),
        "couriers": AdmCourierCompany.objects.all().order_by("name"),
        "forms": forms_map,
        "has_admin_docs_access": _has_admin_docs_access(request.user),
        "form_permissions": {
            key: (not perm_map.get(key) or request.user.has_perm(perm_map[key]))
            for key in form_classes.keys()
        },
    }
    return render(request, "admindocuments/master_data.html", context)


@login_required
@admin_staff_required
def document_create(request):
    if request.method != "POST":
        return redirect("admindocuments:admindocuments_list")
    form = AdmAdministrativeDocumentForm(request.POST, request.FILES)
    if not form.is_valid():
        messages.error(request, "Invalid data. Please check required fields.")
        return redirect("admindocuments:admindocuments_list")

    doc = form.save(commit=False)
    doc.created_by = request.user

    if not getattr(doc, "status_id", None):
        default_status = AdmDocumentStatus.objects.filter(
            code=AdmDocumentStatus.CODE_DRAFT
        ).first() or AdmDocumentStatus.objects.order_by("id").first()
        if default_status:
            doc.status = default_status

    attachment_link = form.cleaned_data.get("attachment_link")
    issue_date = form.cleaned_data.get("issue_date")
    if not issue_date:
        issue_date = timezone.localdate() if settings.USE_TZ else date.today()
    doc.issue_date = issue_date

    attempts = 0
    max_attempts = 30
    while attempts < max_attempts:
        attempts += 1
        try:
            with transaction.atomic():
                current_year = timezone.now().year
                doc.running_number, void_conflicts = allocate_running_number(
                    doc.doc_type_id, doc.issuing_company_id, current_year
                )
                doc.save()
                _create_attachment_version(
                    document=doc,
                    user=request.user,
                    uploaded_file=request.FILES.get("attachment"),
                    link=attachment_link,
                )
            break
        except IntegrityError:
            AdmDocumentCounter.objects.filter(
                doc_type_id=doc.doc_type_id,
                company_id=doc.issuing_company_id,
                year=current_year,
            ).update(next_number=F("next_number") + 1)
            if attempts >= max_attempts:
                messages.error(
                    request, "Could not allocate unique number. Please try again."
                )
                return redirect("admindocuments:admindocuments_list")
            continue

    messages.success(
        request,
        f"Văn bản {doc.document_number_full} đã tạo thành công."
        + ("" if not void_conflicts else f" (Sử dụng lại số đã thu hồi từ {len(void_conflicts)} văn bản)"),
    )
    redirect_url = f"{reverse('admindocuments:admindocuments_list')}?new={doc.id}"
    return redirect(redirect_url)


@login_required
@admin_staff_required
def document_change_status(request, doc_id: int):
    if request.method != "POST":
        return redirect("admindocuments:admindocuments_list")

    status_code = request.POST.get("status_code")
    if not status_code:
        messages.error(request, "Missing status_code.")
        return redirect("admindocuments:admindocuments_list")

    try:
        doc = AdmAdministrativeDocument.objects.select_related("status").get(pk=doc_id)
    except AdmAdministrativeDocument.DoesNotExist:
        messages.error(request, "Document not found.")
        return redirect("admindocuments:admindocuments_list")

    new_status = AdmDocumentStatus.objects.filter(code=status_code).first()
    if not new_status:
        messages.error(request, "Invalid status.")
        return redirect("admindocuments:admindocuments_list")

    if doc.status_id == new_status.id:
        messages.info(request, "Status is already set to this value.")
        return redirect("admindocuments:admindocuments_list")

    doc.status = new_status
    if hasattr(doc, "updated_by"):
        doc.updated_by = request.user
    doc.save()
    messages.success(request, "Status updated successfully.")
    return redirect("admindocuments:admindocuments_list")


@login_required
@admin_staff_required
def document_detail(request, doc_id: int):
    try:
        doc = AdmAdministrativeDocument.objects.select_related(
            "doc_type",
            "content_type",
            "signer_role",
            "issuing_company",
            "issuing_department",
            "status",
        ).prefetch_related("attachments__created_by", "attachments__deleted_by").get(pk=doc_id)
    except AdmAdministrativeDocument.DoesNotExist:
        messages.error(request, "Document not found.")
        return redirect("admindocuments:admindocuments_list")

    as_drawer = request.GET.get("drawer") == "1"
    form = AdmAdministrativeDocumentUpdateForm(instance=doc)
    doc_types = AdmDocumentType.objects.all().order_by("name")
    content_types = AdmContentType.objects.all().order_by("name")
    signer_roles = AdmSignerRole.objects.all().order_by("title")
    companies = AdmCompany.objects.all().order_by("name")
    departments = (
        AdmDepartment.objects.select_related("company").all().order_by("name")
    )
    statuses = AdmDocumentStatus.objects.all().order_by("name")
    reference_docs = AdmAdministrativeDocument.objects.exclude(pk=doc_id).order_by(
        "-created_at"
    )
    status_history = []
    hist_qs = (
        doc.history.select_related("changed_by")
        .filter(
            models.Q(changes__has_key="status")
            | models.Q(change_type=AdmAdministrativeDocumentHistory.CHANGE_CREATED)
        )
        .order_by("-changed_at")
    )
    for h in hist_qs:
        new_status = None
        old_status = None
        if isinstance(h.changes, dict):
            if "status" in h.changes:
                old_status = h.changes["status"].get("old")
                new_status = h.changes["status"].get("new")
            elif "new_values" in h.changes and isinstance(h.changes["new_values"], dict):
                new_status = h.changes["new_values"].get("status")
        status_history.append(
            {
                "timestamp": h.changed_at,
                "user": h.changed_by,
                "new_status": new_status or "",
                "old_status": old_status or "",
                "type": h.change_type,
            }
        )

    context = {
        "doc": doc,
        "form": form,
        "doc_types": doc_types,
        "content_types": content_types,
        "signer_roles": signer_roles,
        "companies": companies,
        "departments": departments,
        "statuses": statuses,
        "reference_docs": reference_docs,
        "status_history": status_history,
        "has_admin_docs_access": _has_admin_docs_access(request.user),
        "STATUS_DRAFT": AdmDocumentStatus.CODE_DRAFT,
        "STATUS_PENDING": AdmDocumentStatus.CODE_PENDING,
        "STATUS_ISSUED": AdmDocumentStatus.CODE_ISSUED,
        "STATUS_EXPIRED": AdmDocumentStatus.CODE_EXPIRED,
    }
    template_name = (
        "admindocuments/document_detail_drawer.html"
        if as_drawer
        else "admindocuments/document_detail.html"
    )
    return render(request, template_name, context)


@login_required
@admin_staff_required
def document_update(request, doc_id: int):
    try:
        doc = AdmAdministrativeDocument.objects.get(pk=doc_id)
    except AdmAdministrativeDocument.DoesNotExist:
        messages.error(request, "Document not found.")
        return redirect("admindocuments:admindocuments_list")

    if request.method != "POST":
        return redirect("admindocuments:admindocuments_detail", doc_id=doc_id)

    form = AdmAdministrativeDocumentUpdateForm(
        request.POST, request.FILES, instance=doc
    )
    if not form.is_valid():
        messages.error(request, "Invalid data. Please check required fields.")
        return redirect("admindocuments:admindocuments_detail", doc_id=doc_id)

    doc = form.save(commit=False)
    attachment_link = form.cleaned_data.get("attachment_link")
    uploaded_file = request.FILES.get("attachment")
    issue_date = form.cleaned_data.get("issue_date") or doc.issue_date
    if not issue_date:
        issue_date = timezone.localdate() if settings.USE_TZ else date.today()
    doc.issue_date = issue_date
    doc.updated_by = request.user

    try:
        os.makedirs(settings.MEDIA_ROOT, exist_ok=True)
    except Exception:
        pass

    with transaction.atomic():
        doc.save()
        if uploaded_file or attachment_link:
            _create_attachment_version(
                document=doc,
                user=request.user,
                uploaded_file=uploaded_file,
                link=attachment_link,
            )

    if uploaded_file or attachment_link:
        messages.success(request, "Document updated successfully!")
    else:
        messages.success(request, "Document updated (không có file/link mới).")
    return redirect("admindocuments:admindocuments_detail", doc_id=doc_id)


@login_required
@admin_staff_required
def document_delete(request, doc_id: int):
    if request.method != "POST":
        return redirect("admindocuments:admindocuments_detail", doc_id=doc_id)

    with transaction.atomic():
        doc = (
            AdmAdministrativeDocument.objects.select_for_update()
            .select_related("doc_type", "issuing_company")
            .get(pk=doc_id)
        )
        if doc.is_void:
            messages.info(request, "Văn bản đã ở trạng thái vô hiệu.")
            return redirect("admindocuments:admindocuments_detail", doc_id=doc_id)

        year = doc.created_at.year
        counter = (
            AdmDocumentCounter.objects.select_for_update()
            .filter(doc_type=doc.doc_type, company=doc.issuing_company, year=year)
            .first()
        )
        if counter and doc.running_number == counter.next_number - 1:
            counter.next_number = doc.running_number
            counter.save(update_fields=["next_number", "updated_at"])

        original_number = doc.document_number_full
        doc.is_void = True
        doc.voided_at = timezone.now()
        doc.voided_by = request.user
        doc.updated_by = request.user
        doc.document_number_full = f"{original_number}-VOID"
        doc.save(
            update_fields=[
                "is_void",
                "voided_at",
                "voided_by",
                "updated_by",
                "document_number_full",
                "updated_at",
            ]
        )
    messages.success(request, "Đã vô hiệu văn bản và trả số hiệu về bộ đếm (nếu có thể).")
    return redirect("admindocuments:admindocuments_list")


@login_required
@admin_staff_required
def document_attachment_delete(request, doc_id: int, att_id: int):
    try:
        attachment = AdmDocumentAttachment.objects.select_related("document").get(
            pk=att_id, document_id=doc_id
        )
    except AdmDocumentAttachment.DoesNotExist:
        messages.error(request, "File không tồn tại.")
        return redirect("admindocuments:admindocuments_detail", doc_id=doc_id)

    if request.method != "POST":
        return redirect("admindocuments:admindocuments_detail", doc_id=doc_id)

    with transaction.atomic():
        attachment.is_deleted = True
        attachment.is_latest = False
        attachment.deleted_by = request.user
        attachment.deleted_at = timezone.now()
        attachment.save(update_fields=["is_deleted", "is_latest", "deleted_by", "deleted_at"])

        latest = (
            AdmDocumentAttachment.objects.filter(
                document_id=doc_id, is_deleted=False
            )
            .order_by("-version")
            .first()
        )
        if latest:
            latest.is_latest = True
            latest.save(update_fields=["is_latest"])

    messages.success(request, "Đã đánh dấu xóa file.")
    return redirect("admindocuments:admindocuments_detail", doc_id=doc_id)
