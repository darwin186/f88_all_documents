from django.db import migrations, models
from django.db.models import F


OLD_SUBJECT = "{{campaign_code}} · Theo dõi phản hồi PGD"
OLD_BODY = (
    "Kính gửi {{area_manager_name}},\n\n"
    "Anh/chị vui lòng theo dõi phản hồi của các PGD thuộc khu vực trong kỳ {{report_month}}.\n"
    "Link theo dõi: {{manager_url}}\n"
    "Link hết hạn: {{link_expires_at}}\n\nTrân trọng."
)
NEW_SUBJECT = "Báo cáo lỗi chứng từ bản cứng _ Tháng {{report_month}}_Theo Khu vực"
NEW_BODY = (
    "<p>Kính gửi Anh/Chị <strong>{{area_manager_name}}</strong>,</p>"
    "<p>PVH gửi Anh/Chị báo cáo lỗi chứng từ bản cứng tháng {{report_month}}.</p>"
    "<p>1. Báo cáo lỗi chứng từ: <a href=\"{{report_url}}\">{{report_url}}</a><br>"
    "2. Hướng dẫn cách xem báo cáo: <a href=\"{{report_guide_url}}\">{{report_guide_url}}</a><br>"
    "Trong đó, Power BI là 01 trang báo cáo tổng hợp của PVH về các lỗi chứng từ "
    "của PGD theo khu vực QLKV đang quản lý.<br>"
    "02 nội dung QLKV cần lưu ý và nhắc nhở PGD trong thời gian phản hồi lỗi:<br>"
    "(a) Tỷ lệ phản hồi lỗi của PGD về các lỗi đang được ghi nhận (theo Báo cáo Power BI)<br>"
    "(b) Chi tiết lỗi chứng từ bản cứng theo từng PGD mà QLKV quản lý.<br>"
    "3. Danh sách lỗi chi tiết: <a href=\"{{manager_url}}\">{{manager_url}}</a></p>"
    "<p>Anh/Chị vui lòng theo dõi tỷ lệ phản hồi của PGD thuộc khu vực quản lý, "
    "đảm bảo 100% PGD hoàn tất phản hồi trước 17h ngày {{response_end_date}}.</p>"
    "<p>Mọi thắc mắc vui lòng liên hệ đầu mối Gapo:<br>"
    "- Trần Thị Lan Hương VH<br>"
    "- Lương Hồng Uyên VH<br>"
    "- Nguyễn Thị Hà VH</p>"
    "<p>Trân trọng,</p>"
)


def update_legacy_default(apps, schema_editor):
    config = apps.get_model("app_document_campaigns", "CampaignAreaEmailConfig")
    config.objects.filter(
        monitoring_subject_template=OLD_SUBJECT,
        monitoring_body_template=OLD_BODY,
    ).update(
        monitoring_subject_template=NEW_SUBJECT,
        monitoring_body_template=NEW_BODY,
        template_version=F("template_version") + 1,
    )


def restore_legacy_default(apps, schema_editor):
    config = apps.get_model("app_document_campaigns", "CampaignAreaEmailConfig")
    config.objects.filter(
        monitoring_subject_template=NEW_SUBJECT,
        monitoring_body_template=NEW_BODY,
    ).update(
        monitoring_subject_template=OLD_SUBJECT,
        monitoring_body_template=OLD_BODY,
        template_version=F("template_version") - 1,
    )


class Migration(migrations.Migration):
    dependencies = [
        ("app_document_campaigns", "0037_update_default_pgd_email_template"),
    ]

    operations = [
        migrations.AddField(
            model_name="campaignareaemailconfig",
            name="monitoring_report_url",
            field=models.URLField(blank=True, default=""),
        ),
        migrations.AddField(
            model_name="campaignareaemailconfig",
            name="monitoring_guide_url",
            field=models.URLField(blank=True, default=""),
        ),
        migrations.RunPython(update_legacy_default, restore_legacy_default),
        migrations.AlterField(
            model_name="campaignareaemailconfig",
            name="monitoring_subject_template",
            field=models.CharField(default=NEW_SUBJECT, max_length=500),
        ),
        migrations.AlterField(
            model_name="campaignareaemailconfig",
            name="monitoring_body_template",
            field=models.TextField(default=NEW_BODY),
        ),
    ]
