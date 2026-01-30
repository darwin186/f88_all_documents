from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("app_admindocuments", "0011_add_paper_counter"),
    ]

    operations = [
        migrations.AddField(
            model_name="admcompany",
            name="badge_text_color",
            field=models.CharField(blank=True, max_length=20, null=True),
        ),
        migrations.AddField(
            model_name="admcompany",
            name="badge_bg_color",
            field=models.CharField(blank=True, max_length=20, null=True),
        ),
        migrations.AddField(
            model_name="admcompany",
            name="badge_logo_url",
            field=models.URLField(blank=True, max_length=500, null=True),
        ),
    ]
