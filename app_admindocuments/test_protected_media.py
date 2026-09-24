from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.contrib.auth.models import Group, User
from django.test import TestCase, override_settings
from django.urls import reverse


class ProtectedAdminDocumentMediaTests(TestCase):
    def setUp(self):
        admin_group = Group.objects.create(name="administrative staff")
        self.allowed_user = User.objects.create_user(
            username="admin_docs_media",
            password="test",
        )
        self.allowed_user.groups.add(admin_group)
        self.other_user = User.objects.create_user(
            username="other_media_user",
            password="test",
        )
        self.relative_path = "92/2026/09/a3adc481_Tóm_tắt_khóa_học.pdf"
        self.url = reverse(
            "protected_admindocument_file",
            kwargs={"relative_path": self.relative_path},
        )

    def test_anonymous_user_is_redirected_to_login(self):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 302)
        self.assertIn("/accounts/login/", response["Location"])

    @patch("app_admindocuments.media_views._file_is_registered", return_value=True)
    def test_authorized_user_can_stream_registered_file(self, _mock_registered):
        with TemporaryDirectory() as media_root:
            file_path = Path(media_root, "admindocuments", "files", self.relative_path)
            file_path.parent.mkdir(parents=True)
            file_path.write_bytes(b"pdf-content")
            self.client.force_login(self.allowed_user)

            with override_settings(MEDIA_ROOT=media_root):
                response = self.client.get(self.url)

            self.assertEqual(response.status_code, 200)
            self.assertEqual(b"".join(response.streaming_content), b"pdf-content")
            self.assertEqual(response["Content-Type"], "application/pdf")
            self.assertEqual(response["Cache-Control"], "private, no-store")

    @patch("app_admindocuments.media_views._file_is_registered", return_value=True)
    def test_authenticated_user_without_module_access_gets_404(self, _mock_registered):
        self.client.force_login(self.other_user)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 404)

    @patch("app_admindocuments.media_views._file_is_registered", return_value=False)
    def test_unregistered_file_is_not_served(self, _mock_registered):
        self.client.force_login(self.allowed_user)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 404)
