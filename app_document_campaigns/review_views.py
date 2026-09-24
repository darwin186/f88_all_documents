from app_document_campaigns.services.response_deadlines import shop_deadlines, shop_deadline_passed
import json
from datetime import timedelta

from django.contrib.auth.decorators import login_required
from django.conf import settings
from django.core.paginator import Paginator
from django.db import IntegrityError, transaction
from django.db.models import Count, OuterRef, Q, Subquery
from django.http import FileResponse, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from .models import Campaign, CampaignError, ShopSubmission, TeamReview, TeamReviewExcelJob
from .services.monitoring_access import scope_campaign_errors
from .services.team_review_excel import eligible_errors, MAX_FILE_SIZE
from .services.folder_receipt import with_folder_receipt, receipt_values
from .views import _is_campaign_admin, campaign_admin_required


def review_queryset(campaign):
    latest = TeamReview.objects.filter(error_id=OuterRef("pk")).order_by("-created_at", "-pk")
    return with_folder_receipt(eligible_errors(campaign)).select_related("shop", "shop_response").annotate(
        review_id=Subquery(latest.values("id")[:1]),
        review_decision=Subquery(latest.values("decision")[:1]),
        review_note=Subquery(latest.values("note")[:1]),
        reviewer=Subquery(latest.values("reviewed_by__username")[:1]),
        review_time=Subquery(latest.values("created_at")[:1]),
    )


def metrics(queryset):
    return queryset.aggregate(total=Count("id"), reviewed=Count("id", filter=Q(review_id__isnull=False)), kept=Count("id", filter=Q(review_decision="approved")), excluded=Count("id", filter=Q(review_decision="excluded")))


def deadline_passed(campaign):
    return bool(campaign.response_deadline and timezone.now() >= campaign.response_deadline)


@login_required
@require_POST
@campaign_admin_required
def queue_review_excel(request, campaign_id):
    campaign = get_object_or_404(Campaign, pk=campaign_id)
    kind = request.POST.get("kind")
    upload = request.FILES.get("file")
    if kind not in {"export", "import"}:
        return JsonResponse({"error": "Loại thao tác không hợp lệ."}, status=400)
    if kind == "import" and (campaign.status != Campaign.Status.ACTIVE or not upload or not upload.name.lower().endswith(".xlsx") or upload.size > MAX_FILE_SIZE):
        return JsonResponse({"error": "Chỉ import file .xlsx tối đa 50 MB khi kỳ đang team review."}, status=400)
    try:
        with transaction.atomic():
            job = TeamReviewExcelJob.objects.create(campaign=campaign, requested_by=request.user, kind=kind, message="Đang chờ xử lý")
    except IntegrityError:
        return JsonResponse({"error": "Đang có file cùng loại được xử lý. Vui lòng chờ."}, status=409)
    try:
        if upload and kind == "import":
            job.input_file.save(f"team-review-import-{job.pk}.xlsx", upload)
        from .tasks import process_team_review_excel
        if settings.FILE_JOBS_RUN_ON_WEB:
            process_team_review_excel.apply(args=[job.pk], throw=False)
        else:
            process_team_review_excel.delay(job.pk)
        job.refresh_from_db()
    except Exception:
        TeamReviewExcelJob.objects.filter(pk=job.pk).update(status="failed", message="Không xử lý được file trên web service. Kiểm tra storage và log web.", updated_at=timezone.now())
    return JsonResponse({"id": job.pk}, status=202)


@login_required
@campaign_admin_required
def review_excel_status(request, campaign_id, job_id):
    job = get_object_or_404(TeamReviewExcelJob, pk=job_id, campaign_id=campaign_id)
    cutoff = timezone.now() - timedelta(minutes=12)
    if job.status in {"queued", "running"} and job.updated_at < cutoff:
        TeamReviewExcelJob.objects.filter(pk=job.pk, status__in=["queued", "running"], updated_at__lt=cutoff).update(status="failed", message="Quá 12 phút không có tiến độ. Kiểm tra web service và tạo lại file.", updated_at=timezone.now())
        job.refresh_from_db()
    response = JsonResponse({"id": job.pk, "kind": job.kind, "status": job.status, "progress": job.progress, "message": job.message, "summary": job.summary, "download_url": f"/error-campaigns/campaigns/{campaign_id}/review/excel/{job.pk}/download/" if job.output_file and job.status == "succeeded" else None})
    response["Cache-Control"] = "no-store"
    return response


@login_required
@campaign_admin_required
def download_review_excel(request, campaign_id, job_id):
    job = get_object_or_404(TeamReviewExcelJob, pk=job_id, campaign_id=campaign_id, kind="export", status="succeeded")
    try:
        if not job.output_file:
            raise FileNotFoundError()
        stream = job.output_file.open("rb")
    except FileNotFoundError:
        return JsonResponse({"error": "Không tìm thấy file trên media của web service. Hãy tạo lại file."}, status=404)
    response = FileResponse(stream, as_attachment=True, filename=job.output_file.name.rsplit("/", 1)[-1], content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    response["Cache-Control"] = "no-store"
    return response


@login_required
@campaign_admin_required
def refresh_folder_receipt(request, campaign_id, error_id):
    campaign = get_object_or_404(Campaign, pk=campaign_id)
    error = get_object_or_404(review_queryset(campaign), pk=error_id)
    label, date = receipt_values(error)
    response = JsonResponse({"label": label, "date": date, "received": bool(error.error_type == "folder" and error.receipt_received)})
    response["Cache-Control"] = "no-store"
    return response


@login_required
def campaign_review(request, campaign_id):
    campaign = get_object_or_404(Campaign, pk=campaign_id)
    queryset, scope = scope_campaign_errors(review_queryset(campaign), request.user)
    stats = metrics(queryset)
    shops = queryset.order_by("shop__shop_code").values("shop_id", "shop__shop_code", "shop__shop_name").distinct()
    shop_filter = request.GET.get("shop", "")
    if shop_filter.isdigit():
        queryset = queryset.filter(shop_id=int(shop_filter))
    query = request.GET.get("q", "").strip()
    if query:
        queryset = queryset.filter(Q(contract_code__icontains=query) | Q(shop__shop_name__icontains=query) | Q(checking_issue__icontains=query))
    decision = request.GET.get("decision", "")
    response_choices = dict(campaign.response_options.values_list("value", "label"))
    for value in queryset.exclude(shop_response__answer_code="").values_list("shop_response__answer_code", flat=True).distinct():
        if value:
            response_choices.setdefault(value, value)
    response_filter = request.GET.get("response", "")
    if response_filter == "__unanswered__":
        queryset = queryset.filter(Q(shop_response__isnull=True) | Q(shop_response__answer_code=""))
    elif response_filter:
        queryset = queryset.filter(shop_response__answer_code=response_filter)
    if decision == "pending":
        queryset = queryset.filter(review_id__isnull=True)
    elif decision in {"approved", "excluded"}:
        queryset = queryset.filter(review_decision=decision)
    page = Paginator(queryset.order_by("shop__shop_code", "id"), 50).get_page(request.GET.get("page"))
    submitted_shops = set(ShopSubmission.objects.filter(campaign=campaign).values_list("shop_id", flat=True))
    expired = deadline_passed(campaign)
    deadlines = shop_deadlines(campaign)
    can_manage = _is_campaign_admin(request.user)
    labels = dict(campaign.response_options.values_list("value", "label"))
    for error in page:
        response = getattr(error, "shop_response", None)
        error.response_label = labels.get(response.answer_code, response.answer_code) if response else ""
        error.can_review = can_manage and campaign.status == Campaign.Status.ACTIVE and (error.shop_id in submitted_shops or shop_deadline_passed(campaign, error.shop_id, deadlines))
        error.shop_submitted = error.shop_id in submitted_shops
        error.shop_expired = shop_deadline_passed(campaign, error.shop_id, deadlines)
        error.receipt_label, error.receipt_display_date = receipt_values(error)
    excel_jobs = {kind: campaign.review_excel_jobs.filter(kind=kind).order_by("-pk").values_list("pk", flat=True).first() for kind in ("export", "import")} if can_manage else {}
    return render(request, "app_document_campaigns/campaign_review.html", {"campaign": campaign, "page": page, "shops": shops, "stats": stats, "percent": round(stats["reviewed"] * 100 / stats["total"]) if stats["total"] else 0, "can_manage_campaigns": can_manage, "scope": scope, "q": query, "shop_filter": shop_filter, "decision_filter": decision, "expired": expired, "excel_jobs": excel_jobs, "response_filter": response_filter, "response_choices": response_choices.items()})


@login_required
@require_POST
@campaign_admin_required
def bulk_team_review(request, campaign_id):
    try:
        data = json.loads(request.body)
        rows = data.get("rows")
        note = data.get("note", "")
        decision = data.get("decision", "")
        mode = data.get("mode", "append")
        if not isinstance(rows, list) or not 1 <= len(rows) <= 200 or not isinstance(note, str) or len(note) > 2000 or mode not in {"append", "replace"} or decision not in {"", "approved", "excluded"} or not (note.strip() or decision):
            raise ValueError("Chọn 1–200 dòng và nhập nhận xét hoặc kết luận hợp lệ.")
        ids = []
        for row in rows:
            if not isinstance(row, dict) or type(row.get("id")) is not int or "expected_review_id" not in row or (row["expected_review_id"] is not None and type(row["expected_review_id"]) is not int):
                raise ValueError("Thiếu thông tin phiên review. Tải lại trang.")
            ids.append(row["id"])
        if len(set(ids)) != len(ids):
            raise ValueError("Danh sách có dòng trùng.")
    except (ValueError, TypeError, AttributeError, UnicodeDecodeError) as exc:
        return JsonResponse({"error": str(exc)}, status=400)
    with transaction.atomic():
        campaign = get_object_or_404(Campaign.objects.select_for_update(), pk=campaign_id)
        if campaign.status != Campaign.Status.ACTIVE:
            return JsonResponse({"error": "Kỳ không ở giai đoạn team review."}, status=409)
        errors = {error.pk: error for error in eligible_errors(campaign).select_for_update(of=("self",)).filter(pk__in=ids)}
        submitted = set(ShopSubmission.objects.filter(campaign=campaign).values_list("shop_id", flat=True))
        latest = {}
        for review in TeamReview.objects.filter(error_id__in=ids).order_by("error_id", "-created_at", "-pk"):
            latest.setdefault(review.error_id, review)
        pending = []
        deadlines = shop_deadlines(campaign)
        for row in rows:
            error = errors.get(row["id"])
            previous = latest.get(row["id"])
            if not error or not (shop_deadline_passed(campaign, error.shop_id, deadlines) or error.shop_id in submitted):
                return JsonResponse({"error": "Có dòng chưa được phép review. Chưa cập nhật dòng nào."}, status=409)
            if (previous.pk if previous else None) != row["expected_review_id"]:
                return JsonResponse({"error": "Có dòng đã được người khác sửa. Tải lại trang; chưa cập nhật dòng nào."}, status=409)
            selected = decision or (previous.decision if previous else "")
            combined_note = (previous.note + "\n" + note.strip()).strip() if mode == "append" and previous and note.strip() else (previous.note if mode == "append" and previous else note.strip())
            if selected not in {"approved", "excluded"} or len(combined_note) > 2000:
                return JsonResponse({"error": "Có dòng chưa có kết luận hoặc nhận xét vượt 2.000 ký tự. Chọn kết luận chung; chưa cập nhật dòng nào."}, status=400)
            if not previous or previous.decision != selected or previous.note != combined_note:
                pending.append(TeamReview(error=error, decision=selected, note=combined_note, reviewed_by=request.user))
        TeamReview.objects.bulk_create(pending, batch_size=200)
    return JsonResponse({"updated": len(pending)})


@login_required
@require_POST
@campaign_admin_required
def save_team_review(request, campaign_id, error_id):
    try:
        data = json.loads(request.body)
        if not isinstance(data, dict) or data.get("decision") not in {"approved", "excluded"}:
            raise ValueError("Chọn Giữ lỗi hoặc Loại lỗi.")
        note = data.get("note", "")
        if not isinstance(note, str) or len(note) > 2000:
            raise ValueError("Nhận xét tối đa 2.000 ký tự.")
        if "expected_review_id" not in data or (data["expected_review_id"] is not None and type(data["expected_review_id"]) is not int):
            raise ValueError("Thiếu thông tin phiên review. Vui lòng tải lại trang.")
    except (ValueError, UnicodeDecodeError) as exc:
        return JsonResponse({"error": str(exc)}, status=400)
    with transaction.atomic():
        campaign = get_object_or_404(Campaign.objects.select_for_update(), pk=campaign_id)
        error = get_object_or_404(CampaignError.objects.select_for_update(), campaign=campaign, pk=error_id)
        if campaign.status != Campaign.Status.ACTIVE or error.status == CampaignError.Status.CANCELLED or (error.status == CampaignError.Status.EXCLUDED and not error.team_reviews.exists()):
            return JsonResponse({"error": "Dòng dữ liệu không ở giai đoạn review phản hồi PGD."}, status=409)
        if not shop_deadline_passed(campaign, error.shop_id) and not ShopSubmission.objects.filter(campaign=campaign, shop_id=error.shop_id).exists():
            return JsonResponse({"error": "PGD chưa gửi chính thức và chưa hết hạn phản hồi."}, status=409)
        latest = error.team_reviews.order_by("-created_at", "-pk").first()
        if (latest.pk if latest else None) != data["expected_review_id"]:
            return JsonResponse({"error": "Dòng này đã được người khác review. Tải lại trang để xem kết quả mới."}, status=409)
        review = TeamReview.objects.create(error=error, decision=data["decision"], note=note.strip(), reviewed_by=request.user)
    stats = metrics(review_queryset(campaign))
    return JsonResponse({"review_id": review.pk, "reviewer": request.user.username, "stats": stats, "percent": round(stats["reviewed"] * 100 / stats["total"]) if stats["total"] else 0})
