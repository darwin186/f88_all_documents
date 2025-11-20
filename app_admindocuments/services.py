from django.db import transaction
from django.utils import timezone

from .models import AdmDocumentCounter


@transaction.atomic
def allocate_running_number(doc_type_id: int, year: int | None = None) -> int:
    """Allocate the next running number for a given doc_type and year."""
    if year is None:
        year = timezone.now().year
    counter, _created = (
        AdmDocumentCounter.objects.select_for_update().get_or_create(
            doc_type_id=doc_type_id, year=year, defaults={"next_number": 1}
        )
    )
    current = counter.next_number
    counter.next_number = current + 1
    counter.save(update_fields=["next_number", "updated_at"])
    return current

