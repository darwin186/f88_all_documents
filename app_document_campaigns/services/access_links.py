import hashlib
import secrets

from django.utils import timezone

from app_document_campaigns.models import AreaManagerAccessLink, ShopAccessLink


class AccessLinkError(Exception):
    """Base exception for public Shop access links."""


class AccessLinkNotFound(AccessLinkError):
    pass


class AccessLinkExpired(AccessLinkError):
    pass


class AccessLinkRevoked(AccessLinkError):
    pass


def token_digest(raw_token):
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def issue_shop_access_link(*, campaign, shop, allowed_email, created_by, response_deadline=None, expires_at=None):
    raw_token = secrets.token_urlsafe(32)
    existing = ShopAccessLink.objects.filter(campaign=campaign, shop=shop, has_deadline_extension=True).first()
    if existing:
        response_deadline = response_deadline or existing.response_deadline
        expires_at = expires_at or existing.expires_at
    deadline = response_deadline or campaign.response_deadline
    expiration = expires_at or campaign.link_expires_at
    if not deadline or not expiration:
        raise ValueError("Chiến dịch phải có hạn phản hồi và hạn link trước khi phát hành.")
    link, _ = ShopAccessLink.objects.update_or_create(
        campaign=campaign,
        shop=shop,
        defaults={
            "allowed_email": allowed_email,
            "token_digest": token_digest(raw_token),
            "response_deadline": deadline,
            "expires_at": expiration,
            "revoked_at": None,
            "last_accessed_at": None,
            "created_by": created_by,
        },
    )
    return link, raw_token


def resolve_shop_access_link(raw_token, *, touch=False):
    try:
        link = (
            ShopAccessLink.objects.select_related("campaign", "shop")
            .get(token_digest=token_digest(raw_token))
        )
    except ShopAccessLink.DoesNotExist as exc:
        raise AccessLinkNotFound("Link không hợp lệ.") from exc

    now = timezone.now()
    if link.revoked_at:
        raise AccessLinkRevoked("Link đã bị thu hồi.")
    if now >= link.expires_at:
        raise AccessLinkExpired("Link đã hết hạn.")

    if touch:
        ShopAccessLink.objects.filter(pk=link.pk).update(last_accessed_at=now)
        link.last_accessed_at = now
    return link


def issue_area_manager_access_link(*, campaign, area_manager, allowed_email, created_by, expires_at=None):
    raw_token = secrets.token_urlsafe(32)
    expiration = expires_at or campaign.link_expires_at
    if not expiration:
        raise ValueError("Chiến dịch phải có hạn link trước khi phát hành.")
    link, _ = AreaManagerAccessLink.objects.update_or_create(
        campaign=campaign,
        area_manager=area_manager,
        defaults={
            "allowed_email": allowed_email,
            "token_digest": token_digest(raw_token),
            "expires_at": expiration,
            "revoked_at": None,
            "last_accessed_at": None,
            "email_status": AreaManagerAccessLink.EmailStatus.NOT_SENT,
            "email_message": "",
            "emailed_at": None,
            "created_by": created_by,
        },
    )
    return link, raw_token


def resolve_area_manager_access_link(raw_token, *, touch=False):
    try:
        link = AreaManagerAccessLink.objects.select_related("campaign", "area_manager").get(
            token_digest=token_digest(raw_token)
        )
    except AreaManagerAccessLink.DoesNotExist as exc:
        raise AccessLinkNotFound("Link QLKV không hợp lệ.") from exc
    now = timezone.now()
    if link.revoked_at:
        raise AccessLinkRevoked("Link QLKV đã bị thu hồi.")
    if now >= link.expires_at:
        raise AccessLinkExpired("Link QLKV đã hết hạn.")
    if touch:
        AreaManagerAccessLink.objects.filter(pk=link.pk).update(last_accessed_at=now)
        link.last_accessed_at = now
    return link
