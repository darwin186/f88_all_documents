from unittest.mock import Mock

from django.test import SimpleTestCase

from app_document_campaigns.services.microsoft_graph_storage import (
    GraphStorageConfig,
    MicrosoftGraphArchiveStorage,
    _configured_root_folder,
)


def _response(status, payload=None):
    response = Mock(status_code=status, headers={})
    response.json.return_value = payload or {}
    return response


def _config(**overrides):
    values = {
        "enabled": True,
        "tenant_id": "tenant-id",
        "client_id": "application-id",
        "client_secret": "secret-value",
        "site_url": "https://tenant.sharepoint.com/sites/operations",
        "root_folder": "DocumentArchive",
        "connect_timeout": 1,
        "read_timeout": 2,
        "max_retries": 0,
    }
    values.update(overrides)
    return GraphStorageConfig(**values)


class MicrosoftGraphArchiveStorageTests(SimpleTestCase):
    def test_destination_folder_is_inferred_from_sharepoint_url(self):
        self.assertEqual(
            _configured_root_folder(
                "https://tenant.sharepoint.com/sites/operations/Shared%20Documents/He_thong_chung_tu",
                "",
            ),
            "He_thong_chung_tu",
        )

    def test_not_requested_is_a_noop_even_without_configuration(self):
        storage = MicrosoftGraphArchiveStorage(_config(enabled=False))

        result = storage.archive(b"content", filename="report.xlsx", requested=False)

        self.assertFalse(result.stored)
        self.assertEqual(result.reason, "not_requested")

    def test_disabled_storage_is_a_safe_noop(self):
        storage = MicrosoftGraphArchiveStorage(_config(enabled=False))

        result = storage.archive(b"content", filename="report.xlsx")

        self.assertFalse(result.stored)
        self.assertEqual(result.reason, "disabled")

    def test_upload_creates_archive_folder_and_returns_graph_metadata(self):
        session = Mock()
        session.post.return_value = _response(
            200, {"access_token": "app-token", "expires_in": 3600}
        )
        session.request.side_effect = [
            _response(200, {"id": "site-id"}),
            _response(200, {"id": "drive-id"}),
            _response(200, {"id": "root-id"}),
            _response(404, {"error": {"code": "itemNotFound", "message": "Not found"}}),
            _response(201, {"id": "archive-folder-id", "folder": {}}),
            _response(200, {"id": "campaigns-folder-id", "folder": {}}),
            _response(200, {"id": "month-folder-id", "folder": {}}),
            _response(
                201,
                {
                    "id": "item-id",
                    "name": "report.xlsx",
                    "size": 7,
                    "webUrl": "https://tenant.sharepoint.com/report.xlsx",
                    "eTag": "etag-1",
                },
            ),
        ]
        storage = MicrosoftGraphArchiveStorage(_config(), session=session)

        result = storage.archive(
            b"content",
            filename="report.xlsx",
            folder="campaigns/2026-10",
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

        self.assertTrue(result.stored)
        self.assertEqual(result.item_id, "item-id")
        self.assertEqual(result.drive_id, "drive-id")
        self.assertEqual(result.path, "DocumentArchive/campaigns/2026-10/report.xlsx")
        self.assertEqual(result.e_tag, "etag-1")
        self.assertEqual(session.post.call_count, 1)
        upload_call = session.request.call_args_list[-1]
        self.assertEqual(upload_call.args[0], "PUT")
        self.assertIn("/report.xlsx:/content", upload_call.args[1])
        self.assertEqual(upload_call.kwargs["data"], b"content")

    def test_filename_cannot_escape_destination_folder(self):
        storage = MicrosoftGraphArchiveStorage(_config())

        with self.assertRaisesRegex(ValueError, "không hợp lệ"):
            storage.archive(b"content", filename="../report.xlsx")
