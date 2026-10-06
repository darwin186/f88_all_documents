from django.db import migrations, models


def seed_existing_campaigns(apps, schema_editor):
    Campaign = apps.get_model("app_document_campaigns", "Campaign")
    RiskErrorCode = apps.get_model("app_document_campaigns", "RiskErrorCode")
    code_ids = list(RiskErrorCode.objects.values_list("pk", flat=True))
    if not code_ids:
        return
    for campaign in Campaign.objects.iterator():
        campaign.risk_error_codes.add(*code_ids)


class Migration(migrations.Migration):
    dependencies = [("app_document_campaigns", "0027_areamanageraccesslink_stage")]

    operations = [
        migrations.AddField(
            model_name="campaign",
            name="risk_error_codes",
            field=models.ManyToManyField(
                blank=True,
                db_table="dec_campaign_risk_error_code",
                help_text="Danh sách mã lỗi được phép sử dụng khi book lỗi gửi QTRR.",
                related_name="campaigns",
                to="app_document_campaigns.riskerrorcode",
            ),
        ),
        migrations.RunPython(seed_existing_campaigns, migrations.RunPython.noop),
    ]
