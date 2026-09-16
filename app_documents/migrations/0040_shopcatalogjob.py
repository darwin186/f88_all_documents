from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [("app_documents", "0039_package_history_action"), migrations.swappable_dependency(settings.AUTH_USER_MODEL)]
    operations = [migrations.CreateModel(name="ShopCatalogJob", fields=[
        ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
        ("kind", models.CharField(choices=[("export", "Export"), ("import", "Import")], max_length=10)),
        ("status", models.CharField(default="queued", max_length=12)),
        ("progress", models.PositiveSmallIntegerField(default=0)),
        ("message", models.TextField(blank=True)), ("summary", models.JSONField(default=dict)),
        ("input_file", models.FileField(blank=True, upload_to="master_data/imports/%Y/%m/")),
        ("output_file", models.FileField(blank=True, upload_to="master_data/exports/%Y/%m/")),
        ("created_at", models.DateTimeField(auto_now_add=True)), ("updated_at", models.DateTimeField(auto_now=True)),
        ("requested_by", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to=settings.AUTH_USER_MODEL)),
    ])]
