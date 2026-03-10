from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("app_workshift", "0002_add_max_hours_per_month"),
    ]

    operations = [
        migrations.AddField(
            model_name="workpolicy",
            name="min_hours_per_shift",
            field=models.DecimalField(decimal_places=2, default=4, max_digits=4),
        ),
    ]
