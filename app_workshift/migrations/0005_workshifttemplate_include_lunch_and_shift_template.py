from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("app_workshift", "0004_workshifttemplate"),
    ]

    operations = [
        migrations.AddField(
            model_name="workshifttemplate",
            name="include_lunch_break",
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name="workshift",
            name="shift_template",
            field=models.ForeignKey(
                blank=True,
                db_column="template_id",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="work_shifts",
                to="app_workshift.workshifttemplate",
            ),
        ),
    ]
