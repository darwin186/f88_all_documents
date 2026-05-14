from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("app_workshift", "0003_add_min_hours_per_shift"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="WorkShiftTemplate",
            fields=[
                ("template_id", models.AutoField(primary_key=True, serialize=False)),
                ("template_name", models.CharField(max_length=100)),
                ("start_time", models.TimeField()),
                ("end_time", models.TimeField()),
                ("sort_order", models.PositiveSmallIntegerField(default=0)),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "created_by",
                    models.ForeignKey(
                        blank=True,
                        db_column="created_by",
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="work_shift_templates_created",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "updated_by",
                    models.ForeignKey(
                        blank=True,
                        db_column="updated_by",
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="work_shift_templates_updated",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "db_table": "d_WorkShiftTemplate",
                "ordering": ["sort_order", "start_time", "template_name"],
            },
        ),
    ]
