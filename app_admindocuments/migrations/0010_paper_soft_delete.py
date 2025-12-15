from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("app_admindocuments", "0009_optional_requested_department"),
    ]

    operations = [
        migrations.AddField(
            model_name="admpaperdocument",
            name="is_deleted",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="admpaperdocument",
            name="deleted_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
