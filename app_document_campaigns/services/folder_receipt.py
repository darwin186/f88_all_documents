from django.db.models import OuterRef, Q, Subquery
from django.utils import timezone
from app_documents.models import Folder


def with_folder_receipt(queryset):
    folder = Folder.objects.filter(shop_id=OuterRef("shop_id")).filter(
        Q(pk=OuterRef("folder_id")) | Q(pk=OuterRef("source_object_id"), folder_code=OuterRef("code")) | Q(folder_code=OuterRef("code"))
    ).order_by("pk")
    return queryset.annotate(receipt_folder_id=Subquery(folder.values("pk")[:1]), receipt_received=Subquery(folder.values("folder_status_id__is_received")[:1]), receipt_date=Subquery(folder.values("lastest_received_date")[:1]))


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
