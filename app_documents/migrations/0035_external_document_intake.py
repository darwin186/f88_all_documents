from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("app_documents", "0034_gddb_batch_business_slots"),
    ]

    operations = [
        migrations.CreateModel(
            name="ExternalDocumentIntakeToken",
            fields=[
                ("token_id", models.AutoField(primary_key=True, serialize=False)),
                ("name", models.CharField(max_length=100, unique=True)),
                ("token_prefix", models.CharField(max_length=16)),
                ("token_hash", models.CharField(max_length=64, unique=True)),
                ("scopes", models.JSONField(default=list)),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("last_used_at", models.DateTimeField(blank=True, null=True)),
                ("revoked_at", models.DateTimeField(blank=True, null=True)),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="document_intake_tokens_created", to=settings.AUTH_USER_MODEL)),
                ("revoked_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="document_intake_tokens_revoked", to=settings.AUTH_USER_MODEL)),
            ],
            options={"db_table": "d_ExternalDocumentIntakeToken"},
        ),
        migrations.CreateModel(
            name="ExternalDocumentIntakeBatch",
            fields=[
                ("batch_id", models.AutoField(primary_key=True, serialize=False)),
                ("batch_key", models.CharField(max_length=100, unique=True)),
                ("kind", models.CharField(choices=[("documents", "Documents"), ("master_data", "Master data")], max_length=20)),
                ("business_date", models.DateField()),
                ("source", models.CharField(default="prefect", max_length=100)),
                ("schema_version", models.CharField(default="v1", max_length=20)),
                ("expected_records", models.PositiveIntegerField(blank=True, null=True)),
                ("expected_chunks", models.PositiveIntegerField(blank=True, null=True)),
                ("received_records", models.PositiveIntegerField(default=0)),
                ("received_chunks", models.PositiveIntegerField(default=0)),
                ("status", models.CharField(choices=[("created", "Created"), ("uploading", "Uploading"), ("processing", "Processing"), ("completed", "Completed"), ("completed_with_rejections", "Completed with rejections"), ("failed", "Failed")], default="created", max_length=40)),
                ("summary", models.JSONField(blank=True, default=dict)),
                ("error_message", models.TextField(blank=True, default="")),
                ("finalized_at", models.DateTimeField(blank=True, null=True)),
                ("processed_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("token", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="batches", to="app_documents.externaldocumentintaketoken")),
            ],
            options={"db_table": "f_ExternalDocumentIntakeBatch"},
        ),
        migrations.CreateModel(
            name="ExternalDocumentIntakeChunk",
            fields=[
                ("chunk_id", models.AutoField(primary_key=True, serialize=False)),
                ("chunk_no", models.PositiveIntegerField()),
                ("payload_hash", models.CharField(max_length=64)),
                ("record_count", models.PositiveIntegerField()),
                ("records", models.JSONField(default=list)),
                ("received_at", models.DateTimeField(auto_now_add=True)),
                ("batch", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="chunks", to="app_documents.externaldocumentintakebatch")),
            ],
            options={"db_table": "f_ExternalDocumentIntakeChunk"},
        ),
        migrations.CreateModel(
            name="ExternalDocumentIntakeRejection",
            fields=[
                ("rejection_id", models.AutoField(primary_key=True, serialize=False)),
                ("row_no", models.PositiveIntegerField()),
                ("source_record_id", models.CharField(blank=True, default="", max_length=100)),
                ("error_code", models.CharField(max_length=80)),
                ("message", models.TextField()),
                ("raw_record", models.JSONField(default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("batch", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="rejections", to="app_documents.externaldocumentintakebatch")),
                ("chunk", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to="app_documents.externaldocumentintakechunk")),
            ],
            options={"db_table": "f_ExternalDocumentIntakeRejection"},
        ),
        migrations.AddConstraint(model_name="externaldocumentintakechunk", constraint=models.UniqueConstraint(fields=("batch", "chunk_no"), name="doc_intake_batch_chunk_uniq")),
        migrations.AddIndex(model_name="externaldocumentintakebatch", index=models.Index(fields=["status", "business_date"], name="doc_intake_status_date_idx")),
        migrations.AddIndex(model_name="externaldocumentintakerejection", index=models.Index(fields=["batch", "row_no"], name="doc_intake_rejection_idx")),
    ]
