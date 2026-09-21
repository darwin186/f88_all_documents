from django.db import migrations, models
import django.db.models.deletion


def seed(apps, schema_editor):
    Option = apps.get_model("app_document_campaigns", "ShopResponseOption")
    Selected = apps.get_model("app_document_campaigns", "CampaignResponseOption")
    Campaign = apps.get_model("app_document_campaigns", "Campaign")
    Question = apps.get_model("app_document_campaigns", "ChecklistQuestion")
    labels = ["PGD xác nhận lỗi", "PGD hẹn bổ sung chứng từ", "PGD xác nhận lỗi và không thể bổ sung chứng từ", "Chứng từ thất lạc/ thiếu chữ ký từ PGD cũ", "PGD đã gửi chứng từ/Chứng từ đã gửi đầy đủ theo yêu cầu và không vi phạm lỗi", "PGD đã ticket xin ngoại lệ sự cố chứng từ", "Công quyền đang giữ bộ HĐ/HĐ thiếu chứng từ do xin ngoại lệ bởi các phòng ban khác"]
    catalog = {}
    def register(label):
        if label not in catalog:
            catalog[label] = Option.objects.create(code=f"RESP-{len(catalog)+1:03}", label=label, sort_order=len(catalog))
        return catalog[label]
    for label in labels:
        register(label)
    for campaign in Campaign.objects.select_related("campaign_type"):
        template_ids = set(campaign.errors.values_list("checklist_template_id", flat=True))
        template_ids.add(campaign.campaign_type.shop_checklist_template_id)
        choices = {}
        for question in Question.objects.filter(template_id__in=template_ids, code="SHOP_RESPONSE", is_active=True):
            for option in question.options:
                value = str(option.get("value", "")) if isinstance(option, dict) else str(option)
                label = str(option.get("label", value)) if isinstance(option, dict) else value
                if value:
                    choices[value] = label
        if not choices:
            choices = {label: label for label in labels[:2]}
        for index, (value, label) in enumerate(choices.items()):
            master = register(label)
            Selected.objects.get_or_create(campaign=campaign, option=master, defaults={"value": value, "label": label, "sort_order": index})


class Migration(migrations.Migration):
    dependencies = [("app_document_campaigns", "0009_campaign_shop_instructions")]
    operations = [
        migrations.CreateModel(name="ShopResponseOption", fields=[("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")), ("code", models.CharField(max_length=40, unique=True)), ("label", models.CharField(max_length=255)), ("description", models.TextField(blank=True, max_length=2000)), ("is_active", models.BooleanField(default=True)), ("sort_order", models.PositiveIntegerField(default=0))], options={"ordering": ["sort_order", "id"]}),
        migrations.CreateModel(name="CampaignResponseOption", fields=[("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")), ("value", models.CharField(max_length=255)), ("label", models.CharField(max_length=255)), ("sort_order", models.PositiveIntegerField(default=0)), ("campaign", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="response_options", to="app_document_campaigns.campaign")), ("option", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to="app_document_campaigns.shopresponseoption"))], options={"ordering": ["sort_order", "id"]}),
        migrations.AddConstraint(model_name="campaignresponseoption", constraint=models.UniqueConstraint(fields=("campaign", "option"), name="dec_campaign_response_option_unique")),
        migrations.AddConstraint(model_name="campaignresponseoption", constraint=models.UniqueConstraint(fields=("campaign", "value"), name="dec_campaign_response_value_unique")),
        migrations.RunPython(seed, migrations.RunPython.noop),
    ]
