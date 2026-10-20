import importlib
import uuid
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from datetime import date
from types import SimpleNamespace
from unittest.mock import patch

from django.apps import apps
from django.contrib.auth.models import User
from django.db import IntegrityError, connection, transaction, close_old_connections
from django.test import TestCase, TransactionTestCase, skipUnlessDBFeature
from django.urls import reverse

from .models import (
    AdmAdministrativeDocument, AdmCompany, AdmContentType, AdmDepartment,
    AdmDocumentCounter, AdmDocumentStatus, AdmDocumentType, AdmSignerRole,
)
from .services import allocate_running_number, create_split_document, next_split_suffix


class NumberSplittingTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_superuser(username="split-test", password="test", email="test@example.com")
        cls.company = AdmCompany.objects.create(code="SPL", name="Split company")
        cls.doc_type = AdmDocumentType.objects.create(code="SPL", name="Split type")
        cls.content_type = AdmContentType.objects.create(code="SPL", name="Split content")
        cls.signer = AdmSignerRole.objects.create(code="GD", title="Director")
        cls.other_signer = AdmSignerRole.objects.create(code="PGD", title="Deputy")
        cls.department = AdmDepartment.objects.create(code="HR", name="HR", company=cls.company)
        cls.other_department = AdmDepartment.objects.create(code="IT", name="IT", company=cls.company)
        cls.status = AdmDocumentStatus.objects.filter(code=AdmDocumentStatus.CODE_DRAFT).first()
        if not cls.status:
            cls.status = AdmDocumentStatus.objects.create(code=AdmDocumentStatus.CODE_DRAFT, name="Draft")
        cls.parent = AdmAdministrativeDocument.objects.create(
            **cls.document_fields("Original"), running_number=100, number_year=2025)
        cls.counter = AdmDocumentCounter.objects.create(
            doc_type=cls.doc_type, company=cls.company, year=2025, next_number=201)

    @classmethod
    def document_fields(cls, title):
        return dict(title=title, doc_type=cls.doc_type, content_type=cls.content_type,
                    issuing_company=cls.company, issuing_department=cls.department,
                    signer_role=cls.signer, status=cls.status, created_by=cls.user)

    def split(self, suffix="A", parent=None, key=None):
        document = AdmAdministrativeDocument(**self.document_fields(f"New {suffix}"))
        document.issuing_department = self.other_department
        document.signer_role = self.other_signer
        document.issue_date = date(2025, 4, 1)
        return create_split_document(parent=parent or self.parent, document=document,
            expected_suffix=suffix, request_key=key or uuid.uuid4(), user=self.user)

    def post_data(self, suffix="A", key=None, title="New backdated document"):
        return dict(content_type=self.content_type.pk, title=title, signer_role=self.other_signer.pk, status=self.status.pk,
                    issuing_department=self.other_department.pk, issue_date="01/04/2025",
                    expected_suffix=suffix, request_key=str(key or uuid.uuid4()))

    def test_independent_backdated_document_and_main_counter(self):
        first, created = self.split()
        second, _ = self.split("B")
        self.assertTrue(created)
        self.assertEqual(first.document_number_full, "100A/2025/SPL-SPL/PGD")
        self.assertEqual(second.number_suffix, "B")
        self.assertEqual(first.issuing_department, self.other_department)
        self.assertEqual(first.issue_date, date(2025, 4, 1))
        self.assertNotEqual(first.created_at.date(), first.issue_date)
        self.parent.refresh_from_db()
        self.assertEqual(self.parent.title, "Original")
        self.assertEqual(self.parent.document_number_full, "100/2025/SPL-SPL/GD")
        self.counter.refresh_from_db()
        self.assertEqual(self.counter.next_number, 201)
        self.assertEqual(allocate_running_number(self.doc_type.pk, self.company.pk, 2025)[0], 201)
        self.assertEqual(first.history.first().changes["new_values"]["split_parent"], self.parent.pk)

    def test_void_root_and_void_branch_do_not_block_allocation(self):
        self.parent.is_void = True
        self.parent.document_number_full += "-VOID"
        self.parent.save()
        first, _ = self.split()
        first.is_void = True
        first.document_number_full += "-VOID"
        first.save()
        self.assertEqual(next_split_suffix(self.parent), "B")
        second, _ = self.split("B")
        self.assertFalse(second.is_void)
        self.assertNotIn("VOID", second.document_number_full)

    def test_reused_root_shares_suffixes(self):
        self.parent.is_void = True
        self.parent.document_number_full += "-VOID"
        self.parent.save()
        reused = AdmAdministrativeDocument.objects.create(
            **self.document_fields("Reused original"), running_number=100, number_year=2025)
        self.split()
        self.assertEqual(self.split("B", parent=reused)[0].number_suffix, "B")
        with transaction.atomic():
            self.counter.next_number = 100
            self.counter.save()
        self.assertEqual(allocate_running_number(self.doc_type.pk, self.company.pk, 2025)[0], 101)

    def test_stale_preview_and_duplicate_request(self):
        key = uuid.uuid4()
        first, _ = self.split(key=key)
        repeated, created = self.split(key=key)
        self.assertEqual(first.pk, repeated.pk)
        self.assertFalse(created)
        with self.assertRaisesMessage(ValueError, "100B"):
            self.split()
        self.counter.refresh_from_db()
        self.assertEqual(self.counter.next_number, 201)

    def test_suffix_and_origin_are_immutable(self):
        first, _ = self.split()
        first.number_suffix = "Z"
        first.number_year = 2030
        first.split_parent = None
        first.running_number = 999
        first.save()
        first.refresh_from_db()
        self.assertEqual((first.number_suffix, first.number_year, first.split_parent_id, first.running_number),
                         ("A", 2025, self.parent.pk, 100))

    def test_database_prevents_duplicate_suffix_with_different_signer(self):
        self.split()
        duplicate = AdmAdministrativeDocument(**self.document_fields("Duplicate"),
            running_number=100, number_year=2025, number_suffix="A", split_parent=self.parent)
        with self.assertRaises(IntegrityError), transaction.atomic():
            duplicate.save()

    def test_z_exhaustion(self):
        AdmAdministrativeDocument.objects.create(**self.document_fields("Last suffix"),
            running_number=100, number_year=2025, number_suffix="Z", split_parent=self.parent)
        with self.assertRaisesMessage(ValueError, "A–Z"):
            next_split_suffix(self.parent)
        self.client.force_login(self.user)
        response = self.client.get(reverse("admindocuments:admindocuments_split", args=[self.parent.pk]))
        self.assertContains(response, "A–Z")
        self.assertNotContains(response, 'id="split-document-form"')

    @patch("app_admindocuments.views._create_attachment_version")
    def test_endpoint_locks_group_fields_and_accepts_backdate(self, attachment):
        self.client.force_login(self.user)
        url = reverse("admindocuments:admindocuments_split", args=[self.parent.pk])
        data = self.post_data()
        data.update(doc_type=999999, issuing_company=999999)
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 302)
        child = AdmAdministrativeDocument.objects.get(number_suffix="A")
        self.assertEqual(child.doc_type, self.doc_type)
        self.assertEqual(child.status, self.status)
        self.assertEqual(child.issuing_department, self.other_department)
        self.assertEqual(child.issue_date, date(2025, 4, 1))
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(AdmAdministrativeDocument.objects.filter(number_suffix="A").count(), 1)
        attachment.assert_called_once()

    @patch("app_admindocuments.views._create_attachment_version")
    def test_split_status_defaults_to_draft_and_accepts_selected_status(self, attachment):
        self.client.force_login(self.user)
        url = reverse("admindocuments:admindocuments_split", args=[self.parent.pk])
        issued, _ = AdmDocumentStatus.objects.get_or_create(code=AdmDocumentStatus.CODE_ISSUED,
                                                          defaults={"name": "Đã ban hành"})
        response = self.client.get(url, HTTP_X_REQUESTED_WITH="XMLHttpRequest")
        field = response.context["form"].fields["status"]
        self.assertFalse(field.disabled)
        self.assertEqual(field.initial, self.status)
        self.assertIn(issued, field.queryset)
        data = self.post_data()
        data["status"] = issued.pk
        response = self.client.post(url, data, HTTP_X_REQUESTED_WITH="XMLHttpRequest")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(AdmAdministrativeDocument.objects.get(number_suffix="A").status, issued)
        self.parent.refresh_from_db()
        self.assertEqual(self.parent.status, self.status)

    def test_split_rejects_unknown_status_and_preserves_form(self):
        self.client.force_login(self.user)
        data = self.post_data()
        data["status"] = 999999
        response = self.client.post(reverse("admindocuments:admindocuments_split", args=[self.parent.pk]),
                                    data, HTTP_X_REQUESTED_WITH="XMLHttpRequest")
        self.assertEqual(response.status_code, 200)
        self.assertIn("status", response.context["form"].errors)
        self.assertEqual(AdmAdministrativeDocument.objects.filter(number_suffix="A").count(), 0)

    @patch("app_admindocuments.views._create_attachment_version")
    def test_ordinary_create_accepts_complete_form(self, attachment):
        self.client.force_login(self.user)
        data = self.post_data(title="Valid ordinary document")
        data.update(doc_type=self.doc_type.pk, issuing_company=self.company.pk)
        response = self.client.post(reverse("admindocuments:admindocuments_create"), data)
        self.assertEqual(response.status_code, 302)
        document = AdmAdministrativeDocument.objects.get(title=data["title"])
        self.assertIn(f"?new={document.pk}", response.url)
        self.assertEqual(document.status, self.status)
        attachment.assert_called_once()

    def test_create_reports_missing_fields_and_logs_only_error_codes(self):
        from django.contrib.messages import get_messages
        self.client.force_login(self.user)
        data = self.post_data()
        data.update(doc_type=self.doc_type.pk, issuing_company=self.company.pk, signer_role="")
        with self.assertLogs("app_admindocuments.views", level="WARNING") as captured:
            response = self.client.post(reverse("admindocuments:admindocuments_create"), data)
        self.assertEqual(response.status_code, 302)
        notifications = [str(message) for message in get_messages(response.wsgi_request)]
        self.assertTrue(any("Người ký: Vui lòng nhập hoặc chọn trường này." in message for message in notifications))
        self.assertIn("'signer_role': ['required']", captured.output[0])
        self.assertNotIn(data["title"], captured.output[0])
        self.assertFalse(AdmAdministrativeDocument.objects.filter(title=data["title"]).exists())

    def test_create_reports_invalid_date_and_duplicate_title(self):
        from django.contrib.messages import get_messages
        self.client.force_login(self.user)
        data = self.post_data()
        data.update(doc_type=self.doc_type.pk, issuing_company=self.company.pk, issue_date="31/02/2026")
        response = self.client.post(reverse("admindocuments:admindocuments_create"), data)
        notifications = [str(message) for message in get_messages(response.wsgi_request)]
        self.assertTrue(any("Ngày ban hành: Ngày không hợp lệ" in message for message in notifications))
        # Duplicate checks use the current numbering year for ordinary creation.
        existing = AdmAdministrativeDocument.objects.create(**self.document_fields("Duplicate ordinary title"))
        data.update(title=existing.title, issue_date="15/10/2026")
        response = self.client.post(reverse("admindocuments:admindocuments_create"), data)
        notifications = [str(message) for message in get_messages(response.wsgi_request)]
        self.assertTrue(any("Tên văn bản:" in message and "Tiêu đề trùng" in message for message in notifications))

    def test_popup_get_returns_form_fragment_with_two_vertical_columns(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("admindocuments:admindocuments_split", args=[self.parent.pk]),
                                   HTTP_X_REQUESTED_WITH="XMLHttpRequest")
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "<html")
        self.assertContains(response, 'id="split-document-form"')
        self.assertContains(response, 'data-select-search')
        self.assertContains(response, 'data-document-attachment')
        self.assertContains(response, 'value="text"')
        self.assertContains(response, 'value="file"')
        self.assertContains(response, 'data-document-datepicker', count=3)
        self.assertContains(response, 'datepicker-format="dd/mm/yyyy"', count=3)
        self.assertNotContains(response, 'type="date"')
        columns = response.context["split_columns"]
        self.assertEqual(len(columns), 2)
        self.assertEqual([field.name for field in columns[0]][:4],
                         ["doc_type", "issuing_company", "issuing_department", "signer_role"])
        self.assertEqual([field.name for field in columns[1]][:3],
                         ["issue_date", "effective_date", "expiry_date"])
        self.assertCountEqual([field.name for column in columns for field in column],
                              [field.name for field in response.context["form"].visible_fields()])

    def test_direct_split_link_opens_popup_without_second_click(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("admindocuments:admindocuments_split", args=[self.parent.pk]))
        self.assertContains(response, 'data-split-autoopen')
        self.assertContains(response, 'id="document-split-dialog"')
        self.assertContains(response, 'document_form_controls.js')

    @patch("app_admindocuments.views._create_attachment_version")
    def test_popup_post_redirect_and_validation(self, attachment):
        self.client.force_login(self.user)
        url = reverse("admindocuments:admindocuments_split", args=[self.parent.pk])
        response = self.client.post(url, self.post_data(title=""), HTTP_X_REQUESTED_WITH="XMLHttpRequest")
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "<html")
        self.assertTrue(response.context["form"].errors)
        data = self.post_data()
        response = self.client.post(url, data, HTTP_X_REQUESTED_WITH="XMLHttpRequest")
        self.assertEqual(response.status_code, 200)
        child = AdmAdministrativeDocument.objects.get(number_suffix="A")
        self.assertEqual(response.json()["redirect_url"],
                         reverse("admindocuments:admindocuments_detail", args=[child.pk]))
        response = self.client.post(url, data, HTTP_X_REQUESTED_WITH="XMLHttpRequest")
        self.assertEqual(response.json()["redirect_url"],
                         reverse("admindocuments:admindocuments_detail", args=[child.pk]))
        attachment.assert_called_once()

    def test_endpoint_stale_preview_preserves_input_and_updates_hidden_suffix(self):
        self.client.force_login(self.user)
        self.split()
        response = self.client.post(reverse("admindocuments:admindocuments_split", args=[self.parent.pk]),
                                    self.post_data(title="Keep my title"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Keep my title")
        self.assertContains(response, 'name="expected_suffix" value="B"')
        self.assertEqual(AdmAdministrativeDocument.objects.exclude(number_suffix="").count(), 1)

    def test_foreign_department_and_missing_backdate_are_rejected(self):
        self.client.force_login(self.user)
        other = AdmCompany.objects.create(code="OTHER", name="Other")
        department = AdmDepartment.objects.create(code="OTHER", name="Other", company=other)
        data = self.post_data()
        data.update(issuing_department=department.pk, issue_date="")
        response = self.client.post(reverse("admindocuments:admindocuments_split", args=[self.parent.pk]), data)
        self.assertEqual(response.status_code, 200)
        self.assertIn("issuing_department", response.context["form"].errors)
        self.assertIn("issue_date", response.context["form"].errors)

    def test_clickable_diagrams_for_void_and_old_number_year(self):
        self.parent.is_void = True
        self.parent.document_number_full += "-VOID"
        self.parent.save()
        self.client.force_login(self.user)
        for partial in ["1", "0"]:
            response = self.client.get(reverse("admindocuments:admindocuments_counters_visual"),
                dict(doc_type=self.doc_type.pk, company=self.company.pk, year=2025, partial=partial))
            self.assertContains(response, reverse("admindocuments:admindocuments_split", args=[self.parent.pk]))
            self.assertEqual(response.context["number_cells"][99]["state"], "void")

    def test_void_branch_at_tail_does_not_rewind_counter(self):
        self.counter.next_number = 101
        self.counter.save()
        child, _ = self.split()
        self.client.force_login(self.user)
        response = self.client.post(reverse("admindocuments:admindocuments_delete", args=[child.pk]))
        self.assertEqual(response.status_code, 302)
        self.counter.refresh_from_db()
        self.assertEqual(self.counter.next_number, 101)
        self.assertEqual(next_split_suffix(self.parent), "B")

    def test_void_root_with_active_branch_is_allowed(self):
        child, _ = self.split()
        self.client.force_login(self.user)
        self.client.post(reverse("admindocuments:admindocuments_delete", args=[self.parent.pk]))
        self.parent.refresh_from_db()
        child.refresh_from_db()
        self.assertTrue(self.parent.is_void)
        self.assertFalse(child.is_void)
        self.assertEqual(self.split("B")[0].number_suffix, "B")

    def test_module_permissions_and_nested_split(self):
        url = reverse("admindocuments:admindocuments_split", args=[self.parent.pk])
        self.assertEqual(self.client.get(url).status_code, 302)
        outsider = User.objects.create_user(username="outsider")
        self.client.force_login(outsider)
        self.assertEqual(self.client.post(url, self.post_data()).status_code, 403)
        child, _ = self.split()
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(reverse("admindocuments:admindocuments_split", args=[child.pk])).status_code, 404)

    def test_backfill_uses_issued_number_year_and_preserves_number(self):
        migration = importlib.import_module("app_admindocuments.migrations.0037_admadministrativedocument_number_suffix_and_more")
        number = "100/2023/SPL-SPL/GD-VOID"
        AdmAdministrativeDocument.objects.filter(pk=self.parent.pk).update(document_number_full=number)
        migration.backfill_number_year(apps, SimpleNamespace(connection=connection))
        self.parent.refresh_from_db()
        self.assertEqual(self.parent.number_year, 2023)
        self.assertEqual(self.parent.document_number_full, number)

    def test_counter_summary_distinguishes_base_and_total_documents(self):
        self.split()
        self.split("B")
        self.client.force_login(self.user)
        response = self.client.get(reverse("admindocuments:admindocuments_counters"))
        row = next(row for row in response.context["counters"] if row["doc_type_id"] == self.doc_type.pk)
        self.assertEqual((row["total"], row["base_total"], row["used_max"]), (3, 1, 100))

    def test_void_root_reuse_is_independent_of_branch_and_counter_preview_200(self):
        self.counter.next_number = 200
        self.counter.save()
        self.parent.is_void = True
        self.parent.document_number_full += "-VOID"
        self.parent.save()
        self.split()
        self.counter.refresh_from_db()
        self.assertEqual(self.counter.next_number, 200)
        self.counter.next_number = 100
        self.counter.save()
        number, conflicts = allocate_running_number(self.doc_type.pk, self.company.pk, 2025)
        self.assertEqual(number, 100)
        self.assertEqual([document.pk for document in conflicts], [self.parent.pk])


class ConcurrentNumberSplittingTests(TransactionTestCase):
    document_fields = NumberSplittingTests.__dict__["document_fields"]

    def setUp(self):
        NumberSplittingTests.setUpTestData.__func__(type(self))

    @skipUnlessDBFeature("has_select_for_update")
    def test_simultaneous_requests_cannot_allocate_same_suffix(self):
        barrier = Barrier(2)
        parent_id, user_id = self.parent.pk, self.user.pk

        def worker():
            close_old_connections()
            try:
                parent = AdmAdministrativeDocument.objects.get(pk=parent_id)
                user = User.objects.get(pk=user_id)
                document = AdmAdministrativeDocument(**self.document_fields(str(uuid.uuid4())))
                barrier.wait(timeout=10)
                try:
                    result, _ = create_split_document(parent=parent, document=document,
                        expected_suffix="A", request_key=uuid.uuid4(), user=user)
                    return result.number_suffix
                except ValueError:
                    return "stale"
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(lambda _: worker(), range(2)))
        self.assertCountEqual(results, ["A", "stale"])
        self.assertEqual(next_split_suffix(self.parent), "B")
        self.counter.refresh_from_db()
        self.assertEqual(self.counter.next_number, 201)
