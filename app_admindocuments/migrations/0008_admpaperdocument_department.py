from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("app_admindocuments", "0007_void_flags"),
    ]

    operations = [
        migrations.AddField(
            model_name="admpaperdocument",
            name="department",
            field=models.ForeignKey(
                blank=True,
                help_text="Phòng ban nội bộ phụ trách",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                to="app_admindocuments.admdepartment",
            ),
        ),
    ]
