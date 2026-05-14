from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("app_workshift", "0005_workshifttemplate_include_lunch_and_shift_template"),
    ]

    operations = [
        migrations.AddField(
            model_name="workshifttemplate",
            name="effective_from",
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="workshifttemplate",
            name="effective_to",
            field=models.DateField(blank=True, null=True),
        ),
    ]
