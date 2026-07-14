from django.db import migrations
from django.db.models import Q


def backfill_post_update_status(apps, schema_editor):
    registration_model = apps.get_model("app_documents", "CollateralRegistration")
    labels = {
        "pending": "Chưa đăng kí",
        "registered": "Đã đăng kí",
        "not_registered": "Không đăng kí",
    }
    blank_status = Q(post_update_status__isnull=True) | Q(post_update_status="")
    for status, label in labels.items():
        registration_model.objects.filter(blank_status, gddb_status=status).update(post_update_status=label)


class Migration(migrations.Migration):

    dependencies = [
        ("app_documents", "0028_alter_collateralregistration_gddb_status"),
    ]

    operations = [
        migrations.RunPython(backfill_post_update_status, migrations.RunPython.noop),
    ]
