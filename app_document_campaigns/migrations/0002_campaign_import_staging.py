import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("app_document_campaigns", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="CampaignImportSource",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=100)),
                ("source_type", models.CharField(choices=[("sql", "SQL"), ("excel", "Excel"), ("adjustment", "Điều chỉnh")], max_length=20)),
                ("status", models.CharField(choices=[("staged", "Đã đưa vào staging"), ("validated", "Đã kiểm tra"), ("confirmed", "Đã xác nhận")], default="staged", max_length=20)),
                ("source_filename", models.CharField(blank=True, max_length=255)),
                ("source_checksum", models.CharField(blank=True, max_length=64)),
                ("row_count", models.PositiveIntegerField(default=0)),
                ("invalid_count", models.PositiveIntegerField(default=0)),
                ("preview_summary", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("created_by", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="document_campaign_import_sources_created", to=settings.AUTH_USER_MODEL)),
                ("version", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="import_sources", to="app_document_campaigns.campaignversion")),
            ],
            options={"db_table": "dec_campaign_import_source"},
        ),
        migrations.CreateModel(
            name="CampaignStagingRow",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("row_number", models.PositiveIntegerField()),
                ("source_key", models.CharField(blank=True, max_length=255)),
                ("raw_payload", models.JSONField(default=dict)),
                ("normalized_payload", models.JSONField(blank=True, default=dict)),
                ("content_hash", models.CharField(blank=True, max_length=64)),
                ("validation_errors", models.JSONField(blank=True, default=list)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("source", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="rows", to="app_document_campaigns.campaignimportsource")),
            ],
            options={"db_table": "dec_campaign_staging_row", "ordering": ["source_id", "row_number"]},
        ),
        migrations.AddConstraint(
            model_name="campaignimportsource",
            constraint=models.UniqueConstraint(fields=("version", "name"), name="dec_uq_version_import_source"),
        ),
        migrations.AddConstraint(
            model_name="campaignstagingrow",
            constraint=models.UniqueConstraint(fields=("source", "row_number"), name="dec_uq_staging_source_row"),
        ),
        migrations.AddIndex(
            model_name="campaignstagingrow",
            index=models.Index(fields=["source", "source_key"], name="dec_stage_source_key_idx"),
        ),
    ]
