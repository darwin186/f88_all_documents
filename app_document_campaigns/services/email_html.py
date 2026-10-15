"""Safe, deliberately small HTML subset for campaign email bodies."""

import re
from html import escape
from html.parser import HTMLParser
from urllib.parse import unquote, urlparse


ALLOWED_TAGS = {
    "p", "br", "div", "strong", "b", "em", "i", "u", "s",
    "ul", "ol", "li", "blockquote", "h2", "h3", "a",
}
VOID_TAGS = {"br"}
HTML_TAG_PATTERN = re.compile(r"</?[a-zA-Z][^>]*>")


def is_html_email_template(value):
    return bool(HTML_TAG_PATTERN.search(value or ""))


URL_TEMPLATE_TOKEN = re.compile(r"{{\s*(response_url|manager_url|report_url|report_guide_url|confirmation_guide_url)\s*}}")


def normalize_template_href(value):
    """Recover URL placeholders encoded/absolutized by the rich-text editor."""
    value = (value or "").strip()
    decoded = unquote(value)
    match = URL_TEMPLATE_TOKEN.fullmatch(decoded)
    if match:
        return "{{" + match.group(1) + "}}"
    parsed = urlparse(decoded)
    prefix, _, tail = parsed.path.rpartition("/")
    match = URL_TEMPLATE_TOKEN.fullmatch(tail)
    # Only discard the known editor base path, never an arbitrary URL's prefix/query.
    if (match and parsed.scheme.lower() in {"", "http", "https"}
            and prefix.rstrip("/").endswith("/master-data/email-templates")
            and not parsed.query and not parsed.fragment):
        return "{{" + match.group(1) + "}}"
    return value


def _safe_href(value):
    value = normalize_template_href(value)
    if not value:
        return ""
    if "{{" in value and "}}" in value:
        return value
    parsed = urlparse(value)
    if parsed.scheme.lower() in {"http", "https", "mailto"}:
        return value
    return ""


class _EmailHTMLSanitizer(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.output = []

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        if tag not in ALLOWED_TAGS:
            return
        if tag == "a":
            href = _safe_href(dict(attrs).get("href"))
            attributes = f' href="{escape(href, quote=True)}" target="_blank" rel="noopener noreferrer"' if href else ""
            self.output.append(f"<a{attributes}>")
            return
        self.output.append(f"<{tag}>")

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)

    def handle_endtag(self, tag):
        tag = tag.lower()
        if tag in ALLOWED_TAGS and tag not in VOID_TAGS:
            self.output.append(f"</{tag}>")

    def handle_data(self, data):
        self.output.append(escape(data))


def sanitize_email_template(value):
    """Keep legacy plain text unchanged; sanitize bodies authored as HTML."""
    value = value or ""
    if not is_html_email_template(value):
        return value
    parser = _EmailHTMLSanitizer()
    parser.feed(value)
    parser.close()
    return "".join(parser.output).strip()


def email_body_html(value):
    """Return final safe HTML accepted by Microsoft Graph/Outlook."""
    value = sanitize_email_template(value)
    if is_html_email_template(value):
        content = value
    else:
        content = escape(value).replace("\r\n", "\n").replace("\r", "\n").replace("\n", "<br>")
    return f'<div style="font-family:Arial,sans-serif;font-size:14px;line-height:1.6">{content}</div>'
