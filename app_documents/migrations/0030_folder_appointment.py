import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("app_documents", "0029_backfill_gddb_post_update_status"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="folder",
            name="folder_appointment",
            field=models.BooleanField(db_index=True, default=False),
        ),
        migrations.AddField(
            model_name="folder",
            name="folder_appointment_date",
            field=models.DateField(blank=True, db_index=True, null=True),
        ),
        migrations.AddField(
            model_name="folder",
            name="folder_appointment_reason",
            field=models.TextField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="folder",
            name="folder_appointment_created_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="folder",
            name="folder_appointment_updated_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="folder",
            name="folder_appointment_resolved_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="folder",
            name="folder_appointment_created_by",
            field=models.ForeignKey(
                blank=True,
                db_column="folder_appointment_created_by",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="folder_appointments_created",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name="folder",
            name="folder_appointment_resolved_by",
            field=models.ForeignKey(
                blank=True,
                db_column="folder_appointment_resolved_by",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="folder_appointments_resolved",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.CreateModel(
            name="FolderAppointmentLog",
            fields=[
                ("appointment_log_id", models.AutoField(primary_key=True, serialize=False)),
                (
                    "action",
                    models.CharField(
                        choices=[
                            ("scheduled", "Tạo lịch hẹn"),
                            ("rescheduled", "Cập nhật lịch hẹn"),
                            ("received", "Đã nhận quyển"),
                            ("cancelled", "Hủy lịch hẹn"),
                        ],
                        max_length=30,
                    ),
                ),
                ("appointment_date", models.DateField(blank=True, null=True)),
                ("reason", models.TextField(blank=True, null=True)),
                ("event_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("metadata", models.JSONField(blank=True, default=dict)),
                (
                    "actor",
                    models.ForeignKey(
                        blank=True,
                        db_column="actor_id",
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="folder_appointment_logs",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "folder",
                    models.ForeignKey(
                        db_column="folder_id",
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="appointment_logs",
                        to="app_documents.folder",
                    ),
                ),
            ],
            options={
                "db_table": "f_FolderAppointmentLog",
                "ordering": ["-event_at", "-appointment_log_id"],
                "indexes": [
                    models.Index(fields=["folder", "event_at"], name="folder_appt_folder_event_idx"),
                    models.Index(fields=["action", "event_at"], name="folder_appt_action_event_idx"),
                ],
            },
        ),
    ]
