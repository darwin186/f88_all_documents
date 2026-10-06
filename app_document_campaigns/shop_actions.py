from datetime import timedelta
from dataclasses import replace
from django import forms
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST, require_GET
from django.contrib.auth.decorators import login_required
from app_document_campaigns.forms import CampaignEmailConfigForm
from app_document_campaigns.models import Campaign, CampaignEmailBatch, CampaignError, ShopAccessLink, ShopSubmission, TeamReview, ShopEmailDelivery
from app_document_campaigns.views import campaign_admin_required
from app_document_campaigns.services.access_links import issue_shop_access_link
from app_document_campaigns.services.email_templates import (
    ALLOWED_VARIABLES,
    EmailTemplateError,
    area_manager_details,
    campaign_email_config,
    preflight_campaign_email,
    render_campaign_email,
    template_context,
    validate_templates,
)
from app_document_campaigns.services.email_html import email_body_html


def _campaign_shops(campaign):
    from app_documents.models import Shop

    ids = (
        CampaignError.objects.filter(campaign=campaign)
        .exclude(status__in=[CampaignError.Status.EXCLUDED, CampaignError.Status.CANCELLED])
        .order_by()
        .values_list("shop_id", flat=True)
        .distinct()
    )
    return list(
        Shop.objects.filter(pk__in=ids)
        .select_related("manager_id__areaManager", "manager_id__regionManager")
        .order_by("shop_code", "pk")
    )


@login_required
@require_POST
@campaign_admin_required
def save_campaign_email_config(request, campaign_id):
    campaign = get_object_or_404(Campaign, pk=campaign_id)
    config = campaign_email_config(campaign)
    form = CampaignEmailConfigForm(request.POST, instance=config)
    if not form.is_valid():
        return JsonResponse(
            {"ok": False, "errors": {key: [str(item) for item in values] for key, values in form.errors.items()}},
            status=400,
        )
    config = form.save(updated_by=request.user)
    return JsonResponse({"ok": True, "message": "Đã lưu cấu hình email.", "template_version": config.template_version})


@login_required
@require_GET
@campaign_admin_required
def campaign_email_preflight(request, campaign_id):
    campaign = get_object_or_404(Campaign, pk=campaign_id)
    config = campaign_email_config(campaign)
    try:
        result = preflight_campaign_email(campaign, _campaign_shops(campaign), config)
    except EmailTemplateError as exc:
        return JsonResponse({"ok": False, "error": str(exc)}, status=400)
    return JsonResponse({"ok": True, **result})


@login_required
@require_GET
@campaign_admin_required
def campaign_email_preview(request, campaign_id):
    campaign = get_object_or_404(Campaign, pk=campaign_id)
    shops = _campaign_shops(campaign)
    if not shops:
        return JsonResponse({"ok": False, "error": "Chiến dịch chưa có PGD để preview."}, status=409)
    config = campaign_email_config(campaign)
    preview_url = "https://example.invalid/respond/preview-only/"
    try:
        rendered = render_campaign_email(
            config,
            campaign,
            shops[0],
            preview_url,
        )
    except EmailTemplateError as exc:
        return JsonResponse({"ok": False, "error": str(exc)}, status=400)
    return JsonResponse(
        {
            "ok": True,
            "shop": f"{shops[0].shop_code} · {shops[0].shop_name}",
            "subject": rendered.subject,
            "body": rendered.body,
            "to": rendered.to,
            "cc": rendered.cc,
            "bcc": rendered.bcc,
            "from_email": rendered.from_email,
            "area_email": area_manager_details(shops[0])[2],
            "context": {
                **template_context(campaign, shops[0], preview_url),
                "support_email": config.support_email or "",
            },
            "variables": ALLOWED_VARIABLES,
        }
    )


@login_required
@require_POST
@campaign_admin_required
def send_campaign_test_email(request, campaign_id):
    campaign = get_object_or_404(Campaign, pk=campaign_id)
    shops = _campaign_shops(campaign)
    if not shops:
        return JsonResponse({"ok": False, "error": "Chiến dịch chưa có PGD để gửi thử."}, status=409)
    test_email = (request.POST.get("test_email") or "").strip()
    try:
        validate_email(test_email)
    except ValidationError:
        return JsonResponse({"ok": False, "error": "Email nhận thử không hợp lệ."}, status=400)
    from app_document_campaigns.bulk_email_views import _validate_graph_configuration
    from app_document_campaigns.services.test_email_delivery import queue_test_email
    config = campaign_email_config(campaign)
    try:
        _validate_graph_configuration()
        rendered = render_campaign_email(
            config,
            campaign,
            shops[0],
            "https://example.invalid/respond/email-test-no-live-token/",
            recipient_override=test_email,
        )
        rendered = replace(
            rendered,
            subject=f"[TEST] {rendered.subject}",
            body=("<p><strong>ĐÂY LÀ EMAIL KIỂM THỬ</strong> — không phải link phản hồi thật.</p>"
                  f"{email_body_html(rendered.body)}"),
            cc=[],
            bcc=[],
        )
        batch = queue_test_email(
            campaign=campaign,
            email_type=CampaignEmailBatch.EmailType.PGD_RESPONSE,
            target=shops[0],
            rendered=rendered,
            template_version=config.template_version,
            requested_by=request.user,
        )
    except Exception:
        import logging

        logging.getLogger(__name__).exception(
            "CAMPAIGN_TEST_EMAIL_FAILED campaign_id=%s user_id=%s",
            campaign.pk,
            request.user.pk,
        )
        return JsonResponse({"ok": False, "error": "Không thể đưa email thử vào hàng đợi. Kiểm tra kênh gửi và log web."}, status=502)
    return JsonResponse({
        "ok": True,
        "message": f"Đã đưa email thử tới {test_email} vào hàng đợi. Không gửi CC/BCC thật.",
        "batch_id": str(batch.pk),
    }, status=202)


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
        config = campaign_email_config(campaign)
        try:
            validate_templates(config.subject_template, config.body_template)
        except EmailTemplateError as exc:
            return JsonResponse({"error": str(exc)}, status=400)
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
