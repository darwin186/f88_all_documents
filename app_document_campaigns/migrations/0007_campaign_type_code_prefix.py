from django.db import migrations, models


def set_code_prefix(apps, schema_editor):
    CampaignType = apps.get_model("app_document_campaigns", "CampaignType")
    CampaignType.objects.filter(code="hardcopy-document-error").update(code_prefix="DEC-HC")


class Migration(migrations.Migration):
    dependencies = [("app_document_campaigns", "0006_campaign_type")]

    operations = [
        migrations.AddField(
            model_name="campaigntype",
            name="code_prefix",
            field=models.CharField(blank=True, max_length=20, null=True),
        ),
        migrations.RunPython(set_code_prefix, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="campaigntype",
            name="code_prefix",
            field=models.CharField(max_length=20, unique=True),
        ),
        migrations.AlterField(
            model_name="campaign",
            name="code",
            field=models.CharField(editable=False, max_length=30, unique=True),
        ),
    ]
