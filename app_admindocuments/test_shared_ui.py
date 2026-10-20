from html import unescape
from urllib.parse import parse_qs, urlparse
import re

from django.contrib.auth.models import Group, User
from django.core.paginator import Paginator
from django.template.loader import render_to_string
from django.test import TestCase, RequestFactory
from django.urls import NoReverseMatch, reverse


class AdministrativeSharedUiTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_superuser('shared-ui-admin', 'shared@example.com', 'test')
        cls.employee = User.objects.create_user('shared-ui-employee')
        cls.staff = User.objects.create_user('shared-ui-staff')
        cls.staff.groups.add(Group.objects.get_or_create(name='administrative staff')[0])

    def test_administrative_screens_use_one_shell_and_widgets(self):
        self.client.force_login(self.admin)
        for route in ['admindocuments_list','paper_document_list',
                      'incoming_document_list','parcel_receipt_list','parcel_receipt_completed_list',
                      'parcel_auto_notify_settings','master_data',
                      'admindocuments_counters','admindocuments_counters_visual']:
            with self.subTest(route=route):
                response = self.client.get(reverse(f'admindocuments:{route}'))
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, 'adm-top-nav')
                self.assertContains(response, 'admindocuments/js/admin_ui.js')
                self.assertContains(response, 'admindocuments/css/admin_ui.css')
                self.assertNotContains(response, 'id="sidebar"')
                self.assertContains(response, 'document_form_controls.js', count=1)
                self.assertContains(response, 'js/ui-toast.js', count=1)

    def test_paper_and_document_filter_chips_share_the_button_row(self):
        self.client.force_login(self.admin)
        for route in ['admindocuments_list','paper_document_list']:
            with self.subTest(route=route):
                response = self.client.get(reverse(f'admindocuments:{route}'))
                self.assertContains(response, 'adm-filter-footer adm-filter-footer-with-chips')
                self.assertContains(response, 'data-filter-chips', count=1)

    def test_common_navigation_marks_current_screen_and_preserves_visibility(self):
        self.client.force_login(self.employee)
        response = self.client.get(reverse('admindocuments:incoming_document_list'))
        self.assertContains(response, 'aria-current="page">Công văn đến')
        self.assertNotContains(response, '>Quản trị <')
        self.assertNotContains(response, f'href="{reverse("admindocuments:admindocuments_list")}"')
        self.client.force_login(self.staff)
        response = self.client.get(reverse('admindocuments:admindocuments_counters'))
        self.assertContains(response, 'aria-current="page">Quản trị')
        self.assertContains(response, f'href="{reverse("admindocuments:paper_document_list")}"')

    def test_shared_pager_preserves_repeated_and_special_character_filters(self):
        request = RequestFactory().get('/?q=A%26B%20%2B%20gi%E1%BA%A5y&status=1&status=2&pane=list&receive_location=7&open=42&page=2')
        html = render_to_string('admindocuments/includes/pagination.html', {'page': Paginator(range(60),25).page(2), 'request': request})
        links = re.findall(r'href="([^"]+)"', html)
        self.assertEqual(len(links), 2)
        for href, expected_page in zip(links, ['1','3']):
            query = parse_qs(urlparse(unescape(href)).query)
            self.assertEqual(query['q'], ['A&B + giấy'])
            self.assertEqual(query['status'], ['1','2'])
            self.assertEqual(query['pane'], ['list'])
            self.assertEqual(query['receive_location'], ['7'])
            self.assertEqual(query['page'], [expected_page])
            self.assertNotIn('open', query)

    def test_shared_pager_still_shows_empty_first_page(self):
        html = render_to_string('admindocuments/includes/pagination.html', {'page': Paginator([],25).page(1)})
        self.assertEqual(html.count('aria-disabled="true"'), 2)
        self.assertIn('aria-current="page" aria-label="Trang 1">1</span>', html)

    def test_parcel_filters_submit_one_value_per_field(self):
        from html.parser import HTMLParser

        class FilterParser(HTMLParser):
            def __init__(self):
                super().__init__()
                self.forms = []
                self.current = None

            def handle_starttag(self, tag, attrs):
                attrs = dict(attrs)
                if tag == 'form':
                    self.current = [] if attrs.get('method', '').lower() == 'get' else None
                elif tag in {'input', 'select'} and self.current is not None:
                    self.current.append(attrs.get('name'))

            def handle_endtag(self, tag):
                if tag == 'form' and self.current is not None:
                    self.forms.append(self.current)
                    self.current = None

        self.client.force_login(self.admin)
        response = self.client.get(reverse('admindocuments:parcel_receipt_list'), {'pane': 'list'})
        parser = FilterParser()
        parser.feed(response.content.decode())
        filters = next(fields for fields in parser.forms if 'start_date' in fields)
        for name in ['recipient', 'department', 'start_date', 'end_date', 'receive_location']:
            self.assertEqual(filters.count(name), 1, name)

    def test_overview_and_its_export_are_removed(self):
        self.client.force_login(self.admin)
        self.assertRedirects(self.client.get('/admindocuments/'), reverse('admindocuments:workflow_hub'), fetch_redirect_response=False)
        self.assertEqual(self.client.get('/admindocuments/dashboard/export/').status_code, 404)
        for route in ['admindocuments_dashboard', 'admindocuments_dashboard_export']:
            with self.assertRaises(NoReverseMatch):
                reverse(f'admindocuments:{route}')
        response = self.client.get(reverse('admindocuments:admindocuments_list'))
        self.assertNotContains(response, '>Tổng quan<')
        self.assertNotContains(response, 'Danh bạ người nhận')
