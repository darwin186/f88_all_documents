from datetime import timedelta

from django import forms
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db.models import Count, F, Q
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from app_documents.models import AreaManager, Manager
from app_document_campaigns.forms import CampaignDeadlineForm
from app_document_campaigns.models import AreaManagerAccessLink, Campaign, CampaignError, CampaignVersion, ShopAccessLink, ShopSubmission
from app_document_campaigns.services.access_links import (
    AccessLinkError,
    issue_area_manager_access_link,
    resolve_area_manager_access_link,
)
from app_document_campaigns.services.monitoring_access import scope_campaign_errors


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


def _area_rows(queryset, campaign):
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
    links = {item.area_manager_id: item for item in AreaManagerAccessLink.objects.filter(campaign=campaign, area_manager_id__in=area_ids)}
    submitted = {
        row["shop__manager_id__areaManager_id"]: row["total"]
        for row in ShopSubmission.objects.filter(campaign=campaign, shop__manager_id__areaManager_id__in=area_ids)
        .values("shop__manager_id__areaManager_id")
        .annotate(total=Count("shop_id", distinct=True))
    }
    for row in grouped:
        area_id = row["shop__manager_id__areaManager_id"]
        row.update(
            area_id=area_id,
            area_code=row["shop__manager_id__areaManager__areaManager_code"],
            area_name=row["shop__manager_id__areaManager__areaManager_name"],
            area_email=row["shop__manager_id__areaManager__areaManager_email"] or "",
            region_name=row["shop__manager_id__regionManager__regionManager_name"] or "—",
            submitted_shops=submitted.get(area_id, 0),
            progress=int(row["answered"] * 100 / max(row["errors"], 1)),
            link=links.get(area_id),
        )
    return grouped


@login_required
def campaign_area_monitor(request, campaign_id):
    campaign = get_object_or_404(Campaign.objects.select_related("current_version"), pk=campaign_id)
    errors, scope = scope_campaign_errors(_base_errors(campaign), request.user)
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
    rows = _area_rows(errors.filter(shop_id__in=selected_shop_ids), campaign)
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
    }
    params = request.GET.copy(); params.pop("page", None)
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
    })


def _area_detail_context(campaign, area, queryset, request):
    base = queryset.filter(shop__manager_id__areaManager=area)
    shop_options = list(base.order_by("shop__shop_code").values("shop_id", "shop__shop_code", "shop__shop_name").distinct())
    shop_ids = {row["shop_id"] for row in shop_options}
    total = base.count()
    answered = base.filter(shop_response__answer_code__isnull=False).exclude(shop_response__answer_code="").count()
    contracts = base.exclude(contract_code="").values("contract_code").distinct().count()
    queryset = base
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
        "area_link": AreaManagerAccessLink.objects.filter(campaign=campaign, area_manager=area).first(),
    }


@login_required
def area_manager_detail(request, campaign_id, area_id):
    campaign = get_object_or_404(Campaign, pk=campaign_id)
    scoped, _ = scope_campaign_errors(_base_errors(campaign), request.user)
    area = get_object_or_404(AreaManager, pk=area_id)
    context = _area_detail_context(campaign, area, scoped, request)
    if not context["has_data"]:
        raise Http404("Không có dữ liệu QLKV trong phạm vi được phép.")
    context["public_view"] = False
    return render(request, "app_document_campaigns/area_manager_readonly.html", context)


def public_area_manager_view(request, raw_token):
    try:
        link = resolve_area_manager_access_link(raw_token, touch=True)
    except AccessLinkError as exc:
        return HttpResponse(str(exc), status=410)
    context = _area_detail_context(link.campaign, link.area_manager, _base_errors(link.campaign), request)
    context.update(public_view=True, link=link)
    response = render(request, "app_document_campaigns/area_manager_readonly.html", context)
    response["Cache-Control"] = "no-store"
    return response


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
    if not campaign.link_expires_at or campaign.link_expires_at <= timezone.now():
        return JsonResponse({"ok": False, "error": "Hạn link chung đã hết; hãy điều chỉnh deadline trước."}, status=409)
    link, token = issue_area_manager_access_link(campaign=campaign, area_manager=area, allowed_email=email, created_by=request.user)
    url = request.build_absolute_uri(reverse("document_campaigns:public_area_manager_view", kwargs={"raw_token": token}))
    return JsonResponse({"ok": True, "url": url, "expires_at": link.expires_at.strftime("H:%M %d/%m/%Y")})


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
    link = AreaManagerAccessLink.objects.get(campaign_id=campaign_id, area_manager_id=area_id)
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
    link = get_object_or_404(AreaManagerAccessLink, campaign_id=campaign_id, area_manager_id=area_id)
    try:
        expires_at = forms.DateTimeField().clean(request.POST.get("expires_at"))
    except ValidationError:
        return JsonResponse({"ok": False, "error": "Ngày hết hạn không hợp lệ."}, status=400)
    if expires_at <= timezone.now():
        return JsonResponse({"ok": False, "error": "Ngày hết hạn mới phải ở tương lai."}, status=400)
    link.expires_at = expires_at
    link.save(update_fields=["expires_at"])
    return JsonResponse({"ok": True, "expires_at": expires_at.strftime("H:%M %d/%m/%Y")})
