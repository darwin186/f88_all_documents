from django.db import transaction

from app_document_campaigns.models import (
    CampaignAreaEmailConfig,
    CampaignEmailConfig,
    EmailTemplateMaster,
)


@transaction.atomic
def apply_campaign_email_templates(campaign, field_names=None):
    selected = set(field_names) if field_names is not None else None
    pgd = campaign.pgd_email_template
    if pgd and (selected is None or "pgd_email_template" in selected):
        config, _ = CampaignEmailConfig.objects.get_or_create(campaign=campaign)
        if any(getattr(config, field) != getattr(pgd, field) for field in ("subject_template", "body_template", "cc_template", "bcc_template")):
            config.subject_template = pgd.subject_template
            config.body_template = pgd.body_template
            config.cc_template = pgd.cc_template
            config.bcc_template = pgd.bcc_template
            config.template_version += 1
            config.save(update_fields=["subject_template", "body_template", "cc_template", "bcc_template", "template_version", "updated_at"])

    area_fields = {"area_monitoring_email_template", "area_confirmation_email_template"}
    if selected is not None and not selected.intersection(area_fields):
        return
    area, _ = CampaignAreaEmailConfig.objects.get_or_create(campaign=campaign)
    changed = []
    monitoring = campaign.area_monitoring_email_template
    if monitoring and (selected is None or "area_monitoring_email_template" in selected) and (
        area.monitoring_subject_template != monitoring.subject_template
        or area.monitoring_body_template != monitoring.body_template
        or area.monitoring_cc_template != monitoring.cc_template
        or area.monitoring_bcc_template != monitoring.bcc_template
    ):
        area.monitoring_subject_template = monitoring.subject_template
        area.monitoring_body_template = monitoring.body_template
        area.monitoring_cc_template = monitoring.cc_template
        area.monitoring_bcc_template = monitoring.bcc_template
        changed.extend(["monitoring_subject_template", "monitoring_body_template", "monitoring_cc_template", "monitoring_bcc_template"])
    confirmation = campaign.area_confirmation_email_template
    if confirmation and (selected is None or "area_confirmation_email_template" in selected) and (
        area.confirmation_subject_template != confirmation.subject_template
        or area.confirmation_body_template != confirmation.body_template
        or area.confirmation_cc_template != confirmation.cc_template
        or area.confirmation_bcc_template != confirmation.bcc_template
    ):
        area.confirmation_subject_template = confirmation.subject_template
        area.confirmation_body_template = confirmation.body_template
        area.confirmation_cc_template = confirmation.cc_template
        area.confirmation_bcc_template = confirmation.bcc_template
        changed.extend(["confirmation_subject_template", "confirmation_body_template", "confirmation_cc_template", "confirmation_bcc_template"])
    if changed:
        area.template_version += 1
        area.save(update_fields=[*changed, "template_version", "updated_at"])


def default_template(email_type):
    return EmailTemplateMaster.objects.filter(
        email_type=email_type, is_active=True, is_default=True,
    ).first()
