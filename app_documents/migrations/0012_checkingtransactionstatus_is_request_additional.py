from django.db import migrations, models


def set_request_additional(apps, schema_editor):
    CheckingTransactionStatus = apps.get_model("app_documents", "CheckingTransactionStatus")
    CheckingTransactionStatus.objects.filter(checking_status_code="103").update(is_request_additional=True)


class Migration(migrations.Migration):

    dependencies = [
        ("app_documents", "0011_documentkpisetting"),
    ]

    operations = [
        migrations.AddField(
            model_name="checkingtransactionstatus",
            name="is_request_additional",
            field=models.BooleanField(default=False),
        ),
        migrations.RunPython(set_request_additional, migrations.RunPython.noop),
    ]
