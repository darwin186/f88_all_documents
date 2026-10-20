import re

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from .models import (AdmAdministrativeDocument, AdmCompany, AdmContentType, AdmDepartment, AdmDocumentStatus,
                     AdmDocumentType, AdmSignerRole)


class AdministrativeDocumentUsesUiSelectTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_superuser('doc-select-admin', 'ds@example.com', 'test')
        company = AdmCompany.objects.create(code='F88', name='F88')
        other = AdmCompany.objects.create(code='NNX', name='NNX')
        department = AdmDepartment.objects.create(code='HR', name='Nhân sự', company=company)
        AdmDepartment.objects.create(code='KT', name='Kế toán', company=other)
        doc_type = AdmDocumentType.objects.create(code='QD', name='Quyết định')
        content_type = AdmContentType.objects.create(code='NEW', name='Mới')
        signer = AdmSignerRole.objects.create(code='GD', title='Giám đốc')
        status = AdmDocumentStatus.objects.create(code=AdmDocumentStatus.CODE_DRAFT, name='Nháp')
        cls.doc = AdmAdministrativeDocument.objects.create(
            doc_type=doc_type, content_type=content_type, title='Văn bản mẫu', signer_role=signer,
            issuing_company=company, issuing_department=department, status=status, created_by=cls.admin)

    def setUp(self):
        self.client.force_login(self.admin)

    def test_create_modal_droplists_are_ui_select(self):
        html = self.client.get(reverse('admindocuments:admindocuments_list')).content.decode()
        form = html[html.index('data-adm-create-form'):html.index('name="attachment_mode"')]
        names = re.findall(r'<select\b[^>]*\bname="(\w+)"', form)
        for expected in ('issuing_company', 'doc_type', 'content_type', 'reference_document', 'signer_role', 'issuing_department', 'status'):
            self.assertIn(expected, names)
        self.assertEqual(len(names), len(re.findall(r'<div class="ui-select[^"]*" data-ui-select', form)))
        self.assertNotIn('x-data="adm', form)
        self.assertNotIn('data-document-select', form)

    def test_department_options_carry_company_for_dependent_filtering(self):
        html = self.client.get(reverse('admindocuments:admindocuments_list')).content.decode()
        self.assertRegex(html, r'<option value="\d+" data-company="\d+">Nhân sự \(F88\)</option>')
        self.assertIn('data-company-filtered-by="issuingCompanySelect"', html)

    def test_edit_form_droplists_are_ui_select(self):
        url = reverse('admindocuments:admindocuments_detail', args=[self.doc.pk]) + '?edit=1'
        html = self.client.get(url, HTTP_X_REQUESTED_WITH='XMLHttpRequest').content.decode()
        self.assertIn('data-ui-select', html)
        self.assertNotIn('data-document-select', html)
        self.assertEqual(len(re.findall(r'<select\b', html)), len(re.findall(r'<div class="ui-select[^"]*" data-ui-select', html)))
