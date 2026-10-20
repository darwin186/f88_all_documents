from django.core.validators import RegexValidator
from django.db import migrations, models


def seed_status_colors(apps, schema_editor):
    Status = apps.get_model("app_admindocuments", "AdmDocumentStatus")
    palette = {
        "100": ("#B45309", "#FFFBEB"),
        "101": ("#1D4ED8", "#EFF6FF"),
        "102": ("#047857", "#ECFDF5"),
        "103": ("#6B7280", "#F3F4F6"),
    }
    for code, (text, background) in palette.items():
        Status.objects.using(schema_editor.connection.alias).filter(code=code).update(
            badge_text_color=text, badge_bg_color=background,
        )


class Migration(migrations.Migration):
    dependencies = [
        ("app_admindocuments", "0037_admadministrativedocument_number_suffix_and_more"),
    ]
    operations = [
        migrations.AddField(
            model_name="admdocumentstatus", name="badge_text_color",
            field=models.CharField(default="#374151", max_length=7, validators=[
                RegexValidator(r"^#[0-9a-fA-F]{6}$", "Nhập màu theo định dạng #RRGGBB."),
            ]),
        ),
        migrations.AddField(
            model_name="admdocumentstatus", name="badge_bg_color",
            field=models.CharField(default="#F3F4F6", max_length=7, validators=[
                RegexValidator(r"^#[0-9a-fA-F]{6}$", "Nhập màu theo định dạng #RRGGBB."),
            ]),
        ),
        migrations.RunPython(seed_status_colors, migrations.RunPython.noop),
    ]
