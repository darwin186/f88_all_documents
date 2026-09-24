import json
from datetime import date

from django.contrib.auth.models import Group, User
from django.test import Client, TestCase
from django.urls import reverse

from app_documents.models import (
    DocumentsDetail,
    Folder,
    FolderType,
    Manager,
    Package,
    PackageDocumentHistory,
    PackageFolderHistory,
    PackageHistoryAction,
    PackageTransfer,
    Region,
    Shop,
    UserProfile,
)


class PackageTransferTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        admin_group = Group.objects.create(name="admin")
        cls.user = User.objects.create_user(username="transfer_admin", password="test")
        cls.user.groups.add(admin_group)
        UserProfile.objects.create(user=cls.user, department="Vận hành")
        cls.region = Region.objects.create(region_code="TR", region_name="Transfer Region")
        cls.manager = Manager.objects.create(
            manager_code="TRANSFER-MANAGER",
            qlkv_code="KV01",
            qlkv_name="QLKV Test",
            qlv_code="V01",
            qlv_name="QLV Test",
        )
        cls.shop = Shop.objects.create(
            shop_code=9898,
            shop_name="PGD Transfer Test",
            manager_id=cls.manager,
            region_id=cls.region,
        )
        cls.folder_type = FolderType.objects.create(
            folder_type_code="TRF",
            folder_type_name="Quyển chuyển thùng",
            package_type="TRF",
            created_by=cls.user,
        )

    def setUp(self):
        self.client = Client()
        self.client.force_login(self.user)
        self.source = Package.objects.create(
            package_code="TRF-260923-A01",
            package_type=self.folder_type,
            region_id=self.region,
            created_by=self.user,
        )
        self.target = Package.objects.create(
            package_code="TRF-260923-A02",
            package_type=self.folder_type,
            region_id=self.region,
            created_by=self.user,
        )
        self.folder = Folder.objects.create(
            folder_code="TRANSFER-FOLDER-01",
            shop_id=self.shop,
            folder_type_id=self.folder_type,
            manager_id=self.manager,
            folder_created_date=date(2026, 9, 1),
            package_id=self.source,
        )
        self.document = DocumentsDetail.objects.create(
            documents_code="TRANSFER-DOCUMENT-01",
            shop_id=self.shop,
            manager_id=self.manager,
            folder_id=self.folder,
            documents_created_date=date(2026, 9, 1),
            package_id=self.source,
        )

    def _post(self, confirm):
        return self.client.post(
            reverse("api_package_transfer", args=[self.source.pk]),
            data=json.dumps(
                {
                    "target_package_code": self.target.package_code,
                    "reason": "Thùng nguồn bị hỏng",
                    "confirm": confirm,
                }
            ),
            content_type="application/json",
        )

    def test_preview_does_not_change_data(self):
        response = self._post(False)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["eligible"])
        self.assertEqual(response.json()["folder_count"], 1)
        self.assertEqual(response.json()["document_count"], 1)
        self.folder.refresh_from_db()
        self.assertEqual(self.folder.package_id_id, self.source.pk)

    def test_confirm_moves_all_content_and_writes_audit_history(self):
        response = self._post(True)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["success"])
        self.folder.refresh_from_db()
        self.document.refresh_from_db()
        self.source.refresh_from_db()
        self.assertEqual(self.folder.package_id_id, self.target.pk)
        self.assertEqual(self.document.package_id_id, self.target.pk)
        self.assertEqual(self.source.replaced_by_id, self.target.pk)
        transfer = PackageTransfer.objects.get(source_package=self.source)
        self.assertEqual(transfer.folder_count, 1)
        self.assertEqual(transfer.document_count, 1)
        self.assertEqual(
            set(
                PackageFolderHistory.objects.filter(transfer=transfer).values_list(
                    "action", flat=True
                )
            ),
            {
                PackageHistoryAction.TRANSFERRED_OUT,
                PackageHistoryAction.TRANSFERRED_IN,
            },
        )
        self.assertEqual(
            set(
                PackageDocumentHistory.objects.filter(transfer=transfer).values_list(
                    "action", flat=True
                )
            ),
            {
                PackageHistoryAction.TRANSFERRED_OUT,
                PackageHistoryAction.TRANSFERRED_IN,
            },
        )

    def test_target_must_be_empty(self):
        Folder.objects.create(
            folder_code="TRANSFER-FOLDER-TARGET",
            shop_id=self.shop,
            folder_type_id=self.folder_type,
            manager_id=self.manager,
            folder_created_date=date(2026, 9, 2),
            package_id=self.target,
        )

        response = self._post(False)

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()["eligible"])
        self.assertIn("Thùng thay thế phải là thùng trống.", response.json()["errors"])
