from datetime import timedelta
from dataclasses import replace

from django import forms
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.core.paginator import Paginator
from django.db import IntegrityError, transaction
from django.db.models import Count, F, Q
from django.db.models import OuterRef, Subquery
from django.http import FileResponse, Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST
from django.views.decorators.csrf import ensure_csrf_cookie

from app_documents.models import AreaManager, Manager
from app_document_campaigns.forms import CampaignAreaEmailConfigForm, CampaignDeadlineForm
from app_document_campaigns.models import AreaConfirmation, AreaConfirmationExcelJob, AreaManagerAccessLink, Campaign, CampaignEmailBatch, CampaignError, CampaignVersion, ShopAccessLink, ShopSubmission, TeamReview
from app_document_campaigns.services.area_confirmation_excel import MAX_FILE_SIZE, STEP5_STATUSES, step5_errors
from app_document_campaigns.services.access_links import (
    AccessLinkError,
    issue_area_manager_access_link,
    resolve_area_manager_access_link,
)
from app_document_campaigns.services.monitoring_access import scope_campaign_errors
from app_document_campaigns.services.email_templates import (
    AREA_ALLOWED_VARIABLES,
    EmailTemplateError,
    area_template_context,
    campaign_area_email_config,
    render_area_email,
)
from app_document_campaigns.services.email_html import email_body_html


def _is_admin(user):
    return user.is_superuser or user.groups.filter(name="admin").exists()


def _area_email(area):
    candidates = [area.areaManager_email]
    candidates.extend(
        Manager.objects.filter(areaManager=area, is_valid=True)
        .exclude(qlkv_email__isnull=True)
        .exclude(qlkv_email="")
        .values_list("qlkv_email", flat=True)
        .distinct()[:3]
    )
    field = forms.EmailField()
    for candidate in candidates:
        try:
            return field.clean(candidate)
        except ValidationError:
            continue
    return ""


def _base_errors(campaign):
    return CampaignError.objects.filter(campaign=campaign).exclude(
        status__in=[CampaignError.Status.EXCLUDED, CampaignError.Status.CANCELLED]
    )


def _area_rows(queryset, campaign, *, confirmation_stage=False):
    grouped = list(
        queryset.exclude(shop__manager_id__areaManager_id__isnull=True)
        .values(
            "shop__manager_id__areaManager_id",
            "shop__manager_id__areaManager__areaManager_code",
            "shop__manager_id__areaManager__areaManager_name",
            "shop__manager_id__areaManager__areaManager_email",
            "shop__manager_id__regionManager__regionManager_name",
        )
        .annotate(
            shops=Count("shop_id", distinct=True),
            errors=Count("id"),
            answered=Count("id", filter=Q(shop_response__answer_code__isnull=False) & ~Q(shop_response__answer_code="")),
        )
        .order_by("shop__manager_id__areaManager__areaManager_name")
    )
    area_ids = [row["shop__manager_id__areaManager_id"] for row in grouped]
    link_stage = (
        AreaManagerAccessLink.Stage.CONFIRMATION
        if confirmation_stage
        else AreaManagerAccessLink.Stage.MONITORING
    )
    links = {
        item.area_manager_id: item
        for item in AreaManagerAccessLink.objects.filter(
            campaign=campaign,
            area_manager_id__in=area_ids,
            stage=link_stage,
        )
    }
    submitted = {
        row["shop__manager_id__areaManager_id"]: row["total"]
        for row in ShopSubmission.objects.filter(campaign=campaign, shop__manager_id__areaManager_id__in=area_ids)
        .values("shop__manager_id__areaManager_id")
        .annotate(total=Count("shop_id", distinct=True))
    }
    confirmation_counts = {}
    if confirmation_stage:
        latest_confirmation = AreaConfirmation.objects.filter(error_id=OuterRef("pk")).order_by("-created_at", "-pk")
        confirmation_counts = {
            row["shop__manager_id__areaManager_id"]: row
            for row in queryset.annotate(
                latest_area_decision=Subquery(latest_confirmation.values("is_agreed")[:1])
            ).values("shop__manager_id__areaManager_id").annotate(
                confirmation_total=Count("id"),
                confirmation_done=Count("id", filter=Q(latest_area_decision__isnull=False)),
            )
        }
    for row in grouped:
        area_id = row["shop__manager_id__areaManager_id"]
        confirmation = confirmation_counts.get(area_id, {})
        progress_done = confirmation.get("confirmation_done", 0) if confirmation_stage else row["answered"]
        progress_total = confirmation.get("confirmation_total", row["errors"]) if confirmation_stage else row["errors"]
        row.update(
            area_id=area_id,
            area_code=row["shop__manager_id__areaManager__areaManager_code"],
            area_name=row["shop__manager_id__areaManager__areaManager_name"],
            area_email=row["shop__manager_id__areaManager__areaManager_email"] or "",
            region_name=row["shop__manager_id__regionManager__regionManager_name"] or "—",
            submitted_shops=submitted.get(area_id, 0),
            progress=int(progress_done * 100 / max(progress_total, 1)),
            progress_done=progress_done,
            progress_total=progress_total,
            link=links.get(area_id),
        )
    return grouped


@login_required
def campaign_area_monitor(request, campaign_id):
    campaign = get_object_or_404(Campaign.objects.select_related("current_version"), pk=campaign_id)
    errors, scope = scope_campaign_errors(_base_errors(campaign), request.user)
    confirmation_stage = request.GET.get("stage") == "confirmation" and errors.filter(
        status__in=STEP5_STATUSES
    ).exists()
    if confirmation_stage:
        errors = errors.filter(status__in=STEP5_STATUSES)
    grouped = list(errors.values(
        "shop_id", "shop__shop_code", "shop__shop_name",
        "shop__manager_id__regionManager_id", "shop__manager_id__regionManager__regionManager_name",
        "shop__manager_id__areaManager_id", "shop__manager_id__areaManager__areaManager_name",
    ).annotate(
        total_errors=Count("id"),
        answered_errors=Count("id", filter=Q(shop_response__answer_code__isnull=False) & ~Q(shop_response__answer_code="")),
    ))
    shop_ids = [row["shop_id"] for row in grouped]
    submitted = set(ShopSubmission.objects.filter(campaign=campaign, shop_id__in=shop_ids).values_list("shop_id", flat=True))
    links = {link.shop_id: link for link in ShopAccessLink.objects.filter(campaign=campaign, shop_id__in=shop_ids)}
    from app_document_campaigns.services.response_deadlines import shop_deadline_passed, shop_deadlines
    deadlines = shop_deadlines(campaign)
    regions = sorted({(row["shop__manager_id__regionManager_id"], row["shop__manager_id__regionManager__regionManager_name"] or "Chưa xác định") for row in grouped if row["shop__manager_id__regionManager_id"]}, key=lambda item: item[1])
    areas = sorted({(row["shop__manager_id__areaManager_id"], row["shop__manager_id__areaManager__areaManager_name"] or "Chưa xác định", row["shop__manager_id__regionManager_id"]) for row in grouped if row["shop__manager_id__areaManager_id"]}, key=lambda item: item[1])
    shops = sorted([(row["shop_id"], row["shop__shop_code"], row["shop__shop_name"], row["shop__manager_id__regionManager_id"], row["shop__manager_id__areaManager_id"]) for row in grouped], key=lambda item: item[1] or 0)
    region, area, shop = (request.GET.get(name, "").strip() for name in ("region", "area", "shop"))
    if region not in {str(item[0]) for item in regions}: region = ""
    if area not in {str(item[0]) for item in areas if not region or str(item[2]) == region}: area = ""
    if shop not in {str(item[0]) for item in shops if (not region or str(item[3]) == region) and (not area or str(item[4]) == area)}: shop = ""
    statuses = [value for value in request.GET.getlist("status") if value in {"not_started", "in_progress", "submitted", "expired"}]
    selected_shop_ids = []
    for row in grouped:
        expired = shop_deadline_passed(campaign, row["shop_id"], deadlines)
        status = "submitted" if row["shop_id"] in submitted else "expired" if expired else "in_progress" if row["answered_errors"] else "not_started"
        if ((not region or str(row["shop__manager_id__regionManager_id"]) == region)
            and (not area or str(row["shop__manager_id__areaManager_id"]) == area)
            and (not shop or str(row["shop_id"]) == shop)
            and (not statuses or status in statuses)):
            selected_shop_ids.append(row["shop_id"])
    all_area_rows = _area_rows(errors, campaign, confirmation_stage=confirmation_stage)
    rows = _area_rows(errors.filter(shop_id__in=selected_shop_ids), campaign, confirmation_stage=confirmation_stage)
    page = Paginator(rows, 50).get_page(request.GET.get("page"))
    submitted_count = len(submitted)
    from app_document_campaigns.services.email_metrics import emailed_area_manager_count
    summary = {
        "shops": len(grouped),
        "issued": sum(bool(links.get(row["shop_id"]) and not links[row["shop_id"]].revoked_at) for row in grouped),
        "submitted": submitted_count,
        "submitted_rate": round(submitted_count * 100 / len(grouped)) if grouped else 0,
        "in_progress": sum(row["shop_id"] not in submitted and bool(row["answered_errors"]) for row in grouped),
        "not_started": sum(row["shop_id"] not in submitted and not row["answered_errors"] for row in grouped),
        "errors": errors.count(),
        "contracts": errors.exclude(contract_code="").values("contract_code").distinct().count(),
        "area_emailed": emailed_area_manager_count(campaign, shop_ids),
        "areas": len(all_area_rows),
        "area_links_issued": sum(bool(row["link"] and not row["link"].revoked_at and not row["link"].is_expired) for row in all_area_rows),
        "area_emails_sent": sum(bool(row["link"] and row["link"].email_status == AreaManagerAccessLink.EmailStatus.SENT) for row in all_area_rows),
        "area_confirmation_done": sum(row["progress_done"] for row in all_area_rows) if confirmation_stage else 0,
        "area_confirmation_total": sum(row["progress_total"] for row in all_area_rows) if confirmation_stage else 0,
    }
    params = request.GET.copy(); params.pop("page", None)
    area_email_config = campaign_area_email_config(campaign) if _is_admin(request.user) else None
    area_excel_jobs = {
        kind: campaign.area_confirmation_excel_jobs.filter(kind=kind).order_by("-pk").values_list("pk", flat=True).first()
        for kind in ("export", "import")
    } if confirmation_stage and _is_admin(request.user) else {}
    if confirmation_stage:
        latest_area = AreaConfirmation.objects.filter(error_id=OuterRef("pk")).order_by("-created_at", "-pk")
        step5_stats = step5_errors(campaign).annotate(
            latest_area_decision=Subquery(latest_area.values("is_agreed")[:1])
        ).aggregate(
            total=Count("pk"),
            decided=Count("pk", filter=Q(latest_area_decision__isnull=False)),
            confirmed=Count("pk", filter=Q(latest_area_decision=True)),
            removed=Count("pk", filter=Q(latest_area_decision=False)),
        )
    else:
        step5_stats = {}
    return render(request, "app_document_campaigns/campaign_area_monitor.html", {
        "campaign": campaign,
        "rows": page.object_list,
        "page": page,
        "access_scope": scope,
        "can_manage_area_links": _is_admin(request.user),
        "can_manage_shop_links": _is_admin(request.user),
        "issued_shop_link_count": summary["issued"],
        "can_publish_shop_links": bool(campaign.current_version
            and campaign.current_version.status == CampaignVersion.Status.PUBLISHED
            and campaign.status not in (Campaign.Status.CLOSED, Campaign.Status.CANCELLED)
            and campaign.response_deadline and campaign.response_deadline > timezone.now()),
        "deadline_form": CampaignDeadlineForm(instance=campaign),
        "summary": summary,
        "regions": regions, "areas": areas, "shops": shops,
        "selected_region": region, "selected_area": area, "selected_shop": shop,
        "selected_statuses": statuses, "filter_query": params.urlencode(),
        "active_monitor_tab": "areas",
        "confirmation_stage": confirmation_stage,
        "workflow_current": 5 if confirmation_stage else 3,
        "area_email_config_form": CampaignAreaEmailConfigForm(instance=area_email_config) if area_email_config else None,
        "area_email_variables": AREA_ALLOWED_VARIABLES,
        "email_from_address": settings.DEFAULT_FROM_EMAIL or settings.EMAIL_HOST_USER or "Chưa cấu hình",
        "area_excel_jobs": area_excel_jobs,
        "step5_stats": step5_stats,
    })


def _area_detail_context(campaign, area, queryset, request, *, confirmation_mode=False):
    base = queryset.filter(shop__manager_id__areaManager=area)
    if confirmation_mode:
        base = base.filter(status__in=STEP5_STATUSES)
    shop_options = list(base.order_by("shop__shop_code").values("shop_id", "shop__shop_code", "shop__shop_name").distinct())
    shop_ids = {row["shop_id"] for row in shop_options}
    total = base.count()
    answered = base.filter(shop_response__answer_code__isnull=False).exclude(shop_response__answer_code="").count()
    contracts = base.exclude(contract_code="").values("contract_code").distinct().count()
    latest_review = TeamReview.objects.filter(error_id=OuterRef("pk")).order_by("-created_at", "-pk")
    latest_confirmation = AreaConfirmation.objects.filter(error_id=OuterRef("pk")).order_by("-created_at", "-pk")
    queryset = base.annotate(
        team_decision=Subquery(latest_review.values("decision")[:1]),
        team_note=Subquery(latest_review.values("note")[:1]),
        area_confirmation_id=Subquery(latest_confirmation.values("pk")[:1]),
        area_decision=Subquery(latest_confirmation.values("is_agreed")[:1]),
        area_note=Subquery(latest_confirmation.values("note")[:1]),
        area_confirmed_at=Subquery(latest_confirmation.values("created_at")[:1]),
    )
    confirmation_metrics = queryset.aggregate(
        agreed=Count("pk", filter=Q(area_decision=True)),
        disagreed=Count("pk", filter=Q(area_decision=False)),
    ) if confirmation_mode else {"agreed": 0, "disagreed": 0}
    query = request.GET.get("q", "").strip()[:200]
    selected_shop = request.GET.get("shop", "").strip()
    selected_error_type = request.GET.get("error_type", "").strip()
    selected_response = request.GET.get("response", "").strip()
    if query:
        queryset = queryset.filter(
            Q(shop__shop_name__icontains=query) | Q(shop__shop_code__icontains=query)
            | Q(contract_code__icontains=query) | Q(employee_name__icontains=query)
            | Q(business_type_name__icontains=query) | Q(checking_issue__icontains=query)
            | Q(document_type_name__icontains=query) | Q(shop_response__answer_code__icontains=query)
            | Q(shop_response__note__icontains=query)
        )
    valid_shop_ids = {str(row["shop_id"]) for row in shop_options}
    if selected_shop in valid_shop_ids:
        queryset = queryset.filter(shop_id=int(selected_shop))
    else:
        selected_shop = ""
    valid_error_types = {value for value, _ in CampaignError.ErrorType.choices}
    if selected_error_type in valid_error_types:
        queryset = queryset.filter(error_type=selected_error_type)
    else:
        selected_error_type = ""
    response_values = set(campaign.response_options.values_list("value", flat=True))
    if selected_response == "unanswered":
        queryset = queryset.filter(Q(shop_response__answer_code__isnull=True) | Q(shop_response__answer_code=""))
    elif selected_response in response_values:
        queryset = queryset.filter(shop_response__answer_code=selected_response)
    else:
        selected_response = ""
    sort_key = request.GET.get("sort", "shop")
    direction = request.GET.get("direction", "asc")
    sort_fields = {
        "shop": ["shop__shop_name", "shop__shop_code"],
        "contract": ["contract_code"],
        "date": ["source_created_at"],
        "error_type": ["error_type"],
        "employee": ["employee_name", "business_type_name"],
        "issue": ["checking_issue"],
        "response": ["shop_response__answer_code"],
        "note": ["shop_response__note"],
    }
    if sort_key not in sort_fields: sort_key = "shop"
    if direction not in {"asc", "desc"}: direction = "asc"
    ordering = [F(field).desc(nulls_last=True) if direction == "desc" else F(field).asc(nulls_last=True) for field in sort_fields[sort_key]]
    page = Paginator(queryset.select_related("shop", "shop_response").order_by(*ordering, "id"), 100).get_page(request.GET.get("page"))
    errors = list(page.object_list)
    labels = dict(campaign.response_options.values_list("value", "label"))
    for error in errors:
        response = getattr(error, "shop_response", None)
        error.response_label = labels.get(response.answer_code, response.answer_code) if response else ""
    submitted_shops = ShopSubmission.objects.filter(campaign=campaign, shop_id__in=shop_ids).count()
    page_params = request.GET.copy(); page_params.pop("page", None)
    return {
        "campaign": campaign,
        "area_manager": area,
        "errors": errors,
        "shops": len(shop_ids),
        "submitted_shops": submitted_shops,
        "submitted_rate": round(submitted_shops * 100 / len(shop_ids)) if shop_ids else 0,
        "contracts": contracts,
        "answered": answered,
        "total": total,
        "has_data": bool(total),
        "page": page,
        "page_query": page_params.urlencode(),
        "shop_options": shop_options,
        "response_options": list(campaign.response_options.values_list("value", "label")),
        "error_type_options": CampaignError.ErrorType.choices,
        "query": query, "selected_shop": selected_shop, "selected_error_type": selected_error_type,
        "selected_response": selected_response,
        "sort_key": sort_key, "sort_direction": direction,
        "area_link": AreaManagerAccessLink.objects.filter(
            campaign=campaign,
            area_manager=area,
            stage=(
                AreaManagerAccessLink.Stage.CONFIRMATION
                if confirmation_mode
                else AreaManagerAccessLink.Stage.MONITORING
            ),
        ).first(),
        "confirmation_mode": confirmation_mode,
        "confirmation_done": sum(error.area_decision is not None for error in errors),
        "agreed_count": confirmation_metrics["agreed"],
        "disagreed_count": confirmation_metrics["disagreed"],
    }


@login_required
def area_manager_detail(request, campaign_id, area_id):
    campaign = get_object_or_404(Campaign, pk=campaign_id)
    scoped, _ = scope_campaign_errors(_base_errors(campaign), request.user)
    area = get_object_or_404(AreaManager, pk=area_id)
    confirmation_mode = request.GET.get("stage") == "confirmation"
    context = _area_detail_context(campaign, area, scoped, request, confirmation_mode=confirmation_mode)
    if not context["has_data"]:
        raise Http404("Không có dữ liệu QLKV trong phạm vi được phép.")
    context["public_view"] = False
    return render(request, "app_document_campaigns/area_manager_readonly.html", context)


@ensure_csrf_cookie
def public_area_manager_view(request, raw_token):
    try:
        link = resolve_area_manager_access_link(raw_token, touch=True)
    except AccessLinkError as exc:
        response = render(
            request,
            "app_document_campaigns/area_link_unavailable.html",
            {"reason": str(exc)},
            status=410,
        )
        response["Cache-Control"] = "no-store"
        return response
    confirmation_mode = link.stage == AreaManagerAccessLink.Stage.CONFIRMATION
    context = _area_detail_context(link.campaign, link.area_manager, _base_errors(link.campaign), request, confirmation_mode=confirmation_mode)
    context.update(public_view=True, link=link, raw_token=raw_token)
    response = render(request, "app_document_campaigns/area_manager_readonly.html", context)
    response["Cache-Control"] = "no-store"
    return response


@require_POST
def confirm_area_error(request, raw_token, error_id):
    import json

    try:
        link = resolve_area_manager_access_link(raw_token, touch=True)
    except AccessLinkError as exc:
        return JsonResponse({"ok": False, "error": str(exc)}, status=410)
    if link.stage != AreaManagerAccessLink.Stage.CONFIRMATION:
        return JsonResponse({"ok": False, "error": "Link Step 3 chỉ được xem, không thể xác nhận."}, status=403)
    if not link.campaign.area_response_deadline:
        return JsonResponse({"ok": False, "error": "Chiến dịch chưa cấu hình hạn QLKV xác nhận."}, status=409)
    if timezone.now() >= link.campaign.area_response_deadline:
        return JsonResponse({"ok": False, "error": "Đã hết hạn QLKV xác nhận."}, status=410)
    try:
        payload = json.loads(request.body)
        note = payload.get("note", "")
        expected_id = payload.get("expected_confirmation_id")
        decision = payload.get("decision")
        if decision in {"true", "confirmed"}:
            decision = True
        elif decision in {"false", "returned"}:
            decision = False
        if type(decision) is not bool:
            raise ValueError("QLKV cần chọn Đồng thuận hoặc Không đồng thuận.")
        if not isinstance(note, str) or len(note) > 2000:
            raise ValueError("Ghi chú tối đa 2.000 ký tự.")
        if expected_id is not None and type(expected_id) is not int:
            raise ValueError("Phiên xác nhận không hợp lệ; hãy tải lại trang.")
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        return JsonResponse({"ok": False, "error": str(exc)}, status=400)
    with transaction.atomic():
        error = get_object_or_404(
            CampaignError.objects.select_for_update(),
            pk=error_id,
            campaign=link.campaign,
            shop__manager_id__areaManager=link.area_manager,
        )
        if error.status not in {
            CampaignError.Status.WAITING_AREA,
            CampaignError.Status.AREA_CONFIRMED,
            CampaignError.Status.AREA_RETURNED,
        }:
            return JsonResponse({"ok": False, "error": "Dòng lỗi chưa được Team phát hành cho QLKV."}, status=409)
        latest_review = error.team_reviews.order_by("-created_at", "-pk").first()
        if not latest_review or latest_review.decision != TeamReview.Decision.APPROVED:
            return JsonResponse({"ok": False, "error": "Dòng lỗi không có kết luận giữ lỗi của Team review."}, status=409)
        latest = error.area_confirmations.order_by("-created_at", "-pk").first()
        if (latest.pk if latest else None) != expected_id:
            return JsonResponse({"ok": False, "error": "Dòng đã được cập nhật ở phiên khác. Hãy tải lại trang."}, status=409)
        clean_note = note.strip()
        if latest and latest.is_agreed is decision and latest.note == clean_note:
            confirmation = latest
        else:
            confirmation = AreaConfirmation.objects.create(
                error=error,
                area_manager=link.area_manager,
                access_link=link,
                is_agreed=decision,
                note=clean_note,
                confirmed_by=None,
            )
        new_status = CampaignError.Status.AREA_CONFIRMED if decision else CampaignError.Status.AREA_RETURNED
        CampaignError.objects.filter(pk=error.pk).update(status=new_status, updated_at=timezone.now())
        latest_confirmation = AreaConfirmation.objects.filter(error_id=OuterRef("pk")).order_by("-created_at", "-pk")
        scoped = _base_errors(link.campaign).filter(
            shop__manager_id__areaManager=link.area_manager,
            status__in=STEP5_STATUSES,
        ).annotate(latest_decision=Subquery(latest_confirmation.values("is_agreed")[:1]))
        total = scoped.count()
        completed = scoped.filter(latest_decision__isnull=False).count()
    return JsonResponse({"ok": True, "confirmation_id": confirmation.pk, "completed": completed, "total": total, "progress": round(completed * 100 / total) if total else 0})


@require_POST
def confirm_all_area_errors(request, raw_token):
    import json

    try:
        link = resolve_area_manager_access_link(raw_token, touch=True)
    except AccessLinkError as exc:
        return JsonResponse({"ok": False, "error": str(exc)}, status=410)
    if link.stage != AreaManagerAccessLink.Stage.CONFIRMATION:
        return JsonResponse({"ok": False, "error": "Link Step 3 chỉ được xem, không thể xác nhận."}, status=403)
    campaign = link.campaign
    if not campaign.area_response_deadline:
        return JsonResponse({"ok": False, "error": "Chiến dịch chưa cấu hình hạn QLKV xác nhận."}, status=409)
    if timezone.now() >= campaign.area_response_deadline:
        return JsonResponse({"ok": False, "error": "Đã hết hạn QLKV xác nhận."}, status=410)
    try:
        payload = json.loads(request.body or "{}")
        if not isinstance(payload, dict):
            raise ValueError("Bộ lọc không hợp lệ.")
        query = str(payload.get("q", "")).strip()[:200]
        shop = str(payload.get("shop", "")).strip()
        error_type = str(payload.get("error_type", "")).strip()
        response_value = str(payload.get("response", "")).strip()
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        return JsonResponse({"ok": False, "error": str(exc)}, status=400)

    latest_review = TeamReview.objects.filter(error_id=OuterRef("pk")).order_by("-created_at", "-pk")
    latest_confirmation = AreaConfirmation.objects.filter(error_id=OuterRef("pk")).order_by("-created_at", "-pk")
    queryset = (
        CampaignError.objects.filter(
            campaign=campaign,
            shop__manager_id__areaManager=link.area_manager,
            status__in=STEP5_STATUSES,
        )
        .annotate(
            latest_team_decision=Subquery(latest_review.values("decision")[:1]),
            latest_area_decision=Subquery(latest_confirmation.values("is_agreed")[:1]),
            latest_area_note=Subquery(latest_confirmation.values("note")[:1]),
        )
        .filter(latest_team_decision=TeamReview.Decision.APPROVED)
    )
    if query:
        queryset = queryset.filter(
            Q(shop__shop_name__icontains=query) | Q(shop__shop_code__icontains=query)
            | Q(contract_code__icontains=query) | Q(employee_name__icontains=query)
            | Q(business_type_name__icontains=query) | Q(checking_issue__icontains=query)
            | Q(document_type_name__icontains=query) | Q(shop_response__answer_code__icontains=query)
            | Q(shop_response__note__icontains=query)
        )
    if shop:
        if not shop.isdigit():
            return JsonResponse({"ok": False, "error": "Phòng giao dịch trong bộ lọc không hợp lệ."}, status=400)
        queryset = queryset.filter(shop_id=int(shop))
    if error_type:
        if error_type not in {value for value, _ in CampaignError.ErrorType.choices}:
            return JsonResponse({"ok": False, "error": "Loại lỗi trong bộ lọc không hợp lệ."}, status=400)
        queryset = queryset.filter(error_type=error_type)
    response_values = set(campaign.response_options.values_list("value", flat=True))
    if response_value == "unanswered":
        queryset = queryset.filter(Q(shop_response__answer_code__isnull=True) | Q(shop_response__answer_code=""))
    elif response_value:
        if response_value not in response_values:
            return JsonResponse({"ok": False, "error": "Phản hồi PGD trong bộ lọc không hợp lệ."}, status=400)
        queryset = queryset.filter(shop_response__answer_code=response_value)

    candidates = list(
        queryset.filter(
            Q(latest_area_decision__isnull=True)
            | Q(latest_area_decision=False)
        ).values_list("pk", flat=True)
    )
    with transaction.atomic():
        locked_ids = set(
            CampaignError.objects.select_for_update()
            .filter(
                pk__in=candidates,
                campaign=campaign,
                shop__manager_id__areaManager=link.area_manager,
                status__in=STEP5_STATUSES,
            )
            .values_list("pk", flat=True)
        )
        current = {}
        for item in AreaConfirmation.objects.filter(error_id__in=locked_ids).order_by("error_id", "-created_at", "-pk"):
            current.setdefault(item.error_id, item)
        update_ids = [
            error_id for error_id in locked_ids
            if not current.get(error_id) or current[error_id].is_agreed is not True
        ]
        confirmations = [
            AreaConfirmation(
                error_id=error_id,
                area_manager=link.area_manager,
                access_link=link,
                is_agreed=True,
                note=current[error_id].note if error_id in current else "",
                confirmed_by=None,
            )
            for error_id in update_ids
        ]
        AreaConfirmation.objects.bulk_create(confirmations, batch_size=500)
        if update_ids:
            CampaignError.objects.filter(pk__in=update_ids).update(
                status=CampaignError.Status.AREA_CONFIRMED,
                updated_at=timezone.now(),
            )

    scoped = CampaignError.objects.filter(
        campaign=campaign,
        shop__manager_id__areaManager=link.area_manager,
        status__in=STEP5_STATUSES,
    ).annotate(latest_decision=Subquery(latest_confirmation.values("is_agreed")[:1]))
    total = scoped.count()
    completed = scoped.filter(latest_decision__isnull=False).count()
    return JsonResponse({
        "ok": True,
        "updated": len(confirmations),
        "completed": completed,
        "total": total,
        "progress": round(completed * 100 / total) if total else 0,
    })


def _sample_area(campaign):
    area_id = (
        _base_errors(campaign)
        .exclude(shop__manager_id__areaManager_id__isnull=True)
        .values_list("shop__manager_id__areaManager_id", flat=True)
        .first()
    )
    return AreaManager.objects.filter(pk=area_id).first()


@login_required
@require_POST
def save_area_email_config(request, campaign_id):
    if not _is_admin(request.user):
        return JsonResponse({"ok": False, "error": "Chỉ Admin được cấu hình email QLKV."}, status=403)
    campaign = get_object_or_404(Campaign, pk=campaign_id)
    config = campaign_area_email_config(campaign)
    form = CampaignAreaEmailConfigForm(request.POST, instance=config)
    if not form.is_valid():
        return JsonResponse({"ok": False, "errors": {key: [str(item) for item in values] for key, values in form.errors.items()}}, status=400)
    config = form.save(updated_by=request.user)
    return JsonResponse({"ok": True, "message": "Đã lưu cấu hình email QLKV.", "template_version": config.template_version})


@login_required
@require_GET
def area_email_preview(request, campaign_id):
    if not _is_admin(request.user):
        return JsonResponse({"ok": False, "error": "Không có quyền."}, status=403)
    campaign = get_object_or_404(Campaign, pk=campaign_id)
    area = _sample_area(campaign)
    if not area:
        return JsonResponse({"ok": False, "error": "Chiến dịch chưa có QLKV để preview."}, status=409)
    confirmation_mode = request.GET.get("stage") == "confirmation"
    config = campaign_area_email_config(campaign)
    preview_expires_at = campaign.area_response_deadline if confirmation_mode else campaign.link_expires_at
    try:
        rendered = render_area_email(
            config, campaign, area,
            "https://example.invalid/manager-view/preview-only/",
            confirmation_mode=confirmation_mode,
            expires_at=preview_expires_at,
        )
    except EmailTemplateError as exc:
        return JsonResponse({"ok": False, "error": str(exc)}, status=400)
    return JsonResponse({
        "ok": True, "area": f"{area.areaManager_code} · {area.areaManager_name}",
        "subject": rendered.subject, "body": rendered.body, "to": rendered.to,
        "cc": rendered.cc, "bcc": rendered.bcc, "from_email": rendered.from_email,
        "context": {
            **area_template_context(
                campaign, area, "https://example.invalid/manager-view/preview-only/",
                expires_at=preview_expires_at,
            ),
            "support_email": config.support_email or "",
        },
    })


@login_required
@require_POST
def send_area_test_email(request, campaign_id):
    if not _is_admin(request.user):
        return JsonResponse({"ok": False, "error": "Không có quyền."}, status=403)
    campaign = get_object_or_404(Campaign, pk=campaign_id)
    area = _sample_area(campaign)
    if not area:
        return JsonResponse({"ok": False, "error": "Chiến dịch chưa có QLKV để gửi thử."}, status=409)
    test_email = (request.POST.get("test_email") or "").strip()
    transport = (request.POST.get("transport") or "").strip()
    confirmation_mode = request.POST.get("stage") == AreaManagerAccessLink.Stage.CONFIRMATION
    try:
        validate_email(test_email)
        from app_document_campaigns.bulk_email_views import _validate_transport
        from app_document_campaigns.services.test_email_delivery import queue_test_email
        _validate_transport(transport)
        config = campaign_area_email_config(campaign)
        rendered = render_area_email(
            config, campaign, area,
            "https://example.invalid/manager-view/email-test-no-live-token/",
            confirmation_mode=confirmation_mode, recipient_override=test_email,
        )
        rendered = replace(
            rendered,
            subject=f"[TEST] {rendered.subject}",
            body=("<p><strong>ĐÂY LÀ EMAIL KIỂM THỬ</strong> — link bên dưới không có hiệu lực.</p>"
                  + email_body_html(rendered.body)),
            cc=[],
            bcc=[],
        )
        batch = queue_test_email(
            campaign=campaign,
            email_type=(
                CampaignEmailBatch.EmailType.AREA_CONFIRMATION
                if confirmation_mode else CampaignEmailBatch.EmailType.AREA_MONITORING
            ),
            transport=transport,
            target=area,
            rendered=rendered,
            template_version=config.template_version,
            requested_by=request.user,
        )
    except ValidationError:
        return JsonResponse({"ok": False, "error": "Email nhận thử không hợp lệ."}, status=400)
    except Exception:
        import logging
        logging.getLogger(__name__).exception("AREA_CAMPAIGN_TEST_EMAIL_FAILED campaign_id=%s user_id=%s", campaign.pk, request.user.pk)
        return JsonResponse({"ok": False, "error": "Không thể đưa email thử vào hàng đợi. Kiểm tra kênh gửi và log web."}, status=502)
    return JsonResponse({
        "ok": True,
        "message": f"Đã đưa email QLKV thử tới {test_email} vào hàng đợi.",
        "batch_id": str(batch.pk),
        "transport": batch.transport_provider,
    }, status=202)


@login_required
@require_POST
def issue_area_manager_link(request, campaign_id, area_id):
    if not _is_admin(request.user):
        return JsonResponse({"ok": False, "error": "Chỉ Admin được tạo link QLKV."}, status=403)
    campaign = get_object_or_404(Campaign, pk=campaign_id)
    area = get_object_or_404(AreaManager, pk=area_id)
    if not _base_errors(campaign).filter(shop__manager_id__areaManager=area).exists():
        return JsonResponse({"ok": False, "error": "QLKV không có PGD trong kỳ."}, status=404)
    email = _area_email(area)
    if not email:
        return JsonResponse({"ok": False, "error": "Email QLKV chưa hợp lệ; hãy cập nhật Master Data."}, status=400)
    confirmation_mode = request.POST.get("stage") == AreaManagerAccessLink.Stage.CONFIRMATION
    link_stage = (
        AreaManagerAccessLink.Stage.CONFIRMATION
        if confirmation_mode
        else AreaManagerAccessLink.Stage.MONITORING
    )
    expires_at = campaign.area_response_deadline if confirmation_mode else campaign.link_expires_at
    if confirmation_mode and not campaign.area_response_deadline:
        return JsonResponse({"ok": False, "error": "Hãy cấu hình hạn cuối QLKV xác nhận trước khi tạo link Step 5."}, status=409)
    if not expires_at or expires_at <= timezone.now():
        return JsonResponse({"ok": False, "error": "Hạn link chung đã hết; hãy điều chỉnh deadline trước."}, status=409)
    link, token = issue_area_manager_access_link(
        campaign=campaign,
        area_manager=area,
        allowed_email=email,
        created_by=request.user,
        stage=link_stage,
        expires_at=expires_at,
    )
    url = request.build_absolute_uri(reverse("document_campaigns:public_area_manager_view", kwargs={"raw_token": token}))
    return JsonResponse({"ok": True, "url": url, "stage": link.stage, "expires_at": link.expires_at.strftime("H:%M %d/%m/%Y")})


@login_required
@require_POST
def email_area_manager_link(request, campaign_id, area_id):
    if not _is_admin(request.user):
        return JsonResponse({"ok": False, "error": "Chỉ Admin được gửi email QLKV."}, status=403)
    from app_document_campaigns.tasks import send_area_manager_view_link
    issue = issue_area_manager_link(request, campaign_id, area_id)
    if issue.status_code != 200:
        return issue
    payload = __import__("json").loads(issue.content)
    link = AreaManagerAccessLink.objects.get(
        campaign_id=campaign_id,
        area_manager_id=area_id,
        stage=payload["stage"],
    )
    AreaManagerAccessLink.objects.filter(pk=link.pk).update(email_status=AreaManagerAccessLink.EmailStatus.QUEUED, email_message="Đang chờ gửi email.")
    try:
        send_area_manager_view_link.delay(link.pk, payload["url"])
    except Exception:
        AreaManagerAccessLink.objects.filter(pk=link.pk).update(email_status=AreaManagerAccessLink.EmailStatus.FAILED, email_message="Không kết nối được worker/broker.")
        return JsonResponse({"ok": False, "error": "Đã tạo link nhưng chưa đưa được email vào hàng đợi.", "url": payload["url"]}, status=503)
    return JsonResponse({"ok": True, "url": payload["url"], "message": "Đã đưa email QLKV vào hàng đợi."})


@login_required
@require_POST
def extend_area_manager_link(request, campaign_id, area_id):
    if not _is_admin(request.user):
        return JsonResponse({"ok": False, "error": "Chỉ Admin được gia hạn link QLKV."}, status=403)
    stage = request.POST.get("stage") or AreaManagerAccessLink.Stage.MONITORING
    if stage not in AreaManagerAccessLink.Stage.values:
        return JsonResponse({"ok": False, "error": "Giai đoạn link QLKV không hợp lệ."}, status=400)
    link = get_object_or_404(
        AreaManagerAccessLink,
        campaign_id=campaign_id,
        area_manager_id=area_id,
        stage=stage,
    )
    try:
        expires_at = forms.DateTimeField().clean(request.POST.get("expires_at"))
    except ValidationError:
        return JsonResponse({"ok": False, "error": "Ngày hết hạn không hợp lệ."}, status=400)
    if expires_at <= timezone.now():
        return JsonResponse({"ok": False, "error": "Ngày hết hạn mới phải ở tương lai."}, status=400)
    link.expires_at = expires_at
    link.save(update_fields=["expires_at"])
    return JsonResponse({"ok": True, "expires_at": expires_at.strftime("H:%M %d/%m/%Y")})


@login_required
@require_POST
def queue_area_confirmation_excel(request, campaign_id):
    if not _is_admin(request.user):
        return JsonResponse({"error": "Chỉ Admin được xử lý Excel Step 5."}, status=403)
    campaign = get_object_or_404(Campaign, pk=campaign_id)
    kind = request.POST.get("kind")
    upload = request.FILES.get("file")
    if kind not in {"export", "import"}:
        return JsonResponse({"error": "Loại thao tác không hợp lệ."}, status=400)
    if kind == "import" and (not upload or not upload.name.lower().endswith(".xlsx") or upload.size > MAX_FILE_SIZE):
        return JsonResponse({"error": "Chỉ import file .xlsx tối đa 50 MB."}, status=400)
    if not step5_errors(campaign).exists():
        return JsonResponse({"error": "Chưa có dữ liệu được chuyển tới Step 5."}, status=409)
    try:
        with transaction.atomic():
            job = AreaConfirmationExcelJob.objects.create(
                campaign=campaign, requested_by=request.user, kind=kind, message="Đang chờ xử lý"
            )
    except IntegrityError:
        return JsonResponse({"error": "Đang có file cùng loại được xử lý. Vui lòng chờ."}, status=409)
    try:
        if upload and kind == "import":
            job.input_file.save(f"area-confirmation-import-{job.pk}.xlsx", upload)
        from app_document_campaigns.tasks import process_area_confirmation_excel
        if settings.FILE_JOBS_RUN_ON_WEB:
            process_area_confirmation_excel.apply(args=[job.pk], throw=False)
        else:
            process_area_confirmation_excel.delay(job.pk)
        job.refresh_from_db()
    except Exception:
        AreaConfirmationExcelJob.objects.filter(pk=job.pk).update(
            status="failed", message="Không xử lý được file. Kiểm tra storage và log web.", updated_at=timezone.now()
        )
    return JsonResponse({"id": job.pk}, status=202)


@login_required
def area_confirmation_excel_status(request, campaign_id, job_id):
    if not _is_admin(request.user):
        return JsonResponse({"error": "Không có quyền."}, status=403)
    job = get_object_or_404(AreaConfirmationExcelJob, pk=job_id, campaign_id=campaign_id)
    cutoff = timezone.now() - timedelta(minutes=12)
    if job.status in {"queued", "running"} and job.updated_at < cutoff:
        AreaConfirmationExcelJob.objects.filter(pk=job.pk, status__in=["queued", "running"], updated_at__lt=cutoff).update(
            status="failed", message="Quá 12 phút không có tiến độ. Hãy thử lại.", updated_at=timezone.now()
        )
        job.refresh_from_db()
    response = JsonResponse({
        "id": job.pk, "kind": job.kind, "status": job.status, "progress": job.progress,
        "message": job.message, "summary": job.summary,
        "download_url": reverse("document_campaigns:download_area_confirmation_excel", kwargs={"campaign_id": campaign_id, "job_id": job.pk}) if job.output_file and job.status == "succeeded" else None,
    })
    response["Cache-Control"] = "no-store"
    return response


@login_required
def download_area_confirmation_excel(request, campaign_id, job_id):
    if not _is_admin(request.user):
        return JsonResponse({"error": "Không có quyền."}, status=403)
    job = get_object_or_404(AreaConfirmationExcelJob, pk=job_id, campaign_id=campaign_id, kind="export", status="succeeded")
    try:
        if not job.output_file:
            raise FileNotFoundError()
        stream = job.output_file.open("rb")
    except FileNotFoundError:
        return JsonResponse({"error": "Không tìm thấy file trên media. Hãy tạo lại file."}, status=404)
    response = FileResponse(stream, as_attachment=True, filename=job.output_file.name.rsplit("/", 1)[-1], content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    response["Cache-Control"] = "no-store"
    return response
