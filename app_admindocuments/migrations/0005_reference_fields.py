from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("app_admindocuments", "0004_administrativedocument_dates"),
    ]

    operations = [
        migrations.AddField(
            model_name="admadministrativedocument",
            name="is_reference_document",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="admadministrativedocument",
            name="reference_document",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=models.SET_NULL,
                related_name="referenced_by",
                to="app_admindocuments.admadministrativedocument",
            ),
        ),
    ]
