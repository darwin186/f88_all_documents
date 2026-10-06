import json
import uuid
from datetime import date
from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from app_document_campaigns.models import (
    Campaign,
    CampaignEmailBatch,
    CampaignEmailDelivery,
    CampaignEmailWebhookEvent,
    CampaignType,
)
from app_document_campaigns.services.email_templates import RenderedCampaignEmail
from app_document_campaigns.services.power_automate_email import _message_payload, dispatch_email_chunk


@override_settings(POWER_AUTOMATE_EMAIL_CALLBACK_SECRET="callback-test-secret")
class PowerAutomateEmailCallbackTests(TestCase):
    def setUp(self):
        user = get_user_model().objects.create_user(username="power-automate-test")
        campaign_type, _ = CampaignType.objects.get_or_create(
            code="power-automate-test",
            defaults={"code_prefix": "PAT", "name": "Power Automate test"},
        )
        self.campaign = Campaign.objects.create(
            code="PAT-202610",
            name="Test Power Automate",
            campaign_type=campaign_type,
            report_month=date(2026, 10, 1),
            created_by=user,
        )
        self.batch = CampaignEmailBatch.objects.create(
            campaign=self.campaign,
            email_type=CampaignEmailBatch.EmailType.PGD_RESPONSE,
            idempotency_key="batch-test-1",
            total_count=2,
            requested_by=user,
        )
        self.first = self._delivery("delivery-test-1", 1)
        self.second = self._delivery("delivery-test-2", 2)
        self.url = reverse("power_automate_email_callback")

    def _delivery(self, key, target_id):
        return CampaignEmailDelivery.objects.create(
            batch=self.batch,
            target_type=CampaignEmailDelivery.TargetType.SHOP,
            target_id=target_id,
            to_emails=[f"shop{target_id}@example.com"],
            from_email="ops@example.com",
            rendered_subject="Test",
            idempotency_key=key,
            status=CampaignEmailDelivery.Status.ACCEPTED,
        )

    def _callback(self, payload, secret="callback-test-secret"):
        return self.client.post(
            self.url,
            data=json.dumps(payload),
            content_type="application/json",
            HTTP_X_WEBHOOK_SECRET=secret,
        )

    def test_callback_updates_each_delivery_and_batch(self):
        response = self._callback({
            "event_id": str(uuid.uuid4()),
            "batch_id": str(self.batch.pk),
            "results": [
                {"message_id": str(self.first.pk), "status": "sent", "provider_message_id": "outlook-1"},
                {"message_id": str(self.second.pk), "status": "failed", "error_code": "mailbox", "error_message": "Mailbox unavailable"},
            ],
        })
        self.assertEqual(response.status_code, 200)
        self.first.refresh_from_db(); self.second.refresh_from_db(); self.batch.refresh_from_db()
        self.assertEqual(self.first.status, CampaignEmailDelivery.Status.SENT)
        self.assertEqual(self.second.status, CampaignEmailDelivery.Status.FAILED)
        self.assertEqual(self.batch.status, CampaignEmailBatch.Status.PARTIALLY_FAILED)
        self.assertEqual((self.batch.sent_count, self.batch.failed_count), (1, 1))

    def test_callback_is_idempotent_and_sent_cannot_be_downgraded(self):
        event_id = str(uuid.uuid4())
        payload = {"event_id": event_id, "batch_id": str(self.batch.pk), "results": [{"message_id": str(self.first.pk), "status": "sent"}]}
        self.assertEqual(self._callback(payload).status_code, 200)
        duplicate = self._callback(payload)
        self.assertTrue(duplicate.json()["duplicate"])
        self.assertEqual(CampaignEmailWebhookEvent.objects.filter(event_id=event_id).count(), 1)
        later = {"event_id": str(uuid.uuid4()), "batch_id": str(self.batch.pk), "results": [{"message_id": str(self.first.pk), "status": "failed"}]}
        self.assertEqual(self._callback(later).status_code, 200)
        self.first.refresh_from_db()
        self.assertEqual(self.first.status, CampaignEmailDelivery.Status.SENT)

    def test_callback_fails_closed_without_correct_secret(self):
        payload = {"event_id": str(uuid.uuid4()), "batch_id": str(self.batch.pk), "results": []}
        self.assertEqual(self._callback(payload, "wrong").status_code, 401)
        self.assertEqual(CampaignEmailWebhookEvent.objects.count(), 0)

    def test_callback_rejects_message_from_another_batch(self):
        other = CampaignEmailBatch.objects.create(
            campaign=self.campaign,
            email_type=CampaignEmailBatch.EmailType.PGD_RESPONSE,
            idempotency_key="batch-test-2",
            total_count=0,
            requested_by=self.batch.requested_by,
        )
        payload = {"event_id": str(uuid.uuid4()), "batch_id": str(other.pk), "results": [{"message_id": str(self.first.pk), "status": "sent"}]}
        self.assertEqual(self._callback(payload).status_code, 400)

    @override_settings(
        POWER_AUTOMATE_EMAIL_WEBHOOK_URL="https://example.invalid/email-intake",
        POWER_AUTOMATE_EMAIL_WEBHOOK_SECRET="intake-secret",
        POWER_AUTOMATE_EMAIL_CALLBACK_URL="https://ida.example/api/integrations/power-automate/email/callback/",
    )
    @patch("app_document_campaigns.services.power_automate_email.requests.post")
    def test_dispatch_marks_accepted_but_not_sent(self, post):
        class Response:
            status_code = 202
            def __init__(self, payload): self.payload = payload
            def json(self):
                return {
                    "ok": True,
                    "batch_id": self.payload["batch_id"],
                    "request_id": self.payload["request_id"],
                    "provider_batch_id": "flow-run-1",
                    "status": "accepted",
                    "results": [{"message_id": self.payload["messages"][0]["message_id"], "status": "accepted"}],
                }
        def respond(_url, **kwargs):
            return Response(json.loads(kwargs["data"].decode("utf-8")))
        post.side_effect = respond
        message = {
            "message_id": str(self.first.pk), "idempotency_key": self.first.idempotency_key,
            "target": {"type": "shop", "id": 1, "code": "1", "name": "PGD Test"},
            "from": {"address": "ops@example.com", "name": "Ops"},
            "to": ["shop1@example.com"], "cc": [], "bcc": [], "subject": "Test",
            "body": {"content_type": "html", "content": "<p>Test</p>"}, "metadata": {},
        }
        result = dispatch_email_chunk(self.batch, [message])
        self.first.refresh_from_db()
        self.assertEqual(result.provider_batch_id, "flow-run-1")
        self.assertEqual(self.first.status, CampaignEmailDelivery.Status.ACCEPTED)
        self.assertIsNone(self.first.sent_at)
        self.assertEqual(self.first.attempts.count(), 1)
        headers = post.call_args.kwargs["headers"]
        self.assertEqual(headers["X-Webhook-Secret"], "intake-secret")
        self.assertTrue(headers["X-Signature"].startswith("sha256="))

    def test_message_payload_preserves_safe_rich_html(self):
        rendered = RenderedCampaignEmail(
            subject="Email HTML",
            body='<p>Xin chào <strong>PGD</strong></p><script>alert(1)</script>',
            to=["shop1@example.com"], cc=[], bcc=[], from_email="Ops <ops@example.com>",
            area_email="", area_manager_id=None,
        )
        target = SimpleNamespace(pk=1, shop_code=1001, shop_name="PGD Test")
        payload = _message_payload(self.first, target, rendered, {})
        self.assertEqual(payload["body"]["content_type"], "html")
        self.assertIn("<strong>PGD</strong>", payload["body"]["content"])
        self.assertNotIn("<script", payload["body"]["content"])
