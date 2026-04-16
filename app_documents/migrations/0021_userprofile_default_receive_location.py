from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("app_admindocuments", "0036_admparcelreceivelocation_parcel_receive_location"),
        ("app_documents", "0020_gaposcheduledmessage_body_metadata_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="userprofile",
            name="default_receive_location",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="default_users",
                to="app_admindocuments.admparcelreceivelocation",
            ),
        ),
    ]
