from django.contrib.auth.models import Group, User
from django.test import TestCase

from app_documents.access_controls import AccessControls
from app_documents.models import Region, UserProfile


class AccessControlsNationwideCheckerTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        checker_group = Group.objects.create(name='checker')
        admin_group = Group.objects.create(name='admin')
        cls.north = Region.objects.create(region_code='1', region_name='Miền Bắc')
        cls.south = Region.objects.create(region_code='2', region_name='Miền Nam')
        cls.nationwide = Region.objects.create(region_code='3', region_name='Toàn Quốc')

        cls.nationwide_checker = User.objects.create_user(username='checker_nationwide')
        cls.nationwide_checker.groups.add(checker_group)
        UserProfile.objects.create(
            user=cls.nationwide_checker,
            department='Vận hành',
            region=cls.nationwide,
        )

        cls.north_checker = User.objects.create_user(username='checker_north')
        cls.north_checker.groups.add(checker_group)
        UserProfile.objects.create(
            user=cls.north_checker,
            department='Vận hành',
            region=cls.north,
        )

        cls.admin = User.objects.create_user(username='document_admin')
        cls.admin.groups.add(admin_group)

    def test_nationwide_checker_does_not_receive_a_region_filter(self):
        self.assertEqual(
            AccessControls.get_filters_for_user(self.nationwide_checker),
            {},
        )
        self.assertEqual(
            AccessControls.filter_shop_region_based_on_role(self.nationwide_checker),
            {},
        )

    def test_regional_checker_remains_limited_to_its_region(self):
        self.assertEqual(
            AccessControls.get_filters_for_user(self.north_checker),
            {'region_id': self.north.region_id},
        )
        self.assertEqual(
            AccessControls.filter_shop_region_based_on_role(self.north_checker),
            {'shop_id__region_id': self.north.region_id},
        )

    def test_nationwide_checker_can_see_checkers_and_admins_from_all_regions(self):
        visible_users = AccessControls.get_users_based_on_role(
            self.nationwide_checker
        )
        self.assertQuerySetEqual(
            visible_users.order_by('username'),
            [self.nationwide_checker, self.north_checker, self.admin],
        )
