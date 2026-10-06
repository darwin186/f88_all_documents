from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("app_documents", "0042_package_transfer"),
    ]

    operations = [
        migrations.AlterField(
            model_name="packagedocumenthistory",
            name="action",
            field=models.CharField(
                choices=[
                    ("assigned", "Gán thùng"),
                    ("unassigned", "Gỡ thùng"),
                    ("transferred_out", "Chuyển khỏi thùng"),
                    ("transferred_in", "Chuyển vào thùng"),
                ],
                db_default="assigned",
                db_index=True,
                default="assigned",
                max_length=20,
            ),
        ),
        migrations.AlterField(
            model_name="packagefolderhistory",
            name="action",
            field=models.CharField(
                choices=[
                    ("assigned", "Gán thùng"),
                    ("unassigned", "Gỡ thùng"),
                    ("transferred_out", "Chuyển khỏi thùng"),
                    ("transferred_in", "Chuyển vào thùng"),
                ],
                db_default="assigned",
                db_index=True,
                default="assigned",
                max_length=20,
            ),
        ),
    ]
