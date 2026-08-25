import hashlib
import json
from unittest.mock import patch

from django.test import TestCase, override_settings
from django.urls import reverse

from gapo_relay.models import GapoRelayEvent
from gapo_relay.services import make_event_id, store_event


@override_settings(
    GAPO_RELAY_INGRESS_SECRET="ingress-secret",
    GAPO_RELAY_MAX_BODY_BYTES=1024,
)
class IngressTests(TestCase):
    def setUp(self):
        self.url = reverse("gapo_relay:ingress", args=["ingress-secret"])

    def _post(self, payload, **extra):
        raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        response = self.client.post(
            self.url,
            data=raw,
            content_type="application/json",
            **extra,
        )
        return response, raw

    def test_stores_original_payload_and_metadata_before_success(self):
        payload = {
            "id": "evt-123",
            "event": "message_created",
            "message": {
                "id": "msg-456",
                "text": "Xin chào",
                "thread": {"id": "thread-789"},
            },
        }

        with self.assertLogs("gapo_relay.views", level="INFO") as captured_logs:
            with patch("gapo_relay.views.store_event", wraps=store_event) as mocked_store:
                response, raw = self._post(payload)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {
                "ok": True,
                "event_id": "evt-123",
                "duplicate": False,
                "received_at": response.json()["received_at"],
            },
        )
        self.assertTrue(response.json()["received_at"].endswith("+07:00"))
        self.assertIn("received_at", mocked_store.call_args.kwargs)
        event = GapoRelayEvent.objects.get()
        self.assertEqual(event.raw_payload, payload)
        self.assertEqual(event.payload_sha256, hashlib.sha256(raw).hexdigest())
        self.assertEqual(event.event_type, "message_created")
        self.assertEqual(event.thread_id, "thread-789")
        self.assertEqual(event.message_id, "msg-456")
        self.assertEqual(event.delivery_status, GapoRelayEvent.Status.PENDING)
        rendered_logs = "\n".join(captured_logs.output)
        self.assertIn('"action": "ingress_accepted"', rendered_logs)
        self.assertIn('"event_id": "evt-123"', rendered_logs)
        self.assertNotIn("ingress-secret", rendered_logs)
        self.assertNotIn("Xin chào", rendered_logs)

    def test_duplicate_is_idempotent_and_does_not_reset_existing_event(self):
        payload = {"id": "evt-duplicate", "event": "message_created"}
        first, _ = self._post(payload)
        event = GapoRelayEvent.objects.get()
        event.delivery_status = GapoRelayEvent.Status.DELIVERED
        event.save(update_fields=["delivery_status"])

        second, _ = self._post(payload)

        self.assertEqual(second.status_code, 200)
        self.assertTrue(second.json()["duplicate"])
        self.assertEqual(second.json()["received_at"], first.json()["received_at"])
        self.assertEqual(GapoRelayEvent.objects.count(), 1)
        event.refresh_from_db()
        self.assertEqual(event.delivery_status, GapoRelayEvent.Status.DELIVERED)

    def test_event_id_priority_and_canonical_hash_fallback(self):
        self.assertEqual(make_event_id({"id": 12, "event_id": "ignored"}), "12")
        self.assertEqual(make_event_id({"event_id": 34}), "34")

        payload = {"z": "Tiếng Việt", "a": {"second": 2, "first": 1}}
        expected = "sha256:" + hashlib.sha256(
            json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
        ).hexdigest()
        response, _ = self._post(payload)
        self.assertEqual(response.json()["event_id"], expected)

    def test_rejects_bad_auth_content_and_oversized_payload(self):
        bad_auth = self.client.post(
            reverse("gapo_relay:ingress", args=["wrong-secret"]),
            data=b"{}",
            content_type="application/json",
        )
        self.assertEqual(bad_auth.status_code, 401)

        wrong_type = self.client.post(self.url, data="{}", content_type="text/plain")
        self.assertEqual(wrong_type.status_code, 415)

        invalid = self.client.post(self.url, data=b"{", content_type="application/json")
        self.assertEqual(invalid.status_code, 400)
        self.assertEqual(invalid.json()["error"], "invalid_json")

        nonstandard_nan = self.client.post(
            self.url, data=b'{"value":NaN}', content_type="application/json"
        )
        self.assertEqual(nonstandard_nan.status_code, 400)
        self.assertEqual(nonstandard_nan.json()["error"], "invalid_json")

        array = self.client.post(self.url, data=b"[]", content_type="application/json")
        self.assertEqual(array.status_code, 400)
        self.assertEqual(array.json()["error"], "object_required")

        oversized = self.client.post(
            self.url,
            data=b'{"value":"' + (b"a" * 1100) + b'"}',
            content_type="application/json",
        )
        self.assertEqual(oversized.status_code, 413)
        self.assertEqual(GapoRelayEvent.objects.count(), 0)

    @override_settings(GAPO_RELAY_INGRESS_SECRET="")
    def test_unset_ingress_secret_fails_closed(self):
        response = self.client.post(
            self.url, data=b"{}", content_type="application/json"
        )
        self.assertEqual(response.status_code, 401)
