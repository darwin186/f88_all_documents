from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("app_documents", "0035_external_document_intake"),
    ]

    operations = [
        migrations.AddField(
            model_name="collateralregistration",
            name="asset_type",
            field=models.CharField(blank=True, max_length=100, null=True),
        ),
    ]
