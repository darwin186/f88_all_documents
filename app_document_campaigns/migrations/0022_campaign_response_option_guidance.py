from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("app_document_campaigns", "0021_risk_error_booking")]

    operations = [
        migrations.AddField(
            model_name="campaignresponseoption",
            name="guidance_text",
            field=models.TextField(
                blank=True,
                default="",
                help_text="Hướng dẫn hiện dưới ô ghi chú khi PGD chọn phản hồi này.",
                max_length=2000,
            ),
        ),
    ]
