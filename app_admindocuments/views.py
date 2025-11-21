import csv
import os
from datetime import datetime
from functools import wraps

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.paginator import EmptyPage, PageNotAnInteger, Paginator
from django.db import IntegrityError, transaction
from django.db.models import Count, Q, Max
from django.db.models.functions import TruncDay
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

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
    AdmPaperDocument,
    AdmPaperType,
    AdmSignerRole,
)
from .services import allocate_running_number


def _has_admin_docs_access(user) -> bool:
    allowed_groups = ["administrative staff", "adminpaper"]
    return bool(
        getattr(user, "is_superuser", False)
        or user.groups.filter(name__in=allowed_groups).exists()
    )


def admin_staff_required(view_func):
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        if not request.user.is_authenticated:
            raise PermissionDenied
        if _has_admin_docs_access(request.user):
            return view_func(request, *args, **kwargs)
        raise PermissionDenied

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
    sort = request.GET.get("sort", "created")
    direction = request.GET.get("dir", "desc")

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
            "companies": companies,
            "departments": departments,
            "default_status": default_status,
            "has_admin_docs_access": _has_admin_docs_access(request.user),
            "STATUS_DRAFT": AdmDocumentStatus.CODE_DRAFT,
            "STATUS_PENDING": AdmDocumentStatus.CODE_PENDING,
            "STATUS_ISSUED": AdmDocumentStatus.CODE_ISSUED,
            "STATUS_EXPIRED": AdmDocumentStatus.CODE_EXPIRED,
        },
    )


@login_required
@admin_staff_required
def paper_document_list(request):
    selected_type = request.GET.get("paper_type", "")
    sort = request.GET.get("sort", "created")
    direction = request.GET.get("dir", "desc")

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
    ).order_by(order_field)
    paper_types = AdmPaperType.objects.filter(is_active=True).order_by("name")
    if selected_type:
        documents_qs = documents_qs.filter(paper_type_id=selected_type)

    if request.method == "POST":
        form = AdmPaperDocumentForm(request.POST)
        if form.is_valid():
            paper_doc = form.save(commit=False)
            paper_doc.created_by = request.user
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
                redirect_url += f"?{params.urlencode()}"
            return redirect(redirect_url)
        messages.error(request, "Dữ liệu không hợp lệ, vui lòng kiểm tra lại.")
    form = AdmPaperDocumentForm()

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
    }
    return render(request, "admindocuments/paper_document_list.html", context)


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
    if not request.FILES.get("attachment") and attachment_link:
        prefix = "\n" if doc.note else ""
        doc.note = f"{doc.note or ''}{prefix}Link đính kèm: {attachment_link}"

    attempts = 0
    while attempts < 3:
        attempts += 1
        try:
            with transaction.atomic():
                current_year = timezone.now().year
                doc.running_number = allocate_running_number(
                    doc.doc_type_id, current_year
                )
                doc.save()
            break
        except IntegrityError:
            if attempts >= 3:
                messages.error(
                    request, "Could not allocate unique number. Please try again."
                )
                return redirect("admindocuments:admindocuments_list")
            continue

    messages.success(request, "Document created successfully!")
    return redirect("admindocuments:admindocuments_list")


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
        ).get(pk=doc_id)
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
    doc.updated_by = request.user

    try:
        os.makedirs(settings.MEDIA_ROOT, exist_ok=True)
    except Exception:
        pass

    if request.FILES.get("attachment"):
        doc.attachment = request.FILES["attachment"]

    attachment_link = form.cleaned_data.get("attachment_link")
    if not request.FILES.get("attachment") and attachment_link:
        prefix = "\n" if doc.note else ""
        doc.note = f"{doc.note or ''}{prefix}Link đính kèm: {attachment_link}"

    doc.save()
    messages.success(request, "Document updated successfully!")
    return redirect("admindocuments:admindocuments_detail", doc_id=doc_id)
