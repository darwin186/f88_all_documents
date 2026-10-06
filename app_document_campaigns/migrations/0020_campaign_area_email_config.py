import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("app_document_campaigns", "0019_area_confirmation_by_link"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="CampaignAreaEmailConfig",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("monitoring_subject_template", models.CharField(default="{{campaign_code}} · Theo dõi phản hồi PGD", max_length=500)),
                ("monitoring_body_template", models.TextField(default="Kính gửi {{area_manager_name}},\n\nAnh/chị vui lòng theo dõi phản hồi của các PGD thuộc khu vực trong kỳ {{report_month}}.\nLink theo dõi: {{manager_url}}\nLink hết hạn: {{link_expires_at}}\n\nTrân trọng.")),
                ("confirmation_subject_template", models.CharField(default="{{campaign_code}} · Xác nhận kết quả book lỗi", max_length=500)),
                ("confirmation_body_template", models.TextField(default="Kính gửi {{area_manager_name}},\n\nAnh/chị vui lòng kiểm tra và xác nhận kết quả Team review cho kỳ {{report_month}}.\nLink xác nhận: {{manager_url}}\nLink hết hạn: {{link_expires_at}}\n\nTrân trọng.")),
                ("from_name", models.CharField(blank=True, default="", max_length=200)),
                ("cc_emails", models.JSONField(blank=True, default=list)),
                ("bcc_emails", models.JSONField(blank=True, default=list)),
                ("support_email", models.EmailField(blank=True, default="", max_length=254)),
                ("template_version", models.PositiveIntegerField(default=1)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("campaign", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="area_email_config", to="app_document_campaigns.campaign")),
                ("updated_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="document_campaign_area_email_configs_updated", to=settings.AUTH_USER_MODEL)),
            ],
            options={"db_table": "dec_campaign_area_email_config"},
        ),
    ]
