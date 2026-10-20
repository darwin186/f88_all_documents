import re

from django.contrib.auth.models import User
from django.template.loader import render_to_string
from django.test import TestCase
from django.urls import reverse

from app_documents.models import Manager, Region, Shop
from .forms import AdmPaperDocumentForm


class PaperCreateUsesUiSelectTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_superuser('select-admin', 'select@example.com', 'test')
        cls.region = Region.objects.create(region_id=12, region_code='SEL', region_name='Miền Bắc')
        manager = Manager.objects.create(manager_code='SEL', qlkv_code='SEL', qlkv_name='QL', qlv_code='SEL', qlv_name='QV')
        Shop.objects.bulk_create([Shop(shop_code=7001, shop_name='PGD một', manager_id=manager, region_id=cls.region)])

    def test_create_modal_selects_use_ui_select_component(self):
        self.client.force_login(self.admin)
        html = self.client.get(reverse('admindocuments:paper_document_list')).content.decode()
        create_panel = html[html.index('data-paper-create-form'):html.index('id="paper-import-panel"')]
        selects = re.findall(r'<select\b', create_panel)
        wrappers = re.findall(r'<div class="ui-select[^"]*" data-ui-select', create_panel)
        self.assertGreaterEqual(len(selects), 4)
        self.assertEqual(len(selects), len(wrappers))
        self.assertNotIn('data-document-select', create_panel)

    def test_component_template_supports_variants(self):
        form = AdmPaperDocumentForm()
        html = render_to_string('components/ui_select.html', {
            'field': form['requested_department'], 'search': 'on', 'max': 3, 'summary': 'count', 'size': 'sm', 'clear': 'off',
        })
        for expected in ('ui-select-sm', 'data-ui-select', 'data-search="on"', 'data-max="3"', 'data-summary="count"', 'data-clear="off"', '<select'):
            self.assertIn(expected, html)
        self.assertNotIn('data-invalid', html)
