from django.db import migrations, models
from django.db.models import F


OLD_SUBJECT = "{{campaign_code}} · Xác nhận kết quả book lỗi"
OLD_BODY = (
    "Kính gửi {{area_manager_name}},\n\n"
    "Anh/chị vui lòng kiểm tra và xác nhận kết quả Team review cho kỳ {{report_month}}.\n"
    "Link xác nhận: {{manager_url}}\n"
    "Link hết hạn: {{link_expires_at}}\n\nTrân trọng."
)
NEW_SUBJECT = "Chốt Báo cáo ghi nhận lỗi chứng từ bản cứng _ Tháng {{report_month}}"
NEW_BODY = (
    "<p>Kính gửi Anh/Chị <strong>{{area_manager_name}}</strong>,</p>"
    "<p>Sau thời gian nhận phản hồi và kiểm tra thông tin phản hồi của PGD, "
    "PVH gửi Anh/Chị báo cáo kết quả ghi nhận lỗi như sau:</p>"
    "<p>1. Danh sách chi tiết: <a href=\"{{manager_url}}\">{{manager_url}}</a><br>"
    "Anh/Chị QLKV thực hiện kiểm tra xác nhận lỗi với PGD và phản hồi theo link "
    "để PVH xử lý bước tiếp theo.<br>"
    "2. Hướng dẫn QLKV phản hồi: "
    "<a href=\"{{confirmation_guide_url}}\">{{confirmation_guide_url}}</a></p>"
    "<p>Thời hạn phản hồi: Đến hết 17h ngày {{area_response_end_date}}.</p>"
    "<p>Nhờ QLKV lưu ý việc phản hồi tại link danh sách gửi lỗi được đính kèm "
    "trong thời gian quy định. Các thông tin sau thời gian quy định sẽ không được "
    "ghi nhận và gỡ lỗi bởi bộ phận PVH/RRHĐ/Nhân sự.</p>"
    "<p>Mọi thắc mắc cần hỗ trợ, Anh/Chị vui lòng liên hệ theo đầu mối Gapo sau:<br>"
    "- Trần Thị Lan Hương VH<br>"
    "- Nguyễn Thị Hà VH</p>"
    "<p>Trân trọng,</p>"
)


def update_legacy_default(apps, schema_editor):
    config = apps.get_model("app_document_campaigns", "CampaignAreaEmailConfig")
    config.objects.filter(
        confirmation_subject_template=OLD_SUBJECT,
        confirmation_body_template=OLD_BODY,
    ).update(
        confirmation_subject_template=NEW_SUBJECT,
        confirmation_body_template=NEW_BODY,
        template_version=F("template_version") + 1,
    )


def restore_legacy_default(apps, schema_editor):
    config = apps.get_model("app_document_campaigns", "CampaignAreaEmailConfig")
    config.objects.filter(
        confirmation_subject_template=NEW_SUBJECT,
        confirmation_body_template=NEW_BODY,
    ).update(
        confirmation_subject_template=OLD_SUBJECT,
        confirmation_body_template=OLD_BODY,
        template_version=F("template_version") - 1,
    )


class Migration(migrations.Migration):
    dependencies = [
        ("app_document_campaigns", "0038_update_default_area_monitoring_email"),
    ]

    operations = [
        migrations.AddField(
            model_name="campaignareaemailconfig",
            name="confirmation_guide_url",
            field=models.URLField(blank=True, default=""),
        ),
        migrations.RunPython(update_legacy_default, restore_legacy_default),
        migrations.AlterField(
            model_name="campaignareaemailconfig",
            name="confirmation_subject_template",
            field=models.CharField(default=NEW_SUBJECT, max_length=500),
        ),
        migrations.AlterField(
            model_name="campaignareaemailconfig",
            name="confirmation_body_template",
            field=models.TextField(default=NEW_BODY),
        ),
    ]
