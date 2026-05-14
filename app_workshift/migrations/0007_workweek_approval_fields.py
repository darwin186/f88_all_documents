from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("app_workshift", "0006_workshifttemplate_effective_dates"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AlterField(
            model_name="workweek",
            name="status",
            field=models.CharField(
                choices=[
                    ("draft", "Draft"),
                    ("submitted", "Submitted"),
                    ("approved", "Approved"),
                    ("rejected", "Rejected"),
                    ("locked", "Locked"),
                ],
                default="draft",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="workweek",
            name="approved_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="workweek",
            name="approved_by",
            field=models.ForeignKey(
                blank=True,
                db_column="approved_by",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="work_weeks_approved",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name="workweek",
            name="rejected_reason",
            field=models.TextField(blank=True, null=True),
        ),
    ]
