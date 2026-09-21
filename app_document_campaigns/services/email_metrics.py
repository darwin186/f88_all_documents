from django.db.models import F
from app_document_campaigns.models import ShopEmailDelivery


def emailed_area_manager_count(campaign, shop_ids):
    """Count distinct current area managers CC'd in successful sends in scope."""
    return ShopEmailDelivery.objects.filter(
        link__campaign=campaign, link__shop_id__in=shop_ids,
        status=ShopEmailDelivery.Status.SENT,
        area_manager_id=F("link__shop__manager_id__areaManager_id"),
    ).exclude(area_email="").order_by().values("area_manager_id").distinct().count()
