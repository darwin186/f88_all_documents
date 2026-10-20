from django.contrib.auth.models import Group, User
from django.test import TestCase
from django.urls import reverse

from .forms import AdmDocumentStatusForm
from .models import (
    AdmAdministrativeDocument, AdmCompany, AdmContentType, AdmDepartment, AdmDocumentStatus,
    AdmDocumentType, AdmSignerRole,
)


class DocumentStatusColorTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_superuser("status-admin", "admin@example.com", "test")
        cls.status = AdmDocumentStatus.objects.create(code="CUSTOM", name="Chờ kiểm tra")
        company = AdmCompany.objects.create(code="F88", name="F88")
        cls.document = AdmAdministrativeDocument.objects.create(
            title="Văn bản kiểm tra màu", created_by=cls.user, status=cls.status,
            doc_type=AdmDocumentType.objects.create(code="QD", name="Quyết định"),
            content_type=AdmContentType.objects.create(code="NEW", name="Mới"),
            issuing_company=company,
            issuing_department=AdmDepartment.objects.create(code="HC", name="Hành chính", company=company),
            signer_role=AdmSignerRole.objects.create(code="GD", title="Giám đốc"),
        )

    def setUp(self):
        self.client.force_login(self.user)
        self.url = reverse("admindocuments:master_data")
        self.payload = {"form_name": "status_colors", "status_id": self.status.pk,
                        "badge_text_color": "#8123AB", "badge_bg_color": "#FFF1DA"}

    def test_saved_configuration_colors_custom_status_in_grid_and_drawer(self):
        number = self.document.document_number_full
        response = self.client.post(self.url, self.payload)
        self.assertRedirects(response, self.url + "#status")
        self.status.refresh_from_db()
        self.assertEqual(self.status.badge_text_color, "#8123AB")
        self.assertEqual(self.status.updated_by_id, self.user.pk)
        self.document.refresh_from_db()
        self.assertEqual(self.document.document_number_full, number)
        self.assertEqual(self.document.status_id, self.status.pk)
        response = self.client.get(reverse("admindocuments:admindocuments_list"))
        self.assertContains(response, 'color:#8123AB;background-color:#FFF1DA;')
        response = self.client.get(reverse("admindocuments:admindocuments_detail", args=[self.document.pk]), {"drawer": 1})
        self.assertContains(response, 'background-color:#FFF1DA;border-color:#8123AB;color:#8123AB;')

    def test_module_access_without_change_permission_cannot_update_colors(self):
        staff = User.objects.create_user("status-reader")
        staff.groups.add(Group.objects.create(name="administrative staff"))
        self.client.force_login(staff)
        response = self.client.post(self.url, self.payload)
        self.assertEqual(response.status_code, 403)
        self.status.refresh_from_db()
        self.assertEqual(self.status.badge_text_color, "#374151")

    def test_invalid_colors_do_not_overwrite_saved_configuration(self):
        self.payload["badge_text_color"] = "red;background:url(example)"
        response = self.client.post(self.url, self.payload)
        self.assertEqual(response.status_code, 302)
        self.status.refresh_from_db()
        self.assertEqual(self.status.badge_text_color, "#374151")
        self.assertEqual(self.status.badge_bg_color, "#F3F4F6")

    def test_new_status_accepts_configured_palette(self):
        form = AdmDocumentStatusForm({"code": "READY", "name": "Sẵn sàng", "is_active": True,
                                      "badge_text_color": "#00844A", "badge_bg_color": "#FFFFFF"})
        self.assertTrue(form.is_valid(), form.errors)
        status = form.save()
        self.assertEqual((status.badge_text_color, status.badge_bg_color), ("#00844A", "#FFFFFF"))

    def test_bad_status_identifier_returns_validation_error(self):
        self.payload["status_id"] = "invalid"
        self.assertEqual(self.client.post(self.url, self.payload).status_code, 400)

    def test_color_update_cannot_rename_or_recode_existing_status(self):
        self.client.post(self.url, {**self.payload, "code": "OTHER", "name": "Overwrite", "is_active": ""})
        self.status.refresh_from_db()
        self.assertEqual((self.status.code, self.status.name, self.status.is_active), ("CUSTOM", "Chờ kiểm tra", True))

    def test_migration_sets_initial_colors_without_changing_status_names(self):
        import importlib
        from types import SimpleNamespace
        from django.apps import apps
        from django.db import connection

        draft = AdmDocumentStatus.objects.create(code="100", name="Tên trạng thái hiện có")
        migration = importlib.import_module("app_admindocuments.migrations.0038_admdocumentstatus_badge_colors")
        migration.seed_status_colors(apps, SimpleNamespace(connection=connection))
        draft.refresh_from_db()
        self.status.refresh_from_db()
        self.assertEqual((draft.badge_text_color, draft.badge_bg_color), ("#B45309", "#FFFBEB"))
        self.assertEqual(draft.name, "Tên trạng thái hiện có")
        self.assertEqual((self.status.badge_text_color, self.status.badge_bg_color), ("#374151", "#F3F4F6"))
