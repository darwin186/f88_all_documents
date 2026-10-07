import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from app_document_campaigns.models import MediaArchiveJob
from app_document_campaigns.tasks import process_media_archive
from app_documents.models import UserProfile


class _SuccessfulStorage:
    enabled = True

    def __init__(self):
        self.uploads = []

    def archive(self, stream, *, filename, folder, requested, **kwargs):
        self.uploads.append((filename, folder, stream.read()))
        return SimpleNamespace(
            stored=True,
            reason="",
            web_url=f"https://sharepoint.example/{filename}",
            item_id=f"item-{filename}",
        )

    def ensure_folder(self, folder, **kwargs):
        return SimpleNamespace(stored=True, web_url="https://sharepoint.example/folder", item_id="folder-id")


class MediaStorageFlowTests(TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.media_root = Path(self.temp_dir.name)
        self.folder = self.media_root / "app_documents_campaigns" / "book_loi" / "BOOK-10" / "final"
        self.folder.mkdir(parents=True)
        (self.folder / "book.xlsx").write_bytes(b"xlsx-data")
        self.admin = get_user_model().objects.create_user(
            username="archive-admin",
            password="test-password",
            is_superuser=True,
            is_staff=True,
        )
        UserProfile.objects.create(user=self.admin, department="Vận hành")
        self.viewer = get_user_model().objects.create_user(username="archive-viewer", password="test-password")
        self.settings_override = override_settings(
            MEDIA_ROOT=self.media_root,
            MICROSOFT_GRAPH_STORAGE_ENABLED=True,
            MICROSOFT_GRAPH_STORAGE_MEDIA_PREFIX="app_documents_campaigns",
            MICROSOFT_GRAPH_STORAGE_MAX_FILES_PER_JOB=100,
        )
        self.settings_override.enable()

    def tearDown(self):
        self.settings_override.disable()
        self.temp_dir.cleanup()

    def test_admin_can_browse_media_and_queue_one_file(self):
        self.client.force_login(self.admin)
        browser_url = reverse("media_storage_browser")
        self.assertEqual(browser_url, "/storage/")
        home = self.client.get(reverse("home"))
        self.assertEqual(home.status_code, 200)
        self.assertContains(home, "Lưu trữ")
        self.assertContains(home, 'href="/storage/"')
        page = self.client.get(browser_url, {"path": "app_documents_campaigns/book_loi/BOOK-10/final"})

        self.assertEqual(page.status_code, 200)
        self.assertContains(page, "book.xlsx")
        preview = self.client.get(
            reverse("media_file_preview"),
            {"path": "app_documents_campaigns/book_loi/BOOK-10/final/book.xlsx"},
        )
        self.assertEqual(preview.status_code, 200)
        self.assertEqual(b"".join(preview.streaming_content), b"xlsx-data")
        with patch("app_document_campaigns.storage_views.enqueue_archive_job", side_effect=lambda job: job):
            response = self.client.post(
                reverse("queue_media_archive"),
                {
                    "source_path": "app_documents_campaigns/book_loi/BOOK-10/final/book.xlsx",
                    "return_path": "app_documents_campaigns/book_loi/BOOK-10/final",
                },
            )

        self.assertEqual(response.status_code, 302)
        job = MediaArchiveJob.objects.get()
        self.assertEqual(job.source_kind, MediaArchiveJob.SourceKind.FILE)
        self.assertEqual(job.requested_by, self.admin)

    def test_non_admin_cannot_open_media_storage(self):
        self.client.force_login(self.viewer)

        response = self.client.get(reverse("media_storage_browser"))

        self.assertEqual(response.status_code, 403)

    def test_archive_task_uploads_file_to_matching_sharepoint_tree(self):
        job = MediaArchiveJob.objects.create(
            source_path="app_documents_campaigns/book_loi/BOOK-10/final/book.xlsx",
            source_kind=MediaArchiveJob.SourceKind.FILE,
            requested_by=self.admin,
        )
        storage = _SuccessfulStorage()

        with patch(
            "app_document_campaigns.services.microsoft_graph_storage.MicrosoftGraphArchiveStorage",
            return_value=storage,
        ):
            result = process_media_archive(job.pk)

        job.refresh_from_db()
        self.assertEqual(result["status"], MediaArchiveJob.Status.SUCCEEDED)
        self.assertEqual(job.status, MediaArchiveJob.Status.SUCCEEDED)
        self.assertEqual(job.archived_files, 1)
        self.assertEqual(
            storage.uploads,
            [("book.xlsx", "app_documents_campaigns/book_loi/BOOK-10/final", b"xlsx-data")],
        )
