from django.contrib.auth.models import Group, User
from django.test import TestCase
from django.urls import reverse

from .forms import AdmIncomingDispatchForm
from .models import (
    AdmAdministrativeDocument,
    AdmCompany,
    AdmContentType,
    AdmDepartment,
    AdmDocumentStatus,
    AdmDocumentType,
    AdmIncomingDispatchType,
    AdmIncomingDispatchStatus,
    AdmIncomingGapoGroup,
    AdmIncomingDispatch,
    AdmSignerRole,
)


class AdmAdministrativeDocumentNumberInvariantTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="tester", password="secret")
        cls.doc_type = AdmDocumentType.objects.create(code="QD", name="Quyet dinh")
        cls.content_type = AdmContentType.objects.create(code="NEW", name="New")
        cls.signer_role = AdmSignerRole.objects.create(code="GD", title="Giam doc")
        cls.status = AdmDocumentStatus.objects.create(
            code=AdmDocumentStatus.CODE_DRAFT,
            name="Draft",
        )
        cls.company = AdmCompany.objects.create(code="F88", name="F88")
        cls.department = AdmDepartment.objects.create(
            code="HR",
            name="Nhan su",
            company=cls.company,
        )

    def _create_document(self, title="Van ban goc"):
        return AdmAdministrativeDocument.objects.create(
            doc_type=self.doc_type,
            content_type=self.content_type,
            title=title,
            signer_role=self.signer_role,
            issuing_company=self.company,
            issuing_department=self.department,
            status=self.status,
            created_by=self.user,
        )

    def test_number_and_running_number_stay_immutable_after_normal_update(self):
        doc = self._create_document()
        original_number = doc.document_number_full
        original_running = doc.running_number

        doc.title = "Cap nhat tieu de"
        doc.save()
        doc.refresh_from_db()

        self.assertEqual(doc.document_number_full, original_number)
        self.assertEqual(doc.running_number, original_running)

    def test_direct_tampering_is_reverted_on_save(self):
        doc = self._create_document()
        original_number = doc.document_number_full
        original_running = doc.running_number

        doc.running_number = original_running + 99
        doc.document_number_full = "999/2099/FAKE-FAKE/FAKE"
        doc.save()
        doc.refresh_from_db()

        self.assertEqual(doc.document_number_full, original_number)
        self.assertEqual(doc.running_number, original_running)

    def test_void_transition_can_append_void_suffix(self):
        doc = self._create_document()
        original_number = doc.document_number_full
        original_running = doc.running_number

        doc.is_void = True
        doc.document_number_full = f"{original_number}-VOID"
        doc.save(update_fields=["is_void", "document_number_full", "updated_at"])
        doc.refresh_from_db()

        self.assertTrue(doc.is_void)
        self.assertEqual(doc.document_number_full, f"{original_number}-VOID")
        self.assertEqual(doc.running_number, original_running)

    def test_void_suffix_without_void_flag_is_reverted(self):
        doc = self._create_document()
        original_number = doc.document_number_full

        doc.document_number_full = f"{original_number}-VOID"
        doc.save()
        doc.refresh_from_db()

        self.assertFalse(doc.is_void)
        self.assertEqual(doc.document_number_full, original_number)


class AdmIncomingDispatchTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.company_f88 = AdmCompany.objects.create(code="F88", name="F88")
        cls.company_nnx = AdmCompany.objects.create(code="NNX", name="NNX")
        cls.company_dtf88 = AdmCompany.objects.create(
            code="DTF88",
            name="Dau Tu F88",
        )
        cls.dispatch_type, _ = AdmIncomingDispatchType.objects.update_or_create(
            code="buu_pham_buu_kien",
            defaults={
                "name": "Bưu phẩm/bưu kiện",
                "sort_order": 2,
                "is_active": True,
            },
        )
        cls.dispatch_type_doc, _ = AdmIncomingDispatchType.objects.update_or_create(
            code="cong_van",
            defaults={
                "name": "Công văn đến",
                "sort_order": 1,
                "is_active": True,
            },
        )
        cls.dispatch_status, _ = AdmIncomingDispatchStatus.objects.update_or_create(
            code="pkg_received",
            defaults={
                "name": "Đã tiếp nhận",
                "sort_order": 1,
                "is_active": True,
            },
        )
        cls.dispatch_status_2, _ = AdmIncomingDispatchStatus.objects.update_or_create(
            code="pkg_at_clerical",
            defaults={
                "name": "Đang ở Văn thư",
                "sort_order": 2,
                "is_active": True,
            },
        )
        cls.dispatch_status_3, _ = AdmIncomingDispatchStatus.objects.update_or_create(
            code="pkg_processing",
            defaults={
                "name": "Đang xử lý",
                "sort_order": 3,
                "is_active": True,
            },
        )
        cls.dispatch_status_4, _ = AdmIncomingDispatchStatus.objects.update_or_create(
            code="pkg_archived",
            defaults={
                "name": "Lưu trữ",
                "sort_order": 4,
                "is_active": True,
            },
        )
        cls.dispatch_status_5, _ = AdmIncomingDispatchStatus.objects.update_or_create(
            code="doc_received",
            defaults={
                "name": "Đã tiếp nhận",
                "sort_order": 5,
                "is_active": True,
            },
        )
        cls.dispatch_status_6, _ = AdmIncomingDispatchStatus.objects.update_or_create(
            code="doc_at_clerical",
            defaults={
                "name": "Đang ở Văn thư",
                "sort_order": 6,
                "is_active": True,
            },
        )
        cls.gapo_group = AdmIncomingGapoGroup.objects.create(
            code="HCVT_GROUP",
            name="Nhóm HCVT",
            gapo_group_id="gapo-group-001",
            sort_order=1,
            is_active=True,
        )
        cls.department = AdmDepartment.objects.create(
            code="HCNS",
            name="Hanh chinh nhan su",
            company=cls.company_f88,
        )
        cls.admin_user = User.objects.create_user(username="admin", password="secret")
        cls.vanthu_user = User.objects.create_user(username="vanthu", password="secret")
        cls.viewer_user = User.objects.create_user(username="viewer", password="secret")
        vanthu_group = Group.objects.create(name="cv van thu")
        cls.vanthu_user.groups.add(vanthu_group)

    def test_form_requires_processing_departments(self):
        form = AdmIncomingDispatchForm(
            data={
                "document_number": "CV-001",
                "sending_unit": "UBND",
                "signer_name": "Nguyen Van A",
                "summary": "Noi dung test",
                "incoming_item_type": self.dispatch_type.code,
                "receiving_company": self.company_f88.code,
                "gapo_group": self.gapo_group.code,
            }
        )
        self.assertFalse(form.is_valid())
        self.assertIn("processing_department", form.errors)

    def test_responsible_user_and_received_date_are_immutable(self):
        dispatch = AdmIncomingDispatch.objects.create(
            document_number="CV-002",
            responsible_user=self.vanthu_user,
            sending_unit="So Tu Phap",
            signer_name="Tran Van B",
            summary="Noi dung test",
            incoming_item_type=self.dispatch_type,
            receiving_company=self.company_nnx,
            gapo_group=self.gapo_group,
            status=self.dispatch_status_2,
            created_by=self.vanthu_user,
        )
        original_date = dispatch.received_date

        dispatch.responsible_user = self.admin_user
        dispatch.received_date = original_date.replace(day=max(1, original_date.day - 1))
        dispatch.save()
        dispatch.refresh_from_db()

        self.assertEqual(dispatch.responsible_user_id, self.vanthu_user.id)
        self.assertEqual(dispatch.received_date, original_date)

    def test_viewer_can_view_and_create_dispatch(self):
        self.client.login(username="viewer", password="secret")
        list_url = reverse("admindocuments:incoming_dispatch_list")

        response = self.client.get(list_url)
        self.assertEqual(response.status_code, 200)

        post_response = self.client.post(
            list_url,
            data={
                "document_number": "CV-003",
                "sending_unit": "So Y Te",
                "signer_name": "Le Van C",
                "summary": "Noi dung test",
                "processing_department": self.department.id,
                "incoming_item_type": self.dispatch_type.code,
                "receiving_company": self.company_f88.code,
                "gapo_group": self.gapo_group.code,
            },
        )
        self.assertEqual(post_response.status_code, 302)
        self.assertEqual(AdmIncomingDispatch.objects.count(), 1)
        created = AdmIncomingDispatch.objects.first()
        self.assertEqual(created.status_id, self.dispatch_status.code)

    def test_vanthu_can_create_dispatch(self):
        self.client.login(username="vanthu", password="secret")
        list_url = reverse("admindocuments:incoming_dispatch_list")
        response = self.client.post(
            list_url,
            data={
                "document_number": "CV-004",
                "sending_unit": "So Tai Chinh",
                "signer_name": "Pham Van D",
                "summary": "Noi dung test",
                "processing_department": self.department.id,
                "incoming_item_type": self.dispatch_type.code,
                "receiving_company": self.company_dtf88.code,
                "gapo_group": self.gapo_group.code,
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(AdmIncomingDispatch.objects.count(), 1)
        created = AdmIncomingDispatch.objects.first()
        self.assertIsNotNone(created)
        self.assertEqual(created.responsible_user_id, self.vanthu_user.id)
        self.assertEqual(created.signer_name, "Pham Van D")
        self.assertEqual(created.status_id, self.dispatch_status.code)

    def test_can_create_dispatch_without_document_number(self):
        self.client.login(username="vanthu", password="secret")
        list_url = reverse("admindocuments:incoming_dispatch_list")
        response = self.client.post(
            list_url,
            data={
                "document_number": "",
                "sending_unit": "So GTVT",
                "signer_name": "Le Van E",
                "summary": "Noi dung khong so hieu",
                "processing_department": self.department.id,
                "incoming_item_type": self.dispatch_type.code,
                "receiving_company": self.company_f88.code,
                "gapo_group": self.gapo_group.code,
            },
        )
        self.assertEqual(response.status_code, 302)
        created = AdmIncomingDispatch.objects.latest("id")
        self.assertIsNone(created.document_number)

    def test_change_status_by_select_step_uses_type_specific_flow(self):
        superuser = User.objects.create_superuser(
            username="super_dispatch",
            password="secret",
            email="super_dispatch@example.com",
        )
        dispatch = AdmIncomingDispatch.objects.create(
            document_number="CV-005",
            responsible_user=self.vanthu_user,
            sending_unit="So Cong Thuong",
            signer_name="Test Signer",
            summary="Noi dung test doi trang thai",
            incoming_item_type=self.dispatch_type_doc,
            receiving_company=self.company_f88,
            gapo_group=self.gapo_group,
            status=self.dispatch_status_5,
            created_by=self.vanthu_user,
        )
        dispatch.processing_departments.set([self.department])

        self.client.force_login(superuser)
        url = reverse("admindocuments:incoming_dispatch_change_status", args=[dispatch.id])
        response = self.client.post(url, data={"status": self.dispatch_status_6.code})

        self.assertEqual(response.status_code, 302)
        dispatch.refresh_from_db()
        self.assertEqual(dispatch.status_id, self.dispatch_status_6.code)
