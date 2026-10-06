from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("app_document_campaigns", "0032_campaignemailbatch_is_test")]

    operations = [
        migrations.AlterField(
            model_name="campaignemailbatch",
            name="transport_provider",
            field=models.CharField(
                choices=[
                    ("power_automate", "Power Automate"),
                    ("microsoft_graph", "Microsoft Graph"),
                    ("smtp", "SMTP"),
                ],
                default="power_automate",
                max_length=24,
            ),
        ),
    ]
