from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
from django.db.models import Q


class Migration(migrations.Migration):
    dependencies = [
        ("app_document_campaigns", "0024_campaign_area_response_deadline"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="AreaConfirmationExcelJob",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("kind", models.CharField(choices=[("export", "Xuất Excel"), ("import", "Import Excel")], max_length=10)),
                ("status", models.CharField(default="queued", max_length=12)),
                ("progress", models.PositiveSmallIntegerField(default=0)),
                ("message", models.TextField(blank=True)),
                ("summary", models.JSONField(blank=True, default=dict)),
                ("input_file", models.FileField(blank=True, upload_to="document_campaigns/area_confirmation/imports/%Y/%m/")),
                ("output_file", models.FileField(blank=True, upload_to="document_campaigns/area_confirmation/exports/%Y/%m/")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("campaign", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="area_confirmation_excel_jobs", to="app_document_campaigns.campaign")),
                ("requested_by", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.AddConstraint(
            model_name="areaconfirmationexceljob",
            constraint=models.UniqueConstraint(
                condition=Q(("status__in", ["queued", "running"])),
                fields=("campaign", "kind"),
                name="dec_one_active_area_excel",
            ),
        ),
    ]
