from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("app_document_campaigns", "0030_power_automate_email_transport")]

    operations = [
        migrations.AddField(
            model_name="campaignemailbatch",
            name="transport_provider",
            field=models.CharField(
                choices=[("power_automate", "Power Automate"), ("smtp", "SMTP")],
                default="power_automate",
                max_length=24,
            ),
        ),
    ]
