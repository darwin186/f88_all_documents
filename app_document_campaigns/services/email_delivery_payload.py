import re
from email.utils import parseaddr

from app_document_campaigns.models import CampaignEmailDelivery
from app_document_campaigns.services.email_html import email_body_html


def redact_access_urls(body):
    return re.sub(r"/(respond|manager-view)/[^/&<\s]+/?", r"/\1/[REDACTED]/", body)


def message_payload(delivery, target, rendered, metadata):
    if delivery.target_type == CampaignEmailDelivery.TargetType.SHOP:
        target_data = {
            "type": "shop",
            "id": target.pk,
            "code": str(target.shop_code or ""),
            "name": target.shop_name,
        }
    else:
        target_data = {
            "type": "area_manager",
            "id": target.pk,
            "code": str(target.areaManager_code or ""),
            "name": target.areaManager_name,
        }
    return {
        "message_id": str(delivery.pk),
        "idempotency_key": delivery.idempotency_key,
        "target": target_data,
        "from": {
            "address": parseaddr(rendered.from_email)[1],
            "name": parseaddr(rendered.from_email)[0],
        },
        "to": rendered.to,
        "cc": rendered.cc,
        "bcc": rendered.bcc,
        "subject": rendered.subject,
        "body": {"content_type": "html", "content": email_body_html(rendered.body)},
        "metadata": metadata,
    }
