from datetime import timedelta

from django.contrib.auth.models import Group, User
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from .gddb import import_collateral_registrations
from .models import (
    CollateralRegistration,
    CollateralRegistrationStatus,
    UserProfile,
)


class GddbDashboardTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        admin_group = Group.objects.create(name="admin")
        checker_group = Group.objects.create(name="checker")
        cls.admin = User.objects.create_user(username="dashboard_admin", password="test")
        cls.admin.groups.add(admin_group)
        UserProfile.objects.create(user=cls.admin, department="Vận hành")
        cls.checker = User.objects.create_user(username="dashboard_checker", password="test")
        cls.checker.groups.add(checker_group)
        UserProfile.objects.create(user=cls.checker, department="Vận hành")

    def setUp(self):
        now = timezone.now()
        previous_day = now - timedelta(days=1)

        CollateralRegistration.objects.create(
            contract_code="DASH-PENDING",
            gddb_status=CollateralRegistrationStatus.PENDING,
            disbursement_source="F88 Fund",
            asset_type="Ô tô",
        )
        CollateralRegistration.objects.create(
            contract_code="DASH-WAITING",
            gddb_status=CollateralRegistrationStatus.REGISTERED,
            postmini_updated="Chưa cập nhật",
            disbursement_source="CIMB",
            asset_type="Xe máy",
            registered_by=self.admin,
            registered_at=now,
        )
        CollateralRegistration.objects.create(
            contract_code="DASH-NOT-REGISTERED",
            gddb_status=CollateralRegistrationStatus.NOT_REGISTERED,
            disbursement_source=None,
            asset_type=None,
            processing_by=self.admin,
            archived_at=now,
        )
        completed = CollateralRegistration.objects.create(
            contract_code="DASH-COMPLETED",
            gddb_status=CollateralRegistrationStatus.REGISTERED,
            postmini_updated="Đã cập nhật",
            disbursement_source="F88",
            asset_type="Ô tô",
            registered_by=self.admin,
            registered_at=previous_day,
            archived_at=previous_day,
        )
        CollateralRegistration.objects.filter(pk=completed.pk).update(
            created_at=previous_day,
            archived_at=previous_day,
            registered_at=previous_day,
        )

    def test_dashboard_page_and_api_are_admin_only(self):
        admin_client = Client()
        admin_client.force_login(self.admin)
        checker_client = Client()
        checker_client.force_login(self.checker)

        self.assertEqual(admin_client.get(reverse("gddb_dashboard")).status_code, 200)
        self.assertEqual(checker_client.get(reverse("gddb_dashboard")).status_code, 403)
        self.assertEqual(
            checker_client.get(reverse("api_gddb_dashboard")).status_code,
            403,
        )

    def test_dashboard_returns_realtime_cards_and_breakdowns(self):
        client = Client()
        client.force_login(self.admin)
        today = timezone.now().date()
        response = client.get(
            reverse("api_gddb_dashboard"),
            {"period": "month", "month": today.strftime("%Y-%m")},
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["success"])
        self.assertEqual(data["cards"]["month_total"], 4)
        self.assertEqual(data["cards"]["pending"], 1)
        self.assertEqual(data["cards"]["unassigned"], 1)
        self.assertEqual(data["cards"]["waiting_posmini"], 1)

        status = {row["label"]: row["value"] for row in data["status"]}
        self.assertEqual(status["Chưa đăng ký"], 1)
        self.assertEqual(status["Chờ PosMini"], 1)
        self.assertEqual(status["Không đăng ký"], 1)
        self.assertEqual(status["Hoàn tất đăng ký"], 1)

        source = {row["label"]: row["value"] for row in data["source"]}
        self.assertEqual(source["F88"], 2)
        self.assertEqual(source["CIMB"], 1)
        self.assertEqual(source["MB"], 1)

        asset = {row["label"]: row["value"] for row in data["asset"]}
        self.assertEqual(asset["Ô tô"], 2)
        self.assertEqual(asset["Xe máy"], 1)
        self.assertEqual(asset["Chưa xác định"], 1)

        checker = {row["label"]: row["value"] for row in data["checker"]}
        self.assertEqual(checker[self.admin.username], 2)

    def test_dashboard_rejects_ranges_over_one_year(self):
        client = Client()
        client.force_login(self.admin)
        response = client.get(
            reverse("api_gddb_dashboard"),
            {
                "period": "range",
                "date_from": "2025-01-01",
                "date_to": "2026-02-01",
            },
        )
        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.json()["success"])

    def test_intake_persists_asset_type_for_dashboard(self):
        import_collateral_registrations(
            [
                {
                    "Mã hợp đồng": "DASH-ASSET-INTAKE",
                    "Loại tài sản": "Ô tô tải",
                }
            ],
            user=self.admin,
            source_type="api",
        )

        registration = CollateralRegistration.objects.get(
            contract_code="DASH-ASSET-INTAKE"
        )
        self.assertEqual(registration.asset_type, "Ô tô tải")
