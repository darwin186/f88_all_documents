import re
from html import unescape
from urllib.parse import parse_qs, urlsplit

from django.core.paginator import Paginator
from django.http import QueryDict
from django.template import Context
from django.template.loader import render_to_string
from django.test import RequestFactory, SimpleTestCase

from app_documents.templatetags.ui_pagination import page_numbers, ui_pagination_data


class PaginationComponentTests(SimpleTestCase):
    def page(self, current=1, total=10):
        return Paginator(range(total * 25), 25).page(current)

    def render(self, page, **options):
        return render_to_string('components/ui_pagination.html', {'page': page, **options})

    def queries(self, html):
        return [parse_qs(urlsplit(unescape(url)).query) for url in re.findall(r'href="([^"]+)"', html)]

    def test_windows_keep_current_boundaries_and_five_numbers(self):
        for total in range(1, 60):
            for current in range(1, total + 1):
                numbers = page_numbers(current, total)
                self.assertLessEqual(len(numbers), 5)
                self.assertEqual(numbers, sorted(set(numbers)))
                self.assertEqual((numbers[0], numbers[-1]), (1, total))
                self.assertIn(current, numbers)
        self.assertEqual(page_numbers(1, 10), [1, 2, 3, 9, 10])
        self.assertEqual(page_numbers(5, 10), [1, 4, 5, 6, 10])
        self.assertEqual(page_numbers(10, 10), [1, 2, 8, 9, 10])
        self.assertEqual(len(page_numbers(500000, 1000000)), 5)

    def test_request_filters_unicode_repeated_keys_and_sort_are_preserved(self):
        request = RequestFactory().get('/?q=A%26B%20%2B%20gi%E1%BA%A5y&shop=1&shop=2&sort=created&dir=asc&page=2&page=3')
        original = request.GET.urlencode()
        html = self.render(self.page(2), request=request)
        for query in self.queries(html):
            self.assertEqual(query['q'], ['A&B + giấy'])
            self.assertEqual(query['shop'], ['1', '2'])
            self.assertEqual(query['sort'], ['created'])
            self.assertEqual(query['dir'], ['asc'])
            self.assertEqual(len(query['page']), 1)
        self.assertEqual(request.GET.urlencode(), original)

    def test_explicit_query_overrides_request_without_double_page(self):
        html = self.render(self.page(2), request=RequestFactory().get('/?q=ignored'), query='?q=ticket&page=8&page=9')
        for query in self.queries(html):
            self.assertEqual(query['q'], ['ticket'])
            self.assertEqual(len(query['page']), 1)

    def test_mapping_lists_and_explicit_empty_queries(self):
        request = RequestFactory().get('/?q=ignored')
        for query in ({}, QueryDict('')):
            html = self.render(self.page(), request=request, query=query)
            self.assertTrue(all(set(values) == {'page'} for values in self.queries(html)))
        data = ui_pagination_data(Context(), self.page(), {'shop': [1, 2], 'empty': None})
        self.assertEqual(parse_qs(urlsplit(data['next']).query), {'shop': ['1', '2'], 'page': ['2']})

    def test_multiple_paginators_keep_the_other_page_parameter(self):
        html = self.render(self.page(4), page_param='contracts_page', query='contracts_page=4&errors_page=8', label='Phân trang hợp đồng')
        self.assertIn('aria-label="Phân trang hợp đồng"', html)
        for query in self.queries(html):
            self.assertEqual(query['errors_page'], ['8'])
            self.assertEqual(len(query['contracts_page']), 1)
            self.assertNotIn('page', query)

    def test_empty_and_single_pages_have_no_links(self):
        for count in (0, 1, 25):
            html = self.render(Paginator(range(count), 25).page(1), show_summary=True)
            self.assertEqual(html.count('aria-disabled="true"'), 2)
            self.assertEqual(html.count('aria-current="page"'), 1)
            self.assertNotIn('href=', html)
            self.assertIn('0 kết quả' if count == 0 else f'1–{count} / {count} kết quả', html)

    def test_boundaries_have_only_one_disabled_arrow(self):
        for current in (1, 10):
            html = self.render(self.page(current))
            self.assertEqual(html.count('aria-disabled="true"'), 1)
            self.assertNotIn(f'page={current}"', html)
        html = self.render(self.page(5), size='md', show_summary=True)
        self.assertIn('ui-pagination-md', html)
        self.assertIn('101–125 / 250 kết quả', html)
        self.assertIn('rel="prev"', html)
        self.assertIn('rel="next"', html)

    def test_labels_and_search_terms_cannot_inject_html(self):
        html = self.render(self.page(), label='<img src=x>', query={'q': '<script>alert(1)</script>'})
        self.assertIn('aria-label="&lt;img src=x&gt;"', html)
        self.assertNotIn('<script>', html)
        self.assertNotIn('<img', html)
        for query in self.queries(html):
            self.assertEqual(query['q'], ['<script>alert(1)</script>'])

    def test_missing_page_does_not_render_navigation(self):
        self.assertEqual(self.render(None).strip(), '')
