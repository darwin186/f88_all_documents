from django.db import migrations, models


def classify_existing_links(apps, schema_editor):
    AccessLink = apps.get_model("app_document_campaigns", "AreaManagerAccessLink")
    CampaignError = apps.get_model("app_document_campaigns", "CampaignError")
    step5_statuses = ["waiting_area", "area_confirmed", "area_returned"]
    for link in AccessLink.objects.all().iterator(chunk_size=500):
        is_confirmation = CampaignError.objects.filter(
            campaign_id=link.campaign_id,
            shop__manager_id__areaManager_id=link.area_manager_id,
            status__in=step5_statuses,
        ).exists()
        if is_confirmation:
            AccessLink.objects.filter(pk=link.pk).update(stage="confirmation")


class Migration(migrations.Migration):
    dependencies = [
        ("app_document_campaigns", "0026_campaign_area_choice_labels"),
    ]

    operations = [
        migrations.AddField(
            model_name="areamanageraccesslink",
            name="stage",
            field=models.CharField(
                choices=[
                    ("monitoring", "Theo dõi phản hồi PGD"),
                    ("confirmation", "Xác nhận kết quả"),
                ],
                db_index=True,
                default="monitoring",
                max_length=20,
            ),
        ),
        migrations.RunPython(classify_existing_links, migrations.RunPython.noop),
        migrations.RemoveConstraint(
            model_name="areamanageraccesslink",
            name="dec_uq_campaign_area_link",
        ),
        migrations.AddConstraint(
            model_name="areamanageraccesslink",
            constraint=models.UniqueConstraint(
                fields=("campaign", "area_manager", "stage"),
                name="dec_uq_campaign_area_stage",
            ),
        ),
    ]
