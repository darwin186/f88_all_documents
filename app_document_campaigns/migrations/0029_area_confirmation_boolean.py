from django.db import migrations, models


def migrate_area_decisions(apps, schema_editor):
    AreaConfirmation = apps.get_model("app_document_campaigns", "AreaConfirmation")
    AreaConfirmation.objects.filter(decision="confirmed").update(is_agreed=True)
    AreaConfirmation.objects.filter(decision="returned").update(is_agreed=False)


class Migration(migrations.Migration):
    dependencies = [("app_document_campaigns", "0028_campaign_risk_error_codes")]

    operations = [
        migrations.AddField(
            model_name="areaconfirmation",
            name="is_agreed",
            field=models.BooleanField(
                choices=[(True, "Đồng thuận"), (False, "Không đồng thuận")],
                null=True,
                verbose_name="QLKV đồng thuận",
            ),
        ),
        migrations.RunPython(migrate_area_decisions, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="areaconfirmation",
            name="is_agreed",
            field=models.BooleanField(
                choices=[(True, "Đồng thuận"), (False, "Không đồng thuận")],
                verbose_name="QLKV đồng thuận",
            ),
        ),
        migrations.RemoveField(model_name="areaconfirmation", name="decision"),
        migrations.RemoveField(model_name="campaign", name="area_agree_label"),
        migrations.RemoveField(model_name="campaign", name="area_disagree_label"),
    ]
