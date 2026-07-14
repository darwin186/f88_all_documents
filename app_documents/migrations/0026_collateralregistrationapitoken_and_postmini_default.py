import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


def set_default_postmini_status(apps, schema_editor):
    registration = apps.get_model("app_documents", "CollateralRegistration")
    registration.objects.filter(postmini_updated__isnull=True).update(postmini_updated="Chưa cập nhật")
    registration.objects.filter(postmini_updated="").update(postmini_updated="Chưa cập nhật")


def enable_checker_gddb_screen(apps, schema_editor):
    ui_permission = apps.get_model("app_documents", "UiPermission")
    ui_permission.objects.filter(
        screen__screen_key="gddb_registration",
        role_code="checker",
    ).update(can_view=True)


class Migration(migrations.Migration):

    dependencies = [
        ("app_documents", "0025_collateral_registration"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="CollateralRegistrationApiToken",
            fields=[
                ("token_id", models.AutoField(primary_key=True, serialize=False)),
                ("name", models.CharField(max_length=100)),
                ("token_hash", models.CharField(editable=False, max_length=64, unique=True)),
                ("token_prefix", models.CharField(editable=False, max_length=16)),
                ("is_active", models.BooleanField(default=True)),
                ("last_used_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("revoked_at", models.DateTimeField(blank=True, null=True)),
                (
                    "created_by",
                    models.ForeignKey(
                        db_column="created_by",
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="gddb_api_tokens_created",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "owner",
                    models.ForeignKey(
                        db_column="owner_id",
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="gddb_api_tokens",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "revoked_by",
                    models.ForeignKey(
                        blank=True,
                        db_column="revoked_by",
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="gddb_api_tokens_revoked",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "db_table": "f_CollateralRegistrationApiToken",
                "ordering": ["-created_at"],
            },
        ),
        migrations.RunPython(set_default_postmini_status, migrations.RunPython.noop),
        migrations.RunPython(enable_checker_gddb_screen, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="collateralregistration",
            name="postmini_updated",
            field=models.CharField(blank=True, default="Chưa cập nhật", max_length=255),
        ),
    ]
