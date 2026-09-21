from datetime import timedelta
from django import forms
from django.core.exceptions import ValidationError
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST, require_GET
from django.contrib.auth.decorators import login_required
from app_document_campaigns.models import Campaign, CampaignError, ShopAccessLink, ShopSubmission, TeamReview, ShopEmailDelivery
from app_document_campaigns.views import campaign_admin_required
from app_document_campaigns.services.access_links import issue_shop_access_link


@login_required
@require_POST
@campaign_admin_required
@transaction.atomic
def extend_shop_deadline(request, campaign_id, shop_id):
    campaign = get_object_or_404(Campaign.objects.select_for_update(), pk=campaign_id)
    link = get_object_or_404(ShopAccessLink.objects.select_for_update(), campaign=campaign, shop_id=shop_id)
    if campaign.status != Campaign.Status.ACTIVE or link.revoked_at:
        return JsonResponse({"error": "Kỳ hoặc link đã khóa."}, status=409)
    if ShopSubmission.objects.filter(campaign=campaign, shop_id=shop_id).exists() or TeamReview.objects.filter(error__campaign=campaign, error__shop_id=shop_id).exists():
        return JsonResponse({"error": "PGD đã gửi chính thức hoặc team đã review; không mở lại phản hồi."}, status=409)
    try:
        deadline = forms.DateTimeField().clean(request.POST.get("deadline"))
    except ValidationError:
        return JsonResponse({"error": "Ngày giờ gia hạn không hợp lệ."}, status=400)
    if deadline <= max(timezone.now(), link.response_deadline):
        return JsonResponse({"error": "Deadline mới phải ở tương lai và sau deadline hiện tại."}, status=400)
    link.response_deadline = deadline
    link.has_deadline_extension = True
    if link.expires_at < deadline:
        link.expires_at = deadline + timedelta(days=31)
    link.save(update_fields=["response_deadline", "expires_at", "has_deadline_extension"])
    return JsonResponse({"ok": True, "deadline": deadline.strftime("%H:%M %d/%m/%Y"), "expires_at": link.expires_at.strftime("%H:%M %d/%m/%Y")})


@login_required
@require_POST
@campaign_admin_required
def email_shop_link(request, campaign_id, shop_id):
    from app_document_campaigns.tasks import send_campaign_shop_link
    with transaction.atomic():
        campaign = get_object_or_404(Campaign.objects.select_for_update(), pk=campaign_id)
        error = CampaignError.objects.filter(campaign=campaign, shop_id=shop_id).exclude(status__in=["excluded", "cancelled"]).select_related("shop").first()
        if not error:
            return JsonResponse({"error": "PGD không có lỗi trong kỳ."}, status=404)
        existing = ShopAccessLink.objects.filter(campaign=campaign, shop_id=shop_id).first()
        if campaign.status != Campaign.Status.ACTIVE or not existing or existing.revoked_at or not existing.is_editable or ShopSubmission.objects.filter(campaign=campaign, shop_id=shop_id).exists():
            return JsonResponse({"error": "Cần link đang nhận phản hồi và PGD chưa gửi chính thức."}, status=409)
        try:
            forms.EmailField().clean(error.shop.shop_email)
        except ValidationError:
            return JsonResponse({"error": "Email PGD chưa hợp lệ; hãy cập nhật Master Data."}, status=400)
        link, token = issue_shop_access_link(campaign=campaign, shop=error.shop, allowed_email=error.shop.shop_email, created_by=request.user, response_deadline=existing.response_deadline, expires_at=existing.expires_at)
        url = request.build_absolute_uri(reverse("document_campaigns:shop_response", kwargs={"raw_token": token}))
        delivery = ShopEmailDelivery.objects.create(link=link)
    try:
        send_campaign_shop_link.delay(link.pk, url, delivery.pk)
    except Exception:
        ShopEmailDelivery.objects.filter(pk=delivery.pk).update(status="failed", message="Không kết nối được hàng đợi gửi email.", finished_at=timezone.now())
        response = JsonResponse({"error": "Đã đổi link nhưng chưa gửi email: không kết nối được worker/broker. Hãy copy link mới.", "url": url}, status=503)
        response["Cache-Control"] = "no-store"
        return response
    response = JsonResponse({"ok": True, "url": url, "status_url": reverse("document_campaigns:shop_email_status", kwargs={"campaign_id": campaign.pk, "delivery_id": delivery.pk}), "message": "Đã đưa email vào hàng đợi. Link cũ đã hết hiệu lực."})
    response["Cache-Control"] = "no-store"
    return response


@login_required
@require_GET
@campaign_admin_required
def shop_email_status(request, campaign_id, delivery_id):
    from app_document_campaigns.services.email_metrics import emailed_area_manager_count
    delivery = get_object_or_404(ShopEmailDelivery.objects.select_related("link__campaign"), pk=delivery_id, link__campaign_id=campaign_id)
    ids = CampaignError.objects.filter(campaign_id=campaign_id).exclude(status__in=["excluded", "cancelled"]).order_by().values("shop_id")
    response = JsonResponse({"status": delivery.status, "message": delivery.message, "area_emailed": emailed_area_manager_count(delivery.link.campaign, ids)})
    response["Cache-Control"] = "no-store"
    return response
