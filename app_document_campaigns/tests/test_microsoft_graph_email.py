import base64
import json
from unittest.mock import Mock, patch

from django.test import SimpleTestCase, override_settings

from app_document_campaigns.services import microsoft_graph_email


GRAPH_SETTINGS = {
    "MICROSOFT_GRAPH_TENANT_ID": "tenant-id",
    "MICROSOFT_GRAPH_CLIENT_ID": "application-id",
    "MICROSOFT_GRAPH_CLIENT_SECRET": "secret-value",
    "MICROSOFT_GRAPH_MAILBOX_EMAIL": "datnm@f88.vn",
    "MICROSOFT_GRAPH_SENDER_EMAIL": "phongvanhanh@f88.vn",
    "MICROSOFT_GRAPH_CONNECT_TIMEOUT": 3.05,
    "MICROSOFT_GRAPH_READ_TIMEOUT": 30,
}


def _app_token(*roles):
    claims = base64.urlsafe_b64encode(json.dumps({"roles": list(roles)}).encode()).decode().rstrip("=")
    return f"header.{claims}.signature"


@override_settings(**GRAPH_SETTINGS)
class MicrosoftGraphEmailTests(SimpleTestCase):
    def setUp(self):
        microsoft_graph_email._token_value = ""
        microsoft_graph_email._token_expires_at = 0.0

    @patch("app_document_campaigns.services.microsoft_graph_email.requests.post")
    def test_send_message_gets_app_token_and_posts_html_email(self, post):
        token_response = Mock(status_code=200)
        token_response.json.return_value = {"access_token": _app_token("Mail.Send"), "expires_in": 3600}
        send_response = Mock(status_code=202)
        post.side_effect = [token_response, send_response]

        result = microsoft_graph_email.send_message({
            "from": {"address": "phongvanhanh@f88.vn", "name": "Phòng Vận Hành"},
            "to": ["pgd@example.com"],
            "cc": ["qlkv@example.com"],
            "bcc": [],
            "subject": "Kiểm thử Graph",
            "body": {"content_type": "html", "content": "<strong>Nội dung</strong>"},
        })

        self.assertEqual(result.http_status, 202)
        token_call, send_call = post.call_args_list
        self.assertIn("/tenant-id/oauth2/v2.0/token", token_call.args[0])
        self.assertEqual(token_call.kwargs["data"]["client_secret"], "secret-value")
        self.assertIn("/users/datnm@f88.vn/sendMail", send_call.args[0])
        self.assertEqual(send_call.kwargs["headers"]["Authorization"], f"Bearer {_app_token('Mail.Send')}")
        message = send_call.kwargs["json"]["message"]
        self.assertEqual(message["body"]["contentType"], "HTML")
        self.assertEqual(message["from"]["emailAddress"]["address"], "phongvanhanh@f88.vn")
        self.assertEqual(message["toRecipients"][0]["emailAddress"]["address"], "pgd@example.com")
        self.assertEqual(message["ccRecipients"][0]["emailAddress"]["address"], "qlkv@example.com")

    @patch("app_document_campaigns.services.microsoft_graph_email.requests.post")
    def test_stale_template_sender_is_overridden_by_graph_configuration(self, post):
        token_response = Mock(status_code=200)
        token_response.json.return_value = {"access_token": _app_token("Mail.Send"), "expires_in": 3600}
        send_response = Mock(status_code=202)
        post.side_effect = [token_response, send_response]

        with self.assertLogs(
            "app_document_campaigns.services.microsoft_graph_email", level="WARNING"
        ) as logs:
            result = microsoft_graph_email.send_message({
                "from": {"address": "another@f88.vn"},
                "to": ["pgd@example.com"],
                "subject": "Sender cũ",
                "body": {"content_type": "html", "content": "Test"},
            })
        self.assertEqual(result.http_status, 202)
        self.assertEqual(
            post.call_args_list[1].kwargs["json"]["message"]["from"]["emailAddress"]["address"],
            "phongvanhanh@f88.vn",
        )
        self.assertIn("MICROSOFT_GRAPH_FROM_OVERRIDDEN", " ".join(logs.output))

    @patch("app_document_campaigns.services.microsoft_graph_email.requests.post")
    def test_token_without_mail_send_can_use_exchange_application_rbac(self, post):
        token_response = Mock(status_code=200)
        token_response.json.return_value = {"access_token": _app_token(), "expires_in": 3600}
        send_response = Mock(status_code=202)
        post.side_effect = [token_response, send_response]

        with self.assertLogs(
            "app_document_campaigns.services.microsoft_graph_email", level="WARNING"
        ) as logs:
            result = microsoft_graph_email.send_message({
                "from": {"address": "phongvanhanh@f88.vn"},
                "to": ["pgd@example.com"],
                "subject": "Exchange RBAC",
                "body": {"content_type": "html", "content": "Test"},
            })
        self.assertEqual(result.http_status, 202)
        self.assertEqual(post.call_count, 2)
        self.assertIn("relying_on=exchange_application_rbac", " ".join(logs.output))
