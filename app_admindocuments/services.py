from django.db import transaction
from django.utils import timezone

from .models import AdmAdministrativeDocument, AdmDocumentCounter


@transaction.atomic
def allocate_running_number(
    doc_type_id: int, company_id: int, year: int | None = None
) -> int:
    """Allocate the next running number for a given doc_type, company, and year."""
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
    while True:
        exists = AdmAdministrativeDocument.objects.filter(
            doc_type_id=doc_type_id,
            issuing_company_id=company_id,
            created_at__year=year,
            running_number=candidate,
        ).exists()
        if not exists:
            break
        candidate += 1
        attempts += 1
        if attempts > 1000:
            raise ValueError("Could not allocate unique running number.")

    counter.next_number = candidate + 1
    counter.save(update_fields=["next_number", "updated_at"])
    return candidate

