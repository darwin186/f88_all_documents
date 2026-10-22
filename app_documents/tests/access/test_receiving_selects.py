import re

from django.contrib.auth.models import Group, User
from django.test import TestCase
from django.urls import reverse

from app_documents.models import Region, UserProfile


class ReceivingScreenSelectTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        region = Region.objects.create(region_code='R-RECV', region_name='Toàn quốc')
        cls.admin = User.objects.create_superuser('recv_admin', 'r@example.com', 'test')
        cls.admin.groups.add(Group.objects.get_or_create(name='admin')[0])
        UserProfile.objects.create(user=cls.admin, department='Vận hành', region=region)

    def setUp(self):
        self.client.force_login(self.admin)
        self.html = self.client.get(reverse('receiving_transaction_v2')).content.decode()

    def test_every_select_is_wrapped_by_the_kit(self):
        selects = re.findall(r'<select\b[^>]*>', self.html)
        self.assertGreaterEqual(len(selects), 9)
        for tag in selects:
            start = self.html.index(tag)
            self.assertIn('data-ui-select', self.html[max(0, start - 400):start], tag)

    def test_hand_made_alpine_dropdowns_are_gone(self):
        for marker in ("selected || 'Phòng giao dịch'", "label(selected)", "placeholder=\"Tìm phòng giao dịch\"",
                       "placeholder=\"Nhập username\""):
            self.assertNotIn(marker, self.html)

    def test_filter_fields_keep_their_names(self):
        for name in ('choice_shop', 'choice_folder_status', 'choice_folder_type', 'choice_lastest_receiver'):
            self.assertRegex(self.html, rf'<select[^>]*name="{name}"')
        self.assertIn('id="choice-shop"', self.html)


class PackageCodeSuggestTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        from app_documents.models import Package
        cls.user = User.objects.create_user('suggest_user', password='test')
        Package.objects.create(package_code='VH-261020-01')
        Package.objects.create(package_code='VH-261020-02')
        Package.objects.create(package_code='HN-261019-01')
        cls.url = reverse('package_code_suggest')

    def test_requires_login(self):
        self.assertEqual(self.client.get(self.url, {'q': 'VH'}).status_code, 302)

    def test_suggests_matching_codes_case_insensitively(self):
        self.client.force_login(self.user)
        results = self.client.get(self.url, {'q': 'vh-'}).json()['results']
        self.assertEqual(sorted(item['label'] for item in results), ['VH-261020-01', 'VH-261020-02'])
        self.assertEqual(results[0]['id'], results[0]['label'])

    def test_empty_query_returns_nothing_and_results_are_capped(self):
        from app_documents.models import Package
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(self.url).json()['results'], [])
        for index in range(20):
            Package.objects.create(package_code=f'ZZ-{index:02d}')
        self.assertEqual(len(self.client.get(self.url, {'q': 'ZZ'}).json()['results']), 15)


class ReceivingPackageFilterComboboxTests(ReceivingScreenSelectTests):
    def test_package_filter_is_a_free_text_combobox(self):
        html = self.client.get(reverse('receiving_transaction_v2'), {'filter_package': 'VH-1'}).content.decode()
        self.assertRegex(html, r'data-ui-combobox data-free data-name="filter_package" data-value="VH-1"')
        self.assertIn(reverse('package_code_suggest'), html)
        self.assertNotRegex(html, r'<input name="filter_package"')


class PartnerPackageSuggestTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        from django.utils import timezone
        from app_documents.models import Package, PartnerPackage
        cls.user = User.objects.create_user('partner_suggest_user', password='test')
        f88 = Package.objects.create(package_code='VH-261020-09')
        PartnerPackage.objects.create(package_id=f88, partner_package_code='PX-A-001', partner_name='VTP', created_date=timezone.now())
        PartnerPackage.objects.create(partner_package_code='PX-B-777', partner_name='GHN', created_date=timezone.now())
        cls.url = reverse('partner_package_code_suggest')

    def test_requires_login(self):
        self.assertEqual(self.client.get(self.url, {'q': 'PX'}).status_code, 302)

    def test_suggests_partner_codes_with_context(self):
        self.client.force_login(self.user)
        results = self.client.get(self.url, {'q': 'px-a'}).json()['results']
        self.assertEqual([item['label'] for item in results], ['PX-A-001'])
        self.assertIn('VTP', results[0]['meta'])
        self.assertIn('VH-261020-09', results[0]['meta'])
        self.assertEqual(self.client.get(self.url).json()['results'], [])


class ReceivingFilterLayoutTests(ReceivingScreenSelectTests):
    def test_partner_filter_is_a_combobox_and_extra_filters_fit_one_row(self):
        html = self.client.get(reverse('receiving_transaction_v2'), {'filter_partner_package': 'PX-1'}).content.decode()
        self.assertRegex(html, r'data-ui-combobox data-free data-name="filter_partner_package" data-value="PX-1"')
        self.assertIn(reverse('partner_package_code_suggest'), html)
        self.assertIn('sm:grid-cols-2 lg:grid-cols-4', html)
        self.assertNotIn('md:grid-cols-3 gap-3" x-show="showMore"', html)


class ReceivingDateFilterTests(ReceivingScreenSelectTests):
    def test_date_filters_use_the_date_component(self):
        html = self.client.get(reverse('receiving_transaction_v2'), {'filter_receive_date': '2026-10-01 to 2026-10-07'}).content.decode()
        self.assertEqual(html.count('data-ui-date data-mode="range" data-max-days="30"'), 2)
        self.assertRegex(html, r'<input id="filter-receive-date" name="filter_receive_date" value="2026-10-01 to 2026-10-07"')
        self.assertIn('js/ui-date.js', html)
        self.assertIn('flatpickr@4.6.13', html)
        self.assertNotIn('initFlatRange', html)
        self.assertNotRegex(html, r'<input id="filter-folder-date"[^>]*readonly')
