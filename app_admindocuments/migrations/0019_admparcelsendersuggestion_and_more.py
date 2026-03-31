# Generated manually for parcel workflow refactor.

import datetime
import uuid

import app_admindocuments.models
import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models


def backfill_parcel_receipt_schema(apps, schema_editor):
    ParcelReceipt = apps.get_model("app_admindocuments", "AdmParcelReceipt")
    ParcelSenderSuggestion = apps.get_model("app_admindocuments", "AdmParcelSenderSuggestion")
    ParcelReceiptLog = apps.get_model("app_admindocuments", "AdmParcelReceiptLog")

    for idx, name in enumerate(["Viettel post", "247Express", "Vnpost", "Newpost"], start=1):
        ParcelSenderSuggestion.objects.get_or_create(
            name=name,
            defaults={"sort_order": idx, "is_active": True},
        )

    for parcel in ParcelReceipt.objects.all().order_by("id"):
        received_at = parcel.created_at or django.utils.timezone.now()
        if getattr(parcel, "received_date", None) and getattr(parcel, "created_at", None):
            received_at = datetime.datetime.combine(
                parcel.received_date,
                parcel.created_at.time(),
            )
        elif getattr(parcel, "received_date", None):
            received_at = datetime.datetime.combine(
                parcel.received_date,
                datetime.time(0, 0, 0),
            )

        first_department = (
            parcel.processing_departments.order_by("id").values_list("name", flat=True).first()
            if hasattr(parcel, "processing_departments")
            else ""
        ) or ""

        parcel.sender_unit = getattr(parcel, "sending_unit", "") or ""
        parcel.content = (getattr(parcel, "summary", "") or "")[:255]
        parcel.received_at = received_at
        parcel.received_by_id = getattr(parcel, "responsible_user_id", None)
        parcel.recipient_department = first_department
        parcel.parcel_type = "khac"
        parcel.confirmation_token = uuid.uuid4().hex
        if parcel.status_id == "pkg_at_clerical":
            parcel.notified_at = parcel.created_at
        elif parcel.status_id == "pkg_processing":
            parcel.notified_at = parcel.created_at
            parcel.completed_at = parcel.updated_at or parcel.created_at

        parcel.save(
            update_fields=[
                "sender_unit",
                "content",
                "received_at",
                "received_by",
                "recipient_department",
                "parcel_type",
                "confirmation_token",
                "notified_at",
                "completed_at",
                "updated_at",
            ]
        )

        ParcelReceiptLog.objects.create(
            parcel_receipt_id=parcel.id,
            action="created",
            actor_id=getattr(parcel, "responsible_user_id", None),
            to_status_id=parcel.status_id,
            note="Backfill từ dữ liệu tiếp nhận cũ.",
            metadata={},
        )
        if parcel.notified_at:
            ParcelReceiptLog.objects.create(
                parcel_receipt_id=parcel.id,
                action="notified",
                actor_id=getattr(parcel, "responsible_user_id", None),
                from_status_id="pkg_received",
                to_status_id="pkg_at_clerical",
                note="Backfill trạng thái đã thông báo.",
                metadata={},
            )
        if parcel.completed_at:
            ParcelReceiptLog.objects.create(
                parcel_receipt_id=parcel.id,
                action="confirmed",
                actor_id=getattr(parcel, "responsible_user_id", None),
                from_status_id="pkg_at_clerical",
                to_status_id="pkg_processing",
                note="Backfill trạng thái hoàn tất.",
                metadata={},
            )


def update_parcel_status_labels(apps, schema_editor):
    Status = apps.get_model("app_admindocuments", "AdmIncomingDispatchStatus")
    updates = {
        "pkg_received": "Lễ tân tiếp nhận",
        "pkg_at_clerical": "Đã thông báo",
        "pkg_processing": "Hoàn tất",
    }
    for code, name in updates.items():
        Status.objects.filter(code=code).update(name=name, is_active=True)


class Migration(migrations.Migration):

    dependencies = [
        ("app_documents", "0019_user_presence_hourly_and_daily_fields"),
        ("app_admindocuments", "0018_admparcelreceipt_admparcelreceiptimage"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="AdmParcelSenderSuggestion",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=255, unique=True)),
                ("is_active", models.BooleanField(default=True)),
                ("sort_order", models.PositiveIntegerField(default=0)),
            ],
            options={
                "verbose_name": "Parcel Sender Suggestion",
                "verbose_name_plural": "Parcel Sender Suggestions",
                "db_table": "adm_parcel_sender_suggestion",
                "ordering": ["sort_order", "name"],
            },
        ),
        migrations.AddField(
            model_name="admparcelreceipt",
            name="actual_receiver_employee_code",
            field=models.CharField(blank=True, max_length=50),
        ),
        migrations.AddField(
            model_name="admparcelreceipt",
            name="actual_receiver_name",
            field=models.CharField(blank=True, max_length=255),
        ),
        migrations.AddField(
            model_name="admparcelreceipt",
            name="completed_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="admparcelreceipt",
            name="confirmation_token",
            field=models.CharField(blank=True, default="", editable=False, max_length=64),
        ),
        migrations.AddField(
            model_name="admparcelreceipt",
            name="content",
            field=models.CharField(blank=True, max_length=255),
        ),
        migrations.AddField(
            model_name="admparcelreceipt",
            name="notification_schedule",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="adm_parcel_receipt_notification_schedule", to="app_documents.gaposcheduledmessage"),
        ),
        migrations.AddField(
            model_name="admparcelreceipt",
            name="notified_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="admparcelreceipt",
            name="parcel_type",
            field=models.CharField(choices=[("hoso", "Hồ sơ"), ("hanghoa", "Hàng hóa"), ("khac", "Khác")], default="khac", max_length=20),
        ),
        migrations.AddField(
            model_name="admparcelreceipt",
            name="proxy_qr_token",
            field=models.CharField(blank=True, max_length=64, null=True, unique=True),
        ),
        migrations.AddField(
            model_name="admparcelreceipt",
            name="proxy_receiver_name",
            field=models.CharField(blank=True, max_length=255),
        ),
        migrations.AddField(
            model_name="admparcelreceipt",
            name="received_at",
            field=models.DateTimeField(blank=True, db_index=True, default=django.utils.timezone.now, editable=False, null=True),
        ),
        migrations.AddField(
            model_name="admparcelreceipt",
            name="received_by",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="adm_parcel_receipt_received_by", to=settings.AUTH_USER_MODEL),
        ),
        migrations.AddField(
            model_name="admparcelreceipt",
            name="recipient_department",
            field=models.CharField(blank=True, db_index=True, default="", max_length=100),
        ),
        migrations.AddField(
            model_name="admparcelreceipt",
            name="recipient_user",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="adm_parcel_receipt_recipient_user", to=settings.AUTH_USER_MODEL),
        ),
        migrations.AddField(
            model_name="admparcelreceipt",
            name="reminded_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="admparcelreceipt",
            name="reminder_schedule",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="adm_parcel_receipt_reminder_schedule", to="app_documents.gaposcheduledmessage"),
        ),
        migrations.AddField(
            model_name="admparcelreceipt",
            name="reminder_scheduled_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="admparcelreceipt",
            name="sender_unit",
            field=models.CharField(blank=True, default="", max_length=255),
        ),
        migrations.AddField(
            model_name="admparcelreceipt",
            name="tracking_code",
            field=models.CharField(blank=True, max_length=100),
        ),
        migrations.CreateModel(
            name="AdmParcelReceiptLog",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("action", models.CharField(choices=[("created", "Created"), ("notified", "Notified"), ("confirmed", "Confirmed"), ("proxy_registered", "Proxy Registered"), ("updated", "Updated")], max_length=30)),
                ("note", models.CharField(blank=True, max_length=255)),
                ("metadata", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("actor", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="adm_parcel_receipt_logs", to=settings.AUTH_USER_MODEL)),
                ("from_status", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="parcel_logs_from_status", to="app_admindocuments.admincomingdispatchstatus")),
                ("parcel_receipt", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="audit_logs", to="app_admindocuments.admparcelreceipt")),
                ("to_status", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="parcel_logs_to_status", to="app_admindocuments.admincomingdispatchstatus")),
            ],
            options={
                "verbose_name": "Parcel Receipt Log",
                "verbose_name_plural": "Parcel Receipt Logs",
                "db_table": "adm_parcel_receipt_log",
                "ordering": ["-created_at"],
            },
        ),
        migrations.RunPython(backfill_parcel_receipt_schema, migrations.RunPython.noop),
        migrations.RunPython(update_parcel_status_labels, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="admparcelreceipt",
            name="confirmation_token",
            field=models.CharField(default=app_admindocuments.models._parcel_token, editable=False, max_length=64, unique=True),
        ),
        migrations.RemoveField(model_name="admparcelreceipt", name="gapo_group"),
        migrations.RemoveField(model_name="admparcelreceipt", name="processing_departments"),
        migrations.RemoveField(model_name="admparcelreceipt", name="received_date"),
        migrations.RemoveField(model_name="admparcelreceipt", name="responsible_user"),
        migrations.RemoveField(model_name="admparcelreceipt", name="sending_unit"),
        migrations.RemoveField(model_name="admparcelreceipt", name="signer_name"),
        migrations.RemoveField(model_name="admparcelreceipt", name="summary"),
    ]
