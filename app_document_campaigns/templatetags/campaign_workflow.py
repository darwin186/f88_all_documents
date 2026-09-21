from django import template
from django.db.models import Count, OuterRef, Q, Subquery
from django.urls import reverse
from django.utils import timezone

from app_document_campaigns.models import CampaignError, CampaignVersion, ShopSubmission, TeamReview
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
    if campaign:
        done.add(1)
        if campaign.current_version_id and campaign.current_version.status == CampaignVersion.Status.PUBLISHED:
            done.add(2)
        errors, _ = scope_campaign_errors(CampaignError.objects.filter(campaign=campaign).exclude(status__in=["excluded", "cancelled"]), request.user)
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
        review_percent = round(counts["reviewed"] * 100 / counts["total"]) if counts["total"] else 0
        if errors.exists() and not reviewed.exclude(latest_decision__in=["approved", "excluded"]).exists() and not reviewed.filter(latest_decision__isnull=True).exists():
            done.add(4)
    definitions = [
        (1, "Tạo kỳ", "Thông tin chiến dịch"),
        (2, "Review dữ liệu", "SQL · Excel · dữ liệu cuối"),
        (3, "Gửi & phản hồi PGD", "Phát hành · QLKV theo dõi"),
        (4, "Team review phản hồi", "Giữ/loại lỗi · nhận xét"),
        (5, "QLKV xác nhận", "Xác nhận lỗi sau khi book"),
        (6, "QLV kết quả cuối", "Kết quả tổng hợp cấp vùng"),
    ]
    steps = []
    for number, label, description in definitions:
        url = None
        if campaign and number <= 4:
            route = {1: "campaign_detail", 2: "campaign_detail", 3: "campaign_response_monitor", 4: "campaign_review"}[number]
            url = reverse(f"document_campaigns:{route}", kwargs={"campaign_id": campaign.pk})
            if number == 1 and admin:
                url += "?settings=1"
        elif number == 1 and admin:
            url = reverse("document_campaigns:campaign_create")
        progress = context.get("workflow_progress", 100 if 2 in done else 0) if number == 2 else review_percent
        if number == 3:
            progress = response_percent
        steps.append({"number": number, "label": label, "description": description, "url": url, "current": number == current, "done": number in done, "unbuilt": number >= 5, "progress": progress, "progress_hue": round(progress * 1.2)})
    match = getattr(request, "resolver_match", None)
    return {"steps": steps, "campaign": campaign, "messages": context.get("messages", ()), "show_workflow_intro": not match or match.url_name != "campaign_list", "can_edit_campaign": admin, "settings_on_page": bool(context.get("settings_form"))}
