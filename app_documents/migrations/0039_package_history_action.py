from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("app_documents", "0038_gddb_reason_catalog"),
    ]

    operations = [
        migrations.AddField(
            model_name="packagedocumenthistory",
            name="action",
            field=models.CharField(
                choices=[
                    ("assigned", "Gán thùng"),
                    ("unassigned", "Gỡ thùng"),
                ],
                db_index=True,
                default="assigned",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="packagefolderhistory",
            name="action",
            field=models.CharField(
                choices=[
                    ("assigned", "Gán thùng"),
                    ("unassigned", "Gỡ thùng"),
                ],
                db_index=True,
                default="assigned",
                max_length=20,
            ),
        ),
    ]
