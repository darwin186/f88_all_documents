from django.db import migrations, models
from django.db.models import F


OLD_SUBJECT = "{{campaign_code}} · {{campaign_name}}"
OLD_BODY = (
    "Kính gửi PGD {{shop_name}},\n\n"
    "Phòng giao dịch vui lòng kiểm tra và phản hồi chiến dịch {{campaign_name}}.\n"
    "Hạn phản hồi: {{response_deadline}}\n"
    "Link hết hạn: {{link_expires_at}}\n\n"
    "Link phản hồi: {{response_url}}\n\n"
    "Trân trọng."
)
NEW_SUBJECT = "BÁO CÁO LỖI chứng từ bản cứng_Tháng {{report_month}}_ {{shop_name}}"
NEW_BODY = (
    "<p>Kính gửi Anh/Chị PGD <strong>{{shop_name}}</strong>,</p>"
    "<p>PVH gửi báo cáo lỗi chứng từ bản cứng tháng {{report_month}}.</p>"
    "<p>1. Số lượng lỗi cần phản hồi của PGD: <strong>{{error_count}}</strong><br>"
    "2. Link danh sách lỗi chi tiết: <a href=\"{{response_url}}\">{{response_url}}</a><br>"
    "Hướng dẫn điền thông tin phản hồi lỗi, chi tiết trong link Danh sách lỗi.<br>"
    "4. Thời hạn phản hồi: từ {{response_start_date}} - {{response_end_date}}</p>"
    "<p>PGD vui lòng kiểm tra và hoàn tất phản hồi trước 17h ngày {{response_end_date}}. "
    "Trường hợp PGD không thực hiện phản hồi, hệ thống sẽ tự động ghi nhận lỗi và "
    "không thực hiện điều chỉnh (nếu có).</p>"
    "<p>Trân trọng,</p>"
)


def update_legacy_defaults(apps, schema_editor):
    config = apps.get_model("app_document_campaigns", "CampaignEmailConfig")
    config.objects.filter(
        subject_template=OLD_SUBJECT,
        body_template=OLD_BODY,
    ).update(
        subject_template=NEW_SUBJECT,
        body_template=NEW_BODY,
        template_version=F("template_version") + 1,
    )


def restore_legacy_defaults(apps, schema_editor):
    config = apps.get_model("app_document_campaigns", "CampaignEmailConfig")
    config.objects.filter(
        subject_template=NEW_SUBJECT,
        body_template=NEW_BODY,
    ).update(
        subject_template=OLD_SUBJECT,
        body_template=OLD_BODY,
        template_version=F("template_version") - 1,
    )


class Migration(migrations.Migration):
    dependencies = [
        ("app_document_campaigns", "0036_mediaarchivejob"),
    ]

    operations = [
        migrations.RunPython(update_legacy_defaults, restore_legacy_defaults),
        migrations.AlterField(
            model_name="campaignemailconfig",
            name="subject_template",
            field=models.CharField(default=NEW_SUBJECT, max_length=500),
        ),
        migrations.AlterField(
            model_name="campaignemailconfig",
            name="body_template",
            field=models.TextField(default=NEW_BODY),
        ),
    ]
