from django.db import transaction
from django.utils import timezone

from .models import AdmAdministrativeDocument, AdmDocumentCounter, AdmPaperDocument


@transaction.atomic
def allocate_running_number(
    doc_type_id: int, company_id: int, year: int | None = None
) -> tuple[int, list]:
    """
    Allocate the next running number for a given doc_type, company, and year.

    The counter row is locked (select_for_update) so concurrent requests do not
    reuse the same number. We also check existing AdmAdministrativeDocument
    records to skip over any number that was already taken (e.g. manual insert
    or backfill) before bumping the counter forward.

    Returns (number, void_conflicts) where void_conflicts holds voided documents
    that occupied skipped numbers (for warning UX).
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
        if conflict is None or conflict.is_void is False:
            break
        void_conflicts.append(conflict)
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

    while True:
        doc_num = f"{candidate:05d}/{year}/{paper_type_code}-F88"
        if not AdmPaperDocument.objects.filter(document_number_full=doc_num).exists():
            break
        candidate += 1
    return candidate, doc_num

