from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("app_documents", "0016_folder_issue_types"),
    ]

    operations = [
        migrations.AddField(
            model_name="userprofile",
            name="avatar",
            field=models.FileField(blank=True, null=True, upload_to="avatars/"),
        ),
        migrations.AddField(
            model_name="userprofile",
            name="date_of_birth",
            field=models.DateField(blank=True, null=True),
        ),
    ]
