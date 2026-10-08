from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("app_documents", "0043_package_history_action_db_default"),
    ]

    operations = [
        migrations.AddField(
            model_name="shop",
            name="shop_manager_name",
            field=models.CharField(max_length=255, blank=True, default=""),
        ),
        migrations.AddField(
            model_name="shop",
            name="shop_manager_employee_code",
            field=models.CharField(max_length=100, blank=True, default=""),
        ),
        migrations.AddField(
            model_name="shop",
            name="shop_manager_email",
            field=models.EmailField(max_length=254, blank=True, default=""),
        ),
    ]
