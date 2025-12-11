from django.db import migrations, models
from django.conf import settings


class Migration(migrations.Migration):
    dependencies = [
        ("app_admindocuments", "0006_merge_0005_counter_and_reference"),
    ]

    operations = [
        migrations.AddField(
            model_name="admadministrativedocument",
            name="is_void",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="admadministrativedocument",
            name="voided_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="admadministrativedocument",
            name="voided_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=models.SET_NULL,
                related_name="adm_document_voided_by",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
    ]
