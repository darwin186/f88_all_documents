from django.db import migrations


def update_parcel_status_labels(apps, schema_editor):
    Status = apps.get_model("app_admindocuments", "AdmIncomingDispatchStatus")

    updates = [
        ("pkg_received", "Lễ tân tiếp nhận", 6),
        ("pkg_at_clerical", "Đã thông báo", 7),
        ("pkg_processing", "Đã bàn giao", 8),
    ]

    for code, name, sort_order in updates:
        Status.objects.update_or_create(
            code=code,
            defaults={
                "name": name,
                "sort_order": sort_order,
                "is_active": True,
            },
        )


class Migration(migrations.Migration):

    dependencies = [
        ("app_admindocuments", "0016_admincomingdispatch_signer_role_and_more"),
    ]

    operations = [
        migrations.RunPython(update_parcel_status_labels, migrations.RunPython.noop),
    ]
