from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("app_documents", "0009_partnerpackagehistory"),
    ]

    operations = [
        migrations.AddField(
            model_name="package",
            name="note",
            field=models.TextField(blank=True, null=True),
        ),
    ]
