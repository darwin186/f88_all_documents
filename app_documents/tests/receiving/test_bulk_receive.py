import json
from datetime import date
from unittest.mock import patch

from django.contrib.auth.models import User
from django.db import IntegrityError, connection
from django.test import Client, TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from app_documents.models import (
    DocumentsDetail,
    Folder,
    FolderIssue,
    FolderIssueType,
    FolderStatus,
    FolderType,
    FoldersTransactionReceiving,
    Manager,
    Package,
    PackageDocumentHistory,
    PackageFolderHistory,
    PackageHistoryAction,
    Region,
    Shop,
)


class BulkReceiveConcurrencyTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="bulk_receiver", password="test")
        cls.manager = Manager.objects.create(
            manager_code="M-BULK-RECEIVE",
            qlkv_code="A",
            qlkv_name="A",
            qlv_code="B",
            qlv_name="B",
        )
        cls.region = Region.objects.create(
            region_code="R-BULK",
            region_name="Vùng bulk",
        )
        cls.shop = Shop.objects.create(
            shop_code=9898,
            shop_name="PGD bulk",
            manager_id=cls.manager,
            region_id=cls.region,
        )
        cls.folder_type = FolderType.objects.create(
            folder_type_code="BR1",
            folder_type_name="Quyển bulk",
            package_type="BR",
            created_by=cls.user,
        )
        cls.pending_status = FolderStatus.objects.create(
            folder_status_code="BP1",
            folder_status_name="Chưa nhận bulk",
            created_by=cls.user,
            is_not_received_yet=True,
        )
        cls.received_status = FolderStatus.objects.create(
            folder_status_code="BR1",
            folder_status_name="Đã nhận bulk",
            created_by=cls.user,
            is_received=True,
        )
        cls.issue_type = FolderIssueType.objects.create(
            issue_type_name="Không lỗi bulk",
            is_no_issue=True,
            created_by=cls.user,
        )

    def setUp(self):
        self.client = Client()
        self.client.force_login(self.user)
        self.package = Package.objects.create(
            package_code="BR-260929-01",
            package_type=self.folder_type,
            created_by=self.user,
        )
        self.folders = []
        self.documents = []
        for index in range(2):
            folder = Folder.objects.create(
                folder_code=f"FOLDER-BULK-{index}",
                shop_id=self.shop,
                folder_type_id=self.folder_type,
                folder_status_id=self.pending_status,
                manager_id=self.manager,
                folder_created_date=date(2026, 9, 20 + index),
            )
            document = DocumentsDetail.objects.create(
                documents_code=f"DOCUMENT-BULK-{index}",
                shop_id=self.shop,
                manager_id=self.manager,
                folder_id=folder,
                documents_created_date=date(2026, 9, 20 + index),
            )
            self.folders.append(folder)
            self.documents.append(document)

    def _payload(self):
        return {
            "selectedItems": [f"checkingitem{folder.pk}" for folder in reversed(self.folders)],
            "trueLastestReceiveDate": "2026-09-29 10:00",
            "package_choice": self.package.package_code,
            "folder_status_choice": str(self.received_status.pk),
            "folder_note_choice": "Nhận cùng lúc",
            "issue_type_ids": [self.issue_type.pk],
            "require_issue_types": True,
        }

    def _post(self):
        return self.client.post(
            reverse("bulk_receiving"),
            data=json.dumps(self._payload()),
            content_type="application/json",
        )

    def test_bulk_receive_locks_package_and_folders_and_updates_the_batch(self):
        with CaptureQueriesContext(connection) as queries:
            response = self._post()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["success"])
        if connection.features.has_select_for_update:
            locking_sql = [query["sql"] for query in queries if "FOR UPDATE" in query["sql"].upper()]
            self.assertTrue(any('d_Package' in sql for sql in locking_sql))
            self.assertTrue(any('f_FolderDetail' in sql for sql in locking_sql))

        for folder, document in zip(self.folders, self.documents):
            folder.refresh_from_db()
            document.refresh_from_db()
            self.assertEqual(folder.package_id, self.package)
            self.assertEqual(folder.folder_status_id, self.received_status)
            self.assertEqual(document.package_id, self.package)
            self.assertTrue(
                FolderIssue.objects.filter(folder=folder, issue_type=self.issue_type).exists()
            )
            self.assertTrue(FoldersTransactionReceiving.objects.filter(folder_id=folder).exists())
            self.assertTrue(
                PackageFolderHistory.objects.filter(
                    folder_id=folder,
                    action=PackageHistoryAction.ASSIGNED,
                ).exists()
            )
            self.assertTrue(
                PackageDocumentHistory.objects.filter(
                    document_id=document,
                    action=PackageHistoryAction.ASSIGNED,
                ).exists()
            )

    def test_database_supplies_assigned_action_for_an_old_web_pod_insert(self):
        with connection.cursor() as cursor:
            cursor.execute(
                'INSERT INTO "f_PackageFolderHistory" '
                '(folder_id, package_id, trans_created_date, trans_created_by) '
                'VALUES (%s, %s, %s, %s) RETURNING trans_id',
                [
                    self.folders[0].pk,
                    self.package.pk,
                    timezone.now(),
                    self.user.pk,
                ],
            )
            history_id = cursor.fetchone()[0]

        history = PackageFolderHistory.objects.get(pk=history_id)
        self.assertEqual(history.action, PackageHistoryAction.ASSIGNED)

    def test_integrity_error_rolls_back_whole_batch_and_is_logged(self):
        with (
            patch(
                "app_documents.views.PackageFolderHistory.objects.create",
                side_effect=IntegrityError("duplicate test row"),
            ),
            patch("app_documents.views.logger.exception") as log_exception,
        ):
            response = self._post()

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["success"], False)
        self.assertIn("sys001", response.json()["error"])
        log_exception.assert_called_once()
        for folder, document in zip(self.folders, self.documents):
            folder.refresh_from_db()
            document.refresh_from_db()
            self.assertEqual(folder.folder_status_id, self.pending_status)
            self.assertIsNone(folder.package_id)
            self.assertIsNone(document.package_id)
        self.assertFalse(FoldersTransactionReceiving.objects.exists())
        self.assertFalse(PackageFolderHistory.objects.exists())
        self.assertFalse(PackageDocumentHistory.objects.exists())
        self.assertFalse(FolderIssue.objects.exists())
