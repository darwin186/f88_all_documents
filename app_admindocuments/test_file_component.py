import re

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse


class FileInputsUseUiFileTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_superuser('file-admin', 'f@example.com', 'test')

    def setUp(self):
        self.client.force_login(self.admin)

    def _single_file_inputs(self, html):
        return [m for m in re.findall(r'<input\b[^>]*type="file"[^>]*>', html) if ' multiple' not in m and 'class="hidden"' not in m]

    def test_document_create_and_attachment_dialogs_use_ui_file(self):
        html = self.client.get(reverse('admindocuments:admindocuments_list')).content.decode()
        inputs = self._single_file_inputs(html)
        self.assertGreaterEqual(len(inputs), 2)
        self.assertEqual(len(inputs), len(re.findall(r'<div class="ui-file" data-ui-file', html)))
        self.assertNotIn('file:bg-f88green', html)

    def test_paper_import_uses_ui_file(self):
        html = self.client.get(reverse('admindocuments:paper_document_list')).content.decode()
        self.assertIn('<div class="ui-file" data-ui-file data-max-mb="10"><input type="file" id="paper-import-file"', html)

    def test_ui_file_assets_are_loaded_by_v2_base(self):
        html = self.client.get(reverse('admindocuments:admindocuments_list')).content.decode()
        self.assertIn('js/ui-file.js', html)
