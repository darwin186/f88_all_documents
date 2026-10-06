from django.db.models import Case, IntegerField, OuterRef, Q, Subquery, Value, When
from django.utils import timezone
from app_documents.models import Folder


def with_folder_receipt(queryset):
    folder = (
        Folder.objects.filter(shop_id=OuterRef("shop_id"))
        .filter(
            Q(pk=OuterRef("folder_id"))
            | Q(pk=OuterRef("source_object_id"), folder_code=OuterRef("code"))
            | Q(folder_code=OuterRef("code"))
        )
        .annotate(
            match_priority=Case(
                When(pk=OuterRef("folder_id"), then=Value(0)),
                When(
                    pk=OuterRef("source_object_id"),
                    folder_code=OuterRef("code"),
                    then=Value(1),
                ),
                default=Value(2),
                output_field=IntegerField(),
            )
        )
        .order_by("match_priority", "-pk")
    )
    return queryset.annotate(
        receipt_folder_id=Subquery(folder.values("pk")[:1]),
        receipt_folder_type_id=Subquery(folder.values("folder_type_id")[:1]),
        receipt_folder_type_code=Subquery(folder.values("folder_type_id__folder_type_code")[:1]),
        receipt_folder_type_name=Subquery(folder.values("folder_type_id__folder_type_name")[:1]),
        receipt_status_id=Subquery(folder.values("folder_status_id")[:1]),
        receipt_status_code=Subquery(folder.values("folder_status_id__folder_status_code")[:1]),
        receipt_status_name=Subquery(folder.values("folder_status_id__folder_status_name")[:1]),
        receipt_status_badge_color=Subquery(folder.values("folder_status_id__badge_color")[:1]),
        receipt_received=Subquery(folder.values("folder_status_id__is_received")[:1]),
        receipt_date=Subquery(folder.values("lastest_received_date")[:1]),
    )


def folder_state_values(error):
    if error.error_type != "folder":
        return ["—", "—"]
    if not getattr(error, "receipt_folder_id", None):
        return ["Không tìm thấy quyển", "Không tìm thấy quyển"]
    folder_type = getattr(error, "receipt_folder_type_name", None) or getattr(error, "receipt_folder_type_code", None) or "Chưa xác định"
    status = getattr(error, "receipt_status_name", None) or getattr(error, "receipt_status_code", None) or "Chưa xác định"
    return [folder_type, status]


def receipt_values(error):
    if error.error_type != "folder":
        return ["—", ""]
    if not getattr(error, "receipt_folder_id", None):
        return ["Không tìm thấy quyển", ""]
    received = error.receipt_received
    status = "Đã nhận" if received else ("Chưa nhận" if received is False else "Chưa xác định")
    date = error.receipt_date
    if date and timezone.is_aware(date):
        date = timezone.localtime(date)
    return [status, date.strftime("%d/%m/%Y %H:%M") if date else ""]
