import uuid

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("app_document_campaigns", "0029_area_confirmation_boolean"),
    ]

    operations = [
        migrations.CreateModel(
            name="CampaignEmailBatch",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("email_type", models.CharField(choices=[("pgd_response", "Gửi PGD phản hồi"), ("area_monitoring", "QLKV theo dõi"), ("area_confirmation", "QLKV xác nhận"), ("shop_submission_receipt", "Xác nhận PGD đã gửi")], max_length=32)),
                ("status", models.CharField(choices=[("queued", "Chờ gửi"), ("dispatching", "Đang chuyển"), ("accepted", "Power Automate đã nhận"), ("processing", "Đang gửi"), ("completed", "Hoàn tất"), ("partially_failed", "Hoàn tất một phần"), ("failed", "Thất bại"), ("cancelled", "Đã hủy")], db_index=True, default="queued", max_length=24)),
                ("idempotency_key", models.CharField(max_length=255, unique=True)),
                ("total_count", models.PositiveIntegerField(default=0)),
                ("accepted_count", models.PositiveIntegerField(default=0)),
                ("sent_count", models.PositiveIntegerField(default=0)),
                ("failed_count", models.PositiveIntegerField(default=0)),
                ("skipped_count", models.PositiveIntegerField(default=0)),
                ("provider_batch_id", models.CharField(blank=True, max_length=255)),
                ("queued_at", models.DateTimeField(default=django.utils.timezone.now)),
                ("submitted_at", models.DateTimeField(blank=True, null=True)),
                ("completed_at", models.DateTimeField(blank=True, null=True)),
                ("last_error_code", models.CharField(blank=True, max_length=100)),
                ("last_error_message", models.CharField(blank=True, max_length=500)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("campaign", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="email_batches", to="app_document_campaigns.campaign")),
                ("requested_by", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="document_campaign_email_batches", to=settings.AUTH_USER_MODEL)),
            ],
            options={"db_table": "dec_campaign_email_batch"},
        ),
        migrations.CreateModel(
            name="CampaignEmailDelivery",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("target_type", models.CharField(choices=[("shop", "Phòng giao dịch"), ("area_manager", "Quản lý khu vực")], max_length=20)),
                ("target_id", models.PositiveBigIntegerField()),
                ("to_emails", models.JSONField(default=list)),
                ("cc_emails", models.JSONField(blank=True, default=list)),
                ("bcc_emails", models.JSONField(blank=True, default=list)),
                ("from_email", models.EmailField(max_length=254)),
                ("from_name", models.CharField(blank=True, max_length=200)),
                ("rendered_subject", models.CharField(max_length=500)),
                ("rendered_body_redacted", models.TextField(blank=True)),
                ("encrypted_payload", models.TextField(blank=True)),
                ("template_version", models.PositiveIntegerField(default=1)),
                ("idempotency_key", models.CharField(max_length=255, unique=True)),
                ("status", models.CharField(choices=[("queued", "Chờ gửi"), ("submitting", "Đang chuyển"), ("accepted", "Power Automate đã nhận"), ("sent", "Đã gửi"), ("failed", "Thất bại"), ("skipped", "Bỏ qua"), ("cancelled", "Đã hủy")], db_index=True, default="queued", max_length=16)),
                ("attempt_count", models.PositiveIntegerField(default=0)),
                ("provider_batch_id", models.CharField(blank=True, max_length=255)),
                ("provider_message_id", models.CharField(blank=True, max_length=255)),
                ("accepted_at", models.DateTimeField(blank=True, null=True)),
                ("sent_at", models.DateTimeField(blank=True, null=True)),
                ("failed_at", models.DateTimeField(blank=True, null=True)),
                ("error_code", models.CharField(blank=True, max_length=100)),
                ("error_message", models.CharField(blank=True, max_length=500)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("area_access_link", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="transport_deliveries", to="app_document_campaigns.areamanageraccesslink")),
                ("batch", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="deliveries", to="app_document_campaigns.campaignemailbatch")),
                ("legacy_shop_delivery", models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="transport_delivery", to="app_document_campaigns.shopemaildelivery")),
                ("shop_access_link", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="transport_deliveries", to="app_document_campaigns.shopaccesslink")),
            ],
            options={"db_table": "dec_campaign_email_delivery"},
        ),
        migrations.CreateModel(
            name="CampaignEmailAttempt",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("attempt_number", models.PositiveIntegerField()),
                ("request_id", models.UUIDField(default=uuid.uuid4, editable=False)),
                ("http_status", models.PositiveSmallIntegerField(blank=True, null=True)),
                ("provider_batch_id", models.CharField(blank=True, max_length=255)),
                ("outcome", models.CharField(choices=[("accepted", "Đã nhận"), ("rejected", "Bị từ chối"), ("timeout", "Timeout"), ("transport_error", "Lỗi kết nối")], max_length=20)),
                ("duration_ms", models.PositiveIntegerField(default=0)),
                ("error_code", models.CharField(blank=True, max_length=100)),
                ("error_message", models.CharField(blank=True, max_length=500)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("delivery", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="attempts", to="app_document_campaigns.campaignemaildelivery")),
            ],
            options={"db_table": "dec_campaign_email_attempt"},
        ),
        migrations.CreateModel(
            name="CampaignEmailWebhookEvent",
            fields=[
                ("event_id", models.UUIDField(editable=False, primary_key=True, serialize=False)),
                ("received_at", models.DateTimeField(auto_now_add=True)),
                ("payload_digest", models.CharField(max_length=64)),
                ("processed_at", models.DateTimeField(blank=True, null=True)),
                ("status", models.CharField(choices=[("processed", "Đã xử lý"), ("rejected", "Bị từ chối")], max_length=12)),
                ("message", models.CharField(blank=True, max_length=500)),
                ("batch", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="webhook_events", to="app_document_campaigns.campaignemailbatch")),
            ],
            options={"db_table": "dec_campaign_email_webhook_event"},
        ),
        migrations.AddIndex(model_name="campaignemailbatch", index=models.Index(fields=["campaign", "-created_at"], name="dec_email_batch_campaign_idx")),
        migrations.AddIndex(model_name="campaignemaildelivery", index=models.Index(fields=["batch", "status"], name="dec_email_delivery_batch_idx")),
        migrations.AddConstraint(model_name="campaignemailattempt", constraint=models.UniqueConstraint(fields=("delivery", "attempt_number"), name="dec_uq_email_attempt")),
    ]
