from datetime import timedelta

from django.db import migrations, models
from django.utils import timezone


def classify_run_time(run_time):
    if timezone.is_aware(run_time):
        run_time = timezone.localtime(run_time)
    run_date = run_time.date()
    run_hour = run_time.hour
    if run_hour < 9:
        return run_date - timedelta(days=1), 4
    if run_hour < 13:
        return run_date, 1
    if run_hour < 16:
        return run_date, 2
    if run_hour < 19:
        return run_date, 3
    return run_date, 4


def backfill_batch_slots(apps, schema_editor):
    Batch = apps.get_model("app_documents", "CollateralRegistrationImportBatch")
    for batch in Batch.objects.filter(
        models.Q(business_date__isnull=True) | models.Q(slot_number__isnull=True)
    ).iterator():
        business_date, slot_number = classify_run_time(batch.created_at)
        Batch.objects.filter(pk=batch.pk).update(
            business_date=business_date,
            slot_number=slot_number,
        )


class Migration(migrations.Migration):

    dependencies = [
        ("app_documents", "0033_gddb_archive_completed_cases"),
    ]

    operations = [
        migrations.AddField(
            model_name="collateralregistrationimportbatch",
            name="business_date",
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="collateralregistrationimportbatch",
            name="slot_number",
            field=models.PositiveSmallIntegerField(
                blank=True,
                choices=[(1, "09:00"), (2, "13:00"), (3, "16:00"), (4, "19:00")],
                null=True,
            ),
        ),
        migrations.AddIndex(
            model_name="collateralregistrationimportbatch",
            index=models.Index(
                fields=["business_date", "slot_number"],
                name="gddb_batch_slot_idx",
            ),
        ),
        migrations.RunPython(backfill_batch_slots, migrations.RunPython.noop),
    ]
