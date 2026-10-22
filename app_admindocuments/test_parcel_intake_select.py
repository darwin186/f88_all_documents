import re

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from .models import AdmParcelReceiveLocation


class ParcelIntakeSelectTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_superuser('parcel-select-admin', 'ps@example.com', 'test')
        AdmParcelReceiveLocation.objects.create(name='Kho Hà Nội', is_active=True)

    def setUp(self):
        self.client.force_login(self.admin)
        self.html = self.client.get(reverse('admindocuments:parcel_receipt_list')).content.decode()

    def test_every_droplist_on_the_page_is_wrapped_by_the_kit(self):
        selects = re.findall(r'<select\b[^>]*>', self.html)
        self.assertGreaterEqual(len(selects), 4)
        for tag in selects:
            start = self.html.index(tag)
            self.assertIn('data-ui-select', self.html[max(0, start - 400):start], tag)

    def test_old_department_search_box_is_gone(self):
        for marker in ('departmentSearchInput', 'departmentClearButton', 'clearSelectedDepartment'):
            self.assertNotIn(marker, self.html)

    def test_department_droplist_has_search_on(self):
        self.assertRegex(self.html, r'data-ui-select data-search="on"[^>]*>\s*<select[^>]*id="id_recipient_department"')

    def test_recipient_field_is_one_combobox(self):
        self.assertEqual(self.html.count('<div class="ui-combobox" data-ui-combobox'), 1)
        self.assertIn('js/ui-combobox.js', self.html)
        self.assertIn(reverse('admindocuments:parcel_recipient_search'), self.html)
        for marker in ('recipientSearchInput', 'recipientSearchResults', 'recipientSelectedLabel', 'selectUnknownRecipient',
                       'clearSelectedRecipient', 'searchRecipientDirectory'):
            self.assertNotIn(marker, self.html)

    def test_attachments_use_the_upload_component_with_a_single_images_field(self):
        self.assertIn('js/ui-upload.js', self.html)
        self.assertIn('data-ui-upload data-camera', self.html)
        self.assertEqual(len(re.findall(r'<input[^>]*type="file"[^>]*name="images"', self.html)), 1)
        self.assertNotIn('capture="environment"', self.html)
        self.assertNotIn('Chụp ảnh</span>', self.html)

    def test_incoming_dispatch_attachments_use_upload_without_camera(self):
        html = self.client.get(reverse('admindocuments:incoming_document_list')).content.decode()
        self.assertEqual(html.count('data-ui-upload'), 1)
        self.assertNotIn('data-camera', html)
        self.assertNotIn('bindIncomingFileSummary', html)
        self.assertEqual(len(re.findall(r'<input[^>]*type="file"[^>]*name="images"', html)), 1)

    def test_status_colors_show_live_preview_pair(self):
        from .models import AdmDocumentStatus
        AdmDocumentStatus.objects.update_or_create(code='999', defaults={'name': 'Thử màu', 'badge_text_color': '#112233', 'badge_bg_color': '#ddeeff'})
        html = self.client.get(reverse('admindocuments:master_data')).content.decode()
        self.assertIn('data-ui-color-pair', html)
        self.assertIn('data-color-preview', html)
        self.assertIn('js/ui-color.js', html)
