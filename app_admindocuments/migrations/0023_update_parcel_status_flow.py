from django.db import migrations


def seed_parcel_status_flow(apps, schema_editor):
    Status = apps.get_model("app_admindocuments", "AdmIncomingDispatchStatus")
    status_specs = [
        ("pkg_received", "Lễ tân tiếp nhận", 1),
        ("pkg_at_clerical", "Đã thông báo", 2),
        ("pkg_processing", "Đã xác nhận", 3),
        ("pkg_done", "Đã bàn giao toàn bộ", 4),
    ]
    for code, name, sort_order in status_specs:
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
        ("app_admindocuments", "0022_admparcelreceipt_confirmed_at_and_more"),
    ]

    operations = [
        migrations.RunPython(seed_parcel_status_flow, migrations.RunPython.noop),
    ]
