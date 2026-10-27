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


class PackageCodeRecentSuggestTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        from django.contrib.auth.models import Group
        from django.utils import timezone
        from datetime import timedelta
        from app_documents.models import Package
        cls.owner = User.objects.create_user('recent_owner', password='test')
        cls.other = User.objects.create_user('recent_other', password='test')
        cls.admin = User.objects.create_user('recent_admin', password='test')
        cls.admin.groups.add(Group.objects.get_or_create(name='admin')[0])
        now = timezone.now()
        for code, user, age in (('R-OLD', cls.owner, 3), ('R-MINE', cls.owner, 2), ('R-THEIRS', cls.other, 1)):
            package = Package.objects.create(package_code=code, created_by=user)
            Package.objects.filter(pk=package.pk).update(created_date=now - timedelta(days=age))
        cls.url = reverse('package_code_suggest')

    def labels(self, user, **params):
        self.client.force_login(user)
        return [item['label'] for item in self.client.get(self.url, params).json()['results']]

    def test_regular_user_gets_only_own_packages_newest_first(self):
        self.assertEqual(self.labels(self.owner, recent=1), ['R-MINE', 'R-OLD'])
        self.assertEqual(self.labels(self.other, recent=1), ['R-THEIRS'])

    def test_admin_gets_everyone_newest_first(self):
        self.assertEqual(self.labels(self.admin, recent=1), ['R-THEIRS', 'R-MINE', 'R-OLD'])

    def test_empty_query_without_recent_flag_returns_nothing(self):
        self.assertEqual(self.labels(self.admin), [])


class PackageCodeTypeCheckTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        from app_documents.models import FolderType, Package
        cls.user = User.objects.create_user('type_user', password='test')
        vh = FolderType.objects.create(folder_type_code='VHX', folder_type_name='VH x', package_type='VH', is_valid=True, created_by=cls.user)
        nh = FolderType.objects.create(folder_type_code='NHX', folder_type_name='NH x', package_type='NH', is_valid=True, created_by=cls.user)
        Package.objects.create(package_code='T-VH-1', package_type=vh, created_by=cls.user)
        Package.objects.create(package_code='T-NH-1', package_type=nh, created_by=cls.user)
        cls.url = reverse('package_code_suggest')

    def get(self, **params):
        self.client.force_login(self.user)
        return self.client.get(self.url, params).json()

    def test_suggestions_limited_to_package_type(self):
        labels = [i['label'] for i in self.get(recent=1, package_type='vh')['results']]
        self.assertEqual(labels, ['T-VH-1'])

    def test_check_statuses(self):
        self.assertEqual(self.get(check='t-vh-1', package_type='VH')['status'], 'ok')
        self.assertEqual(self.get(check='T-NH-1', package_type='VH')['status'], 'wrong_type')
        self.assertEqual(self.get(check='nope', package_type='VH')['status'], 'not_found')


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


class CheckingChangePackageRulesTests(TestCase):
    """Quy tắc đổi thùng ở duyet-chung-tu-v2 (nhánh package_code_submit)."""

    @classmethod
    def setUpTestData(cls):
        from datetime import date
        from app_documents.models import (
            DocumentStatus, DocumentsDetail, Folder, FolderStatus, FolderType, Manager, Package,
            PackageDocumentHistory, PartnerPackage, PartnerPackageStatus, Shop,
        )
        cls.PackageDocumentHistory = PackageDocumentHistory
        cls.DocumentsDetail = DocumentsDetail
        cls.user = User.objects.create_user('chg_user', password='test', is_superuser=True, is_staff=True)
        from django.contrib.auth.models import Group
        cls.user.groups.add(Group.objects.get_or_create(name='admin')[0])
        from app_documents.models import Region, UserProfile
        UserProfile.objects.create(user=cls.user, department='Vận hành', region=Region.objects.create(region_code='R-CHG', region_name='Toàn quốc'))
        manager = Manager.objects.create(manager_code='M1', qlkv_code='Q1', qlkv_name='QL', qlv_code='V1', qlv_name='QV')
        shop = Shop.objects.create(shop_name='S1', manager_id=manager)
        vh = FolderType.objects.create(folder_type_code='VHC', folder_type_name='VH c', package_type='VH', is_valid=True, created_by=cls.user)
        nh = FolderType.objects.create(folder_type_code='NHC', folder_type_name='NH c', package_type='NH', is_valid=True, created_by=cls.user)
        received = FolderStatus.objects.create(folder_status_code='RCV', folder_status_name='Đã nhận', is_received=True, created_by=cls.user)
        doc_status = DocumentStatus.objects.create(documents_status_name='Chọn được', documents_status_code='100', is_selectable=True, created_by=cls.user)
        cls.old = Package.objects.create(package_code='C-VH-OLD', package_type=vh, created_by=cls.user)
        cls.new = Package.objects.create(package_code='C-VH-NEW', package_type=vh, created_by=cls.user)
        cls.wrong = Package.objects.create(package_code='C-NH-1', package_type=nh, created_by=cls.user)
        cls.partner_new = Package.objects.create(package_code='C-VH-PARTNER', package_type=vh, created_by=cls.user)
        released = PartnerPackageStatus.objects.create(package_status_name='Đã giao', is_released=True)
        from django.utils import timezone
        PartnerPackage.objects.create(package_id=cls.partner_new, partner_package_code='P-1', created_date=timezone.now(), status_id=released)
        folder = Folder.objects.create(
            folder_code='F-1', shop_id=shop, folder_type_id=vh, folder_status_id=received,
            folder_created_date=date.today(), package_id=cls.old,
        )
        cls.doc = DocumentsDetail.objects.create(
            documents_code='D-1', shop_id=shop, manager_id=manager, folder_id=folder,
            documents_created_date=date.today(), document_status_id=doc_status, package_id=cls.old,
        )
        cls.url = reverse('checking_transaction_v2')

    def post(self, code):
        self.client.force_login(self.user)
        return self.client.post(
            self.url, {'documents_id_submit': self.doc.documents_id, 'package_code_submit': code},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )

    def current(self):
        return self.DocumentsDetail.objects.get(pk=self.doc.pk).package_id

    def test_change_to_same_type_records_old_and_new_history(self):
        self.assertEqual(self.post('C-VH-NEW').status_code, 200)
        self.assertEqual(self.current(), self.new)
        rows = list(self.PackageDocumentHistory.objects.filter(document_id=self.doc).order_by('trans_id').values_list('package_id__package_code', 'action'))
        self.assertEqual(rows, [('C-VH-OLD', 'unassigned'), ('C-VH-NEW', 'assigned')])

    def test_wrong_type_is_rejected(self):
        response = self.post('C-NH-1')
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.current(), self.old)
        self.assertFalse(self.PackageDocumentHistory.objects.filter(document_id=self.doc).exists())

    def test_target_package_with_partner_is_rejected(self):
        self.assertEqual(self.post('C-VH-PARTNER').status_code, 400)
        self.assertEqual(self.current(), self.old)

    def test_current_package_with_partner_blocks_change(self):
        from django.utils import timezone
        from app_documents.models import PartnerPackage, PartnerPackageStatus
        released = PartnerPackageStatus.objects.get(package_status_name='Đã giao')
        PartnerPackage.objects.create(package_id=self.old, partner_package_code='P-OLD', created_date=timezone.now(), status_id=released)
        self.assertEqual(self.post('C-VH-NEW').status_code, 400)
        self.assertEqual(self.current(), self.old)

    def test_same_package_does_nothing(self):
        self.assertEqual(self.post('C-VH-OLD').status_code, 200)
        self.assertEqual(self.current(), self.old)
        self.assertFalse(self.PackageDocumentHistory.objects.filter(document_id=self.doc).exists())
