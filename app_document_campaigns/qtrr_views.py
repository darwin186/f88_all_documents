from io import BytesIO

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.db import transaction
from django.db.models import Q
from django.http import FileResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST
from openpyxl import Workbook

from app_document_campaigns.models import (
    Campaign, CampaignError, CampaignErrorBooking, MediaArchiveJob, RiskErrorCode,
)
from app_document_campaigns.services.monitoring_access import scope_campaign_errors
from app_document_campaigns.views import _is_campaign_admin, campaign_admin_required


def _qtrr_rows(campaign):
    return (
        CampaignError.objects.filter(
            campaign=campaign,
            status__in=[CampaignError.Status.WAITING_AREA, CampaignError.Status.AREA_CONFIRMED],
        )
        .select_related("shop", "risk_booking__risk_code")
    )


def _build_final_qtrr_workbook(campaign):
    rows = _qtrr_rows(campaign).order_by("shop__shop_code", "contract_code", "pk")
    total = rows.count()
    if not total or rows.exclude(status=CampaignError.Status.AREA_CONFIRMED).exists():
        raise ValueError("QLKV chưa xác nhận xong toàn bộ dữ liệu.")
    if rows.filter(risk_booking__isnull=True).exists():
        raise ValueError("Còn dòng chưa mapping mã lỗi QTRR.")
    workbook = Workbook(write_only=True)
    sheet = workbook.create_sheet("Book loi QTRR")
    headers = ["Mã kỳ", "Mã PGD", "Tên PGD", "Mã hợp đồng", "Ngày phát sinh", "Loại lỗi", "Nội dung lỗi", "Nhân viên", "Nghiệp vụ", "Nguồn QTRR", "Mã lỗi QTRR", "Tên lỗi QTRR", "Ghi chú mapping"]
    sheet.append(headers)
    for error in rows.iterator(chunk_size=1000):
        booking = error.risk_booking
        sheet.append([
            campaign.code, error.shop.shop_code, error.shop.shop_name, error.contract_code,
            timezone.localtime(error.source_created_at).replace(tzinfo=None) if error.source_created_at and timezone.is_aware(error.source_created_at) else error.source_created_at,
            error.get_error_type_display(), error.checking_issue, error.employee_name, error.business_type_name,
            booking.risk_code.source, booking.risk_code.code, booking.risk_code.name, booking.note,
        ])
    output = BytesIO()
    workbook.save(output)
    return output.getvalue()


@login_required
def campaign_qtrr_booking(request, campaign_id):
    campaign = get_object_or_404(Campaign, pk=campaign_id)
    queryset, scope = scope_campaign_errors(_qtrr_rows(campaign), request.user)
    query = request.GET.get("q", "").strip()[:200]
    selected_code = request.GET.get("risk_code", "").strip()
    selected_type = request.GET.get("error_type", "").strip()
    if query:
        queryset = queryset.filter(
            Q(contract_code__icontains=query) | Q(shop__shop_name__icontains=query)
            | Q(checking_issue__icontains=query) | Q(document_type_name__icontains=query)
        )
    if selected_code == "__missing__":
        queryset = queryset.filter(risk_booking__isnull=True)
    elif selected_code.isdigit():
        queryset = queryset.filter(risk_booking__risk_code_id=int(selected_code))
    if selected_type in dict(CampaignError.ErrorType.choices):
        queryset = queryset.filter(error_type=selected_type)
    else:
        selected_type = ""
    all_rows = _qtrr_rows(campaign)
    total = all_rows.count()
    confirmed = all_rows.filter(status=CampaignError.Status.AREA_CONFIRMED).count()
    mapped = all_rows.filter(status=CampaignError.Status.AREA_CONFIRMED, risk_booking__isnull=False).count()
    from django.core.paginator import Paginator
    page = Paginator(queryset.order_by("shop__shop_code", "contract_code", "pk"), 100).get_page(request.GET.get("page"))
    params = request.GET.copy(); params.pop("page", None)
    archive_prefix = f"app_documents_campaigns/book_loi/{campaign.code}/final/"
    return render(request, "app_document_campaigns/campaign_qtrr_booking.html", {
        "campaign": campaign, "page": page, "scope": scope,
        "risk_codes": campaign.risk_error_codes.all().order_by("sort_order", "code"),
        "error_type_options": CampaignError.ErrorType.choices,
        "query": query, "selected_code": selected_code, "selected_type": selected_type,
        "filter_query": params.urlencode(), "total": total, "confirmed": confirmed, "mapped": mapped,
        "waiting_confirmation": max(total - confirmed, 0),
        "waiting_mapping": max(total - mapped, 0),
        "area_progress": round(confirmed * 100 / total) if total else 0,
        "mapping_progress": round(mapped * 100 / total) if total else 0,
        "ready_to_export": bool(total and confirmed == total and mapped == total),
        "can_manage": _is_campaign_admin(request.user),
        "latest_archive_job": MediaArchiveJob.objects.filter(source_path__startswith=archive_prefix).first(),
    })


@login_required
@require_POST
@campaign_admin_required
def map_qtrr_codes(request, campaign_id):
    import json
    campaign = get_object_or_404(Campaign, pk=campaign_id)
    try:
        payload = json.loads(request.body)
        ids = payload.get("error_ids")
        risk_code_id = int(payload.get("risk_code_id"))
        note = payload.get("note", "")
        if not isinstance(ids, list) or not ids or len(ids) > 500 or any(type(pk) is not int for pk in ids):
            raise ValueError("Chọn từ 1–500 dòng hợp lệ.")
        if not isinstance(note, str) or len(note) > 2000:
            raise ValueError("Ghi chú tối đa 2.000 ký tự.")
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        return JsonResponse({"ok": False, "error": str(exc)}, status=400)
    risk_code = get_object_or_404(campaign.risk_error_codes.all(), pk=risk_code_id)
    with transaction.atomic():
        rows = list(_qtrr_rows(campaign).select_for_update(of=("self",)).filter(pk__in=set(ids)))
        if len(rows) != len(set(ids)):
            return JsonResponse({"ok": False, "error": "Có dòng không thuộc kỳ hoặc không còn ở bước QTRR."}, status=409)
        if any(row.status != CampaignError.Status.AREA_CONFIRMED for row in rows):
            return JsonResponse({"ok": False, "error": "Chỉ mapping dòng QLKV đã xác nhận."}, status=409)
        for row in rows:
            CampaignErrorBooking.objects.update_or_create(
                error=row,
                defaults={"risk_code": risk_code, "note": note.strip(), "mapped_by": request.user},
            )
    return JsonResponse({"ok": True, "updated": len(rows), "message": f"Đã gán mã {risk_code.code} cho {len(rows)} dòng."})


@login_required
@campaign_admin_required
def export_qtrr_mapping_excel(request, campaign_id):
    from app_document_campaigns.services.qtrr_booking_excel import build_workbook

    campaign = get_object_or_404(Campaign, pk=campaign_id)
    try:
        content, _ = build_workbook(campaign)
    except ValueError as exc:
        messages.error(request, str(exc))
        return redirect("document_campaigns:campaign_qtrr_booking", campaign_id=campaign.pk)
    return FileResponse(
        BytesIO(content),
        as_attachment=True,
        filename=f"book-loi-qtrr-manual-{campaign.code}.xlsx",
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


@login_required
@require_POST
@campaign_admin_required
def import_qtrr_mapping_excel(request, campaign_id):
    from app_document_campaigns.services.qtrr_booking_excel import MAX_FILE_SIZE, import_workbook

    campaign = get_object_or_404(Campaign, pk=campaign_id)
    uploaded = request.FILES.get("file")
    if not uploaded or not uploaded.name.lower().endswith(".xlsx"):
        messages.error(request, "Chọn file Excel .xlsx đã tải từ Step 6.")
        return redirect("document_campaigns:campaign_qtrr_booking", campaign_id=campaign.pk)
    if uploaded.size > MAX_FILE_SIZE:
        messages.error(request, "File Excel tối đa 50 MB.")
        return redirect("document_campaigns:campaign_qtrr_booking", campaign_id=campaign.pk)
    try:
        summary = import_workbook(campaign.pk, request.user, uploaded.read(MAX_FILE_SIZE + 1))
    except Exception as exc:
        messages.error(request, f"Không thể cập nhật file Excel: {str(exc)[:1000]}")
    else:
        messages.success(request, f"Đã cập nhật {summary['updated']:,} dòng mapping từ Excel.")
    return redirect("document_campaigns:campaign_qtrr_booking", campaign_id=campaign.pk)


@login_required
@campaign_admin_required
def export_qtrr_excel(request, campaign_id):
    campaign = get_object_or_404(Campaign, pk=campaign_id)
    try:
        content = _build_final_qtrr_workbook(campaign)
    except ValueError as exc:
        return JsonResponse({"error": str(exc)}, status=409)
    return FileResponse(BytesIO(content), as_attachment=True, filename=f"book-loi-qtrr-{campaign.code}.xlsx", content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


@login_required
@require_POST
@campaign_admin_required
def archive_qtrr_excel(request, campaign_id):
    from app_document_campaigns.storage_views import enqueue_archive_job

    campaign = get_object_or_404(Campaign, pk=campaign_id)
    try:
        content = _build_final_qtrr_workbook(campaign)
    except ValueError as exc:
        messages.error(request, str(exc))
        return redirect("document_campaigns:campaign_qtrr_booking", campaign_id=campaign.pk)
    now = timezone.now()
    if timezone.is_aware(now):
        now = timezone.localtime(now)
    timestamp = now.strftime("%Y%m%d-%H%M%S")
    filename = f"book-loi-qtrr-{campaign.code}-{timestamp}.xlsx"
    local_path = default_storage.save(
        f"app_documents_campaigns/book_loi/{campaign.code}/final/{filename}",
        ContentFile(content),
    )
    job = MediaArchiveJob.objects.create(
        source_path=str(local_path).replace("\\", "/"),
        source_kind=MediaArchiveJob.SourceKind.FILE,
        requested_by=request.user,
    )
    job = enqueue_archive_job(job)
    if job.status == MediaArchiveJob.Status.FAILED:
        messages.error(request, f"Đã lưu file vào media nhưng chưa đồng bộ SharePoint: {job.error_message}")
    elif job.status == MediaArchiveJob.Status.SUCCEEDED:
        messages.success(request, "Đã lưu file cuối vào media và đồng bộ SharePoint thành công.")
    else:
        messages.success(request, "Đã lưu file cuối vào media và đưa yêu cầu SharePoint vào hàng đợi.")
    return redirect("document_campaigns:campaign_qtrr_booking", campaign_id=campaign.pk)
