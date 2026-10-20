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
