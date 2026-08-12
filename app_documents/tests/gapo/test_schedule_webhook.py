import json
from unittest.mock import patch

from django.contrib.auth.models import User
from django.urls import reverse
from django.test import TestCase, override_settings
from django.utils import timezone

from app_documents.forms import GapoScheduleForm
from app_documents.models import GapoScheduledMessage, GapoWebhookEvent
from app_documents.tasks import send_gapo_scheduled_message


class GapoScheduleFormTests(TestCase):
    def test_dynamic_form_accepts_layout_metadata(self):
        form = GapoScheduleForm(
            data={
                "target_type": GapoScheduledMessage.TargetType.COLLAB,
                "target_value": "6988361890911272961",
                "body_type": GapoScheduledMessage.BodyType.DYNAMIC,
                "message": "Parcel notification",
                "body_metadata": json.dumps(
                    {
                        "metadata": {
                            "layout": {
                                "type": "container",
                                "direction": "vertical",
                                "children": [
                                    {
                                        "type": "text",
                                        "text_object": {
                                            "text": "Xin chao",
                                            "font": {
                                                "name": "SFProText",
                                                "style": "regular",
                                                "size": 14,
                                            },
                                            "number_of_lines": 0,
                                            "color": "#18202A",
                                        },
                                    }
                                ],
                            }
                        }
                    }
                ),
                "schedule_at": "2026-03-20T10:30",
            }
        )

        self.assertTrue(form.is_valid(), form.errors)
        instance = form.save(commit=False)
        self.assertEqual(instance.collab_id, "6988361890911272961")
        self.assertEqual(instance.body_type, GapoScheduledMessage.BodyType.DYNAMIC)
        self.assertIn("metadata", instance.body_metadata)

    def test_dynamic_form_rejects_missing_layout(self):
        form = GapoScheduleForm(
            data={
                "target_type": GapoScheduledMessage.TargetType.RECEIVER,
                "target_value": "123456",
                "body_type": GapoScheduledMessage.BodyType.DYNAMIC,
                "message": "Parcel notification",
                "body_metadata": json.dumps({"metadata": {}}),
                "schedule_at": "2026-03-20T10:30",
            }
        )

        self.assertFalse(form.is_valid())
        self.assertIn("body_metadata", form.errors)


@override_settings(
    GAPO_API_URL="https://api.gapowork.vn/3rd-bot/v1.0/3rd/messages",
    GAPO_BOT_API_KEY="test-api-key",
    GAPO_BOT_ID="5828367940457829714",
)
class GapoScheduledMessageTaskTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="gapo_admin", password="secret")

    @patch("app_documents.tasks.post_gapo_message")
    def test_task_sends_dynamic_payload_to_collab(self, mocked_post):
        schedule = GapoScheduledMessage.objects.create(
            collab_id="6988361890911272961",
            message="123",
            body_type=GapoScheduledMessage.BodyType.DYNAMIC,
            body_metadata={
                "metadata": {
                    "layout": {
                        "type": "container",
                        "direction": "vertical",
                        "children": [],
                    }
                }
            },
            schedule_at=timezone.now(),
            created_by=self.user,
        )
        mocked_post.return_value = {"ok": True}

        result = send_gapo_scheduled_message.run(schedule.id)

        self.assertIn("Sent to", result)
        mocked_post.assert_called_once()
        payload = mocked_post.call_args.args[0]
        self.assertEqual(payload["collab_id"], "6988361890911272961")
        self.assertEqual(payload["bot_id"], 5828367940457829714)
        self.assertEqual(payload["body"]["type"], "dynamic")
        self.assertEqual(payload["body"]["text"], "123")
        self.assertIn("metadata", payload["body"])

        schedule.refresh_from_db()
        self.assertEqual(schedule.status, GapoScheduledMessage.Status.SENT)


class GapoWebhookPOCTests(TestCase):
    def test_webhook_endpoint_stores_incoming_payload(self):
        response = self.client.post(
            reverse("gapo_webhook_poc"),
            data=json.dumps(
                {
                    "type": "message_created",
                    "bot_id": "5828367940457829714",
                    "thread_id": 123456789,
                    "message": {
                        "id": "msg-001",
                        "text": "hello from bot A",
                        "sender_id": "bot-a",
                    },
                }
            ),
            content_type="application/json",
            HTTP_X_GAPO_REQUEST_ID="req-1",
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["ok"])

        event = GapoWebhookEvent.objects.get()
        self.assertEqual(event.event_type, "message_created")
        self.assertEqual(event.bot_id, "5828367940457829714")
        self.assertEqual(event.thread_id, "123456789")
        self.assertEqual(event.message_id, "msg-001")
        self.assertEqual(event.sender_id, "bot-a")
        self.assertEqual(event.message_text, "hello from bot A")
        self.assertTrue(event.is_json_valid)
        self.assertEqual(event.headers["X-Gapo-Request-Id"], "req-1")

    @override_settings(GAPO_WEBHOOK_SECRET="test-secret")
    def test_webhook_endpoint_rejects_invalid_secret(self):
        response = self.client.post(
            reverse("gapo_webhook_poc"),
            data=json.dumps({"type": "message_created"}),
            content_type="application/json",
            HTTP_X_GAPO_WEBHOOK_SECRET="wrong-secret",
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(GapoWebhookEvent.objects.count(), 0)
