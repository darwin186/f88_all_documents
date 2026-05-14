from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("app_admindocuments", "0036_admparcelreceivelocation_parcel_receive_location"),
        ("app_documents", "0023_checkingstatustype_is_missing_document"),
    ]

    operations = [
        migrations.AddField(
            model_name="borrowrequest",
            name="contact_recipient",
            field=models.ForeignKey(
                blank=True,
                db_column="contact_recipient_id",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="borrow_requests",
                to="app_admindocuments.admparcelrecipientcatalog",
            ),
        ),
        migrations.AddField(
            model_name="borrowrequest",
            name="contact_name",
            field=models.CharField(blank=True, max_length=255, null=True),
        ),
        migrations.AddField(
            model_name="borrowrequest",
            name="contact_employee_code",
            field=models.CharField(blank=True, max_length=50, null=True),
        ),
        migrations.AddField(
            model_name="borrowrequest",
            name="contact_gapo_user_id",
            field=models.CharField(blank=True, max_length=100, null=True),
        ),
    ]
