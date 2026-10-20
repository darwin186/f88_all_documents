import re
from html import unescape
from urllib.parse import parse_qs, urlparse

from django.core.paginator import Paginator
from django.template.loader import render_to_string
from django.test import RequestFactory, SimpleTestCase

from .templatetags.admin_ui import admin_page_numbers


class DocumentPaginationTests(SimpleTestCase):
    def test_page_choices_keep_current_page_and_boundaries(self):
        for total in range(1, 31):
            paginator = Paginator(range(total), 1)
            for current in range(1, total + 1):
                with self.subTest(total=total, current=current):
                    numbers = list(admin_page_numbers(paginator.page(current), True))
                    self.assertLessEqual(len(numbers), 5)
                    self.assertEqual(numbers, sorted(set(numbers)))
                    self.assertEqual(numbers[0], 1)
                    self.assertEqual(numbers[-1], total)
                    self.assertIn(current, numbers)

    def test_first_pages_show_three_first_and_two_last_numbers(self):
        paginator = Paginator(range(10), 1)
        for current in [1, 2, 3]:
            self.assertEqual(admin_page_numbers(paginator.page(current), True), [1, 2, 3, 9, 10])

    def test_single_and_empty_page_keep_both_disabled_arrows(self):
        for count in [0, 1]:
            html = render_to_string('admindocuments/includes/document_pagination.html', {
                'documents': Paginator(range(count), 25).page(1),
            })
            self.assertEqual(html.count('aria-disabled="true"'), 2)
            self.assertEqual(html.count('aria-current="page"'), 1)
            self.assertNotIn('href=', html)
            self.assertIn('adm-pagination-compact', html)

    def test_number_links_preserve_filters_and_sort(self):
        request = RequestFactory().get('/?q=A%26B%20%2B%20gi%E1%BA%A5y&status=1&status=2&sort=created&dir=asc&page=2')
        html = render_to_string('admindocuments/includes/document_pagination.html', {
            'documents': Paginator(range(10), 1).page(2),
            'list_query': request.GET.urlencode().replace('&page=2', ''),
            'request': request,
        })
        targets = []
        for href in re.findall(r'href="([^"]+)"', html):
            query = parse_qs(urlparse(unescape(href)).query)
            self.assertEqual(query['q'], ['A&B + giấy'])
            self.assertEqual(query['status'], ['1', '2'])
            self.assertEqual(query['sort'], ['created'])
            self.assertEqual(query['dir'], ['asc'])
            self.assertEqual(len(query['page']), 1)
            targets.append(query['page'][0])
        self.assertEqual(targets, ['1', '1', '3', '9', '10', '3'])

    def test_other_shared_pagers_keep_the_current_page_only(self):
        html = render_to_string('admindocuments/includes/pagination.html', {
            'page': Paginator(range(10), 1).page(4),
        })
        self.assertEqual(len(re.findall(r'href="', html)), 2)
        self.assertNotIn('adm-pagination-compact', html)
