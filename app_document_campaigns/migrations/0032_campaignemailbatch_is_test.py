from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("app_document_campaigns", "0031_campaignemailbatch_transport_provider")]

    operations = [
        migrations.AddField(
            model_name="campaignemailbatch",
            name="is_test",
            field=models.BooleanField(db_index=True, default=False),
        ),
    ]
