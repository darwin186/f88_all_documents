from datetime import date

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


HOLIDAYS = [
    (date(2025, 1, 1), "Tết Dương lịch 2025"),
    (date(2025, 1, 27), "Tết Nguyên đán 2025"),
    (date(2025, 1, 28), "Tết Nguyên đán 2025"),
    (date(2025, 1, 29), "Tết Nguyên đán 2025"),
    (date(2025, 1, 30), "Tết Nguyên đán 2025"),
    (date(2025, 1, 31), "Tết Nguyên đán 2025"),
    (date(2025, 4, 7), "Giỗ Tổ Hùng Vương 2025"),
    (date(2025, 4, 30), "Ngày Chiến thắng 30/4"),
    (date(2025, 5, 1), "Ngày Quốc tế Lao động"),
    (date(2025, 9, 1), "Nghỉ Quốc khánh 2025"),
    (date(2025, 9, 2), "Quốc khánh 2025"),
    (date(2026, 1, 1), "Tết Dương lịch 2026"),
    (date(2026, 2, 16), "Tết Nguyên đán 2026"),
    (date(2026, 2, 17), "Tết Nguyên đán 2026"),
    (date(2026, 2, 18), "Tết Nguyên đán 2026"),
    (date(2026, 2, 19), "Tết Nguyên đán 2026"),
    (date(2026, 2, 20), "Tết Nguyên đán 2026"),
    (date(2026, 4, 27), "Nghỉ bù Giỗ Tổ Hùng Vương 2026"),
    (date(2026, 4, 30), "Ngày Chiến thắng 30/4"),
    (date(2026, 5, 1), "Ngày Quốc tế Lao động"),
    (date(2026, 9, 1), "Nghỉ Quốc khánh 2026"),
    (date(2026, 9, 2), "Quốc khánh 2026"),
]


def seed_holidays(apps, schema_editor):
    Holiday = apps.get_model("app_documents", "CollateralRegistrationHoliday")
    Holiday.objects.bulk_create(
        [
            Holiday(
                holiday_date=holiday_date,
                holiday_name=holiday_name,
                note="Lịch nghỉ Việt Nam; Admin có thể điều chỉnh theo lịch vận hành F88.",
            )
            for holiday_date, holiday_name in HOLIDAYS
        ],
        ignore_conflicts=True,
    )


class Migration(migrations.Migration):

    dependencies = [
        ("app_documents", "0036_collateralregistration_asset_type"),
    ]

    operations = [
        migrations.CreateModel(
            name="CollateralRegistrationHoliday",
            fields=[
                ("holiday_id", models.AutoField(primary_key=True, serialize=False)),
                ("holiday_date", models.DateField(db_index=True, unique=True)),
                ("holiday_name", models.CharField(max_length=255)),
                ("is_active", models.BooleanField(db_index=True, default=True)),
                ("note", models.TextField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "created_by",
                    models.ForeignKey(
                        blank=True,
                        db_column="created_by",
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="gddb_holidays_created",
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
                        related_name="gddb_holidays_updated",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "db_table": "d_CollateralRegistrationHoliday",
                "ordering": ["holiday_date"],
            },
        ),
        migrations.RunPython(seed_holidays, migrations.RunPython.noop),
    ]
