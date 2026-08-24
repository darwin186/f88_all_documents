from datetime import timedelta

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from gapo_relay.models import GapoRelayEvent


class Command(BaseCommand):
    help = "Delete relay events past their delivered/dead-letter retention period."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Only report how many events would be deleted.",
        )
        parser.add_argument("--delivered-days", type=int)
        parser.add_argument("--dead-letter-days", type=int)

    def handle(self, *args, **options):
        delivered_days = options["delivered_days"]
        if delivered_days is None:
            delivered_days = int(getattr(settings, "GAPO_RELAY_RETENTION_DAYS", 30))
        dead_letter_days = options["dead_letter_days"]
        if dead_letter_days is None:
            dead_letter_days = int(
                getattr(settings, "GAPO_RELAY_DEAD_LETTER_RETENTION_DAYS", 90)
            )
        if delivered_days < 1 or dead_letter_days < 1:
            raise CommandError("Retention days must be positive integers.")

        now = timezone.now()
        delivered = GapoRelayEvent.objects.filter(
            delivery_status=GapoRelayEvent.Status.DELIVERED,
            delivered_at__lt=now - timedelta(days=delivered_days),
        )
        dead_letters = GapoRelayEvent.objects.filter(
            delivery_status=GapoRelayEvent.Status.DEAD_LETTER,
            updated_at__lt=now - timedelta(days=dead_letter_days),
        )
        delivered_count = delivered.count()
        dead_letter_count = dead_letters.count()

        if not options["dry_run"]:
            with transaction.atomic():
                delivered.delete()
                dead_letters.delete()

        action = "Would delete" if options["dry_run"] else "Deleted"
        self.stdout.write(
            self.style.SUCCESS(
                f"{action} {delivered_count} delivered and "
                f"{dead_letter_count} dead-letter event(s)."
            )
        )
