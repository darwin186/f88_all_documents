from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("app_document_campaigns", "0014_areamanageraccesslink")]
    operations = [
        migrations.AddField(
            model_name="campaign",
            name="area_manager_instructions",
            field=models.TextField(blank=True, default="", max_length=10000, verbose_name="Hướng dẫn Quản lý khu vực"),
        )
    ]
