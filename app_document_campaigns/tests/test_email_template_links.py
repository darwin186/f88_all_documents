from datetime import date, datetime
from types import SimpleNamespace as NS

from django.test import SimpleTestCase, override_settings

from app_document_campaigns.services.email_html import normalize_template_href, sanitize_email_template, email_body_html
from app_document_campaigns.services.email_templates import _render, render_area_email, validate_templates


class EmailTemplateLinkTests(SimpleTestCase):
    def test_browser_encoded_and_editor_relative_links_are_recovered(self):
        for href in (
            '{{manager_url}}', '%7B%7Bmanager_url%7D%7D', '%7b%7b%20manager_url%20%7d%7d',
            'https://chungtu.f88.vn/master-data/email-templates/%7B%7Bmanager_url%7D%7D',
            '/master-data/email-templates/{{manager_url}}',
        ):
            with self.subTest(href=href):
                self.assertEqual(normalize_template_href(href), '{{manager_url}}')
                body = sanitize_email_template(f'<p><a href="{href}">Mở link QLKV</a></p>')
                self.assertIn('href="{{manager_url}}"', body)
                rendered = email_body_html(_render(body, {'manager_url': 'https://chungtu.f88.vn/manager/unique-token/'}))
                self.assertIn('href="https://chungtu.f88.vn/manager/unique-token/"', rendered)
                self.assertNotIn('manager_url', rendered)
                self.assertNotIn('/master-data/email-templates/', rendered)

    def test_existing_encoded_snapshot_renders_without_resaving(self):
        body = '<a href="https://chungtu.f88.vn/master-data/email-templates/%7B%7Bmanager_url%7D%7D">Xem báo cáo</a>'
        rendered = _render(body, {'manager_url': 'https://chungtu.f88.vn/manager/token/?a=1&b=2'})
        self.assertIn('href="https://chungtu.f88.vn/manager/token/?a=1&amp;b=2"', rendered)
        self.assertNotIn('%7B', rendered)

    def test_normal_links_and_percent_encoded_paths_are_unchanged(self):
        for href in ('https://reports.example.com/a%20b?x=1&y=2', 'mailto:support@example.com',
                     'https://reports.example.com/redirect?target={{manager_url}}',
                     'https://reports.example.com/path/{{manager_url}}'):
            self.assertEqual(normalize_template_href(href), href)
        self.assertNotIn('href=', sanitize_email_template('<a href="javascript:alert(1)">X</a>'))
        self.assertNotIn('<script', sanitize_email_template('<script>alert(1)</script>'))

    def test_pgd_link_validation_and_rendering_support_encoded_url_token(self):
        body = '<a href="%7B%7Bresponse_url%7D%7D">Phản hồi</a>'
        validate_templates('Email PGD', body)
        rendered = _render(body, {'response_url': 'https://chungtu.f88.vn/pgd/token/'})
        self.assertIn('href="https://chungtu.f88.vn/pgd/token/"', rendered)

    @override_settings(DEFAULT_FROM_EMAIL='support@example.com')
    def test_step3_and_step5_render_encoded_manager_snapshot(self):
        body = '<a href="https://chungtu.f88.vn/master-data/email-templates/%7B%7Bmanager_url%7D%7D">QLKV</a>'
        config = NS(monitoring_subject_template='Theo dõi {{campaign_code}}', monitoring_body_template=body,
                    confirmation_subject_template='Xác nhận {{campaign_code}}', confirmation_body_template=body,
                    monitoring_cc_template='', monitoring_bcc_template='', confirmation_cc_template='',
                    confirmation_bcc_template='', support_email='', monitoring_report_url='',
                    monitoring_guide_url='', confirmation_guide_url='', from_name='Vận hành')
        campaign = NS(code='TEST', name='Kỳ test', report_month=date(2026, 10, 1),
                      link_expires_at=datetime(2026, 11, 1), response_deadline=None, area_response_deadline=None)
        area = NS(pk=1, areaManager_code='QLKV01', areaManager_name='QLKV', areaManager_email='qlkv@example.com')
        for confirmation in (False, True):
            rendered = render_area_email(config, campaign, area, 'https://chungtu.f88.vn/manager/real-token/',
                                         confirmation_mode=confirmation)
            self.assertIn('href="https://chungtu.f88.vn/manager/real-token/"', rendered.body)
            self.assertEqual(rendered.to, ['qlkv@example.com'])
            self.assertNotIn('manager_url', rendered.body)
