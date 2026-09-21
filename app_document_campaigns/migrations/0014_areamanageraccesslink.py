import django.db.models.deletion
import uuid
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("app_document_campaigns", "0013_shopemaildelivery"),
        ("app_documents", "0041_shopcatalogjob_one_active"),
    ]
    operations = [
        migrations.CreateModel(
            name="AreaManagerAccessLink",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("public_id", models.UUIDField(default=uuid.uuid4, editable=False, unique=True)),
                ("allowed_email", models.EmailField(max_length=254)),
                ("token_digest", models.CharField(editable=False, max_length=64, unique=True)),
                ("expires_at", models.DateTimeField()),
                ("revoked_at", models.DateTimeField(blank=True, null=True)),
                ("last_accessed_at", models.DateTimeField(blank=True, null=True)),
                ("email_status", models.CharField(choices=[("not_sent", "Chưa gửi"), ("queued", "Chờ gửi"), ("sent", "Đã gửi"), ("failed", "Gửi thất bại")], default="not_sent", max_length=12)),
                ("email_message", models.CharField(blank=True, max_length=500)),
                ("emailed_at", models.DateTimeField(blank=True, null=True)),
                ("area_manager", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="document_campaign_links", to="app_documents.areamanager")),
                ("campaign", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="area_manager_links", to="app_document_campaigns.campaign")),
                ("created_by", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="document_campaign_area_links_created", to=settings.AUTH_USER_MODEL)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={"db_table": "dec_area_manager_access_link"},
        ),
        migrations.AddConstraint(
            model_name="areamanageraccesslink",
            constraint=models.UniqueConstraint(fields=("campaign", "area_manager"), name="dec_uq_campaign_area_link"),
        ),
    ]
