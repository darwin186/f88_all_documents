import re

from django.contrib.auth.models import Group, User
from django.test import TestCase
from django.urls import reverse

from app_documents.models import Region, UserProfile

LEGACY_MARKERS = ('class="toast-container"', 'id="toast-container"', 'adm-toast-host', 'campaign-toasts',
                  'SERVER_TOASTS', 'id="gddb-toast"', 'class="toast ')


class ToastSystemTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        region = Region.objects.create(region_code='R-TOAST', region_name='Toàn quốc')
        cls.admin = User.objects.create_superuser('toast_admin', 't@example.com', 'test')
        cls.admin.groups.add(Group.objects.get_or_create(name='admin')[0])
        UserProfile.objects.create(user=cls.admin, department='Vận hành', region=region)

    def setUp(self):
        self.client.force_login(self.admin)

    def test_every_v2_page_loads_the_toast_kit_exactly_once(self):
        pages = [reverse(name) for name in (
            'receiving_transaction_v2', 'checking_transaction_v2', 'package_list_management', 'borrow_request_management_v2',
            'borrow_management_v2', 'gddb_registration_v2', 'user_profile_v2', 'master_data_tokens', 'document_intake_management',
            'folder_appointment_report_v2', 'workshift_register')]
        pages += [reverse(f'admindocuments:{name}') for name in (
            'admindocuments_list', 'paper_document_list', 'parcel_receipt_completed_list', 'admindocuments_counters', 'workflow_hub')]
        for url in pages:
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 200)
                html = response.content.decode()
                self.assertEqual(html.count('js/ui-toast.js'), 1)
                self.assertEqual(html.count('css/ui-toast.css'), 1)

    def test_old_toast_implementations_are_gone(self):
        for url in (reverse('receiving_transaction_v2'), reverse('checking_transaction_v2'), reverse('gddb_registration_v2'),
                    reverse('admindocuments:admindocuments_list'), reverse('borrow_request_management_v2')):
            html = self.client.get(url).content.decode()
            for marker in LEGACY_MARKERS:
                with self.subTest(url=url, marker=marker):
                    self.assertNotIn(marker, html)

    def test_django_message_becomes_exactly_one_toast_seed(self):
        response = self.client.post(reverse('admindocuments:admindocuments_counters'),
                                    {'target': 'admin', 'doc_type': '', 'company': '', 'year': 2026, 'next_number': 5}, follow=True)
        html = response.content.decode()
        self.assertEqual(len(re.findall(r'<span data-ui-toast-seed ', html)), 1)
        self.assertIn('Vui lòng chọn đủ loại văn bản và công ty.', html)
        self.assertIn('data-level="error"', html)

    def test_messages_on_v2_pages_are_not_rendered_as_inline_banners_any_more(self):
        response = self.client.post(reverse('document_intake_token_create'), {'name': '', 'scope': ''}, follow=True)
        html = response.content.decode()
        self.assertEqual(len(re.findall(r'<span data-ui-toast-seed ', html)), 1)
        self.assertNotIn('border-emerald-200 bg-emerald-50 px-4 py-3', html)

    def test_message_text_is_escaped_in_seed(self):
        from django.contrib.messages import constants
        from django.contrib.messages.storage.base import Message
        from django.template.loader import render_to_string
        html = render_to_string('components/ui_toast_seeds.html', {'messages': [Message(constants.ERROR, '<img src=x onerror=alert(1)>')]})
        self.assertIn('&lt;img', html)
        self.assertNotIn('<img', html)

    def test_toast_block_can_be_overridden_per_page(self):
        from django.template import Context, Template
        html = Template("{% extends 'app_documents/base_app_documents_v2.html' %}{% block toast_messages %}{% endblock %}").render(
            Context({'messages': []}))
        self.assertNotIn('data-ui-toast-seeds', html)

    def test_login_page_uses_toast_kit(self):
        self.client.logout()
        html = self.client.get(reverse('login')).content.decode()
        self.assertEqual(html.count('js/ui-toast.js'), 1)
        self.assertNotIn('toast-container position-fixed', html)

    def test_campaign_list_uses_the_shared_toast(self):
        from app_document_campaigns.models import Campaign  # noqa: F401  (đảm bảo app được nạp)
        html = self.client.get(reverse('document_campaigns:campaign_list')).content.decode()
        self.assertEqual(html.count('js/ui-toast.js'), 1)
        self.assertNotIn('data-campaign-toasts', html)


class CheckingScreenDateTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        region = Region.objects.create(region_code='R-CHK', region_name='Toàn quốc')
        cls.admin = User.objects.create_superuser('chk_admin', 'c@example.com', 'test')
        cls.admin.groups.add(Group.objects.get_or_create(name='admin')[0])
        UserProfile.objects.create(user=cls.admin, department='Vận hành', region=region)

    def test_duyet_chung_tu_uses_the_date_component_everywhere(self):
        self.client.force_login(self.admin)
        html = self.client.get(reverse('checking_transaction_v2'), {'filterdocumentdate': '2026-10-01 to 2026-10-07'}).content.decode()
        self.assertEqual(html.count('data-ui-date data-mode="range"'), 2)
        self.assertEqual(html.count('data-ui-date data-mode="single"'), 2)
        self.assertRegex(html, r'<input id="filter-document-date" name="filterdocumentdate" value="2026-10-01 to 2026-10-07"')
        self.assertRegex(html, r'<input id="drawer-supplement-date" name="additional_date"')
        self.assertIn('js/ui-date.js', html)
        self.assertNotIn('initRange', html)
        self.assertNotIn('flatpickr(bulkCheckDate', html)

    def test_duyet_chung_tu_droplists_use_the_select_component(self):
        import re as _re
        self.client.force_login(self.admin)
        html = self.client.get(reverse('checking_transaction_v2')).content.decode()
        selects = _re.findall(r'<select\b[^>]*>', html)
        self.assertGreaterEqual(len(selects), 7)
        for tag in selects:
            self.assertIn('data-ui-select', html[max(0, html.index(tag) - 400):html.index(tag)], tag)
        for name in ('choice_shop', 'choicedocumentstatus', 'choice_user_duyet', 'choicecheckstatus', 'choicebusinesstype'):
            self.assertRegex(html, rf'<select[^>]*name="{name}"')
        for marker in ("x-text=\"selected || 'Phòng giao dịch'\"", 'selectedLabel', 'class="hidden" @change="syncLabel()"'):
            self.assertNotIn(marker, html)

    def test_duyet_chung_tu_package_filters_have_suggestions(self):
        self.client.force_login(self.admin)
        html = self.client.get(reverse('checking_transaction_v2'), {'filter_package': 'VH-1', 'filter_partner_package': 'PX-2'}).content.decode()
        self.assertRegex(html, r'data-ui-combobox data-free data-name="filter_package" data-value="VH-1"')
        self.assertRegex(html, r'data-ui-combobox data-free data-name="filter_partner_package" data-value="PX-2"')
        self.assertIn(reverse('package_code_suggest'), html)
        self.assertIn(reverse('partner_package_code_suggest'), html)
        self.assertNotRegex(html, r'<input name="filter_package"')
        self.assertNotRegex(html, r'<input name="filter_partner_package"')
