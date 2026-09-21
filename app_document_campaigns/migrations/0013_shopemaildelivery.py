import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("app_document_campaigns", "0012_shopaccesslink_has_deadline_extension")]
    operations = [migrations.CreateModel(
        name="ShopEmailDelivery",
        fields=[
            ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
            ("area_email", models.EmailField(blank=True, max_length=254)),
            ("to_email", models.EmailField(blank=True, max_length=254)),
            ("cc_emails", models.JSONField(blank=True, default=list)),
            ("status", models.CharField(choices=[("queued", "Chờ gửi"), ("sending", "Đang gửi"), ("sent", "Đã gửi"), ("failed", "Gửi thất bại"), ("skipped", "Không gửi")], db_index=True, default="queued", max_length=12)),
            ("message", models.CharField(blank=True, max_length=500)),
            ("created_at", models.DateTimeField(auto_now_add=True)),
            ("finished_at", models.DateTimeField(blank=True, null=True)),
            ("area_manager", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to="app_documents.areamanager")),
            ("link", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="email_deliveries", to="app_document_campaigns.shopaccesslink")),
        ],
        options={"db_table": "dec_shop_email_delivery"},
    )]
