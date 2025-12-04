import csv
import os
from datetime import datetime, time
from io import BytesIO
from functools import wraps

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.paginator import EmptyPage, PageNotAnInteger, Paginator
from django.db import IntegrityError, transaction, models
from django.db.models import Count, Q, Max
from django.db.models.functions import TruncDay, ExtractYear
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from openpyxl import Workbook

from .forms import (
    AdmAdministrativeDocumentForm,
    AdmAdministrativeDocumentUpdateForm,
    AdmPaperDocumentForm,
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
    AdmPaperDocument,
    AdmPaperType,
    AdmSignerRole,
)
from .services import allocate_running_number


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
            return datetime.strptime(value, "%Y-%m-%d").replace(tzinfo=tz)

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

    paper_queryset = AdmPaperDocument.objects.filter(created_at__gte=start, created_at__lt=end)
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
    sort = request.GET.get("sort", "created")
    direction = request.GET.get("dir", "desc")
    new_doc_id = request.GET.get("new")

    sort_map = {
        "number": "document_number_full",
        "title": "title",
        "type": "doc_type__name",
        "status": "status__code",
        "company": "issuing_company__name",
        "created": "created_at",
        "expiry": "expiry_date",
    }
    order_field = sort_map.get(sort, "created_at")
    if direction == "desc":
        order_field = f"-{order_field}"

    documents_qs = AdmAdministrativeDocument.objects.select_related(
        "doc_type", "signer_role", "status", "issuing_company"
    )
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
    documents_qs = documents_qs.order_by(order_field)

    page = request.GET.get("page", "1")
    paginator = Paginator(documents_qs, 10)
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
        },
    )


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
    )
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
                max_running = (
                    AdmPaperDocument.objects.filter(paper_type=paper_doc.paper_type).aggregate(
                        Max("running_number")
                    )["running_number__max"]
                    or 0
                )
                paper_doc.running_number = max_running + 1
                year_now = timezone.now().year
                paper_doc.document_number_full = (
                    f"{paper_doc.running_number:05d}/{year_now}/{paper_doc.paper_type.code}-F88"
                )
                paper_doc.save()
                messages.success(request, "Tạo phiếu giấy tờ thành công.")
            params = request.GET.copy()
            redirect_url = reverse("admindocuments:paper_document_list")
            if params:
                params.pop("edit", None)
                redirect_url += f"?{params.urlencode()}"
            return redirect(redirect_url)
        messages.error(request, "Dữ liệu không hợp lệ, vui lòng kiểm tra lại.")
    form = AdmPaperDocumentForm(instance=edit_instance)

    total_by_type = {
        row["paper_type"]: row["total"]
        for row in AdmPaperDocument.objects.values("paper_type").annotate(total=Count("id"))
    }
    paper_type_tabs = [
        {"id": p.pk, "name": p.name, "total": total_by_type.get(p.pk, 0)} for p in paper_types
    ]
    paginator = Paginator(documents_qs, 50)
    page_number = request.GET.get("page", "1")
    try:
        documents = paginator.page(page_number)
    except PageNotAnInteger:
        documents = paginator.page(1)
    except EmptyPage:
        documents = paginator.page(paginator.num_pages)

    context = {
        "documents": documents,
        "form": form,
        "paper_types": paper_type_tabs,
        "selected_type": selected_type,
        "sort": sort,
        "dir": direction,
        "paginator": paginator,
        "edit_id": edit_id or "",
    }
    return render(request, "admindocuments/paper_document_list.html", context)


@login_required
@admin_staff_required
def paper_document_detail(request, doc_id: int):
    paper_doc = get_object_or_404(
        AdmPaperDocument.objects.select_related(
            "paper_type", "requested_department", "courier_company"
        ),
        pk=doc_id,
    )
    if request.method == "POST":
        form = AdmPaperDocumentForm(request.POST, instance=paper_doc)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.updated_by = request.user
            obj.save()
            messages.success(request, "Cập nhật giấy tờ thành công.")
            return redirect("admindocuments:paper_document_detail", doc_id=doc_id)
        messages.error(request, "Dữ liệu không hợp lệ, vui lòng kiểm tra lại.")
    else:
        form = AdmPaperDocumentForm(instance=paper_doc)

    return render(
        request,
        "admindocuments/paper_document_detail.html",
        {"doc": paper_doc, "form": form},
    )


@login_required
@admin_staff_required
def paper_document_template(request):
    """Generate Excel template for paper documents import."""
    wb = Workbook()
    ws = wb.active
    ws.title = "Template"
    headers = [
        "Số hiệu",
        "Loại giấy",
        "Miền",
        "Đơn vị yêu cầu",
        "Nội dung",
        "Đơn vị chuyển phát",
        "Mã vận đơn",
        "Tình trạng",
        "Ngày tạo (yyyy-mm-dd)",
        "Ghi chú",
        "Người phụ trách",
    ]
    ws.append(headers)
    ws.append(
        [
            "00001/2025/ABC-F88",  # Số hiệu (có thể để trống để hệ thống đánh số)
            "Công văn",  # Loại giấy
            "Miền Bắc",  # Miền
            "PGD Hà Nội",  # Đơn vị yêu cầu
            "Nội dung ví dụ",  # Nội dung
            "VNPost",  # Đơn vị chuyển phát
            "ABC123456",  # Mã vận đơn
            "Đang chờ",  # Tình trạng
            "2025-02-03",  # Ngày tạo
            "Ghi chú ví dụ",  # Ghi chú
            "Nguyễn Văn A",  # Người phụ trách
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
def document_counter_manage(request):
    doc_types = AdmDocumentType.objects.all().order_by("name")
    companies = AdmCompany.objects.all().order_by("name")
    year_now = timezone.now().year

    if request.method == "POST":
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

        max_used = (
            AdmAdministrativeDocument.objects.filter(
                doc_type_id=doc_type_id,
                issuing_company_id=company_id,
                created_at__year=year,
            ).aggregate(mx=Max("running_number"))["mx"]
            or 0
        )
        if next_number <= max_used:
            messages.error(
                request,
                f"Số tiếp theo phải lớn hơn số đã dùng ({max_used}).",
            )
            return redirect("admindocuments:admindocuments_counters")

        counter, _ = AdmDocumentCounter.objects.get_or_create(
            doc_type_id=doc_type_id, company_id=company_id, year=year, defaults={"next_number": next_number}
        )
        if not _:
            counter.next_number = next_number
            counter.save(update_fields=["next_number", "updated_at"])
        messages.success(request, "Cập nhật counter thành công.")
        return redirect("admindocuments:admindocuments_counters")

    # prepare tracking
    used_map = {
        (row["doc_type_id"], row["issuing_company_id"], row["created_year"]): {
            "used_max": row["used_max"],
            "total": row["total"],
        }
        for row in AdmAdministrativeDocument.objects.values(
            "doc_type_id", "issuing_company_id", created_year=ExtractYear("created_at")
        ).annotate(used_max=Max("running_number"), total=Count("id"))
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
                "company": c.company,
                "year": c.year,
                "next_number": c.next_number,
                "used_max": used_info["used_max"] or 0,
                "total": used_info["total"] or 0,
                "gap_from": gap_from,
            }
        )

    return render(
        request,
        "admindocuments/document_counters.html",
        {
            "doc_types": doc_types,
            "companies": companies,
            "year_now": year_now,
            "counters": counter_rows,
        },
    )


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
    if issue_date:
        tz = timezone.get_current_timezone()
        doc.created_at = timezone.make_aware(datetime.combine(issue_date, time.min), tz)

    attempts = 0
    while attempts < 3:
        attempts += 1
        try:
            with transaction.atomic():
                current_year = timezone.now().year
                doc.running_number = allocate_running_number(
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
            if attempts >= 3:
                messages.error(
                    request, "Could not allocate unique number. Please try again."
                )
                return redirect("admindocuments:admindocuments_list")
            continue

    messages.success(
        request,
        f"Văn bản {doc.document_number_full} đã tạo thành công.",
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

    form = AdmAdministrativeDocumentUpdateForm(instance=doc)
    doc_types = AdmDocumentType.objects.all().order_by("name")
    content_types = AdmContentType.objects.all().order_by("name")
    signer_roles = AdmSignerRole.objects.all().order_by("title")
    companies = AdmCompany.objects.all().order_by("name")
    departments = (
        AdmDepartment.objects.select_related("company").all().order_by("name")
    )
    statuses = AdmDocumentStatus.objects.all().order_by("name")

    context = {
        "doc": doc,
        "form": form,
        "doc_types": doc_types,
        "content_types": content_types,
        "signer_roles": signer_roles,
        "companies": companies,
        "departments": departments,
        "statuses": statuses,
        "has_admin_docs_access": _has_admin_docs_access(request.user),
        "STATUS_DRAFT": AdmDocumentStatus.CODE_DRAFT,
        "STATUS_PENDING": AdmDocumentStatus.CODE_PENDING,
        "STATUS_ISSUED": AdmDocumentStatus.CODE_ISSUED,
        "STATUS_EXPIRED": AdmDocumentStatus.CODE_EXPIRED,
    }
    return render(request, "admindocuments/document_detail.html", context)


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
    issue_date = form.cleaned_data.get("issue_date")
    attachment_link = form.cleaned_data.get("attachment_link")
    if issue_date:
        tz = timezone.get_current_timezone()
        doc.created_at = timezone.make_aware(datetime.combine(issue_date, time.min), tz)
    doc.updated_by = request.user

    try:
        os.makedirs(settings.MEDIA_ROOT, exist_ok=True)
    except Exception:
        pass

    with transaction.atomic():
        doc.save()
        _create_attachment_version(
            document=doc,
            user=request.user,
            uploaded_file=request.FILES.get("attachment"),
            link=attachment_link,
        )

    messages.success(request, "Document updated successfully!")
    return redirect("admindocuments:admindocuments_detail", doc_id=doc_id)


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
