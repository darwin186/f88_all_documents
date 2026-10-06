import hashlib

from django.db import migrations, models
import django.db.models.deletion


def migrate_existing_guidance(apps, schema_editor):
    CampaignResponseOption = apps.get_model("app_document_campaigns", "CampaignResponseOption")
    ResponseGuidanceTemplate = apps.get_model("app_document_campaigns", "ResponseGuidanceTemplate")
    templates = {}
    for choice in CampaignResponseOption.objects.exclude(guidance_text="").iterator():
        text = choice.guidance_text.strip()
        if not text:
            continue
        template = templates.get(text)
        if template is None:
            digest = hashlib.sha256(text.encode("utf-8")).hexdigest()[:12].upper()
            template, _ = ResponseGuidanceTemplate.objects.get_or_create(
                code=f"GUIDE-{digest}",
                defaults={"name": text[:255], "guidance_text": text, "is_active": True},
            )
            templates[text] = template
        choice.guidance_template_id = template.pk
        choice.save(update_fields=["guidance_template"])


class Migration(migrations.Migration):
    dependencies = [("app_document_campaigns", "0022_campaign_response_option_guidance")]

    operations = [
        migrations.CreateModel(
            name="ResponseGuidanceTemplate",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("code", models.CharField(max_length=40, unique=True)),
                ("name", models.CharField(max_length=255)),
                ("guidance_text", models.TextField(max_length=2000)),
                ("is_active", models.BooleanField(default=True)),
                ("sort_order", models.PositiveIntegerField(default=0)),
            ],
            options={
                "db_table": "dec_response_guidance_template",
                "ordering": ["sort_order", "id"],
            },
        ),
        migrations.AddField(
            model_name="campaignresponseoption",
            name="guidance_template",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="campaign_response_options",
                to="app_document_campaigns.responseguidancetemplate",
            ),
        ),
        migrations.RunPython(migrate_existing_guidance, migrations.RunPython.noop),
    ]
