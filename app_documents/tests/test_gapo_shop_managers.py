import json
from io import BytesIO
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.contrib.admin.models import LogEntry
from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase
from django.urls import reverse
from openpyxl import Workbook

from app_admindocuments.models import AdmParcelRecipientImportBatch
from app_documents.gapo_shop_managers import (
    apply_manager_preview, branch_prefix, manager_preview, sign_manager_preview,
)
from app_documents.models import Manager, Shop


class GapoShopManagerTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_superuser("manager-enrichment", "admin@example.com", "test")
        cls.manager = Manager.objects.create(
            manager_code="enrichment", qlkv_code="KV", qlkv_name="Quản lý khu vực",
            qlv_code="V", qlv_name="Quản lý vùng",
        )

    def setUp(self):
        self.batch = AdmParcelRecipientImportBatch.objects.create(
            original_name="gapo.xlsx", file="gapo/test.xlsx", is_current=True,
        )
        self.shop = Shop.objects.create(
            shop_name="AGG24019.Tân Châu", shop_code=24019, manager_id=self.manager,
            shop_manager_name="Người cũ", shop_manager_employee_code="F000001",
            shop_manager_email="old@example.com",
        )
        self.person = self.batch.recipients.create(
            row_number=2, department_name="AGG24019.Tân Châu", position_name="Trưởng phòng giao dịch",
            full_name="Đức ĐT", employee_code="F0006289", email="ducdt4@example.com", is_active_member=True,
        )

    def preview_token(self):
        self.batch.refresh_from_db()
        return sign_manager_preview(manager_preview(self.batch), self.user)

    def test_unique_active_manager_preview_then_explicit_apply_and_audit(self):
        self.client.force_login(self.user)
        url = reverse("master_data_gapo_directory")
        response = self.client.get(url, {"manager_q": "AGG24019"})
        self.assertContains(response, "Áp dụng 1 dòng khớp duy nhất")
        self.assertContains(response, "old@example.com")
        self.assertContains(response, "ducdt4@example.com")
        self.shop.refresh_from_db()
        self.assertEqual(self.shop.shop_manager_name, "Người cũ")
        self.assertEqual(LogEntry.objects.count(), 0)
        response = self.client.post(url, {"action": "apply_shop_managers", "preview_token": response.context["manager_token"]})
        self.assertRedirects(response, url, fetch_redirect_response=False)
        self.shop.refresh_from_db()
        self.assertEqual(self.shop.shop_manager_employee_code, "F0006289")
        audit = LogEntry.objects.get()
        data = json.loads(audit.change_message)
        self.assertEqual(data["source"], "gapo_shop_manager_enrichment")
        self.assertEqual(data["batch_id"], self.batch.pk)
        self.assertEqual(data["source_row"], 2)
        self.assertEqual(data["before"]["shop_manager_email"], "old@example.com")
        self.assertEqual(data["after"]["shop_manager_email"], "ducdt4@example.com")
        self.assertEqual(audit.user_id, self.user.pk)
        self.assertEqual(manager_preview(self.batch)["counts"]["unchanged"], 1)

    def test_strict_prefix_and_role_normalization(self):
        for value in ["AGG240190.Tân Châu", "AGG24019X", "PGD AGG24019", "24019"]:
            self.assertEqual(branch_prefix(value), "")
        self.assertEqual(branch_prefix(" agg24019.Tân Châu "), "AGG24019")
        self.person.position_name = "  TRƯỞNG   PHÒNG GIAO DỊCH "
        self.person.employee_code = "f0006289"
        self.person.save()
        self.assertEqual(apply_manager_preview(self.preview_token(), self.user), 1)
        self.shop.refresh_from_db()
        self.assertEqual(self.shop.shop_manager_employee_code, "F0006289")

    def test_non_manager_and_inactive_members_never_clear_current_contact(self):
        for changes in [{"position_name": "Phó trưởng phòng giao dịch"}, {"is_active_member": False}]:
            with self.subTest(changes=changes):
                self.batch.recipients.filter(pk=self.person.pk).update(position_name="Trưởng phòng giao dịch", is_active_member=True)
                self.batch.recipients.filter(pk=self.person.pk).update(**changes)
                self.assertEqual(apply_manager_preview(self.preview_token(), self.user), 0)
                self.shop.refresh_from_db()
                self.assertEqual(self.shop.shop_manager_email, "old@example.com")

    def test_ambiguous_people_or_shops_are_blocked(self):
        duplicate = self.batch.recipients.create(
            row_number=3, department_name=self.person.department_name,
            position_name=self.person.position_name, full_name="Người khác", employee_code="F002",
            email="other@example.com",
        )
        self.assertEqual(manager_preview(self.batch)["counts"]["ready"], 0)
        self.assertEqual(apply_manager_preview(self.preview_token(), self.user), 0)
        duplicate.delete()
        Shop.objects.create(shop_name="AGG24019 Trùng mã", manager_id=self.manager)
        self.assertEqual(manager_preview(self.batch)["counts"]["ready"], 0)
        self.assertEqual(apply_manager_preview(self.preview_token(), self.user), 0)

    def test_invalid_or_incomplete_contact_is_blocked(self):
        for field, value in [("email", ""), ("email", "bad-email"), ("employee_code", "123"), ("full_name", " ")]:
            with self.subTest(field=field, value=value):
                original = getattr(self.person, field)
                setattr(self.person, field, value)
                self.person.save()
                self.assertEqual(apply_manager_preview(self.preview_token(), self.user), 0)
                setattr(self.person, field, original)
                self.person.save()
        self.shop.refresh_from_db()
        self.assertEqual(self.shop.shop_manager_email, "old@example.com")

    def test_inactive_or_borrow_only_shop_is_not_updated(self):
        for changes in [{"is_shop_active": False}, {"for_borrow_only": True}]:
            Shop.objects.filter(pk=self.shop.pk).update(is_shop_active=True, for_borrow_only=False)
            Shop.objects.filter(pk=self.shop.pk).update(**changes)
            self.assertEqual(apply_manager_preview(self.preview_token(), self.user), 0)

    def test_orphan_and_malformed_departments_are_reported(self):
        for department in ["HNI12345.Hà Nội", "AGG240190.Không hợp lệ"]:
            self.person.department_name = department
            self.person.save()
            preview = manager_preview(self.batch)
            self.assertEqual(preview["counts"]["ready"], 0)
            self.assertEqual(preview["counts"]["review"], 2)
            self.assertIsNone(preview["rows"][-1]["shop_id"])

    def test_changed_shop_person_or_new_conflicting_candidate_invalidates_preview(self):
        token = self.preview_token()
        Shop.objects.filter(pk=self.shop.pk).update(shop_manager_email="manual@example.com")
        with self.assertRaisesMessage(ValueError, "Dữ liệu đã thay đổi"):
            apply_manager_preview(token, self.user)
        token = self.preview_token()
        self.batch.recipients.filter(pk=self.person.pk).update(email="new@example.com")
        with self.assertRaisesMessage(ValueError, "Dữ liệu đã thay đổi"):
            apply_manager_preview(token, self.user)
        token = self.preview_token()
        self.batch.recipients.create(row_number=3, department_name=self.person.department_name,
                                     position_name=self.person.position_name)
        with self.assertRaisesMessage(ValueError, "Dữ liệu đã thay đổi"):
            apply_manager_preview(token, self.user)
        self.assertEqual(LogEntry.objects.count(), 0)

    def test_changed_source_failed_source_and_reactivated_old_batch_require_new_preview(self):
        token = self.preview_token()
        self.batch.is_current = False
        self.batch.save()
        with self.assertRaisesMessage(ValueError, "không còn hiện hành"):
            apply_manager_preview(token, self.user)
        self.batch.is_current = True
        self.batch.save()
        with self.assertRaisesMessage(ValueError, "Dữ liệu đã thay đổi"):
            apply_manager_preview(token, self.user)
        token = self.preview_token()
        self.batch.has_errors = True
        self.batch.save()
        with self.assertRaisesMessage(ValueError, "có lỗi"):
            apply_manager_preview(token, self.user)

    def test_expired_tampered_and_other_user_preview_rejected(self):
        token = self.preview_token()
        for bad_token in ["", token + "x"]:
            with self.assertRaisesMessage(ValueError, "không hợp lệ"):
                apply_manager_preview(bad_token, self.user)
        other = User.objects.create_superuser("other-super", "other@example.com", "test")
        with self.assertRaisesMessage(ValueError, "người dùng khác"):
            apply_manager_preview(token, other)
        with patch("django.core.signing.time.time", return_value=0):
            expired = self.preview_token()
        with self.assertRaisesMessage(ValueError, "hết hạn"):
            apply_manager_preview(expired, self.user)
        regular = User.objects.create_user("regular")
        with self.assertRaisesMessage(ValueError, "super admin"):
            apply_manager_preview(token, regular)

    def test_audit_failure_rolls_back_contact_changes(self):
        token = self.preview_token()
        with patch.object(LogEntry.objects, "log_action", side_effect=RuntimeError("audit unavailable")):
            with self.assertRaises(RuntimeError):
                apply_manager_preview(token, self.user)
        self.shop.refresh_from_db()
        self.assertEqual(self.shop.shop_manager_email, "old@example.com")

    def test_new_action_requires_csrf_and_invalid_token_is_visible(self):
        self.client.force_login(self.user)
        url = reverse("master_data_gapo_directory")
        response = self.client.post(url, {"action": "apply_shop_managers", "preview_token": "bad"}, follow=True)
        self.assertContains(response, "không hợp lệ")
        protected = Client(enforce_csrf_checks=True)
        protected.force_login(self.user)
        self.assertEqual(protected.post(url, {"action": "apply_shop_managers", "preview_token": self.preview_token()}).status_code, 403)

    def test_search_and_pagination_preserve_query_and_apply_count(self):
        for index in range(30):
            Shop.objects.create(shop_name=f"HNI{index:05d}.Hà Nội", manager_id=self.manager)
        self.client.force_login(self.user)
        url = reverse("master_data_gapo_directory")
        response = self.client.get(url, {"manager_q": "HNI", "manager_page": 2, "q": "AGG24019"})
        self.assertEqual(len(response.context["manager_page"]), 5)
        self.assertContains(response, "manager_q=HNI")
        self.assertContains(response, "q=AGG24019")
        self.assertContains(response, "Áp dụng 1 dòng khớp duy nhất")
        self.assertContains(response, "các trang khác")

    def test_activating_batch_does_not_update_manager(self):
        self.client.force_login(self.user)
        url = reverse("master_data_gapo_directory")
        self.client.post(url, {"action": "activate", "batch_id": self.batch.pk})
        self.shop.refresh_from_db()
        self.assertEqual(self.shop.shop_manager_email, "old@example.com")
        self.assertEqual(LogEntry.objects.count(), 0)

    def test_upload_real_excel_then_preview_and_apply(self):
        workbook = Workbook()
        workbook.active.append(["User ID", "Tên thành viên", "Phòng ban đầy đủ", "Mã nhân viên", "Email", "Trạng thái", "Chức vụ"])
        workbook.active.append(["1234", "Trưởng PGD mới", "F88 || AGG24019.Tân Châu", "F1234", "new@example.com", "Đang hoạt động", "Trưởng phòng giao dịch"])
        stream = BytesIO()
        workbook.save(stream)
        self.client.force_login(self.user)
        url = reverse("master_data_gapo_directory")
        with TemporaryDirectory() as media_root, self.settings(MEDIA_ROOT=media_root):
            response = self.client.post(url, {"action": "upload", "file": SimpleUploadedFile("new-gapo.xlsx", stream.getvalue())}, follow=True)
            self.assertContains(response, "Áp dụng 1 dòng khớp duy nhất")
            self.shop.refresh_from_db()
            self.assertEqual(self.shop.shop_manager_email, "old@example.com")
            response = self.client.post(url, {"action": "apply_shop_managers", "preview_token": response.context["manager_token"]}, follow=True)
            self.assertContains(response, "Đã cập nhật Trưởng PGD cho 1 Shop")
            self.shop.refresh_from_db()
            self.assertEqual(self.shop.shop_manager_email, "new@example.com")

    def test_failed_reimport_preserves_previous_snapshot(self):
        from app_admindocuments.models import AdmParcelRecipientCatalog
        from app_admindocuments.views import _import_parcel_recipient_batch

        parsed = {"sheet_name": "Sheet", "total_rows": 1, "summary": {}, "rows": [{"row_number": 2, "is_active_member": True}]}
        with patch("app_admindocuments.views._parse_parcel_recipient_workbook", return_value=parsed):
            with patch.object(AdmParcelRecipientCatalog.objects, "bulk_create", side_effect=RuntimeError("failed insert")):
                with self.assertRaises(RuntimeError):
                    _import_parcel_recipient_batch(self.batch)
        self.assertTrue(self.batch.recipients.filter(pk=self.person.pk).exists())
        self.batch.refresh_from_db()
        self.assertEqual(self.batch.sheet_name, "")
        self.assertTrue(self.batch.is_current)
