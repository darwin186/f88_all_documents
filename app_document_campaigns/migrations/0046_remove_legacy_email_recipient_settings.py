from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [("app_document_campaigns", "0045_email_recipient_templates")]

    operations = [
        migrations.RemoveField(model_name="campaignemailconfig", name="cc_area_manager"),
        migrations.RemoveField(model_name="campaignemailconfig", name="cc_shop_manager"),
        migrations.RemoveField(model_name="campaignemailconfig", name="cc_emails"),
        migrations.RemoveField(model_name="campaignemailconfig", name="bcc_emails"),
        migrations.RemoveField(model_name="campaignareaemailconfig", name="cc_emails"),
        migrations.RemoveField(model_name="campaignareaemailconfig", name="bcc_emails"),
    ]
