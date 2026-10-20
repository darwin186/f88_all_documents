from django.contrib.auth.models import Group, User
from django.test import TestCase
from django.urls import NoReverseMatch, reverse

from app_documents.models import Region, UserProfile


V2_PAGES = [
    "home",
    "receiving_transaction_v2",
    "checking_transaction_v2",
    "package_list_management",
    "receiving_import_v2",
    "folder_appointment_report_v2",
    "dashboard",
    "document_kpi_v2",
    "document_raw_export",
    "borrow_management_v2",
    "borrow_request_management_v2",
    "ctv_account_management_v2",
    "user_profile_v2",
    "ui_permission_v2",
    "gddb_registration_v2",
    "gddb_dashboard",
    "document_intake_management",
    "document_intake_documentation",
    "master_data",
    "master_data_response_options",
    "master_data_response_guidance",
    "master_data_email_templates",
    "master_data_tokens",
    "master_data_api_docs",
]

V2_EXPORTS = [
    "package_list_export_v2",
    "folder_appointment_export",
    "document_kpi_shop_export",
    "gddb_export",
]

REMOVED_V1_URL_NAMES = [
    "checking_transaction",
    "receiving_transaction",
    "package_management",
    "create_package",
    "additional_management",
    "dashboard_folder_received",
    "historical_folder_view",
    "historical_documents_view",
    "gapo_schedule",
    "gapo_ai_generate",
    "checking_additional_view",
    "fetch_history_receiving",
    "export_productivity_report",
]


class V2PagesSmokeTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        region = Region.objects.create(region_code="R-SMOKE", region_name="Toàn quốc")
        cls.admin = User.objects.create_superuser("v2_smoke_admin", "a@example.com", "test")
        cls.admin.groups.add(Group.objects.get_or_create(name="admin")[0])
        UserProfile.objects.create(user=cls.admin, department="Vận hành", region=region)

    def setUp(self):
        self.client.force_login(self.admin)

    def test_v2_pages_render_without_server_error(self):
        for name in V2_PAGES:
            with self.subTest(page=name):
                response = self.client.get(reverse(name))
                self.assertIn(response.status_code, (200, 302), f"{name} -> {response.status_code}")

    def test_kpi_productivity_tab_renders_without_export_links(self):
        response = self.client.get(reverse("document_kpi_v2"), {"tab": "productivity"})
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "productivity/export")

    def test_v2_exports_do_not_crash(self):
        for name in V2_EXPORTS:
            with self.subTest(export=name):
                response = self.client.get(reverse(name))
                self.assertLess(response.status_code, 500, f"{name} -> {response.status_code}")

    def test_v2_pages_do_not_link_to_removed_v1_routes(self):
        for name in V2_PAGES:
            response = self.client.get(reverse(name))
            if response.status_code != 200 or response.streaming:
                continue
            html = response.content.decode("utf-8", "ignore")
            for old_path in ("/duyet-chung-tu\"", "/nhan-chung-tu\"", "/quan-ly-thung-chung-tu", "/quan-ly-hen-bo-sung"):
                with self.subTest(page=name, path=old_path):
                    self.assertNotIn(old_path, html)

    def test_home_has_no_v1_entry(self):
        html = self.client.get(reverse("home")).content.decode("utf-8", "ignore")
        self.assertIn("Chứng từ bản cứng V2", html)
        self.assertNotIn("Chứng từ bản cứng V1", html)

    def test_v1_routes_are_gone(self):
        for name in REMOVED_V1_URL_NAMES:
            with self.subTest(route=name):
                with self.assertRaises(NoReverseMatch):
                    reverse(name, args=[1]) if name in ("create_package", "checking_additional_view", "fetch_history_receiving") else reverse(name)

    def test_login_pages_still_render_without_navbar(self):
        self.client.logout()
        for name in ("login", "password_reset"):
            with self.subTest(page=name):
                self.assertEqual(self.client.get(reverse(name)).status_code, 200)
