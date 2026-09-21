from django.utils import timezone
from app_document_campaigns.models import ShopAccessLink


def shop_deadlines(campaign):
    """An individual extension overrides the campaign deadline, never link expiry."""
    return {link.shop_id: min(link.response_deadline if link.has_deadline_extension else (campaign.response_deadline or link.response_deadline), link.expires_at) for link in ShopAccessLink.objects.filter(campaign=campaign, revoked_at__isnull=True)}


def shop_deadline_passed(campaign, shop_id, deadlines=None):
    deadline = (deadlines if deadlines is not None else shop_deadlines(campaign)).get(shop_id, campaign.response_deadline)
    return bool(deadline and timezone.now() >= deadline)
