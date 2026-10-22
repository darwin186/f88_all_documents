from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase

ROOT = Path(settings.BASE_DIR)
LEGACY_ARROW_TEMPLATES = [
    'app_admindocuments/templates/admindocuments/includes/document_select.html',
    'app_documents/templates/app_documents/app_borrow_request_v2.html',
    'app_documents/templates/app_documents/app_checkingtransaction_v2.html',
    'app_documents/templates/app_documents/app_document_receiving_v2.html',
    'app_documents/templates/app_documents/app_gddb_registration_v2.html',
]


class SelectArrowTests(SimpleTestCase):
    def test_kit_arrow_is_a_circle_with_a_chevron(self):
        css = (ROOT / 'static/css/ui-kit.css').read_text(encoding='utf-8')
        self.assertIn('.ui-select-arrow {', css)
        self.assertIn('border-radius: 50%', css.split('.ui-select-arrow {', 1)[1].split('}', 1)[0])
        self.assertIn('rotate(180deg)', css)

    def test_native_selects_not_yet_migrated_get_the_same_arrow(self):
        css = (ROOT / 'static/css/ui-kit.css').read_text(encoding='utf-8')
        self.assertIn('select:not([multiple]):not([size]):not(.ui-select-native)', css)
        self.assertIn('appearance: none', css)

    def test_hand_made_text_arrows_are_gone(self):
        for rel in LEGACY_ARROW_TEMPLATES:
            with self.subTest(template=rel):
                self.assertNotIn('>▾</span>', (ROOT / rel).read_text(encoding='utf-8'))

    def test_public_pages_without_the_v2_base_load_the_kit_css(self):
        for rel in ('app_document_campaigns/templates/app_document_campaigns/shop_response.html',
                    'app_document_campaigns/templates/app_document_campaigns/area_manager_readonly.html'):
            with self.subTest(template=rel):
                self.assertIn("css/ui-kit.css", (ROOT / rel).read_text(encoding='utf-8'))
