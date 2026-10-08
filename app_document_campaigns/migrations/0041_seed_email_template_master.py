from django.db import migrations


def seed_templates(apps, schema_editor):
    Template = apps.get_model("app_document_campaigns", "EmailTemplateMaster")
    Campaign = apps.get_model("app_document_campaigns", "Campaign")
    PgdConfig = apps.get_model("app_document_campaigns", "CampaignEmailConfig")
    AreaConfig = apps.get_model("app_document_campaigns", "CampaignAreaEmailConfig")

    pgd, _ = Template.objects.get_or_create(
        email_type="pgd_response", name="Báo cáo lỗi gửi PGD",
        defaults={
            "subject_template": PgdConfig._meta.get_field("subject_template").default,
            "body_template": PgdConfig._meta.get_field("body_template").default,
            "is_default": True,
        },
    )
    monitoring, _ = Template.objects.get_or_create(
        email_type="area_monitoring", name="QLKV theo dõi phản hồi PGD",
        defaults={
            "subject_template": AreaConfig._meta.get_field("monitoring_subject_template").default,
            "body_template": AreaConfig._meta.get_field("monitoring_body_template").default,
            "is_default": True,
        },
    )
    confirmation, _ = Template.objects.get_or_create(
        email_type="area_confirmation", name="QLKV xác nhận lỗi sau chốt",
        defaults={
            "subject_template": AreaConfig._meta.get_field("confirmation_subject_template").default,
            "body_template": AreaConfig._meta.get_field("confirmation_body_template").default,
            "is_default": True,
        },
    )
    Campaign.objects.filter(pgd_email_template__isnull=True).update(pgd_email_template=pgd)
    Campaign.objects.filter(area_monitoring_email_template__isnull=True).update(area_monitoring_email_template=monitoring)
    Campaign.objects.filter(area_confirmation_email_template__isnull=True).update(area_confirmation_email_template=confirmation)


def unseed_templates(apps, schema_editor):
    Template = apps.get_model("app_document_campaigns", "EmailTemplateMaster")
    Campaign = apps.get_model("app_document_campaigns", "Campaign")
    Campaign.objects.update(
        pgd_email_template=None,
        area_monitoring_email_template=None,
        area_confirmation_email_template=None,
    )
    Template.objects.filter(
        name__in=["Báo cáo lỗi gửi PGD", "QLKV theo dõi phản hồi PGD", "QLKV xác nhận lỗi sau chốt"]
    ).delete()


class Migration(migrations.Migration):
    dependencies = [("app_document_campaigns", "0040_emailtemplatemaster_and_more")]
    operations = [migrations.RunPython(seed_templates, unseed_templates)]
