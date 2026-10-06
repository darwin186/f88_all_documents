import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


def seed_codes(apps, schema_editor):
    Code = apps.get_model("app_document_campaigns", "RiskErrorCode")
    for order, (name, source, code) in enumerate([
        ("Lỗi chứng từ không hợp lệ – Thiếu bộ đóng", "File duyệt", "D10.2.4"),
        ("Lỗi chứng từ không hợp lệ – Thiếu bộ mở", "File duyệt", "D8.1"),
        ("Lỗi thiếu quyển – tính theo HĐ", "File nhận", "D10.12.1"),
    ], 1):
        Code.objects.get_or_create(code=code, defaults={"name": name, "source": source, "sort_order": order})


class Migration(migrations.Migration):
    dependencies = [
        ("app_document_campaigns", "0020_campaign_area_email_config"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]
    operations = [
        migrations.CreateModel(
            name="RiskErrorCode",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=500)),
                ("source", models.CharField(blank=True, default="", max_length=100)),
                ("code", models.CharField(max_length=50, unique=True)),
                ("is_active", models.BooleanField(default=True)),
                ("sort_order", models.PositiveIntegerField(default=0)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={"db_table": "dec_risk_error_code", "ordering": ["sort_order", "code"]},
        ),
        migrations.CreateModel(
            name="CampaignErrorBooking",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("note", models.TextField(blank=True, max_length=2000)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("error", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="risk_booking", to="app_document_campaigns.campaignerror")),
                ("mapped_by", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="document_campaign_risk_mappings", to=settings.AUTH_USER_MODEL)),
                ("risk_code", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="campaign_bookings", to="app_document_campaigns.riskerrorcode")),
            ],
            options={"db_table": "dec_campaign_error_booking"},
        ),
        migrations.RunPython(seed_codes, migrations.RunPython.noop),
    ]
