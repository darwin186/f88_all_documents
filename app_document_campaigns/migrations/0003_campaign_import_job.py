import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("app_document_campaigns", "0002_campaign_import_staging"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="CampaignImportJob",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("job_type", models.CharField(choices=[("sql_stage", "Truy xuất dữ liệu SQL")], default="sql_stage", max_length=30)),
                ("status", models.CharField(choices=[("queued", "Đang chờ"), ("running", "Đang chạy"), ("succeeded", "Thành công"), ("failed", "Thất bại")], db_index=True, default="queued", max_length=20)),
                ("current_step", models.PositiveSmallIntegerField(default=0)),
                ("total_steps", models.PositiveSmallIntegerField(default=2)),
                ("summary", models.JSONField(blank=True, default=dict)),
                ("error_message", models.TextField(blank=True)),
                ("celery_task_id", models.CharField(blank=True, max_length=100)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("started_at", models.DateTimeField(blank=True, null=True)),
                ("finished_at", models.DateTimeField(blank=True, null=True)),
                ("created_by", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="document_campaign_import_jobs_created", to=settings.AUTH_USER_MODEL)),
                ("version", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="import_jobs", to="app_document_campaigns.campaignversion")),
            ],
            options={"db_table": "dec_campaign_import_job", "ordering": ["-created_at"]},
        ),
        migrations.AddConstraint(
            model_name="campaignimportjob",
            constraint=models.UniqueConstraint(condition=models.Q(("status__in", ["queued", "running"])), fields=("version", "job_type"), name="dec_uq_active_import_job"),
        ),
        migrations.AddIndex(
            model_name="campaignimportjob",
            index=models.Index(fields=["version", "-created_at"], name="dec_job_version_time_idx"),
        ),
    ]
