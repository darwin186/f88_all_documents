# Generated manually for GDDB collateral registration tracking.

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("app_documents", "0024_borrowrequest_gapo_contact"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="CollateralRegistrationImportBatch",
            fields=[
                ("batch_id", models.AutoField(primary_key=True, serialize=False)),
                ("source_type", models.CharField(default="api", max_length=30)),
                ("source_url", models.TextField(blank=True, null=True)),
                ("total_rows", models.PositiveIntegerField(default=0)),
                ("created_rows", models.PositiveIntegerField(default=0)),
                ("updated_rows", models.PositiveIntegerField(default=0)),
                ("skipped_rows", models.PositiveIntegerField(default=0)),
                ("duplicate_rows", models.PositiveIntegerField(default=0)),
                ("error_rows", models.PositiveIntegerField(default=0)),
                ("summary", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "created_by",
                    models.ForeignKey(
                        blank=True,
                        db_column="created_by",
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "db_table": "f_CollateralRegistrationImportBatch",
                "ordering": ["-created_at"],
            },
        ),
        migrations.CreateModel(
            name="CollateralRegistration",
            fields=[
                ("registration_id", models.AutoField(primary_key=True, serialize=False)),
                ("contract_code", models.CharField(max_length=50)),
                ("license_plate", models.CharField(blank=True, max_length=50, null=True)),
                ("chassis_number", models.CharField(blank=True, max_length=100, null=True)),
                ("engine_number", models.CharField(blank=True, max_length=100, null=True)),
                (
                    "gddb_status",
                    models.CharField(
                        choices=[("pending", "Chưa đăng kí"), ("registered", "Đã đăng kí")],
                        default="pending",
                        max_length=30,
                    ),
                ),
                ("contract_status", models.CharField(blank=True, max_length=100, null=True)),
                ("source_created_date", models.DateField(blank=True, null=True)),
                ("disbursement_date", models.DateField(blank=True, null=True)),
                ("shop_name", models.CharField(blank=True, max_length=255, null=True)),
                ("disbursement_source", models.CharField(blank=True, max_length=255, null=True)),
                ("post_update_status", models.CharField(blank=True, max_length=255, null=True)),
                ("postmini_updated", models.CharField(blank=True, max_length=255, null=True)),
                ("source_user", models.CharField(blank=True, max_length=255, null=True)),
                ("reason", models.TextField(blank=True, null=True)),
                ("note", models.TextField(blank=True, null=True)),
                ("previous_application_no", models.CharField(blank=True, max_length=100, null=True)),
                ("previous_registration_date", models.DateField(blank=True, null=True)),
                ("registered_by_name", models.CharField(blank=True, max_length=255, null=True)),
                ("it_ticket_code", models.CharField(blank=True, max_length=255, null=True)),
                ("pgd_note", models.TextField(blank=True, null=True)),
                ("is_duplicate", models.BooleanField(default=False)),
                ("source_system", models.CharField(blank=True, max_length=100, null=True)),
                ("external_ref", models.CharField(blank=True, max_length=100, null=True)),
                ("raw_payload", models.JSONField(blank=True, default=dict)),
                ("dedupe_key", models.CharField(editable=False, max_length=64, unique=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("registered_at", models.DateTimeField(blank=True, null=True)),
                (
                    "created_by",
                    models.ForeignKey(
                        blank=True,
                        db_column="created_by",
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="gddb_created",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "duplicate_of",
                    models.ForeignKey(
                        blank=True,
                        db_column="duplicate_of_id",
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="duplicate_records",
                        to="app_documents.collateralregistration",
                    ),
                ),
                (
                    "import_batch",
                    models.ForeignKey(
                        blank=True,
                        db_column="batch_id",
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="registrations",
                        to="app_documents.collateralregistrationimportbatch",
                    ),
                ),
                (
                    "registered_by",
                    models.ForeignKey(
                        blank=True,
                        db_column="registered_by",
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="gddb_registered",
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
                        related_name="gddb_updated",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "db_table": "f_CollateralRegistration",
                "ordering": ["-created_at"],
            },
        ),
        migrations.CreateModel(
            name="CollateralRegistrationLog",
            fields=[
                ("log_id", models.AutoField(primary_key=True, serialize=False)),
                ("action", models.CharField(max_length=50)),
                ("from_status", models.CharField(blank=True, max_length=30, null=True)),
                ("to_status", models.CharField(blank=True, max_length=30, null=True)),
                ("note", models.TextField(blank=True, null=True)),
                ("metadata", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "created_by",
                    models.ForeignKey(
                        blank=True,
                        db_column="created_by",
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="gddb_logs",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "registration",
                    models.ForeignKey(
                        db_column="registration_id",
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="logs",
                        to="app_documents.collateralregistration",
                    ),
                ),
            ],
            options={
                "db_table": "f_CollateralRegistrationLog",
                "ordering": ["-created_at"],
            },
        ),
        migrations.AddIndex(
            model_name="collateralregistration",
            index=models.Index(fields=["gddb_status", "is_duplicate"], name="f_Collater_gddb_st_273f8a_idx"),
        ),
        migrations.AddIndex(
            model_name="collateralregistration",
            index=models.Index(fields=["contract_code"], name="f_Collater_contrac_707ecf_idx"),
        ),
        migrations.AddIndex(
            model_name="collateralregistration",
            index=models.Index(fields=["license_plate"], name="f_Collater_license_a62446_idx"),
        ),
        migrations.AddIndex(
            model_name="collateralregistration",
            index=models.Index(fields=["chassis_number"], name="f_Collater_chassis_1d68d4_idx"),
        ),
        migrations.AddIndex(
            model_name="collateralregistration",
            index=models.Index(fields=["engine_number"], name="f_Collater_engine__88e34f_idx"),
        ),
    ]
