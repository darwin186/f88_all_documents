from django import template
from django.db.models import Count, OuterRef, Q, Subquery
from django.urls import reverse
from django.utils import timezone

from app_document_campaigns.models import AreaConfirmation, CampaignError, CampaignVersion, ShopSubmission, TeamReview
from app_document_campaigns.services.monitoring_access import scope_campaign_errors
from app_document_campaigns.services.team_review_excel import eligible_errors

register = template.Library()


@register.simple_tag(takes_context=True)
def area_sort_query(context, key):
    params = context["request"].GET.copy()
    current = params.get("sort", "shop")
    direction = params.get("direction", "asc")
    params["sort"] = key
    params["direction"] = "desc" if current == key and direction == "asc" else "asc"
    params.pop("page", None)
    return params.urlencode()


@register.inclusion_tag("app_document_campaigns/components/workflow_nav.html", takes_context=True)
def campaign_workflow(context, current=1):
    campaign = context.get("campaign")
    request = context["request"]
    admin = request.user.is_superuser or request.user.groups.filter(name="admin").exists()
    done = set()
    review_percent = 0
    response_percent = 0
    area_percent = 0
    qtrr_percent = 0
    review_done_count = 0
    review_total_count = 0
    area_done = 0
    area_total = 0
    area_deadline_passed = False
    if campaign:
        done.add(1)
        if campaign.current_version_id and campaign.current_version.status == CampaignVersion.Status.PUBLISHED:
            done.add(2)
        errors, _ = scope_campaign_errors(CampaignError.objects.filter(campaign=campaign).exclude(status__in=["excluded", "cancelled", "suspended"]), request.user)
        shop_ids = errors.order_by().values("shop_id").distinct()
        total_shops = shop_ids.count()
        from app_document_campaigns.services.response_deadlines import shop_deadlines, shop_deadline_passed
        submitted_ids = set(ShopSubmission.objects.filter(campaign=campaign, shop_id__in=shop_ids).values_list("shop_id", flat=True))
        deadlines = shop_deadlines(campaign)
        completed = sum(shop_id in submitted_ids or shop_deadline_passed(campaign, shop_id, deadlines) for shop_id in shop_ids.values_list("shop_id", flat=True))
        response_percent = round(completed * 100 / total_shops) if total_shops else 0
        if total_shops and completed >= total_shops:
            done.add(3)
        latest = TeamReview.objects.filter(error_id=OuterRef("pk")).order_by("-created_at", "-pk")
        review_errors, _ = scope_campaign_errors(eligible_errors(campaign), request.user)
        reviewed = review_errors.annotate(latest_decision=Subquery(latest.values("decision")[:1]))
        counts = context.get("stats") if current == 4 else None
        if counts is None:
            counts = reviewed.aggregate(total=Count("pk"), reviewed=Count("pk", filter=Q(latest_decision__isnull=False)))
        review_done_count = counts["reviewed"]
        review_total_count = counts["total"]
        review_percent = round(counts["reviewed"] * 100 / counts["total"]) if counts["total"] else 0
        if reviewed.exists() and not reviewed.exclude(latest_decision__in=["approved", "excluded", "suspended"]).exists() and not reviewed.filter(latest_decision__isnull=True).exists():
            done.add(4)
        if 4 in done:
            latest_area = AreaConfirmation.objects.filter(error_id=OuterRef("pk")).order_by("-created_at", "-pk")
            area_rows = reviewed.filter(latest_decision=TeamReview.Decision.APPROVED).exclude(status=CampaignError.Status.SUSPENDED).annotate(
                latest_area_decision=Subquery(latest_area.values("is_agreed")[:1])
            )
            area_total = area_rows.count()
            area_done = area_rows.filter(latest_area_decision__isnull=False).count()
            area_deadline_passed = bool(
                campaign.area_response_deadline
                and timezone.now() >= campaign.area_response_deadline
            )
            area_percent = 100 if area_total and area_deadline_passed else (
                round(area_done * 100 / area_total) if area_total else 0
            )
            if area_total and (area_done >= area_total or area_deadline_passed):
                done.add(5)
                mapped = area_rows.filter(risk_booking__isnull=False).count()
                qtrr_percent = round(mapped * 100 / area_total) if area_total else 0
                if mapped >= area_total:
                    done.add(6)
    definitions = [
        (1, "Tạo kỳ", "Thông tin chiến dịch"),
        (2, "Review dữ liệu", "SQL · Excel · dữ liệu cuối"),
        (3, "Gửi & phản hồi PGD", "Phát hành · QLKV theo dõi"),
        (4, "Team review phản hồi", "Giữ/loại lỗi · nhận xét"),
        (5, "QLKV xác nhận", "Xác nhận lỗi sau khi book"),
        (6, "Book lỗi gửi QTRR", "Mapping mã lỗi · file cuối"),
    ]
    steps = []
    for number, label, description in definitions:
        url = None
        if campaign and number <= 4:
            route = {1: "campaign_detail", 2: "campaign_detail", 3: "campaign_response_monitor", 4: "campaign_review"}[number]
            url = reverse(f"document_campaigns:{route}", kwargs={"campaign_id": campaign.pk})
            if number == 1 and admin:
                url += "?settings=1"
        elif campaign and number == 5 and 4 in done:
            url = reverse("document_campaigns:campaign_area_monitor", kwargs={"campaign_id": campaign.pk}) + "?stage=confirmation"
        elif campaign and number == 6 and 5 in done:
            url = reverse("document_campaigns:campaign_qtrr_booking", kwargs={"campaign_id": campaign.pk})
        elif number == 1 and admin:
            url = reverse("document_campaigns:campaign_create")
        progress = context.get("workflow_progress", 100 if 2 in done else 0) if number == 2 else review_percent
        if number == 1:
            progress = 100 if campaign else 0
        elif number == 3:
            progress = response_percent
        elif number == 5:
            progress = area_percent
        elif number == 6:
            progress = qtrr_percent
        progress_detail = ""
        if number == 3 and campaign:
            progress_detail = f"{completed}/{total_shops} PGD đã hoàn tất hoặc hết hạn · QLKV chỉ xem"
            if campaign.response_deadline:
                deadline = campaign.response_deadline
                if timezone.is_aware(deadline):
                    deadline = timezone.localtime(deadline)
                progress_detail += f" · hạn PGD {deadline:%H:%M %d/%m/%Y}"
        elif number == 4 and campaign:
            progress_detail = f"{review_done_count}/{review_total_count} dòng đã review · còn {max(review_total_count - review_done_count, 0)} dòng"
        elif number == 5 and campaign:
            progress_detail = f"{area_done}/{area_total} dòng QLKV đã xác nhận"
            if area_deadline_passed:
                progress_detail += " · đã hết hạn xác nhận"
            elif campaign.area_response_deadline:
                deadline = campaign.area_response_deadline
                if timezone.is_aware(deadline):
                    deadline = timezone.localtime(deadline)
                progress_detail += f" · hạn {deadline:%H:%M %d/%m/%Y}"
            else:
                progress_detail += " · chưa cấu hình hạn xác nhận"
        steps.append({"number": number, "label": label, "description": description, "url": url, "current": number == current, "done": number in done, "unbuilt": (number == 6 and 5 not in done) or (number == 5 and 4 not in done), "progress": progress, "progress_hue": round(progress * 1.2), "progress_detail": progress_detail})
    match = getattr(request, "resolver_match", None)
    return {
        "steps": steps,
        "campaign": campaign,
        "messages": context.get("messages", ()),
        "show_workflow_intro": not match or match.url_name != "campaign_list",
        "can_edit_campaign": admin,
        "settings_on_page": bool(context.get("settings_form")),
        "workflow_current": current,
        "release_state": context.get("release_state"),
        "csrf_token": context.get("csrf_token"),
    }
