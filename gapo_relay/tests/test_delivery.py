import json
import uuid
from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from gapo_relay.models import GapoRelayEvent


@override_settings(
    GAPO_RELAY_DELIVERY_TOKEN="delivery-token",
    GAPO_RELAY_MAX_BATCH_SIZE=10,
    GAPO_RELAY_DEFAULT_LEASE_SECONDS=120,
    GAPO_RELAY_MAX_LEASE_SECONDS=3600,
    GAPO_RELAY_MAX_ATTEMPTS=20,
)
class DeliveryTests(TestCase):
    auth = {"HTTP_AUTHORIZATION": "Bearer delivery-token"}

    def _event(self, event_id, **overrides):
        now = timezone.now()
        values = {
            "event_id": event_id,
            "event_type": "message_created",
            "received_at": now,
            "raw_payload": {"id": event_id, "event": "message_created"},
            "payload_sha256": "a" * 64,
            "next_attempt_at": now,
        }
        values.update(overrides)
        return GapoRelayEvent.objects.create(**values)

    def _post(self, name, payload, authenticated=True):
        extra = self.auth if authenticated else {}
        return self.client.post(
            reverse(f"gapo_relay:{name}"),
            data=json.dumps(payload),
            content_type="application/json",
            **extra,
        )

    def _claim(self, **overrides):
        payload = {"consumer_id": "project-ops-01", "limit": 10, "lease_seconds": 120}
        payload.update(overrides)
        return self._post("claim", payload)

    def test_health_checks_database(self):
        response = self.client.get(reverse("gapo_relay:health"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"ok": True, "database": "ok"})

    def test_delivery_endpoints_require_nonempty_bearer_token(self):
        response = self._post(
            "claim", {"consumer_id": "consumer", "limit": 1}, authenticated=False
        )
        self.assertEqual(response.status_code, 401)

        with override_settings(GAPO_RELAY_DELIVERY_TOKEN=""):
            response = self.client.post(
                reverse("gapo_relay:claim"),
                data=json.dumps({"consumer_id": "consumer", "limit": 1}),
                content_type="application/json",
                HTTP_AUTHORIZATION="Bearer ",
            )
        self.assertEqual(response.status_code, 401)

    def test_claim_leases_due_and_expired_events_in_received_order(self):
        now = timezone.now()
        first = self._event("first", received_at=now - timedelta(minutes=2))
        expired = self._event(
            "expired",
            received_at=now - timedelta(minutes=1),
            delivery_status=GapoRelayEvent.Status.LEASED,
            lease_token=uuid.uuid4(),
            lease_until=now - timedelta(seconds=1),
        )
        future = self._event("future", next_attempt_at=now + timedelta(minutes=5))
        delivered = self._event(
            "delivered", delivery_status=GapoRelayEvent.Status.DELIVERED
        )

        response = self._claim(limit=2)

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual([item["event_id"] for item in body["events"]], ["first", "expired"])
        self.assertEqual(body["events"][0]["payload"], first.raw_payload)
        lease_token = uuid.UUID(body["lease_token"])
        first.refresh_from_db()
        expired.refresh_from_db()
        self.assertEqual(first.lease_token, lease_token)
        self.assertEqual(expired.lease_token, lease_token)
        self.assertEqual(first.attempt_count, 1)
        self.assertEqual(expired.attempt_count, 1)
        self.assertEqual(future.delivery_status, GapoRelayEvent.Status.PENDING)
        self.assertEqual(delivered.delivery_status, GapoRelayEvent.Status.DELIVERED)

    def test_ack_only_updates_events_in_the_matching_active_lease(self):
        event = self._event("ack-me")
        lease_token = self._claim().json()["lease_token"]

        wrong = self._post(
            "ack",
            {"lease_token": str(uuid.uuid4()), "event_ids": [event.event_id]},
        )
        self.assertEqual(wrong.status_code, 200)
        self.assertEqual(wrong.json()["acknowledged"], 0)
        event.refresh_from_db()
        self.assertEqual(event.delivery_status, GapoRelayEvent.Status.LEASED)

        response = self._post(
            "ack", {"lease_token": lease_token, "event_ids": [event.event_id]}
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["acknowledged"], 1)
        event.refresh_from_db()
        self.assertEqual(event.delivery_status, GapoRelayEvent.Status.DELIVERED)
        self.assertIsNotNone(event.delivered_at)
        self.assertIsNone(event.lease_token)
        self.assertEqual(event.last_http_status, 200)

    @patch("gapo_relay.services.random.uniform", return_value=0)
    def test_nack_schedules_exponential_retry_and_records_failure(self, _random):
        event = self._event("nack-me")
        lease_token = self._claim().json()["lease_token"]
        before = timezone.now()

        response = self._post(
            "nack",
            {
                "lease_token": lease_token,
                "event_id": event.event_id,
                "error": "Project Ops timeout",
                "http_status": 504,
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], GapoRelayEvent.Status.PENDING)
        self.assertEqual(response.json()["retry_after_seconds"], 10)
        event.refresh_from_db()
        self.assertEqual(event.last_error, "Project Ops timeout")
        self.assertEqual(event.last_http_status, 504)
        self.assertIsNone(event.lease_token)
        self.assertGreaterEqual(event.next_attempt_at, before + timedelta(seconds=10))

    def test_twentieth_failed_attempt_moves_to_dead_letter(self):
        lease_token = uuid.uuid4()
        event = self._event(
            "dead-letter-me",
            delivery_status=GapoRelayEvent.Status.LEASED,
            lease_token=lease_token,
            lease_until=timezone.now() + timedelta(seconds=30),
            attempt_count=20,
        )

        response = self._post(
            "nack",
            {
                "lease_token": str(lease_token),
                "event_id": event.event_id,
                "error": "still unavailable",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], GapoRelayEvent.Status.DEAD_LETTER)
        self.assertIsNone(response.json()["retry_after_seconds"])
        event.refresh_from_db()
        self.assertEqual(event.delivery_status, GapoRelayEvent.Status.DEAD_LETTER)

    def test_nack_rejects_stale_or_foreign_lease(self):
        event = self._event("foreign-lease")
        self._claim()
        response = self._post(
            "nack",
            {
                "lease_token": str(uuid.uuid4()),
                "event_id": event.event_id,
                "error": "timeout",
            },
        )
        self.assertEqual(response.status_code, 409)
        event.refresh_from_db()
        self.assertEqual(event.delivery_status, GapoRelayEvent.Status.LEASED)

    def test_claim_validates_consumer_limits_and_json(self):
        self.assertEqual(self._claim(consumer_id="").status_code, 400)
        self.assertEqual(self._claim(limit=0).status_code, 400)
        self.assertEqual(self._claim(limit=11).status_code, 400)
        self.assertEqual(self._claim(lease_seconds=0).status_code, 400)
        response = self.client.post(
            reverse("gapo_relay:claim"),
            data="not-json",
            content_type="application/json",
            **self.auth,
        )
        self.assertEqual(response.status_code, 400)
