from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("app_document_campaigns", "0008_campaigntype_shop_checklist_template")]
    operations = [migrations.AddField(model_name="campaign", name="shop_instructions", field=models.TextField(blank=True, default="", max_length=10000, verbose_name="Hướng Dẫn"))]
