from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("app_document_campaigns", "0004_campaign_import_job_output")]

    operations = [
        migrations.AlterField(
            model_name="campaignimportjob",
            name="job_type",
            field=models.CharField(
                choices=[
                    ("sql_stage", "Truy xuất dữ liệu SQL"),
                    ("excel_export", "Tạo file Excel"),
                    ("excel_import", "Đối chiếu file Excel"),
                ],
                default="sql_stage",
                max_length=30,
            ),
        ),
        migrations.AddField(
            model_name="campaignimportjob",
            name="input_file",
            field=models.FileField(blank=True, upload_to="document_campaigns/imports/%Y/%m/"),
        ),
        migrations.AddField(
            model_name="campaignimportjob",
            name="input_filename",
            field=models.CharField(blank=True, max_length=255),
        ),
    ]
