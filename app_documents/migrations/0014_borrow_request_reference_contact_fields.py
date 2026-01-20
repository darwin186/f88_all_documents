from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('app_documents', '0013_borrow_request_models'),
    ]

    operations = [
        migrations.AddField(
            model_name='borrowrequest',
            name='reference_code',
            field=models.CharField(blank=True, max_length=50, null=True),
        ),
        migrations.AddField(
            model_name='borrowrequest',
            name='contact_phone',
            field=models.CharField(blank=True, max_length=30, null=True),
        ),
    ]
