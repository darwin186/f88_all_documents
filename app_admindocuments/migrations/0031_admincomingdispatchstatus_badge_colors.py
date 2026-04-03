from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("app_admindocuments", "0030_admincomingdispatchstatuslog"),
    ]

    operations = [
        migrations.AddField(
            model_name="admincomingdispatchstatus",
            name="badge_bg_color",
            field=models.CharField(blank=True, max_length=20, null=True),
        ),
        migrations.AddField(
            model_name="admincomingdispatchstatus",
            name="badge_text_color",
            field=models.CharField(blank=True, max_length=20, null=True),
        ),
    ]
