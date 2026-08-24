from datetime import timedelta
from io import StringIO

from django.core.management import call_command
from django.test import TestCase, override_settings
from django.utils import timezone

from gapo_relay.models import GapoRelayEvent


@override_settings(
    GAPO_RELAY_RETENTION_DAYS=30,
    GAPO_RELAY_DEAD_LETTER_RETENTION_DAYS=90,
)
class RelayCleanupTests(TestCase):
    def _event(self, event_id, status):
        now = timezone.now()
        return GapoRelayEvent.objects.create(
            event_id=event_id,
            received_at=now,
            raw_payload={"id": event_id},
            payload_sha256="a" * 64,
            delivery_status=status,
            next_attempt_at=now,
            delivered_at=now if status == GapoRelayEvent.Status.DELIVERED else None,
        )

    def test_cleanup_respects_status_retention_and_dry_run(self):
        old_delivered = self._event("old-delivered", GapoRelayEvent.Status.DELIVERED)
        old_dead = self._event("old-dead", GapoRelayEvent.Status.DEAD_LETTER)
        recent_delivered = self._event("recent-delivered", GapoRelayEvent.Status.DELIVERED)
        pending = self._event("old-pending", GapoRelayEvent.Status.PENDING)
        now = timezone.now()
        GapoRelayEvent.objects.filter(pk=old_delivered.pk).update(
            delivered_at=now - timedelta(days=31)
        )
        GapoRelayEvent.objects.filter(pk=old_dead.pk).update(
            updated_at=now - timedelta(days=91)
        )
        GapoRelayEvent.objects.filter(pk=pending.pk).update(
            updated_at=now - timedelta(days=365)
        )

        output = StringIO()
        call_command("relay_cleanup", "--dry-run", stdout=output)
        self.assertIn("Would delete 1 delivered and 1 dead-letter", output.getvalue())
        self.assertEqual(GapoRelayEvent.objects.count(), 4)

        call_command("relay_cleanup", stdout=StringIO())
        self.assertQuerySetEqual(
            GapoRelayEvent.objects.order_by("event_id").values_list("event_id", flat=True),
            [pending.event_id, recent_delivered.event_id],
            transform=lambda value: value,
        )
