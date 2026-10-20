from django.contrib.auth.models import User
from django.test import SimpleTestCase, TestCase
from django.urls import reverse
from django.utils import timezone

from .models import (AdmAdministrativeDocument, AdmCompany, AdmContentType, AdmDepartment, AdmDocumentCounter,
                     AdmDocumentStatus, AdmDocumentType, AdmPaperType, AdmSignerRole)
from .views import counter_status


class CounterStatusTests(SimpleTestCase):
    def test_continuous_when_no_free_numbers(self):
        self.assertEqual(counter_status(11, 10, 10)['code'], 'ok')
        self.assertEqual(counter_status(1, 0, 0)['code'], 'ok')

    def test_skipped_ahead_counts_as_free_numbers(self):
        status = counter_status(15, 10, 10)
        self.assertEqual(status['code'], 'free')
        self.assertEqual(status['label'], 'Còn 4 số trống')
        self.assertIn('11 đến 14', status['hint'])

    def test_gaps_below_max_count_as_free_numbers(self):
        status = counter_status(11, 10, 7)  # dùng 7 số trong 1..10 -> 3 số trống phía dưới
        self.assertEqual(status['label'], 'Còn 3 số trống')

    def test_free_below_and_ahead_are_summed(self):
        self.assertEqual(counter_status(15, 10, 8)['label'], 'Còn 6 số trống')

    def test_fill_when_next_is_below_used_max(self):
        self.assertEqual(counter_status(3, 10, 7)['code'], 'fill')


class CounterManageScreenTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_superuser('counter-admin', 'c@example.com', 'test')
        cls.company = AdmCompany.objects.create(code='F88', name='F88')
        cls.doc_type = AdmDocumentType.objects.create(code='QD', name='Quyết định')
        content = AdmContentType.objects.create(code='N', name='Mới')
        signer = AdmSignerRole.objects.create(code='GD', title='Giám đốc')
        status = AdmDocumentStatus.objects.create(code=AdmDocumentStatus.CODE_DRAFT, name='Nháp')
        department = AdmDepartment.objects.create(code='HR', name='Nhân sự', company=cls.company)
        cls.year = timezone.now().year
        for i in range(3):
            AdmAdministrativeDocument.objects.create(doc_type=cls.doc_type, content_type=content, title=f'VB {i}', signer_role=signer,
                issuing_company=cls.company, issuing_department=department, status=status, created_by=cls.admin)
        AdmPaperType.objects.create(code='G', name='Giấy giới thiệu')
        cls.url = reverse('admindocuments:admindocuments_counters')

    def setUp(self):
        self.client.force_login(self.admin)

    def _counter(self):
        return AdmDocumentCounter.objects.get(doc_type=self.doc_type, company=self.company, year=self.year)

    def test_row_shows_status_badge_and_no_gap_from_column(self):
        html = self.client.get(self.url).content.decode()
        self.assertIn('cnt-badge', html)
        self.assertNotIn('Chưa dùng từ', html)
        self.assertIn('data-filter-year', html)

    def test_only_active_tab_is_rendered(self):
        admin_html = self.client.get(self.url).content.decode()
        self.assertIn('Cập nhật số tiếp theo', admin_html)
        self.assertNotIn('số hiệu Giấy hành chính', admin_html)
        paper_html = self.client.get(self.url, {'tab': 'paper'}).content.decode()
        self.assertIn('số hiệu Giấy hành chính', paper_html)
        self.assertNotIn('Cập nhật số tiếp theo', paper_html)
        self.assertNotIn('id="cnt-pfy"', paper_html)  # tab giấy ít dòng, không cần bộ lọc
        self.assertNotIn('id="cnt-pq"', paper_html)
        self.assertIn('id="cnt-fy"', admin_html)

    def test_gap_is_flagged_after_raising_next_number(self):
        self.client.post(self.url, {'target': 'admin', 'doc_type': self.doc_type.pk, 'company': self.company.pk, 'year': self.year, 'next_number': 20})
        html = self.client.get(self.url).content.decode()
        self.assertIn('cnt-free', html)
        self.assertIn('Còn 16 số trống', html)
        self.assertNotIn('cnt-gap', html)

    def test_paper_error_returns_to_paper_tab(self):
        response = self.client.post(self.url, {'target': 'paper', 'paper_type': '', 'year': self.year, 'next_number': 5})
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response['Location'].endswith('?tab=paper'), response['Location'])

    def test_admin_error_stays_on_admin_tab(self):
        response = self.client.post(self.url, {'target': 'admin', 'doc_type': '', 'company': '', 'year': self.year, 'next_number': 5})
        self.assertEqual(response.status_code, 302)
        self.assertNotIn('tab=paper', response['Location'])


class CounterVisualSplitMarkTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_superuser('visual-admin', 'v@example.com', 'test')
        company = AdmCompany.objects.create(code='F88', name='F88')
        cls.doc_type = AdmDocumentType.objects.create(code='QD', name='Quyết định')
        content = AdmContentType.objects.create(code='N', name='Mới')
        signer = AdmSignerRole.objects.create(code='GD', title='Giám đốc')
        status = AdmDocumentStatus.objects.create(code=AdmDocumentStatus.CODE_DRAFT, name='Nháp')
        department = AdmDepartment.objects.create(code='HR', name='Nhân sự', company=company)
        cls.company, cls.year = company, timezone.now().year
        kw = dict(doc_type=cls.doc_type, content_type=content, signer_role=signer, issuing_company=company,
                  issuing_department=department, status=status, created_by=cls.admin)
        plain = AdmAdministrativeDocument.objects.create(title='thường', **kw)
        parent = AdmAdministrativeDocument.objects.create(title='gốc', **kw)
        for suffix in 'AB':
            AdmAdministrativeDocument.objects.create(title='nhánh', split_parent=parent, number_suffix=suffix,
                running_number=parent.running_number, number_year=parent.number_year, **kw)
        cls.plain, cls.parent = plain, parent

    def test_split_cells_show_icon_and_branch_count_but_plain_cells_do_not(self):
        self.client.force_login(self.admin)
        html = self.client.get(reverse('admindocuments:admindocuments_counters_visual'),
                               {'doc_type': self.doc_type.pk, 'company': self.company.pk, 'year': self.year, 'partial': 1}).content.decode()
        self.assertEqual(html.count('class="split-mark"'), 1)
        self.assertIn('2 nhánh tách thửa', html)
        self.assertIn('đã tách thửa thành 2 nhánh', html)
        self.assertNotIn('2 nhánh</span>', html)  # không còn chữ "nhánh" xuống dòng trong ô
        self.assertIn('Đã tách thửa (số nhánh)', html)  # có trong chú thích


class CounterOrderingAndTabsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        from datetime import datetime

        from .models import AdmPaperDocument
        cls.admin = User.objects.create_superuser('order-admin', 'o@example.com', 'test')
        cls.company = AdmCompany.objects.create(code='F88', name='F88')
        cls.year = timezone.now().year
        for index, name in enumerate(('Quyết định', 'Thông báo')):
            doc_type = AdmDocumentType.objects.create(code=f'T{index}', name=name)
            for year in (cls.year - 2, cls.year, cls.year - 1):
                AdmDocumentCounter.objects.create(doc_type=doc_type, company=cls.company, year=year, next_number=2)
        paper_type = AdmPaperType.objects.create(code='G', name='Giấy giới thiệu')
        for number, year in enumerate((cls.year - 1, cls.year, cls.year - 2), 1):
            doc = AdmPaperDocument.objects.create(paper_type=paper_type, running_number=number, document_number_full=f'{number}/{year}/G',
                                                  region='Miền Bắc', summary='x', created_by=cls.admin)
            created = datetime(year, 6, 1, 12)
            AdmPaperDocument.objects.filter(pk=doc.pk).update(created_at=timezone.make_aware(created) if timezone.is_aware(timezone.now()) else created)
        cls.url = reverse('admindocuments:admindocuments_counters')

    def setUp(self):
        self.client.force_login(self.admin)

    def _years_in_order(self, html, row_class):
        import re
        return [int(y) for y in re.findall(r'<tr class="%s[^"]*"[^>]*data-year="(\d+)"' % row_class, html)]

    def test_admin_rows_list_newest_year_first(self):
        years = self._years_in_order(self.client.get(self.url).content.decode(), 'counter-row')
        self.assertEqual(years, sorted(years, reverse=True))
        self.assertEqual(years[0], self.year)

    def test_paper_rows_list_newest_year_first(self):
        years = self._years_in_order(self.client.get(self.url, {'tab': 'paper'}).content.decode(), 'paper-counter-row')
        self.assertEqual(years, [self.year, self.year - 1, self.year - 2])

    def test_back_button_removed_and_tabs_attached_to_card(self):
        html = self.client.get(self.url).content.decode()
        self.assertNotIn('Quay lại danh sách', html)
        self.assertIn('class="cnt-tabs"', html)
        self.assertIn('cnt-card cnt-card-attached', html)
