import json
from datetime import date

from django.contrib.auth.models import Group, User
from django.test import Client, TestCase
from django.urls import reverse

from app_documents.models import (
    DocumentsDetail,
    Folder,
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
    UserProfile,
)


class ReceivingPackageUnassignTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        checker_group = Group.objects.create(name="checker")
        cls.user = User.objects.create_user(
            username="receiving_checker",
            password="test",
        )
        cls.user.groups.add(checker_group)
        UserProfile.objects.create(user=cls.user, department="Vận hành")
        cls.manager = Manager.objects.create(
            manager_code="M-UNASSIGN",
            qlkv_code="A",
            qlkv_name="A",
            qlv_code="B",
            qlv_name="B",
        )
        cls.region = Region.objects.create(
            region_code="R-UNASSIGN",
            region_name="Vùng test",
        )
        cls.shop = Shop.objects.create(
            shop_code=9901,
            shop_name="PGD test gỡ thùng",
            manager_id=cls.manager,
            region_id=cls.region,
        )
        cls.folder_type = FolderType.objects.create(
            folder_type_code="U01",
            folder_type_name="Quyển test gỡ thùng",
            package_type="VH",
            created_by=cls.user,
        )
        cls.not_received = FolderStatus.objects.create(
            folder_status_code="N01",
            folder_status_name="Chưa nhận test",
            created_by=cls.user,
            is_not_received_yet=True,
        )
        cls.received = FolderStatus.objects.create(
            folder_status_code="R01",
            folder_status_name="Đã nhận test",
            created_by=cls.user,
            is_received=True,
        )

    def setUp(self):
        self.client = Client()
        self.client.force_login(self.user)
        self.package = Package.objects.create(
            package_code="VH-260728-TEST",
            package_type=self.folder_type,
            created_by=self.user,
        )
        self.folder = Folder.objects.create(
            folder_code="FOLDER-UNASSIGN-001",
            shop_id=self.shop,
            folder_type_id=self.folder_type,
            folder_status_id=self.received,
            manager_id=self.manager,
            folder_created_date=date(2026, 7, 28),
            package_id=self.package,
            lastest_received_by=self.user,
        )
        self.document = DocumentsDetail.objects.create(
            documents_code="DOCUMENT-UNASSIGN-001",
            shop_id=self.shop,
            manager_id=self.manager,
            folder_id=self.folder,
            documents_created_date=date(2026, 7, 28),
            package_id=self.package,
        )
        FoldersTransactionReceiving.objects.create(
            folder_id=self.folder,
            trans_created_by=self.user,
            folder_status_id=self.received,
        )
        PackageFolderHistory.objects.create(
            folder_id=self.folder,
            package_id=self.package,
            trans_created_by=self.user,
        )
        PackageDocumentHistory.objects.create(
            document_id=self.document,
            package_id=self.package,
            trans_created_by=self.user,
        )

    def _clear(self):
        return self.client.post(
            reverse("clear_package", args=[self.folder.pk]),
            data=json.dumps(
                {
                    "folder_id_submit": self.folder.pk,
                    "package_id_submit": self.package.pk,
                }
            ),
            content_type="application/json",
        )

    def test_clear_package_is_atomic_and_logs_folder_and_document(self):
        response = self._clear()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["success"])
        self.folder.refresh_from_db()
        self.document.refresh_from_db()
        self.assertIsNone(self.folder.package_id)
        self.assertIsNone(self.document.package_id)
        self.assertEqual(self.folder.folder_status_id, self.not_received)
        self.assertIsNone(self.folder.lastest_received_date)
        self.assertIsNone(self.folder.lastest_received_by)
        folder_log = PackageFolderHistory.objects.get(
            folder_id=self.folder,
            action=PackageHistoryAction.UNASSIGNED,
        )
        document_log = PackageDocumentHistory.objects.get(
            document_id=self.document,
            action=PackageHistoryAction.UNASSIGNED,
        )
        self.assertEqual(folder_log.package_id, self.package)
        self.assertEqual(folder_log.trans_created_by, self.user)
        self.assertEqual(document_log.package_id, self.package)
        self.assertEqual(document_log.trans_created_by, self.user)
        self.assertTrue(
            FoldersTransactionReceiving.objects.filter(
                folder_id=self.folder,
                folder_status_id=self.not_received,
                trans_created_by=self.user,
            ).exists()
        )

        history_response = self.client.get(
            reverse("fetch_history_receiving_v2", args=[self.folder.pk]),
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(history_response.status_code, 200)
        self.assertEqual(
            history_response.json()["package_history"][0]["action"],
            PackageHistoryAction.UNASSIGNED,
        )

    def test_missing_not_received_configuration_rolls_back_every_change(self):
        self.not_received.is_valid = False
        self.not_received.save(update_fields=["is_valid"])

        response = self._clear()

        self.assertEqual(response.status_code, 409)
        self.folder.refresh_from_db()
        self.document.refresh_from_db()
        self.assertEqual(self.folder.package_id, self.package)
        self.assertEqual(self.folder.folder_status_id, self.received)
        self.assertEqual(self.document.package_id, self.package)
        self.assertFalse(
            PackageFolderHistory.objects.filter(
                folder_id=self.folder,
                action=PackageHistoryAction.UNASSIGNED,
            ).exists()
        )
        self.assertFalse(
            PackageDocumentHistory.objects.filter(
                document_id=self.document,
                action=PackageHistoryAction.UNASSIGNED,
            ).exists()
        )
