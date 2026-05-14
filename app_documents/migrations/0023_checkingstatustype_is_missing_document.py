from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("app_documents", "0022_gapowebhookevent"),
    ]

    operations = [
        migrations.AddField(
            model_name="checkingstatustype",
            name="is_missing_document",
            field=models.BooleanField(default=False),
        ),
    ]
