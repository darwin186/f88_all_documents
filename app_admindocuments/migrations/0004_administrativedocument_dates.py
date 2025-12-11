from django.db import migrations, models


def seed_dates(apps, schema_editor):
    Document = apps.get_model("app_admindocuments", "AdmAdministrativeDocument")
    for doc in Document.objects.all():
        created_date = doc.created_at.date() if doc.created_at else None
        if created_date:
            if not doc.issue_date:
                doc.issue_date = created_date
            if not doc.effective_date:
                doc.effective_date = created_date
            doc.save(update_fields=["issue_date", "effective_date"])


class Migration(migrations.Migration):
    dependencies = [
        ("app_admindocuments", "0003_alter_admdocumentcounter_unique_together_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="admadministrativedocument",
            name="effective_date",
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="admadministrativedocument",
            name="issue_date",
            field=models.DateField(blank=True, null=True),
        ),
        migrations.RunPython(seed_dates, migrations.RunPython.noop),
    ]
