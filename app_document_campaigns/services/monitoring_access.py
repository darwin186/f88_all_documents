from dataclasses import dataclass

from django.db.models import Q

from app_documents.models import AreaManager, Manager, RegionManager, UserProfile


@dataclass(frozen=True)
class MonitoringScope:
    level: str
    label: str


def scope_campaign_errors(queryset, user):
    """Apply a deny-by-default organization scope to campaign error data."""
    roles = set(user.groups.values_list("name", flat=True))
    if user.is_superuser or "admin" in roles:
        return queryset, MonitoringScope("admin", "Toàn hệ thống")

    profile = (
        UserProfile.objects.select_related(
            "shop",
        )
        .filter(user=user)
        .first()
    )
    if "shop" in roles:
        if profile and profile.shop_id:
            return queryset.filter(shop_id=profile.shop_id), MonitoringScope(
                "shop", profile.shop.shop_name
            )
        return queryset.none(), MonitoringScope("none", "Chưa gắn Phòng giao dịch")

    if "supervisor" in roles or "manager" in roles:
        identity_filter = Q()
        if user.email:
            identity_filter |= Q(regionManager_email__iexact=user.email)
        if profile and profile.employee_code:
            identity_filter |= Q(regionManager_code__iexact=profile.employee_code)
        region_manager_ids = set()
        if identity_filter:
            region_manager_ids.update(
                RegionManager.objects.filter(identity_filter).values_list("pk", flat=True)
            )
        manager_filter = Q()
        if user.email:
            manager_filter |= Q(qlv_email__iexact=user.email)
        if profile and profile.employee_code:
            manager_filter |= Q(qlv_code__iexact=profile.employee_code)
        if manager_filter:
            region_manager_ids.update(
                Manager.objects.filter(manager_filter).values_list(
                    "regionManager_id", flat=True
                )
            )
        region_manager_ids.discard(None)
        if region_manager_ids:
            names = list(
                RegionManager.objects.filter(pk__in=region_manager_ids).values_list(
                    "regionManager_name", flat=True
                )
            )
            return queryset.filter(
                shop__manager_id__regionManager_id__in=region_manager_ids
            ), MonitoringScope("region_manager", ", ".join(names))

        area_ids = set()
        area_identity_filter = Q()
        if user.email:
            area_identity_filter |= Q(areaManager_email__iexact=user.email)
        if profile and profile.employee_code:
            area_identity_filter |= Q(areaManager_code__iexact=profile.employee_code)
        if area_identity_filter:
            area_ids.update(
                AreaManager.objects.filter(area_identity_filter).values_list("pk", flat=True)
            )
        area_manager_filter = Q()
        if user.email:
            area_manager_filter |= Q(qlkv_email__iexact=user.email)
        if profile and profile.employee_code:
            area_manager_filter |= Q(qlkv_code__iexact=profile.employee_code)
        if area_manager_filter:
            area_ids.update(
                Manager.objects.filter(area_manager_filter).values_list(
                    "areaManager_id", flat=True
                )
            )
        area_ids.discard(None)
        if area_ids:
            names = list(
                AreaManager.objects.filter(pk__in=area_ids).values_list(
                    "areaManager_name", flat=True
                )
            )
            return queryset.filter(area_manager_id__in=area_ids), MonitoringScope(
                "area", ", ".join(names)
            )
        return queryset.none(), MonitoringScope(
            "none", "Tài khoản chưa khớp Region Manager/Khu vực"
        )

    return queryset.none(), MonitoringScope("none", "Không có quyền xem dữ liệu")
