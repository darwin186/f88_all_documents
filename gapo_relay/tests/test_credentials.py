import json
from datetime import timedelta
from unittest.mock import patch

from django.contrib.admin.models import LogEntry
from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from gapo_relay.credentials import rotate_relay_credential, verify_relay_secret
from gapo_relay.models import GapoRelayCredential


@override_settings(
    GAPO_RELAY_INGRESS_SECRET="env-ingress-secret-0123456789abcdef",
    GAPO_RELAY_DELIVERY_TOKEN="env-delivery-token-0123456789abcdef",
    GAPO_RELAY_SECRET_GRACE_SECONDS=3600,
)
class CredentialServiceTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_superuser(
            username="relay-admin",
            email="relay@example.test",
            password="admin-password",
        )

    def test_rotation_stores_only_hash_and_keeps_environment_fallback_during_grace(self):
        result = rotate_relay_credential(
            GapoRelayCredential.Kind.INGRESS,
            self.user,
        )
        credential = result.credential

        self.assertTrue(result.plaintext.startswith("gri_"))
        self.assertNotEqual(credential.secret_hash, result.plaintext)
        self.assertNotIn(result.plaintext, credential.fingerprint)
        self.assertEqual(len(credential.secret_hash), 64)
        self.assertEqual(credential.rotated_by, self.user)
        self.assertTrue(
            verify_relay_secret(GapoRelayCredential.Kind.INGRESS, result.plaintext)
        )
        self.assertTrue(
            verify_relay_secret(
                GapoRelayCredential.Kind.INGRESS,
                "env-ingress-secret-0123456789abcdef",
            )
        )

    def test_expired_previous_secret_is_rejected(self):
        result = rotate_relay_credential(GapoRelayCredential.Kind.DELIVERY, self.user)
        GapoRelayCredential.objects.filter(pk=result.credential.pk).update(
            previous_valid_until=timezone.now() - timedelta(seconds=1)
        )

        self.assertFalse(
            verify_relay_secret(
                GapoRelayCredential.Kind.DELIVERY,
                "env-delivery-token-0123456789abcdef",
            )
        )
        self.assertTrue(
            verify_relay_secret(GapoRelayCredential.Kind.DELIVERY, result.plaintext)
        )

    def test_second_rotation_accepts_only_current_and_immediate_previous(self):
        first = rotate_relay_credential(GapoRelayCredential.Kind.DELIVERY, self.user)
        second = rotate_relay_credential(GapoRelayCredential.Kind.DELIVERY, self.user)

        self.assertTrue(
            verify_relay_secret(GapoRelayCredential.Kind.DELIVERY, second.plaintext)
        )
        self.assertTrue(
            verify_relay_secret(GapoRelayCredential.Kind.DELIVERY, first.plaintext)
        )
        self.assertFalse(
            verify_relay_secret(
                GapoRelayCredential.Kind.DELIVERY,
                "env-delivery-token-0123456789abcdef",
            )
        )

    def test_managed_ingress_secret_is_used_by_webhook_view(self):
        result = rotate_relay_credential(GapoRelayCredential.Kind.INGRESS, self.user)
        payload = {"id": "managed-secret-event", "event": "message_created"}
        response = self.client.post(
            reverse("gapo_relay:ingress", args=[result.plaintext]),
            data=json.dumps(payload),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)


@override_settings(
    GAPO_RELAY_INGRESS_SECRET="env-ingress-secret-0123456789abcdef",
    GAPO_RELAY_DELIVERY_TOKEN="env-delivery-token-0123456789abcdef",
    GAPO_RELAY_SECRET_GRACE_SECONDS=3600,
)
class CredentialAdminTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_superuser(
            username="credential-admin",
            email="credential@example.test",
            password="correct-password",
        )
        self.client.force_login(self.user)
        self.url = reverse("admin:gapo_relay_gaporelaycredential_changelist")

    def test_page_is_not_cached_and_never_displays_hashes(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertIn("no-store", response["Cache-Control"])
        self.assertContains(response, "Environment fallback", count=2)

    @patch("gapo_relay.credentials.secrets.token_hex", return_value="a" * 64)
    def test_admin_rotates_and_reveals_plaintext_only_in_post_response(self, _token):
        plaintext = "gri_" + ("a" * 64)
        response = self.client.post(
            self.url,
            {
                "kind": GapoRelayCredential.Kind.INGRESS,
                "confirmation": "ROTATE",
                "current_password": "correct-password",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, plaintext)
        self.assertContains(response, "Webhook URL để đăng ký với GAPO")
        credential = GapoRelayCredential.objects.get(
            kind=GapoRelayCredential.Kind.INGRESS
        )
        self.assertNotEqual(credential.secret_hash, plaintext)
        self.assertNotContains(response, credential.secret_hash)
        self.assertEqual(LogEntry.objects.count(), 1)

        reload_response = self.client.get(self.url)
        self.assertNotContains(reload_response, plaintext)
        self.assertContains(reload_response, credential.fingerprint)

    def test_wrong_password_does_not_rotate(self):
        response = self.client.post(
            self.url,
            {
                "kind": GapoRelayCredential.Kind.DELIVERY,
                "confirmation": "ROTATE",
                "current_password": "wrong-password",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Mật khẩu hiện tại không đúng")
        self.assertFalse(GapoRelayCredential.objects.exists())

    def test_same_origin_post_passes_real_csrf_middleware(self):
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.user)
        page = csrf_client.get(self.url)
        csrf_token = page.cookies["csrftoken"].value

        response = csrf_client.post(
            self.url,
            {
                "kind": GapoRelayCredential.Kind.DELIVERY,
                "confirmation": "ROTATE",
                "current_password": "correct-password",
                "csrfmiddlewaretoken": csrf_token,
            },
            HTTP_ORIGIN="http://testserver",
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(
            GapoRelayCredential.objects.filter(
                kind=GapoRelayCredential.Kind.DELIVERY
            ).exists()
        )
