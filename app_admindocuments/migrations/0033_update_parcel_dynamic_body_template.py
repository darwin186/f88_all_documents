from django.db import migrations, models


OLD_BODY_TEMPLATE = (
    "Hiện có {{parcel_count}} kiện từ {{primary_sender}}. "
    "Liên hệ lễ tân để nhận và bấm nút bên dưới để xác nhận."
)

NEW_BODY_TEMPLATE = (
    "Hiện có {{parcel_count}} kiện từ {{primary_sender}}. "
    "Liên hệ lễ tân để nhận. Xác nhận tại đây: {{confirm_url}}"
)


def update_default_parcel_dynamic_body(apps, schema_editor):
    Template = apps.get_model("app_admindocuments", "AdmParcelDynamicTemplate")
    Template.objects.filter(
        template_type="parcel_notify_confirm",
        body_template=OLD_BODY_TEMPLATE,
    ).update(body_template=NEW_BODY_TEMPLATE)


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("app_admindocuments", "0032_cleanup_legacy_incoming_dispatch_statuses"),
    ]

    operations = [
        migrations.AlterField(
            model_name="admparceldynamictemplate",
            name="body_template",
            field=models.TextField(
                default=(
                    "Hiện có {{parcel_count}} kiện từ {{primary_sender}}. "
                    "Liên hệ lễ tân để nhận. Xác nhận tại đây: {{confirm_url}}"
                )
            ),
        ),
        migrations.RunPython(update_default_parcel_dynamic_body, noop_reverse),
    ]
