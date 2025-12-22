from django.db import transaction
from django.utils import timezone

from .models import AdmAdministrativeDocument, AdmDocumentCounter, AdmPaperDocument, AdmPaperCounter


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
        year = timezone.now().year
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
        conflict = AdmAdministrativeDocument.objects.filter(
            doc_type_id=doc_type_id,
            issuing_company_id=company_id,
            created_at__year=year,
            running_number=candidate,
        ).first()
        if conflict is None:
            break
        is_void = getattr(conflict, "is_void", False)
        is_void = is_void or str(conflict.document_number_full or "").endswith("-VOID")
        if is_void:
            void_conflicts.append(conflict)
            break  # allow reuse this number
        candidate += 1
        attempts += 1
        if attempts > 1000:
            raise ValueError("Could not allocate unique running number.")

    counter.next_number = candidate + 1
    counter.save(update_fields=["next_number", "updated_at"])
    return candidate, void_conflicts


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

