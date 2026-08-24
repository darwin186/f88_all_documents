from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("gapo_relay", "0002_gaporelaycredential"),
    ]

    operations = [
        migrations.AlterField(
            model_name="gaporelayevent",
            name="delivery_status",
            field=models.CharField(
                choices=[
                    ("pending", "Pending"),
                    ("leased", "Processing"),
                    ("delivered", "Delivered"),
                    ("dead_letter", "Failed"),
                ],
                default="pending",
                max_length=20,
            ),
        ),
    ]
