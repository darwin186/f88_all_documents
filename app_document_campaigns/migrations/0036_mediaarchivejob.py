import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("app_document_campaigns", "0035_alter_campaignemailbatch_status_and_more"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="MediaArchiveJob",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("source_path", models.CharField(db_index=True, max_length=1000)),
                ("source_kind", models.CharField(choices=[("file", "File"), ("folder", "Thư mục")], max_length=10)),
                ("status", models.CharField(choices=[("queued", "Đang chờ"), ("running", "Đang đồng bộ"), ("succeeded", "Thành công"), ("partial", "Thành công một phần"), ("failed", "Thất bại")], db_index=True, default="queued", max_length=20)),
                ("total_files", models.PositiveIntegerField(default=0)),
                ("archived_files", models.PositiveIntegerField(default=0)),
                ("failed_files", models.PositiveIntegerField(default=0)),
                ("total_bytes", models.PositiveBigIntegerField(default=0)),
                ("archived_bytes", models.PositiveBigIntegerField(default=0)),
                ("remote_root", models.CharField(blank=True, max_length=1200)),
                ("remote_url", models.URLField(blank=True, max_length=1500)),
                ("remote_item_id", models.CharField(blank=True, max_length=255)),
                ("summary", models.JSONField(blank=True, default=dict)),
                ("error_message", models.TextField(blank=True)),
                ("celery_task_id", models.CharField(blank=True, max_length=100)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("started_at", models.DateTimeField(blank=True, null=True)),
                ("finished_at", models.DateTimeField(blank=True, null=True)),
                ("requested_by", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="media_archive_jobs", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "db_table": "dec_media_archive_job",
                "ordering": ["-created_at"],
            },
        ),
        migrations.AddIndex(
            model_name="mediaarchivejob",
            index=models.Index(fields=["source_path", "-created_at"], name="dec_media_archive_path_idx"),
        ),
    ]
