import json

from django.contrib.auth.models import Group, User
from django.test import Client, TestCase
from django.urls import reverse

from .models import Package, UserProfile


class PackageListV2Tests(TestCase):
    @classmethod
    def setUpTestData(cls):
        admin_group = Group.objects.create(name="admin")
        cls.admin = User.objects.create_user(
            username="package_list_admin",
            password="test",
        )
        cls.admin.groups.add(admin_group)
        UserProfile.objects.create(user=cls.admin, department="Vận hành")
        Package.objects.bulk_create(
            [
                Package(
                    package_code=f"PERF-PACKAGE-{index:03d}",
                    created_by=cls.admin,
                )
                for index in range(51)
            ]
        )

    def setUp(self):
        self.client = Client()
        self.client.force_login(self.admin)

    def test_package_list_uses_server_side_pages_of_50(self):
        response = self.client.get(reverse("package_list_management"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["page_obj"].paginator.count, 51)
        self.assertEqual(len(json.loads(response.context["packages_json"])), 50)

    def test_second_page_only_serializes_remaining_packages(self):
        response = self.client.get(
            reverse("package_list_management"),
            {"page": 2},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["page_obj"].number, 2)
        self.assertEqual(len(json.loads(response.context["packages_json"])), 1)

    def test_filter_is_preserved_in_pagination_query(self):
        response = self.client.get(
            reverse("package_list_management"),
            {"package_search": "PERF-PACKAGE", "page": 2},
        )

        self.assertIn(
            "package_search=PERF-PACKAGE",
            response.context["pagination_query_prefix"],
        )
        self.assertNotIn("page=", response.context["pagination_query_prefix"])
