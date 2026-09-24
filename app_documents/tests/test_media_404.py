from pathlib import Path
from tempfile import TemporaryDirectory

from django.test import RequestFactory, SimpleTestCase, override_settings

from documents.error_handlers import handle_404


class Media404DiagnosticsTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def test_existing_unicode_admindocument_is_reported_in_error_log(self):
        with TemporaryDirectory() as media_root:
            relative_path = "admindocuments/files/686/2026/09/Quyết_định.pdf"
            file_path = Path(media_root, relative_path)
            file_path.parent.mkdir(parents=True)
            file_path.write_bytes(b"pdf")
            request = self.factory.get(f"/media/{relative_path}")

            with override_settings(MEDIA_ROOT=media_root, MEDIA_URL="/media/"):
                with self.assertLogs("media_diagnostics", level="ERROR") as logs:
                    response = handle_404(request, Exception("not found"))

            self.assertEqual(response.status_code, 404)
            self.assertContains(response, "Không tìm thấy file", status_code=404)
            self.assertContains(
                response,
                "Kiểm tra media dùng chung giữa web và worker hoặc chuẩn bị lại file.",
                status_code=404,
            )
            message = "\n".join(logs.output)
            self.assertIn("ADMINDOCUMENT_MEDIA_404", message)
            self.assertIn("exists=True", message)
            self.assertIn("storage_exists=True", message)
            self.assertIn("nfc_exists=True", message)

    def test_missing_admindocument_is_reported_as_missing(self):
        with TemporaryDirectory() as media_root:
            request = self.factory.get(
                "/media/admindocuments/files/686/2026/09/missing.pdf"
            )

            with override_settings(MEDIA_ROOT=media_root, MEDIA_URL="/media/"):
                with self.assertLogs("media_diagnostics", level="ERROR") as logs:
                    response = handle_404(request, Exception("not found"))

            self.assertEqual(response.status_code, 404)
            message = "\n".join(logs.output)
            self.assertIn("ADMINDOCUMENT_MEDIA_404", message)
            self.assertIn("exists=False", message)
            self.assertIn("storage_exists=False", message)
