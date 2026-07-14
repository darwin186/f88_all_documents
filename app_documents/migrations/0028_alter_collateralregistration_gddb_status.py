from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("app_documents", "0027_gddb_external_identity"),
    ]

    operations = [
        migrations.AlterField(
            model_name="collateralregistration",
            name="gddb_status",
            field=models.CharField(
                choices=[
                    ("pending", "Chưa đăng kí"),
                    ("registered", "Đã đăng kí"),
                    ("not_registered", "Không đăng kí"),
                ],
                default="pending",
                max_length=30,
            ),
        ),
    ]
