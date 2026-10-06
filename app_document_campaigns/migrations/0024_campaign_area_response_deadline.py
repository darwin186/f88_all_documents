from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("app_document_campaigns", "0023_response_guidance_master")]

    operations = [
        migrations.AddField(
            model_name="campaign",
            name="area_response_deadline",
            field=models.DateTimeField(
                blank=True,
                null=True,
                help_text="Hạn cuối QLKV xác nhận kết quả sau Team review.",
            ),
        ),
    ]
