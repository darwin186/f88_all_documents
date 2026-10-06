import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("app_document_campaigns", "0015_campaign_area_manager_instructions"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="shopemaildelivery",
            name="attempt_count",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="shopemaildelivery",
            name="bcc_emails",
            field=models.JSONField(blank=True, default=list),
        ),
        migrations.AddField(
            model_name="shopemaildelivery",
            name="subject",
            field=models.CharField(blank=True, max_length=500),
        ),
        migrations.AddField(
            model_name="shopemaildelivery",
            name="template_version",
            field=models.PositiveIntegerField(default=1),
        ),
        migrations.CreateModel(
            name="CampaignEmailConfig",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("subject_template", models.CharField(default="{{campaign_code}} · {{campaign_name}}", max_length=500)),
                (
                    "body_template",
                    models.TextField(
                        default=(
                            "Kính gửi {{shop_name}},\n\n"
                            "Phòng giao dịch vui lòng kiểm tra và phản hồi chiến dịch {{campaign_name}}.\n"
                            "Hạn phản hồi: {{response_deadline}}\n"
                            "Link hết hạn: {{link_expires_at}}\n\n"
                            "Link phản hồi: {{response_url}}\n\n"
                            "Trân trọng."
                        )
                    ),
                ),
                ("from_name", models.CharField(blank=True, default="", max_length=200)),
                ("reply_to_email", models.EmailField(blank=True, default="", max_length=254)),
                ("cc_area_manager", models.BooleanField(default=True)),
                ("cc_emails", models.JSONField(blank=True, default=list)),
                ("bcc_emails", models.JSONField(blank=True, default=list)),
                ("support_email", models.EmailField(blank=True, default="", max_length=254)),
                ("template_version", models.PositiveIntegerField(default=1)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "campaign",
                    models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="email_config", to="app_document_campaigns.campaign"),
                ),
                (
                    "updated_by",
                    models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="document_campaign_email_configs_updated", to=settings.AUTH_USER_MODEL),
                ),
            ],
            options={"db_table": "dec_campaign_email_config"},
        ),
    ]
