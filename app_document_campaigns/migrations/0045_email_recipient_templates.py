from django.db import migrations, models


def move_existing_recipients(apps, schema_editor):
    CampaignEmailConfig = apps.get_model("app_document_campaigns", "CampaignEmailConfig")
    CampaignAreaEmailConfig = apps.get_model("app_document_campaigns", "CampaignAreaEmailConfig")
    for config in CampaignEmailConfig.objects.all().iterator():
        cc = list(config.cc_emails or [])
        if config.cc_area_manager:
            cc.insert(0, "{{area_manager_email}}")
        if config.cc_shop_manager:
            cc.insert(0, "{{shop_manager_email}}")
        config.cc_template = ", ".join(cc)
        config.bcc_template = ", ".join(config.bcc_emails or [])
        config.save(update_fields=["cc_template", "bcc_template"])
    for config in CampaignAreaEmailConfig.objects.all().iterator():
        cc = ", ".join(config.cc_emails or [])
        bcc = ", ".join(config.bcc_emails or [])
        config.monitoring_cc_template = cc
        config.monitoring_bcc_template = bcc
        config.confirmation_cc_template = cc
        config.confirmation_bcc_template = bcc
        config.save(update_fields=["monitoring_cc_template", "monitoring_bcc_template", "confirmation_cc_template", "confirmation_bcc_template"])


class Migration(migrations.Migration):
    dependencies = [("app_document_campaigns", "0044_campaignemailconfig_cc_shop_manager")]

    operations = [
        migrations.AddField(model_name="emailtemplatemaster", name="cc_template", field=models.TextField(blank=True, default="")),
        migrations.AddField(model_name="emailtemplatemaster", name="bcc_template", field=models.TextField(blank=True, default="")),
        migrations.AddField(model_name="campaignemailconfig", name="cc_template", field=models.TextField(blank=True, default="")),
        migrations.AddField(model_name="campaignemailconfig", name="bcc_template", field=models.TextField(blank=True, default="")),
        migrations.AddField(model_name="campaignareaemailconfig", name="monitoring_cc_template", field=models.TextField(blank=True, default="")),
        migrations.AddField(model_name="campaignareaemailconfig", name="monitoring_bcc_template", field=models.TextField(blank=True, default="")),
        migrations.AddField(model_name="campaignareaemailconfig", name="confirmation_cc_template", field=models.TextField(blank=True, default="")),
        migrations.AddField(model_name="campaignareaemailconfig", name="confirmation_bcc_template", field=models.TextField(blank=True, default="")),
        migrations.RunPython(move_existing_recipients, migrations.RunPython.noop),
    ]
