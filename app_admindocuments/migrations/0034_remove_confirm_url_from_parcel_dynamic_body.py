from django.db import migrations, models


URL_BODY_TEMPLATE = (
    "Hiện có {{parcel_count}} kiện từ {{primary_sender}}. "
    "Liên hệ lễ tân để nhận. Xác nhận tại đây: {{confirm_url}}"
)

PLAIN_BODY_TEMPLATE = (
    "Hiện có {{parcel_count}} kiện từ {{primary_sender}}. "
    "Liên hệ lễ tân để nhận và bấm nút bên dưới để xác nhận."
)


def update_parcel_dynamic_body(apps, schema_editor):
    Template = apps.get_model("app_admindocuments", "AdmParcelDynamicTemplate")
    Template.objects.filter(
        template_type="parcel_notify_confirm",
        body_template=URL_BODY_TEMPLATE,
    ).update(body_template=PLAIN_BODY_TEMPLATE)


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("app_admindocuments", "0033_update_parcel_dynamic_body_template"),
    ]

    operations = [
        migrations.AlterField(
            model_name="admparceldynamictemplate",
            name="body_template",
            field=models.TextField(
                default=(
                    "Hiện có {{parcel_count}} kiện từ {{primary_sender}}. "
                    "Liên hệ lễ tân để nhận và bấm nút bên dưới để xác nhận."
                )
            ),
        ),
        migrations.RunPython(update_parcel_dynamic_body, noop_reverse),
    ]
