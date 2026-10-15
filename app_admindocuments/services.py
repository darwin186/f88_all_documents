from typing import Any, Dict

from django.db import transaction
from django.db.models import Max
from django.utils import timezone

from app_documents.gapo import (
    GapoMessageError,
    build_gapo_body,
    build_gapo_payload,
    post_gapo_message,
)

from .models import AdmAdministrativeDocument, AdmDocumentCounter, AdmPaperDocument, AdmPaperCounter, administrative_number_year


class NotificationSendError(Exception):
    pass


def send_via_gapo(
    target: str,
    message: str,
    *,
    body_type: str = "text",
    body_metadata: Dict[str, Any] | None = None,
    target_type: str = "receiver",
) -> Dict[str, Any]:
    """Send parcel notifications through the shared Gapo client."""
    try:
        body = build_gapo_body(
            body_type=body_type,
            text=message,
            metadata=body_metadata,
        )
        target_kwargs = {
            "receiver_id": target if target_type == "receiver" else None,
            "thread_id": target if target_type == "thread" else None,
            "collab_id": target if target_type == "collab" else None,
        }
        payload = build_gapo_payload(body=body, **target_kwargs)
        return post_gapo_message(payload)
    except GapoMessageError as exc:
        raise NotificationSendError(str(exc)) from exc


@transaction.atomic
def allocate_running_number(
    doc_type_id: int, company_id: int, year: int | None = None
) -> tuple[int, list]:
    """
    Allocate the next running number cho văn bản hành chính, dựa trên bộ đếm.

    - Khóa row counter (select_for_update) theo doc_type/company/năm.
    - Ưu tiên dùng giá trị next_number của counter. Nếu số đó trùng văn bản đang hoạt động thì tăng tiếp; nếu trùng văn bản đã VOID thì được phép dùng lại (ghi nhận void_conflicts).
    - Không backfill các gap thấp hơn next_number.
    - Counter luôn tiến lên candidate + 1.
    """
    if year is None:
        year = administrative_number_year()
    counter, _created = (
        AdmDocumentCounter.objects.select_for_update().get_or_create(
            doc_type_id=doc_type_id,
            company_id=company_id,
            year=year,
            defaults={"next_number": 1},
        )
    )
    candidate = counter.next_number or 1
    attempts = 0
    void_conflicts = []
    while True:
        conflicts = AdmAdministrativeDocument.objects.filter(
            doc_type_id=doc_type_id,
            issuing_company_id=company_id,
            number_year=year,
            running_number=candidate,
            number_suffix="",
        )
        if not conflicts.exists():
            break
        if not conflicts.filter(is_void=False).exists():
            void_conflicts.extend(conflicts)
            break  # allow reuse this number
        candidate += 1
        attempts += 1
        if attempts > 1000:
            raise ValueError("Could not allocate unique running number.")

    counter.next_number = candidate + 1
    counter.save(update_fields=["next_number", "updated_at"])
    return candidate, void_conflicts


def split_number_group(parent):
    return AdmAdministrativeDocument.objects.filter(
        doc_type_id=parent.doc_type_id, issuing_company_id=parent.issuing_company_id,
        number_year=parent.number_year, running_number=parent.running_number,
    )


def next_split_suffix(parent):
    used = list(split_number_group(parent).exclude(number_suffix="").values_list("number_suffix", flat=True))
    ordinal = max((ord(suffix) - ord("A") + 1 for suffix in used), default=0)
    if ordinal >= 26:
        raise ValueError("Số này đã dùng hết hậu tố A–Z.")
    return chr(ord("A") + ordinal)


@transaction.atomic
def create_split_document(*, parent, document, expected_suffix, request_key, user):
    # Lock the same counter as ordinary allocation, before locking a document.
    AdmDocumentCounter.objects.select_for_update().get_or_create(
        doc_type_id=parent.doc_type_id, company_id=parent.issuing_company_id,
        year=parent.number_year,
        defaults={"next_number": (AdmAdministrativeDocument.objects.filter(
            doc_type_id=parent.doc_type_id, issuing_company_id=parent.issuing_company_id,
            number_year=parent.number_year, number_suffix="",
        ).aggregate(mx=Max("running_number"))["mx"] or 0) + 1},
    )
    existing = AdmAdministrativeDocument.objects.filter(split_request_key=request_key).first()
    if existing:
        if existing.split_parent_id != parent.pk or existing.created_by_id != user.pk:
            raise ValueError("Yêu cầu tạo văn bản không hợp lệ.")
        return existing, False
    parent = AdmAdministrativeDocument.objects.select_for_update().get(pk=parent.pk)
    if parent.split_parent_id:
        raise ValueError("Hãy chọn số gốc để tạo văn bản tách thửa.")
    suffix = next_split_suffix(parent)
    if suffix != expected_suffix:
        raise ValueError(f"Số dự kiến đã thay đổi. Vui lòng lưu lại với {parent.running_number:03d}{suffix}.")
    document.doc_type_id = parent.doc_type_id
    document.issuing_company_id = parent.issuing_company_id
    document.running_number = parent.running_number
    document.number_year = parent.number_year
    document.number_suffix = suffix
    document.split_parent = parent
    document.split_request_key = request_key
    document.created_by = user
    if document.issuing_department.company_id != parent.issuing_company_id:
        raise ValueError("Phòng ban phải thuộc công ty đã chọn.")
    document.save()
    return document, True


@transaction.atomic
def allocate_paper_running_number(
    paper_type_id: int, paper_type_code: str, year: int
) -> tuple[int, str]:
    """
    Allocate the next available running number for a paper type/year.

    - Locks existing rows of that paper_type/year (select_for_update).
    - Fills vào khoảng trống nhỏ nhất (gap) nếu có, không chỉ +1.
    - Nếu có counter (AdmPaperCounter) và next_number lớn hơn gap, ưu tiên next_number.
    - Trả về (running_number, document_number_full).
    """
    existing = (
        AdmPaperDocument.objects.select_for_update()
        .filter(paper_type_id=paper_type_id, created_at__year=year, is_deleted=False)
        .order_by("running_number")
    )
    candidate = 1
    for doc in existing:
        if doc.running_number > candidate:
            break
        candidate = doc.running_number + 1
    counter = (
        AdmPaperCounter.objects.select_for_update()
        .filter(paper_type_id=paper_type_id, year=year)
        .first()
    )
    if counter and counter.next_number and counter.next_number > candidate:
        candidate = counter.next_number

    while True:
        doc_num = f"{candidate:05d}/{year}/{paper_type_code}-F88"
        if not AdmPaperDocument.objects.filter(document_number_full=doc_num).exists():
            break
        candidate += 1

    if counter:
        counter.next_number = candidate + 1
        counter.save(update_fields=["next_number", "updated_at"])
    return candidate, doc_num

