from datetime import date
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from .models import (
    AdmAdministrativeDocument, AdmCompany, AdmContentType, AdmDepartment,
    AdmDocumentStatus, AdmDocumentType, AdmSignerRole,
)


class DocumentEditPopupTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_superuser("edit-admin", "edit@example.com", "test")
        cls.company = AdmCompany.objects.create(code="F88", name="F88")
        cls.department = AdmDepartment.objects.create(code="HC", name="Hành chính", company=cls.company)
        cls.content_type = AdmContentType.objects.create(code="NEW", name="Mới")
        cls.doc_type = AdmDocumentType.objects.create(code="QD", name="Quyết định")
        cls.signer = AdmSignerRole.objects.create(code="GD", title="Giám đốc")
        cls.status = AdmDocumentStatus.objects.create(code="REVIEW", name="Chờ duyệt")
        cls.doc = AdmAdministrativeDocument.objects.create(
            title="Văn bản gốc", created_by=cls.user, status=cls.status, doc_type=cls.doc_type,
            content_type=cls.content_type, issuing_company=cls.company, issuing_department=cls.department,
            signer_role=cls.signer, running_number=101, number_year=2025, issue_date=date(2025, 4, 1),
        )

    def setUp(self):
        self.client.force_login(self.user)
        self.detail_url = reverse("admindocuments:admindocuments_detail", args=[self.doc.pk])
        self.update_url = reverse("admindocuments:admindocuments_update", args=[self.doc.pk])
        self.list_url = reverse("admindocuments:admindocuments_list")
        self.data = {"title": "Nội dung đã sửa", "content_type": self.content_type.pk,
                     "signer_role": self.signer.pk, "issuing_department": self.department.pk,
                     "status": self.status.pk, "issue_date": "15/04/2025", "note": "Ghi chú mới"}

    def post(self, data=None):
        return self.client.post(self.update_url, self.data if data is None else data,
                                HTTP_X_REQUESTED_WITH="XMLHttpRequest")

    def test_detail_link_routes_to_popup_on_list_even_for_older_documents(self):
        response = self.client.get(self.detail_url)
        self.assertRedirects(response, f"{self.list_url}?edit={self.doc.pk}")
        response = self.client.get(self.list_url, {"edit": self.doc.pk})
        self.assertContains(response, "data-edit-autoopen")
        self.assertContains(response, 'id="document-edit-dialog"')

    def test_fragment_preserves_status_dates_and_locked_numbering_fields(self):
        response = self.client.get(self.detail_url, {"edit": 1})
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "<html")
        self.assertContains(response, 'value="01/04/2025"')
        self.assertEqual(response.context["form"]["status"].value(), self.status.pk)
        self.assertTrue(response.context["form"].fields["doc_type"].disabled)
        self.assertTrue(response.context["form"].fields["issuing_company"].disabled)

    def test_ajax_save_updates_existing_document_without_changing_number(self):
        number = self.doc.document_number_full
        response = self.post({**self.data, "doc_type": 999999, "issuing_company": 999999})
        self.assertEqual(response.json(), {"ok": True, "document_id": self.doc.pk})
        self.doc.refresh_from_db()
        self.assertEqual(self.doc.title, self.data["title"])
        self.assertEqual(self.doc.issue_date, date(2025, 4, 15))
        self.assertEqual(self.doc.updated_by, self.user)
        self.assertEqual((self.doc.document_number_full, self.doc.running_number, self.doc.number_year), (number, 101, 2025))
        self.assertEqual(AdmAdministrativeDocument.objects.count(), 1)

    def test_validation_stays_in_popup_and_does_not_write(self):
        response = self.post({**self.data, "title": "", "issue_date": "31/02/2025"})
        self.assertEqual(response.status_code, 422)
        self.assertContains(response, self.data["note"], status_code=422)
        self.assertIn("title", response.context["form"].errors)
        self.assertIn("issue_date", response.context["form"].errors)
        self.doc.refresh_from_db()
        self.assertEqual((self.doc.title, self.doc.issue_date), ("Văn bản gốc", date(2025, 4, 1)))

    def test_department_from_another_company_is_rejected(self):
        company = AdmCompany.objects.create(code="OTHER", name="Other")
        department = AdmDepartment.objects.create(code="OTHER", name="Other", company=company)
        response = self.post({**self.data, "issuing_department": department.pk})
        self.assertEqual(response.status_code, 422)
        self.assertIn("issuing_department", response.context["form"].errors)

    @patch("app_admindocuments.views._create_attachment_version")
    def test_new_link_uses_existing_attachment_version_service(self, create_attachment):
        self.assertEqual(self.post({**self.data, "attachment_link": "https://example.com/v2"}).status_code, 200)
        create_attachment.assert_called_once()
        self.assertEqual(create_attachment.call_args.kwargs["link"], "https://example.com/v2")
        self.assertEqual(create_attachment.call_args.kwargs["document"].pk, self.doc.pk)

    @patch("app_admindocuments.views._create_attachment_version", side_effect=ValueError("Upload failed"))
    def test_attachment_failure_rolls_back_field_changes(self, create_attachment):
        with self.assertRaises(ValueError):
            self.post({**self.data, "attachment_link": "https://example.com/v2"})
        self.doc.refresh_from_db()
        self.assertEqual(self.doc.title, "Văn bản gốc")

    def test_unauthorized_users_cannot_read_or_save_popup(self):
        user = User.objects.create_user("edit-outsider")
        self.client.force_login(user)
        self.assertEqual(self.client.get(self.detail_url, {"edit": 1}).status_code, 403)
        self.assertEqual(self.post().status_code, 403)

    def test_deleted_document_returns_actionable_not_found_response(self):
        url = reverse("admindocuments:admindocuments_detail", args=[999999])
        self.assertEqual(self.client.get(url, {"edit": 1}).status_code, 404)

    def test_invalid_popup_id_does_not_break_list(self):
        response = self.client.get(self.list_url, {"edit": "invalid"})
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "data-edit-autoopen")

    def live_post(self, field, value):
        return self.client.post(reverse("admindocuments:admindocuments_update_field", args=[self.doc.pk]),
                                {"field": field, "value": value}, HTTP_X_REQUESTED_WITH="XMLHttpRequest")

    def test_live_save_updates_one_field_and_preserves_number_and_other_values(self):
        number = self.doc.document_number_full
        response = self.live_post("title", "Sửa trực tiếp")
        self.assertEqual(response.json()["value"], "Sửa trực tiếp")
        self.live_post("note", "Ghi chú tiếp theo")
        self.doc.refresh_from_db()
        self.assertEqual((self.doc.title, self.doc.note), ("Sửa trực tiếp", "Ghi chú tiếp theo"))
        self.assertEqual(self.doc.document_number_full, number)
        self.assertEqual(self.doc.status_id, self.status.pk)
        self.assertEqual(self.doc.updated_by, self.user)

    def test_live_invalid_value_is_rejected_without_writing(self):
        response = self.live_post("issue_date", "31/02/2026")
        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.json()["ok"])
        self.doc.refresh_from_db()
        self.assertEqual(self.doc.issue_date, date(2025, 4, 1))

    def test_live_cannot_change_numbering_fields(self):
        for field in ["running_number", "number_year", "doc_type", "issuing_company"]:
            self.assertEqual(self.live_post(field, 9999).status_code, 400)

    def test_live_date_returns_canonical_display_and_can_be_cleared(self):
        response = self.live_post("effective_date", "2026-10-16")
        self.assertEqual(response.json()["value"], "16/10/2026")
        self.assertEqual(self.live_post("effective_date", "").json()["value"], "")
        self.doc.refresh_from_db()
        self.assertIsNone(self.doc.effective_date)

    def test_live_status_uses_configured_colors(self):
        status = AdmDocumentStatus.objects.create(code="READY", name="Sẵn sàng", badge_text_color="#8123AB", badge_bg_color="#FFF1DA")
        response = self.live_post("status", status.pk)
        self.assertEqual(response.json()["status"]["text_color"], "#8123AB")
        self.assertEqual(response.json()["status"]["bg_color"], "#FFF1DA")

    def test_live_reference_updates_related_values_and_prevents_self_reference(self):
        fields = {"doc_type": self.doc_type, "issuing_company": self.company, "issuing_department": self.department,
                  "content_type": self.content_type, "signer_role": self.signer, "status": self.status, "created_by": self.user}
        reference = AdmAdministrativeDocument.objects.create(**fields, title="Văn bản tham chiếu", number_year=2025, running_number=102)
        response = self.live_post("reference_document", reference.pk)
        self.assertEqual(response.json()["related_values"], {"reference_number": reference.document_number_full, "is_reference_document": True})
        self.assertEqual(self.live_post("reference_document", self.doc.pk).status_code, 400)

    def test_history_tab_contains_live_field_changes_and_actor(self):
        self.live_post("title", "Tên sau khi chỉnh sửa trực tiếp")
        response = self.client.get(self.detail_url, {"drawer": 1})
        self.assertContains(response, 'data-preview-tab="history"')
        self.assertContains(response, 'data-preview-panel="history"')
        self.assertContains(response, "Tên sau khi chỉnh sửa trực tiếp")
        self.assertContains(response, self.user.username)
        history = response.context["document_history"]
        self.assertEqual(history[0]["fields"], [{"label": "Tên văn bản", "old": "Văn bản gốc", "new": "Tên sau khi chỉnh sửa trực tiếp"}])
        edit = self.client.get(self.detail_url, {"edit": 1})
        self.assertNotContains(edit, "Lịch sử trạng thái")

    def test_live_ticket_and_reference_checkbox_persist(self):
        self.assertTrue(self.live_post("ticket_code", "TICKET-42").json()["ok"])
        self.live_post("is_reference_document", "true")
        self.doc.refresh_from_db()
        self.assertEqual(self.doc.ticket_code, "TICKET-42")
        self.assertTrue(self.doc.is_reference_document)
        self.live_post("is_reference_document", "false")
        self.doc.refresh_from_db()
        self.assertFalse(self.doc.is_reference_document)

    def test_live_attachments_add_and_delete_without_field_overwrites(self):
        self.live_post("title", "Tên đã sửa")
        upload = reverse("admindocuments:admindocuments_attachment_upload", args=[self.doc.pk])
        response = self.client.post(upload, {"attachment_link": "https://example.com/live"}, HTTP_X_REQUESTED_WITH="XMLHttpRequest")
        self.assertEqual(response.json(), {"ok": True})
        attachment = self.doc.attachments.get(link="https://example.com/live")
        delete = reverse("admindocuments:admindocuments_attachment_delete", args=[self.doc.pk, attachment.pk])
        self.assertEqual(self.client.post(delete, HTTP_X_REQUESTED_WITH="XMLHttpRequest").json(), {"ok": True})
        attachment.refresh_from_db(); self.doc.refresh_from_db()
        self.assertTrue(attachment.is_deleted)
        self.assertEqual(self.doc.title, "Tên đã sửa")
