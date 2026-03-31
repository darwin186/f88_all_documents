from django.db import migrations


def migrate_pending_signer_to_assistant(apps, schema_editor):
    Dispatch = apps.get_model("app_admindocuments", "AdmIncomingDispatch")
    Status = apps.get_model("app_admindocuments", "AdmIncomingDispatchStatus")

    Dispatch.objects.filter(status_id="doc_pending_signer").update(status_id="doc_at_assistant")
    Status.objects.filter(code="doc_pending_signer").update(is_active=False)


class Migration(migrations.Migration):
    dependencies = [
        ("app_admindocuments", "0027_admparcelautonotifysetting_reminder_send_times"),
    ]

    operations = [
        migrations.RunPython(migrate_pending_signer_to_assistant, migrations.RunPython.noop),
    ]
