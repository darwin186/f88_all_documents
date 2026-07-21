from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


def backfill_case_owner(apps, schema_editor):
    Registration = apps.get_model("app_documents", "CollateralRegistration")
    completed = Registration.objects.exclude(gddb_status="pending").filter(processing_by__isnull=True)
    for registration in completed.iterator():
        owner_id = registration.registered_by_id or registration.updated_by_id
        if owner_id:
            Registration.objects.filter(pk=registration.pk).update(processing_by_id=owner_id)


class Migration(migrations.Migration):

    dependencies = [
        ("app_documents", "0031_gddb_dedupe_by_contract_code"),
    ]

    operations = [
        migrations.AddField(
            model_name="collateralregistration",
            name="processing_by",
            field=models.ForeignKey(
                blank=True,
                db_column="processing_by",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="gddb_processing",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name="collateralregistration",
            name="processing_started_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="collateralregistration",
            name="processing_expires_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddIndex(
            model_name="collateralregistration",
            index=models.Index(
                fields=["processing_by", "processing_expires_at"],
                name="gddb_processing_lease_idx",
            ),
        ),
        migrations.RunPython(backfill_case_owner, migrations.RunPython.noop),
    ]
