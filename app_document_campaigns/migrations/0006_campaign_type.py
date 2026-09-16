from django.db import migrations, models
import django.db.models.deletion


HARD_COPY_CODE = "hardcopy-document-error"


def create_hard_copy_type(apps, schema_editor):
    CampaignType = apps.get_model("app_document_campaigns", "CampaignType")
    Campaign = apps.get_model("app_document_campaigns", "Campaign")
    campaign_type, _ = CampaignType.objects.get_or_create(
        code=HARD_COPY_CODE,
        defaults={
            "name": "Book lỗi chứng từ bản cứng",
            "description": "Đối soát lỗi quyển chứng từ và lỗi chứng từ bản cứng.",
            "sort_order": 10,
        },
    )
    Campaign.objects.filter(campaign_type__isnull=True).update(campaign_type=campaign_type)


class Migration(migrations.Migration):
    dependencies = [("app_document_campaigns", "0005_campaign_import_job_input")]

    operations = [
        migrations.CreateModel(
            name="CampaignType",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("code", models.SlugField(max_length=60, unique=True)),
                ("name", models.CharField(max_length=255)),
                ("description", models.TextField(blank=True)),
                ("is_active", models.BooleanField(default=True)),
                ("sort_order", models.PositiveSmallIntegerField(default=0)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={
                "db_table": "dec_campaign_type",
                "ordering": ["sort_order", "name"],
            },
        ),
        migrations.AlterField(
            model_name="campaign",
            name="report_month",
            field=models.DateField(help_text="Ngày đầu tiên của tháng chiến dịch"),
        ),
        migrations.AddField(
            model_name="campaign",
            name="campaign_type",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="campaigns",
                to="app_document_campaigns.campaigntype",
            ),
        ),
        migrations.RunPython(create_hard_copy_type, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="campaign",
            name="campaign_type",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="campaigns",
                to="app_document_campaigns.campaigntype",
            ),
        ),
        migrations.AddConstraint(
            model_name="campaign",
            constraint=models.UniqueConstraint(
                fields=("campaign_type", "report_month"),
                name="dec_uq_campaign_type_month",
            ),
        ),
    ]
