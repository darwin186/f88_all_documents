"""UI Kit pagination, independent of any application's filtering conventions."""
from django import template
from django.http import QueryDict

register = template.Library()


def page_numbers(current, total):
    """Use the five-number pattern from the administrative paper list."""
    if total <= 5:
        return list(range(1, total + 1))
    if current <= 3:
        return [1, 2, 3, total - 1, total]
    if current >= total - 2:
        return [1, 2, total - 2, total - 1, total]
    return [1, current - 1, current, current + 1, total]


@register.simple_tag(takes_context=True)
def ui_pagination_data(context, page, query=None, page_param="page"):
    if not getattr(page, "paginator", None):
        return None
    page_param = page_param or "page"
    if query is None or query == "":
        request = context.get("request")
        params = request.GET.copy() if request is not None else QueryDict(mutable=True)
    elif isinstance(query, QueryDict):
        params = query.copy()
    elif isinstance(query, str):
        params = QueryDict(query.lstrip("?"), mutable=True)
    else:
        params = QueryDict(mutable=True)
        for key, value in query.items():
            if value is not None:
                params.setlist(key, list(value) if isinstance(value, (list, tuple)) else [value])
    params.pop(page_param, None)

    def url(number):
        target = params.copy()
        target[page_param] = str(number)
        return "?" + target.urlencode()

    return {
        "current": page.number,
        "items": [{"number": number, "url": url(number)} for number in page_numbers(page.number, page.paginator.num_pages)],
        "previous": url(page.previous_page_number()) if page.has_previous() else None,
        "next": url(page.next_page_number()) if page.has_next() else None,
        "start": page.start_index(), "end": page.end_index(), "total": page.paginator.count,
    }
