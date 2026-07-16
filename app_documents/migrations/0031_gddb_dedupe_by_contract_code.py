import hashlib

from django.db import migrations


def _normalize(value):
    return "".join(str(value or "").strip().upper().split())


def _hash(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def migrate_dedupe_keys(apps, schema_editor):
    Registration = apps.get_model("app_documents", "CollateralRegistration")
    groups = {}
    for registration in Registration.objects.all().iterator():
        normalized_contract = _normalize(registration.contract_code)
        if not normalized_contract:
            normalized_contract = f"EMPTY|{registration.pk}"
        groups.setdefault(normalized_contract, []).append(registration)

    for normalized_contract, registrations in groups.items():
        registrations.sort(
            key=lambda item: (
                item.gddb_status == "registered",
                not item.is_duplicate,
                item.updated_at,
                item.pk,
            ),
            reverse=True,
        )
        canonical = registrations[0]
        Registration.objects.filter(pk=canonical.pk).update(
            dedupe_key=_hash(normalized_contract),
            is_duplicate=False,
            duplicate_of_id=None,
        )
        for duplicate in registrations[1:]:
            Registration.objects.filter(pk=duplicate.pk).update(
                dedupe_key=_hash(
                    f"DUPLICATE|{duplicate.pk}|{normalized_contract}"
                ),
                is_duplicate=True,
                duplicate_of_id=canonical.pk,
            )


class Migration(migrations.Migration):

    dependencies = [
        ("app_documents", "0030_folder_appointment"),
    ]

    operations = [
        migrations.RunPython(migrate_dedupe_keys, migrations.RunPython.noop),
    ]
