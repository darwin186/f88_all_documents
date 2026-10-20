from django import template

from app_admindocuments.access import has_admin_docs_access

register = template.Library()


@register.simple_tag
def admin_page_numbers(page, expanded=False):
    """Show at most five page numbers while keeping the current page reachable."""
    if not expanded:
        return [page.number]
    total = page.paginator.num_pages
    current = page.number
    if total <= 5:
        return range(1, total + 1)
    if current <= 3:
        return [1, 2, 3, total - 1, total]
    if current >= total - 2:
        return [1, 2, total - 2, total - 1, total]
    return [1, current - 1, current, current + 1, total]


@register.simple_tag(takes_context=True)
def admin_query(context, **changes):
    """Preserve the full GET query, including repeated values, when navigating."""
    request = context.get("request")
    if request is None:
        return ""
    query = request.GET.copy()
    for name, value in changes.items():
        if value is None:
            query.pop(name, None)
        else:
            query[name] = str(value)
    return query.urlencode()


@register.simple_tag(takes_context=True)
def admin_nav_state(context):
    request = context.get("request")
    user = getattr(request, "user", None)
    route = getattr(getattr(request, "resolver_match", None), "url_name", "") or ""
    if route.startswith("paper_document") or context.get("paper_documents_nav"):
        active = "paper"
    elif route.startswith(("incoming_document", "incoming_dispatch")):
        active = "incoming"
    elif route in {"parcel_receipt_list", "parcel_receipt_completed_list"}:
        active = "parcel"
    elif route in {"master_data", "admindocuments_counters", "admindocuments_counters_visual",
                   "paper_counters_visual", "parcel_auto_notify_settings"}:
        active = "management"
    elif route == "workflow_hub":
        active = "workflows"
    else:
        active = "document"
    can_manage = context.get("has_admin_docs_access")
    if can_manage is None:
        can_manage = has_admin_docs_access(user)
    return {"active": active, "can_manage": can_manage, "is_superuser": bool(getattr(user, "is_superuser", False))}
