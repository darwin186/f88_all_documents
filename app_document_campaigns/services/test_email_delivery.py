import uuid
from email.utils import parseaddr

from django.db import transaction
from django.utils import timezone

from app_document_campaigns.models import CampaignEmailBatch, CampaignEmailDelivery
from app_document_campaigns.services.email_html import email_body_html
from app_document_campaigns.services.power_automate_email import _message_payload, _redact_access_urls


def queue_test_email(*, campaign, email_type, transport, target, rendered, template_version, requested_by):
    """Queue one audited test email without issuing or revoking any access link."""
    key = f"test:{campaign.pk}:{email_type}:{transport}:{uuid.uuid4()}"
    with transaction.atomic():
        batch = CampaignEmailBatch.objects.create(
            campaign=campaign,
            email_type=email_type,
            transport_provider=transport,
            is_test=True,
            idempotency_key=key,
            total_count=1,
            requested_by=requested_by,
        )
        target_type = (
            CampaignEmailDelivery.TargetType.SHOP
            if email_type == CampaignEmailBatch.EmailType.PGD_RESPONSE
            else CampaignEmailDelivery.TargetType.AREA_MANAGER
        )
        delivery = CampaignEmailDelivery.objects.create(
            batch=batch,
            target_type=target_type,
            target_id=target.pk,
            to_emails=rendered.to,
            cc_emails=[],
            bcc_emails=[],
            from_email=parseaddr(rendered.from_email)[1],
            from_name=parseaddr(rendered.from_email)[0],
            rendered_subject=rendered.subject,
            rendered_body_redacted=_redact_access_urls(email_body_html(rendered.body)),
            template_version=template_version,
            idempotency_key=key,
        )
        message = _message_payload(delivery, target, rendered, {
            "test": True,
            "template_version": template_version,
        })
        message["cc"] = []
        message["bcc"] = []

    from app_document_campaigns.tasks import send_bulk_campaign_email_batches
    try:
        send_bulk_campaign_email_batches.delay([{
            "batch_id": str(batch.pk),
            "transport": transport,
            "messages": [message],
        }])
    except Exception:
        now = timezone.now()
        CampaignEmailBatch.objects.filter(pk=batch.pk).update(
            status=CampaignEmailBatch.Status.FAILED,
            failed_count=1,
            completed_at=now,
            last_error_code="queue_unavailable",
            last_error_message="Không kết nối được Celery broker.",
        )
        CampaignEmailDelivery.objects.filter(pk=delivery.pk).update(
            status=CampaignEmailDelivery.Status.FAILED,
            failed_at=now,
            error_code="queue_unavailable",
            error_message="Không kết nối được Celery broker.",
        )
        raise
    return batch
