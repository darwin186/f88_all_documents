from django.db import migrations, models
from django.db.models import F


def archive_completed_cases(apps, schema_editor):
    Registration = apps.get_model("app_documents", "CollateralRegistration")
    Registration.objects.filter(
        gddb_status="registered",
        postmini_updated__in=["Đã cập nhật", "Đã cập nhật 1 dòng"],
        archived_at__isnull=True,
    ).update(archived_at=F("updated_at"))


class Migration(migrations.Migration):

    dependencies = [
        ("app_documents", "0032_gddb_case_processing_lease"),
    ]

    operations = [
        migrations.AddField(
            model_name="collateralregistration",
            name="archived_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddIndex(
            model_name="collateralregistration",
            index=models.Index(
                fields=["archived_at", "is_duplicate"],
                name="gddb_archive_queue_idx",
            ),
        ),
        migrations.RunPython(archive_completed_cases, migrations.RunPython.noop),
    ]
