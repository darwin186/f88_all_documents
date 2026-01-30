from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('app_workshift', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='workpolicy',
            name='max_hours_per_month',
            field=models.DecimalField(decimal_places=2, default=160, max_digits=6),
        ),
    ]
