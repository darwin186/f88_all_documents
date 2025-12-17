from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('app_documents', '0007_gaposcheduledmessage'),
    ]

    operations = [
        migrations.AddField(
            model_name='foldertype',
            name='badge_color',
            field=models.CharField(blank=True, max_length=50, null=True),
        ),
        migrations.AddField(
            model_name='partner',
            name='badge_color',
            field=models.CharField(blank=True, max_length=50, null=True),
        ),
    ]
