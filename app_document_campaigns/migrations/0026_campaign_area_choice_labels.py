from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("app_document_campaigns", "0025_area_confirmation_excel_job")]

    operations = [
        migrations.AddField(
            model_name="campaign",
            name="area_agree_label",
            field=models.CharField(default="Đồng thuận", max_length=100),
        ),
        migrations.AddField(
            model_name="campaign",
            name="area_disagree_label",
            field=models.CharField(default="Không đồng thuận", max_length=100),
        ),
    ]
