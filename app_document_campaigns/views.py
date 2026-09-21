import json
from functools import wraps
from datetime import timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db import IntegrityError, transaction
from django.db.models import Count, F, Max, Q
from django.http import FileResponse, Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_POST

from app_document_campaigns.forms import (
    CampaignCreateForm,
    CampaignDeadlineForm,
    CampaignSettingsForm,
)
from app_document_campaigns.models import (
    Campaign,
    CampaignError,
    CampaignImportSource,
    CampaignImportJob,
    CampaignVersion,
    ShopAccessLink,
    ShopSubmission,
)
from app_document_campaigns.services.access_links import (
    AccessLinkError,
    issue_shop_access_link,
    resolve_shop_access_link,
)
from app_document_campaigns.services.imports import CampaignImportError, publish_excel_version
from app_document_campaigns.services.monitoring_access import scope_campaign_errors
from app_document_campaigns.services.responses import (
    ResponseConflictError,
    ResponseReadOnlyError,
    ResponseValidationError,
    save_response_batch,
    submit_shop_responses,
)
from app_document_campaigns.tasks import (
    run_campaign_excel_export,
    run_campaign_excel_import,
    run_campaign_sql_import,
)


def health(request):
    return JsonResponse({"ok": True, "app": "app_document_campaigns"})


@login_required
def campaign_list(request):
    campaigns = Campaign.objects.select_related("campaign_type", "current_version").all()[:100]
    return render(
        request,
        "app_document_campaigns/campaign_list.html",
        {
            "campaigns": campaigns,
            "can_manage_campaigns": _is_campaign_admin(request.user),
        },
    )


@login_required
@transaction.atomic
def campaign_create(request):
    if not _is_campaign_admin(request.user):
        return HttpResponse("Chỉ admin được tạo chiến dịch.", status=403)
    if request.method == "POST":
        form = CampaignCreateForm(request.POST)
        if form.is_valid():
            campaign = form.save(commit=False)
            campaign.status = Campaign.Status.DATA_REVIEW
            campaign.created_by = request.user
            campaign.save()
            form.save_response_options()
            messages.success(request, "Đã tạo chiến dịch. Hãy tạo version nháp để chạy dữ liệu SQL.")
            return redirect("document_campaigns:campaign_detail", campaign_id=campaign.pk)
    else:
        form = CampaignCreateForm()
    return render(request, "app_document_campaigns/campaign_form.html", {"form": form})


@login_required
def campaign_detail(request, campaign_id):
    campaign = get_object_or_404(Campaign.objects.select_related("current_version"), pk=campaign_id)
    versions = list(campaign.versions.prefetch_related("import_sources").all())
    selected_version = None
    requested_version = request.GET.get("version")
    if requested_version:
        selected_version = next((item for item in versions if str(item.pk) == requested_version), None)
    if selected_version is None and versions:
        selected_version = next((item for item in versions if item.pk == campaign.current_version_id), versions[0])

    sources = []
    dataset_metrics = []
    excel_source = None
    latest_job = None
    latest_export_job = None
    latest_reviewed_export_job = None
    if selected_version:
        latest_job = selected_version.import_jobs.first()
        latest_export_job = (
            selected_version.import_jobs.filter(
                job_type__in=[CampaignImportJob.JobType.SQL_STAGE, CampaignImportJob.JobType.EXCEL_EXPORT],
                status=CampaignImportJob.Status.SUCCEEDED,
                summary__export_kind__isnull=True,
            )
            .exclude(output_file="")
            .first()
        )
        sources = list(selected_version.import_sources.order_by("id"))
        excel_source = next(
            (source for source in sources if source.source_type == CampaignVersion.SourceType.EXCEL),
            None,
        )
        if excel_source:
            latest_reviewed_export_job = selected_version.import_jobs.filter(
                job_type=CampaignImportJob.JobType.EXCEL_EXPORT,
                status=CampaignImportJob.Status.SUCCEEDED,
                summary__export_kind="reviewed",
                summary__source_checksum=excel_source.source_checksum,
            ).exclude(output_file="").first()
        display_sources = [excel_source] if excel_source else sources
        if display_sources:
            from app_document_campaigns.models import CampaignStagingRow

            from app_document_campaigns.services.dataset_metrics import summarize_dataset

            dataset_metrics = summarize_dataset(
                CampaignStagingRow.objects.filter(source__in=display_sources)
            )
    has_sql = any(source.source_type == CampaignVersion.SourceType.SQL for source in sources)
    if selected_version and selected_version.status == CampaignVersion.Status.PUBLISHED:
        workflow_step, workflow_progress = 5, 100
    elif excel_source and excel_source.status == CampaignImportSource.Status.VALIDATED:
        workflow_step, workflow_progress = 4, 75
    elif excel_source:
        workflow_step, workflow_progress = 3, 50
    elif has_sql:
        workflow_step, workflow_progress = 2, 25
    else:
        workflow_step, workflow_progress = 1, 0
    can_manage_shop_links = request.user.is_superuser or request.user.groups.filter(name="admin").exists()
    from app_document_campaigns.services.sql_sources import sql_source_options
    prepared_files = list(selected_version.import_jobs.filter(status=CampaignImportJob.Status.SUCCEEDED, job_type__in=[CampaignImportJob.JobType.SQL_STAGE, CampaignImportJob.JobType.EXCEL_EXPORT]).exclude(output_file="")) if selected_version else []
    prepared_files = [job for job in prepared_files if job.summary.get("export_kind") != "reviewed" or (excel_source and job.summary.get("source_checksum") == excel_source.source_checksum)]
    busy = bool(latest_job and latest_job.status in (CampaignImportJob.Status.QUEUED, CampaignImportJob.Status.RUNNING))
    data_locked = campaign.status in (Campaign.Status.ACTIVE, Campaign.Status.CLOSED, Campaign.Status.CANCELLED) or bool(selected_version and selected_version.status == CampaignVersion.Status.PUBLISHED)
    return render(
        request,
        "app_document_campaigns/campaign_detail.html",
        {
            "campaign": campaign,
            "versions": versions,
            "selected_version": selected_version,
            "sources": sources,
            "excel_source": excel_source,
            "dataset_metrics": dataset_metrics,
            "has_sql": has_sql,
            "workflow_step": workflow_step,
            "workflow_progress": workflow_progress,
            "prepared_files": prepared_files,
            "sql_source_options": sql_source_options(),
            "data_locked": data_locked,
            "job_busy": busy,
            "has_requested_data": bool(sources) or bool(selected_version and selected_version.import_jobs.filter(job_type=CampaignImportJob.JobType.SQL_STAGE).exists()),
            "can_publish_data": bool(excel_source and excel_source.status == CampaignImportSource.Status.VALIDATED and not excel_source.invalid_count and not busy and not data_locked),
            "latest_job": latest_job,
            "latest_export_job": latest_export_job,
            "latest_reviewed_export_job": latest_reviewed_export_job,
            "can_manage_shop_links": can_manage_shop_links,
            "settings_form": CampaignSettingsForm(instance=campaign),
            "open_settings": request.GET.get("settings") == "1",
        },
    )


def _is_campaign_admin(user):
    return user.is_superuser or user.groups.filter(name="admin").exists()


def campaign_admin_required(view):
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        if not _is_campaign_admin(request.user):
            return HttpResponse("Chỉ admin được thay đổi dữ liệu chiến dịch.", status=403)
        return view(request, *args, **kwargs)
    return wrapped


@login_required
@require_POST
@transaction.atomic
def update_campaign_deadline(request, campaign_id):
    wants_json = (
        request.headers.get("X-Requested-With") == "XMLHttpRequest"
        or "application/json" in request.headers.get("Accept", "")
    )
    if not _is_campaign_admin(request.user):
        if wants_json:
            return JsonResponse({"ok": False, "error": "Chỉ Admin được cấu hình hạn phản hồi."}, status=403)
        return HttpResponse("Chỉ Admin được cấu hình hạn phản hồi.", status=403)
    campaign = get_object_or_404(Campaign.objects.select_for_update(), pk=campaign_id)
    form = CampaignDeadlineForm(request.POST, instance=campaign)
    if not form.is_valid():
        if wants_json:
            return JsonResponse({"ok": False, "error": " ".join(str(error) for errors in form.errors.values() for error in errors)}, status=400)
        messages.error(request, "Hạn phản hồi không hợp lệ.")
    else:
        campaign = form.save()
        campaign.shop_links.filter(has_deadline_extension=False).update(
            response_deadline=campaign.response_deadline,
            expires_at=campaign.link_expires_at,
        )
        messages.success(request, "Đã cập nhật hạn PGD và hạn hiệu lực link.")
        if wants_json:
            return JsonResponse({"ok": True})
    if request.POST.get("return_to") == "area_monitor":
        return redirect("document_campaigns:campaign_area_monitor", campaign_id=campaign.pk)
    if request.POST.get("return_to") == "response_monitor":
        return redirect("document_campaigns:campaign_response_monitor", campaign_id=campaign.pk)
    return redirect("document_campaigns:campaign_detail", campaign_id=campaign.pk)


@login_required
@require_POST
@transaction.atomic
def update_campaign_settings(request, campaign_id):
    if not _is_campaign_admin(request.user):
        return HttpResponse("Chỉ Admin được chỉnh sửa chiến dịch.", status=403)
    campaign = get_object_or_404(Campaign.objects.select_for_update(), pk=campaign_id)
    form = CampaignSettingsForm(request.POST, instance=campaign)
    if not form.is_valid():
        error_text = " ".join(
            str(error) for errors in form.errors.values() for error in errors
        )
        messages.error(request, f"Không thể lưu cài đặt. {error_text}")
        return redirect(
            f"{reverse('document_campaigns:campaign_detail', kwargs={'campaign_id': campaign.pk})}?settings=1"
        )
    campaign = form.save()
    if "response_deadline" in form.changed_data:
        campaign.shop_links.filter(has_deadline_extension=False).update(
            response_deadline=campaign.response_deadline,
            expires_at=campaign.link_expires_at,
        )
    messages.success(request, "Đã cập nhật cài đặt chiến dịch.")
    return redirect("document_campaigns:campaign_detail", campaign_id=campaign.pk)


@login_required
@require_POST
def issue_campaign_shop_link(request, campaign_id, shop_id):
    if not _is_campaign_admin(request.user):
        return JsonResponse({"ok": False, "error": "Chỉ Admin được phát hành link PGD."}, status=403)
    campaign = get_object_or_404(Campaign, pk=campaign_id)
    campaign_error = (
        CampaignError.objects.filter(campaign=campaign, shop_id=shop_id)
        .exclude(status__in=[CampaignError.Status.EXCLUDED, CampaignError.Status.CANCELLED])
        .select_related("shop")
        .first()
    )
    if not campaign_error:
        raise Http404("PGD không có lỗi trong chiến dịch này.")
    if not campaign.response_deadline or not campaign.link_expires_at:
        return JsonResponse(
            {"ok": False, "error": "Hãy cấu hình hạn phản hồi PGD trước khi tạo link."},
            status=409,
        )
    link, raw_token = issue_shop_access_link(
        campaign=campaign,
        shop=campaign_error.shop,
        allowed_email=campaign_error.shop.shop_email,
        created_by=request.user,
    )
    response_url = request.build_absolute_uri(
        reverse("document_campaigns:shop_response", kwargs={"raw_token": raw_token})
    )
    response = JsonResponse(
        {
            "ok": True,
            "url": response_url,
            "created_at": timezone.now().strftime("%H:%M %d/%m/%Y"),
        }
    )
    response["Cache-Control"] = "no-store"
    return response


@login_required
@require_POST
def publish_campaign_to_shops(request, campaign_id):
    if not _is_campaign_admin(request.user):
        return JsonResponse({"ok": False, "error": "Chỉ Admin được phát hành tới PGD."}, status=403)
    campaign = get_object_or_404(
        Campaign.objects.select_related("current_version"),
        pk=campaign_id,
    )
    if not campaign.current_version or campaign.current_version.status != CampaignVersion.Status.PUBLISHED:
        return JsonResponse(
            {"ok": False, "error": "Cần xác nhận version dữ liệu chính thức trước khi phát hành."},
            status=409,
        )
    if not campaign.response_deadline or not campaign.link_expires_at:
        return JsonResponse(
            {"ok": False, "error": "Hãy cấu hình hạn phản hồi PGD trước khi phát hành."},
            status=409,
        )
    if campaign.response_deadline <= timezone.now():
        return JsonResponse(
            {"ok": False, "error": "Hạn phản hồi PGD đã qua. Hãy cập nhật deadline trước."},
            status=409,
        )

    shop_rows = list(
        CampaignError.objects.filter(campaign=campaign)
        .exclude(status__in=[CampaignError.Status.EXCLUDED, CampaignError.Status.CANCELLED])
        .values("shop_id", "shop__shop_code", "shop__shop_name", "shop__shop_email")
        .distinct()
        .order_by("shop__shop_code")
    )
    if not shop_rows:
        return JsonResponse(
            {"ok": False, "error": "Chiến dịch chưa có dữ liệu lỗi PGD để phát hành."},
            status=409,
        )

    from app_documents.models import Shop

    shops = Shop.objects.in_bulk(row["shop_id"] for row in shop_rows)
    issued_links = []
    with transaction.atomic():
        for row in shop_rows:
            shop = shops[row["shop_id"]]
            _, raw_token = issue_shop_access_link(
                campaign=campaign,
                shop=shop,
                allowed_email=shop.shop_email,
                created_by=request.user,
            )
            issued_links.append(
                {
                    "shop_id": shop.pk,
                    "shop_code": shop.shop_code,
                    "shop_name": shop.shop_name,
                    "url": request.build_absolute_uri(
                        reverse("document_campaigns:shop_response", kwargs={"raw_token": raw_token})
                    ),
                }
            )
        CampaignError.objects.filter(
            campaign=campaign,
            status=CampaignError.Status.READY,
        ).update(status=CampaignError.Status.WAITING_SHOP)
        campaign.status = Campaign.Status.ACTIVE
        campaign.response_opens_at = timezone.now()
        campaign.save(update_fields=["status", "response_opens_at", "updated_at"])

    response = JsonResponse(
        {
            "ok": True,
            "count": len(issued_links),
            "links": issued_links,
            "status_label": campaign.get_status_display(),
        }
    )
    response["Cache-Control"] = "no-store"
    return response


@login_required
def campaign_response_monitor(request, campaign_id):
    from app_document_campaigns.services.email_metrics import emailed_area_manager_count
    from app_document_campaigns.services.response_deadlines import shop_deadlines, shop_deadline_passed
    campaign = get_object_or_404(Campaign.objects.select_related("current_version"), pk=campaign_id)
    errors, access_scope = scope_campaign_errors(CampaignError.objects.filter(campaign=campaign).exclude(status__in=["excluded", "cancelled"]), request.user)
    grouped = list(errors.values("shop_id", "shop__shop_code", "shop__shop_name", "shop__shop_email",
        "shop__manager_id__regionManager_id", "shop__manager_id__regionManager__regionManager_name",
        "shop__manager_id__areaManager_id", "shop__manager_id__areaManager__areaManager_name").annotate(
        total_errors=Count("id"), answered_errors=Count("id", filter=Q(shop_response__answer_code__isnull=False) & ~Q(shop_response__answer_code="")),
        last_response_at=Max("shop_response__updated_at")))
    ids = [row["shop_id"] for row in grouped]
    submitted = set(ShopSubmission.objects.filter(campaign=campaign, shop_id__in=ids).values_list("shop_id", flat=True))
    links = {link.shop_id: link for link in ShopAccessLink.objects.filter(campaign=campaign, shop_id__in=ids)}
    from app_document_campaigns.models import TeamReview
    reviewed_shops = set(TeamReview.objects.filter(error__campaign=campaign, error__shop_id__in=ids).values_list("error__shop_id", flat=True))
    deadlines = shop_deadlines(campaign)
    regions = sorted({(row["shop__manager_id__regionManager_id"], row["shop__manager_id__regionManager__regionManager_name"] or "Chưa xác định") for row in grouped if row["shop__manager_id__regionManager_id"]}, key=lambda pair: pair[1])
    areas = sorted({(row["shop__manager_id__areaManager_id"], row["shop__manager_id__areaManager__areaManager_name"] or "Chưa xác định", row["shop__manager_id__regionManager_id"]) for row in grouped if row["shop__manager_id__areaManager_id"]}, key=lambda pair: pair[1])
    shops = sorted([(row["shop_id"], row["shop__shop_code"], row["shop__shop_name"], row["shop__manager_id__regionManager_id"], row["shop__manager_id__areaManager_id"]) for row in grouped], key=lambda row: row[1] or 0)
    region = request.GET.get("region", "").strip()
    area = request.GET.get("area", "").strip()
    shop = request.GET.get("shop", "").strip()
    if region not in {str(pair[0]) for pair in regions}: region = ""
    if area not in {str(pair[0]) for pair in areas if not region or str(pair[2]) == region}: area = ""
    if shop not in {str(row[0]) for row in shops if (not region or str(row[3]) == region) and (not area or str(row[4]) == area)}: shop = ""
    statuses = [value for value in request.GET.getlist("status") if value in {"not_started", "in_progress", "submitted", "expired"}]
    all_rows = []
    for row in grouped:
        is_submitted = row["shop_id"] in submitted
        link = links.get(row["shop_id"])
        row["can_extend"] = bool(campaign.status == Campaign.Status.ACTIVE and link and not link.revoked_at and not is_submitted and row["shop_id"] not in reviewed_shops)
        row["can_email"] = bool(campaign.status == Campaign.Status.ACTIVE and link and link.is_editable and not is_submitted)
        expired = shop_deadline_passed(campaign, row["shop_id"], deadlines)
        status = "submitted" if is_submitted else "expired" if expired else "in_progress" if row["answered_errors"] else "not_started"
        labels = {"submitted": "Đã gửi", "expired": "Hết hạn phản hồi", "in_progress": "Đang phản hồi", "not_started": "Chưa phản hồi"}
        response_progress = int(row["answered_errors"] * 100 / max(row["total_errors"], 1))
        row.update(status=status, status_label=labels[status], complete=is_submitted or expired,
            progress=response_progress,
            progress_hue=round(response_progress * 1.2),
            access_link=links.get(row["shop_id"]), deadline=deadlines.get(row["shop_id"], campaign.response_deadline),
            region_manager_name=row["shop__manager_id__regionManager__regionManager_name"],
            area_manager_name=row["shop__manager_id__areaManager__areaManager_name"])
        all_rows.append(row)
    total_errors = errors.count()
    total_contracts = errors.exclude(contract_code="").values("contract_code").distinct().count()
    submitted_count = sum(row["shop_id"] in submitted for row in all_rows)
    summary = {"shops": len(all_rows), "issued": sum(bool(row["access_link"] and not row["access_link"].revoked_at) for row in all_rows),
        "area_emailed": emailed_area_manager_count(campaign, ids),
        "submitted": submitted_count,
        "submitted_rate": round(submitted_count * 100 / len(all_rows)) if all_rows else 0,
        "in_progress": sum(row["shop_id"] not in submitted and bool(row["answered_errors"]) for row in all_rows),
        "not_started": sum(row["shop_id"] not in submitted and not row["answered_errors"] for row in all_rows),
        "errors": total_errors, "contracts": total_contracts}
    rows = [row for row in all_rows if (not region or str(row["shop__manager_id__regionManager_id"]) == region)
        and (not area or str(row["shop__manager_id__areaManager_id"]) == area)
        and (not shop or str(row["shop_id"]) == shop) and (not statuses or row["status"] in statuses)]
    rows.sort(key=lambda row: (row["complete"], row["progress"], row["shop__shop_code"] or 0, row["shop_id"]))
    page = Paginator(rows, 50).get_page(request.GET.get("page"))
    params = request.GET.copy()
    params.pop("page", None)
    progress = round(sum(row["complete"] for row in all_rows) * 100 / len(all_rows)) if all_rows else 0
    return render(request, "app_document_campaigns/campaign_response_monitor.html", {
        "campaign": campaign, "access_scope": access_scope, "rows": page.object_list, "page": page,
        "page_range": page.paginator.get_elided_page_range(page.number, on_each_side=2, on_ends=1), "filter_query": params.urlencode(),
        "regions": regions, "areas": areas, "shops": shops, "selected_region": region, "selected_area": area,
        "selected_shop": shop, "selected_statuses": statuses, "summary": summary, "shop_response_progress": progress,
        "active_monitor_tab": "shops",
        "can_manage_shop_links": _is_campaign_admin(request.user), "issued_shop_link_count": summary["issued"],
        "deadline_form": CampaignDeadlineForm(instance=campaign), "can_publish_shop_links": bool(campaign.current_version
            and campaign.current_version.status == CampaignVersion.Status.PUBLISHED
            and campaign.status not in (Campaign.Status.CLOSED, Campaign.Status.CANCELLED)
            and campaign.response_deadline and campaign.response_deadline > timezone.now())})


def _occurrence_order(request):
    direction = request.GET.get("date_order", "asc")
    if direction not in {"asc", "desc"}:
        direction = "asc"
    field = F("source_created_at")
    return direction, field.desc(nulls_last=True) if direction == "desc" else field.asc(nulls_last=True)


@login_required
def campaign_response_records(request, campaign_id):
    campaign = get_object_or_404(Campaign, pk=campaign_id)
    queryset, scope = scope_campaign_errors(
        CampaignError.objects.filter(campaign=campaign)
        .exclude(status__in=[CampaignError.Status.EXCLUDED, CampaignError.Status.CANCELLED])
        .select_related("shop", "shop_response"), request.user,
    )
    shops = list(queryset.order_by("shop__shop_code").values("shop_id", "shop__shop_code", "shop__shop_name").distinct())
    shop_filter = request.GET.get("shop", "")
    if shop_filter.isdigit():
        queryset = queryset.filter(shop_id=int(shop_filter))
    elif shop_filter:
        queryset = queryset.none()
    direction, ordering = _occurrence_order(request)
    page = Paginator(queryset.order_by(ordering, "id"), 50).get_page(request.GET.get("page"))
    labels = dict(campaign.response_options.values_list("value", "label"))
    for error in page:
        response = getattr(error, "shop_response", None)
        error.response_label = labels.get(response.answer_code, response.answer_code) if response else ""
    return render(request, "app_document_campaigns/campaign_response_records.html", {
        "campaign": campaign, "page": page, "shops": shops, "access_scope": scope,
        "shop_filter": shop_filter, "date_order": direction,
    })


@login_required
def shop_response_monitor_detail(request, campaign_id, shop_id):
    campaign = get_object_or_404(Campaign, pk=campaign_id)
    base_errors = (
        CampaignError.objects.filter(campaign=campaign)
        .exclude(status__in=[CampaignError.Status.EXCLUDED, CampaignError.Status.CANCELLED])
        .select_related("shop", "region", "area_manager", "shop_response")
    )
    scoped_errors, access_scope = scope_campaign_errors(base_errors, request.user)
    direction, ordering = _occurrence_order(request)
    errors = list(scoped_errors.filter(shop_id=shop_id).order_by(ordering, "id"))
    if not errors:
        raise Http404("Không tìm thấy PGD trong phạm vi được phép.")
    shop = errors[0].shop
    submission = ShopSubmission.objects.filter(campaign=campaign, shop=shop).first()
    labels = dict(campaign.response_options.values_list("value", "label"))
    for error in errors:
        response = getattr(error, "shop_response", None)
        error.response_label = labels.get(response.answer_code, response.answer_code) if response else ""
    answered = sum(bool(getattr(error, "shop_response", None) and error.shop_response.answer_code) for error in errors)
    return render(
        request,
        "app_document_campaigns/shop_response_monitor_detail.html",
        {
            "campaign": campaign,
            "shop": shop,
            "errors": errors,
            "submission": submission,
            "answered": answered,
            "total": len(errors),
            "access_scope": access_scope,
            "date_order": direction,
        },
    )


@login_required
@require_POST
@campaign_admin_required
def create_campaign_version(request, campaign_id):
    try:
        selected_sources = _selected_sql_sources(request) if request.POST.get("start_sql") == "1" else None
    except CampaignImportError as exc:
        return HttpResponse(str(exc), status=400)
    with transaction.atomic():
        campaign = get_object_or_404(Campaign.objects.select_for_update(), pk=campaign_id)
        existing = campaign.current_version or campaign.versions.first()
        if existing:
            messages.info(request, "Kỳ đã có bộ dữ liệu làm việc. Không tạo thêm version.")
            return redirect(f"{reverse('document_campaigns:campaign_detail', kwargs={'campaign_id': campaign.pk})}?version={existing.pk}")
        if campaign.status in (Campaign.Status.ACTIVE, Campaign.Status.CLOSED, Campaign.Status.CANCELLED):
            messages.error(request, "Trạng thái chiến dịch hiện tại không cho tạo version SQL mới.")
            return redirect("document_campaigns:campaign_detail", campaign_id=campaign.pk)
        version = CampaignVersion.objects.create(
            campaign=campaign,
            version_number=1,
            source_type=CampaignVersion.SourceType.SQL,
            created_by=request.user,
        )
        messages.success(request, "Đã khởi tạo bộ dữ liệu của kỳ.")
        if request.POST.get("start_sql") == "1":
            job = CampaignImportJob.objects.create(version=version, created_by=request.user, total_steps=len(selected_sources)+1, summary={"prepare_excel": True, "source_names": selected_sources})
            transaction.on_commit(lambda: _enqueue_import_job(job, run_campaign_sql_import))
    return redirect(f"{request.path_info.rsplit('/versions/', 1)[0]}/?version={version.pk}")


@login_required
@require_POST
@campaign_admin_required
def stage_sql_version(request, version_id):
    version = get_object_or_404(CampaignVersion.objects.select_related("campaign"), pk=version_id)
    if version.status == CampaignVersion.Status.PUBLISHED or version.campaign.status in (Campaign.Status.ACTIVE, Campaign.Status.CLOSED, Campaign.Status.CANCELLED):
        return HttpResponse("Dữ liệu đã phát hành hoặc kỳ đã khóa; không thể truy xuất lại.", status=409)
    try:
        selected_sources = _selected_sql_sources(request)
    except CampaignImportError as exc:
        return HttpResponse(str(exc), status=400)
    try:
        with transaction.atomic():
            job = CampaignImportJob.objects.create(
                version=version,
                created_by=request.user,
                total_steps=len(selected_sources) + (1 if request.POST.get("prepare_excel") == "1" else 0),
                summary={"source_names": selected_sources, "prepare_excel": request.POST.get("prepare_excel") == "1"},
            )
            transaction.on_commit(lambda: _enqueue_import_job(job, run_campaign_sql_import))
    except IntegrityError:
        messages.info(request, "Version này đang có một job truy xuất dữ liệu chưa hoàn tất.")
    else:
        job.refresh_from_db()
        if job.status == CampaignImportJob.Status.FAILED:
            messages.error(request, job.error_message)
        else:
            messages.success(request, "Đã đưa yêu cầu vào hàng đợi. Bạn có thể theo dõi tiến độ ngay trên trang.")
    return redirect(
        "document_campaigns:campaign_detail",
        campaign_id=version.campaign_id,
        permanent=False,
    )


def _selected_sql_sources(request):
    from app_document_campaigns.services.sql_sources import sql_source_options
    allowed = [name for name, _ in sql_source_options()]
    selected = request.POST.getlist("sources") if request.POST.get("select_sources") == "1" else allowed
    if not selected or set(selected) - set(allowed):
        raise CampaignImportError("Hãy chọn ít nhất một nguồn dữ liệu hợp lệ.")
    return list(dict.fromkeys(selected))


def _enqueue_import_job(job, task):
    try:
        result = task.delay(job.pk)
    except Exception:
        CampaignImportJob.objects.filter(pk=job.pk).update(
            status=CampaignImportJob.Status.FAILED,
            error_message="Không kết nối được Celery broker. Kiểm tra Redis/worker rồi chạy lại.",
            finished_at=timezone.now(),
        )
    else:
        CampaignImportJob.objects.filter(pk=job.pk).update(celery_task_id=result.id)


def _expire_stale_job(job):
    if not job or job.status not in (CampaignImportJob.Status.QUEUED, CampaignImportJob.Status.RUNNING):
        return job
    now = timezone.now()
    if job.status == CampaignImportJob.Status.QUEUED:
        timeout = timedelta(minutes=2)
    elif job.job_type == CampaignImportJob.JobType.EXCEL_EXPORT:
        timeout = timedelta(minutes=7)
    elif job.job_type == CampaignImportJob.JobType.EXCEL_IMPORT:
        timeout = timedelta(minutes=12)
    else:
        timeout = timedelta(minutes=16)
    reference = job.started_at or job.created_at
    if now - reference > timeout:
        job.status = CampaignImportJob.Status.FAILED
        job.finished_at = now
        job.error_message = (
            "Celery worker chưa nhận job trong thời gian cho phép."
            if not job.started_at
            else "Job vượt quá thời gian xử lý cho phép."
        )
        job.save(update_fields=["status", "finished_at", "error_message"])
    return job


@login_required
def latest_import_job(request, version_id):
    version = get_object_or_404(CampaignVersion, pk=version_id)
    job = _expire_stale_job(version.import_jobs.first())
    if job is None:
        return JsonResponse({"ok": True, "job": None})
    progress = 0
    if job.status == CampaignImportJob.Status.QUEUED:
        progress = 5
    elif job.status == CampaignImportJob.Status.RUNNING:
        progress = max(10, int(job.current_step / max(job.total_steps, 1) * 100))
    elif job.status == CampaignImportJob.Status.SUCCEEDED:
        progress = 100
    return JsonResponse(
        {
            "ok": True,
            "job": {
                "id": job.pk,
                "status": job.status,
                "status_label": job.get_status_display(),
                "progress": progress,
                "current_step": job.current_step,
                "total_steps": job.total_steps,
                "summary": job.summary,
                "error": job.error_message,
            },
        }
    )


def _is_html_form(request):
    return request.POST.get("return_to") == "campaign_detail"


def _version_detail_redirect(version):
    return redirect(
        f"/error-campaigns/campaigns/{version.campaign_id}/?version={version.pk}"
    )


@login_required
def export_staging_excel(request, version_id):
    version = get_object_or_404(
        CampaignVersion.objects.select_related("campaign"),
        pk=version_id,
    )
    job = (
        version.import_jobs.filter(
            job_type__in=[CampaignImportJob.JobType.SQL_STAGE, CampaignImportJob.JobType.EXCEL_EXPORT],
            status=CampaignImportJob.Status.SUCCEEDED,
            summary__export_kind__isnull=True,
        )
        .exclude(output_file="")
        .first()
    )
    if request.GET.get("kind") == "reviewed":
        source = version.import_sources.filter(source_type="excel", name="team-cleaning-excel").first()
        job = version.import_jobs.filter(
            job_type=CampaignImportJob.JobType.EXCEL_EXPORT,
            status=CampaignImportJob.Status.SUCCEEDED,
            summary__export_kind="reviewed",
            summary__source_checksum=source.source_checksum if source else "missing",
        ).exclude(output_file="").first()
    if request.GET.get("job"):
        try:
            job_id = int(request.GET["job"])
        except (TypeError, ValueError):
            return HttpResponse("File không hợp lệ.", status=400)
        job = version.import_jobs.filter(pk=job_id, status=CampaignImportJob.Status.SUCCEEDED, job_type__in=[CampaignImportJob.JobType.SQL_STAGE, CampaignImportJob.JobType.EXCEL_EXPORT]).exclude(output_file="").first()
        if job and job.summary.get("export_kind") == "reviewed":
            source = version.import_sources.filter(source_type="excel", name="team-cleaning-excel").first()
            if not source or source.source_checksum != job.summary.get("source_checksum"):
                return HttpResponse("File kết quả đã cũ; hãy chuẩn bị lại file từ dữ liệu hiện tại.", status=409)
    if job is None:
        return HttpResponse(
            "Chưa có file Excel được tạo thành công.",
            status=409,
            content_type="text/plain; charset=utf-8",
        )
    try:
        stream = job.output_file.open("rb")
    except FileNotFoundError:
        return HttpResponse("Không tìm thấy file. Kiểm tra media dùng chung giữa web và worker hoặc chuẩn bị lại file.", status=404)
    response = FileResponse(
        stream,
        as_attachment=True,
        filename=job.output_filename or job.output_file.name.rsplit("/", 1)[-1],
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    response["Cache-Control"] = "no-store"
    return response


@login_required
@require_POST
@campaign_admin_required
def queue_staging_excel_export(request, version_id):
    version = get_object_or_404(
        CampaignVersion.objects.select_related("campaign"),
        pk=version_id,
    )
    summary = {}
    if request.POST.get("export_kind") == "reviewed":
        source = version.import_sources.filter(source_type="excel", name="team-cleaning-excel").first()
        if not source or source.invalid_count or source.status not in ("validated", "confirmed"):
            messages.error(request, "Chưa có file team review hợp lệ để xuất.")
            return _version_detail_redirect(version)
        summary = {"export_kind": "reviewed", "source_checksum": source.source_checksum}
    try:
        with transaction.atomic():
            job = CampaignImportJob.objects.create(
                version=version,
                job_type=CampaignImportJob.JobType.EXCEL_EXPORT,
                total_steps=1,
                created_by=request.user,
                summary=summary,
            )
            transaction.on_commit(lambda: _enqueue_import_job(job, run_campaign_excel_export))
    except IntegrityError:
        messages.info(request, "Version này đang có một job tạo file Excel chưa hoàn tất.")
    else:
        job.refresh_from_db()
        if job.status == CampaignImportJob.Status.FAILED:
            messages.error(request, job.error_message)
        else:
            messages.success(
                request,
                "Đã đưa yêu cầu tạo file Excel vào hàng đợi. File tải sẽ xuất hiện khi job hoàn tất.",
            )
    return _version_detail_redirect(version)


@login_required
@require_POST
@campaign_admin_required
def import_staging_excel(request, version_id):
    version = get_object_or_404(
        CampaignVersion.objects.select_related("campaign"),
        pk=version_id,
    )
    uploaded_file = request.FILES.get("file")
    if version.status == CampaignVersion.Status.PUBLISHED or version.campaign.status in (Campaign.Status.ACTIVE, Campaign.Status.CLOSED, Campaign.Status.CANCELLED):
        return HttpResponse("Dữ liệu đã phát hành hoặc kỳ đã khóa; không thể upload lại.", status=409)
    if uploaded_file is None:
        if _is_html_form(request):
            messages.error(request, "Chưa chọn file Excel.")
            return _version_detail_redirect(version)
        return JsonResponse({"ok": False, "error": "Chưa chọn file Excel."}, status=400)
    filename = str(uploaded_file.name).replace("\\", "/").split("/")[-1]
    if not filename.lower().endswith(".xlsx"):
        error = "Chỉ chấp nhận file .xlsx không chứa macro."
        if _is_html_form(request):
            messages.error(request, error)
            return _version_detail_redirect(version)
        return JsonResponse({"ok": False, "error": error}, status=400)
    if uploaded_file.size <= 0 or uploaded_file.size > 10 * 1024 * 1024:
        error = "File Excel rỗng hoặc vượt quá giới hạn 10 MB."
        if _is_html_form(request):
            messages.error(request, error)
            return _version_detail_redirect(version)
        return JsonResponse({"ok": False, "error": error}, status=400)
    try:
        with transaction.atomic():
            job = CampaignImportJob.objects.create(
                version=version,
                job_type=CampaignImportJob.JobType.EXCEL_IMPORT,
                total_steps=3,
                input_file=uploaded_file,
                input_filename=filename,
                created_by=request.user,
            )
            transaction.on_commit(lambda: _enqueue_import_job(job, run_campaign_excel_import))
    except IntegrityError:
        error = "Version này đang có một job đối chiếu Excel chưa hoàn tất."
        if _is_html_form(request):
            messages.info(request, error)
            return _version_detail_redirect(version)
        return JsonResponse({"ok": False, "error": error}, status=409)
    if _is_html_form(request):
        job.refresh_from_db()
        if job.status == CampaignImportJob.Status.FAILED:
            messages.error(request, job.error_message)
        else:
            messages.success(
                request,
                "Đã tải file lên và đưa vào hàng đợi đối chiếu. Bạn có thể theo dõi tiến độ ngay trên trang.",
            )
        return _version_detail_redirect(version)
    return JsonResponse({"ok": True, "job_id": job.pk, "status": job.status}, status=202)


@login_required
@require_POST
@campaign_admin_required
def confirm_staging_excel(request, version_id):
    version = get_object_or_404(CampaignVersion.objects.select_related("campaign"), pk=version_id)
    try:
        summary = publish_excel_version(version=version, confirmed_by=request.user)
    except CampaignImportError as exc:
        if _is_html_form(request):
            messages.error(request, str(exc))
            return _version_detail_redirect(version)
        return JsonResponse({"ok": False, "error": str(exc)}, status=409)
    if _is_html_form(request):
        messages.success(
            request,
            f"Đã publish version: thêm {summary['applied_added']}, cập nhật {summary['applied_updated']}, loại {summary['applied_excluded']}.",
        )
        return _version_detail_redirect(version)
    return JsonResponse({"ok": True, "applied": summary})


def _resolve_link_or_response(raw_token):
    try:
        return resolve_shop_access_link(raw_token, touch=True), None
    except AccessLinkError as exc:
        return None, HttpResponse(str(exc), status=410)


@ensure_csrf_cookie
def shop_response_page(request, raw_token):
    link, error_response = _resolve_link_or_response(raw_token)
    if error_response:
        return error_response

    direction, ordering = _occurrence_order(request)
    errors = list(
        CampaignError.objects.filter(campaign=link.campaign, shop=link.shop)
        .exclude(status__in=[CampaignError.Status.EXCLUDED, CampaignError.Status.CANCELLED])
        .select_related("checklist_template", "campaign__campaign_type__shop_checklist_template")
        .prefetch_related(
            "checklist_template__questions",
            "campaign__campaign_type__shop_checklist_template__questions",
            "shop_response",
        )
        .order_by(ordering, "id")
    )
    rows = []
    completed = 0
    campaign_options = list(link.campaign.response_options.values("value", "label"))
    for error in errors:
        response = getattr(error, "shop_response", None)
        if response and response.answer_code:
            completed += 1
        options = list(campaign_options)
        checklist = error.checklist_template or error.campaign.campaign_type.shop_checklist_template
        if checklist and not campaign_options:
            for question in checklist.questions.all():
                if not question.is_active or question.question_type != question.QuestionType.SINGLE:
                    continue
                if question.error_type and question.error_type != error.error_type:
                    continue
                options = [
                    {
                        "value": str(option.get("value", "")).strip(),
                        "label": str(option.get("label", option.get("value", ""))).strip(),
                    }
                    if isinstance(option, dict)
                    else {"value": str(option), "label": str(option)}
                    for option in question.options
                ]
                break
        document_types = [
            item.strip()
            for item in (error.document_type_name or "").splitlines()
            if item.strip()
        ]
        rows.append(
            {
                "error": error,
                "response": response,
                "options": options,
                "document_types": document_types,
            }
        )

    submitted = ShopSubmission.objects.filter(campaign=link.campaign, shop=link.shop).exists()
    read_only = submitted or not link.is_editable or link.campaign.status != Campaign.Status.ACTIVE
    response = render(
        request,
        "app_document_campaigns/shop_response.html",
        {
            "link": link,
            "raw_token": raw_token,
            "rows": rows,
            "completed": completed,
            "total": len(rows),
            "submitted": submitted,
            "read_only": read_only,
            "date_order": direction,
        },
    )
    response["Cache-Control"] = "no-store"
    response["Referrer-Policy"] = "same-origin"
    return response


def _json_body(request):
    try:
        payload = json.loads(request.body or "{}")
    except (TypeError, ValueError) as exc:
        raise ResponseValidationError("Payload JSON không hợp lệ.") from exc
    if not isinstance(payload, dict):
        raise ResponseValidationError("Payload phải là object JSON.")
    return payload


@require_POST
def autosave_batch(request, raw_token):
    try:
        link = resolve_shop_access_link(raw_token)
        payload = _json_body(request)
        saved = save_response_batch(link=link, changes=payload.get("changes"))
    except AccessLinkError as exc:
        return JsonResponse({"ok": False, "error": str(exc)}, status=410)
    except ResponseConflictError as exc:
        return JsonResponse(
            {"ok": False, "error": str(exc), "conflicts": exc.conflicts},
            status=409,
        )
    except ResponseReadOnlyError as exc:
        return JsonResponse({"ok": False, "error": str(exc)}, status=423)
    except ResponseValidationError as exc:
        return JsonResponse(
            {"ok": False, "error": str(exc), "missing_uids": exc.missing_uids},
            status=400,
        )
    return JsonResponse({"ok": True, "saved": saved})


@require_POST
def submit_responses(request, raw_token):
    try:
        link = resolve_shop_access_link(raw_token)
        payload = _json_body(request)
        submission, idempotent = submit_shop_responses(
            link=link,
            idempotency_key=str(payload.get("idempotency_key", "")).strip(),
        )
    except AccessLinkError as exc:
        return JsonResponse({"ok": False, "error": str(exc)}, status=410)
    except ResponseReadOnlyError as exc:
        return JsonResponse({"ok": False, "error": str(exc)}, status=423)
    except ResponseValidationError as exc:
        return JsonResponse(
            {"ok": False, "error": str(exc), "missing_uids": exc.missing_uids},
            status=400,
        )
    return JsonResponse(
        {
            "ok": True,
            "idempotent": idempotent,
            "submitted_at": submission.submitted_at.isoformat(),
            "response_count": submission.response_count,
        }
    )
