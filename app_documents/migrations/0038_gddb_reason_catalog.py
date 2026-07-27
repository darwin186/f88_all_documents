from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


REASONS = {
    "registration": [
        "Đăng ký mới",
        "Đăng ký lại",
        "Bổ sung/thay đổi thông tin",
        "Khác",
    ],
    "non_registration": [
        "Hợp đồng hết hiệu lực",
        "Hợp đồng đã tất toán",
        "Hợp đồng không đủ điều kiện đăng ký",
        "Thông tin hợp đồng/tài sản không hợp lệ",
        "Trùng giao dịch bảo đảm",
        "Khác",
    ],
    "status_change": [
        "Thao tác nhầm",
        "TDTD/VH yêu cầu đăng ký bổ sung",
        "Điều chỉnh GDBD",
    ],
}


def seed_reasons(apps, schema_editor):
    Reason = apps.get_model("app_documents", "CollateralRegistrationReason")
    Reason.objects.bulk_create(
        [
            Reason(
                reason_type=reason_type,
                reason_text=reason_text,
                sort_order=index * 10,
            )
            for reason_type, reasons in REASONS.items()
            for index, reason_text in enumerate(reasons, start=1)
        ],
        ignore_conflicts=True,
    )


class Migration(migrations.Migration):

    dependencies = [
        ("app_documents", "0037_gddb_sla_holidays"),
    ]

    operations = [
        migrations.CreateModel(
            name="CollateralRegistrationReason",
            fields=[
                ("reason_id", models.AutoField(primary_key=True, serialize=False)),
                (
                    "reason_type",
                    models.CharField(
                        choices=[
                            ("registration", "Lý do/loại đăng ký"),
                            ("non_registration", "Lý do không đăng ký"),
                            ("status_change", "Lý do điều chỉnh trạng thái"),
                        ],
                        db_index=True,
                        max_length=30,
                    ),
                ),
                ("reason_text", models.CharField(max_length=255)),
                ("sort_order", models.PositiveIntegerField(default=0)),
                ("is_active", models.BooleanField(db_index=True, default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "created_by",
                    models.ForeignKey(
                        blank=True,
                        db_column="created_by",
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="gddb_reasons_created",
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
                        related_name="gddb_reasons_updated",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "db_table": "d_CollateralRegistrationReason",
                "ordering": ["reason_type", "sort_order", "reason_text"],
            },
        ),
        migrations.AddConstraint(
            model_name="collateralregistrationreason",
            constraint=models.UniqueConstraint(
                fields=("reason_type", "reason_text"),
                name="gddb_reason_type_text_uniq",
            ),
        ),
        migrations.RunPython(seed_reasons, migrations.RunPython.noop),
    ]
