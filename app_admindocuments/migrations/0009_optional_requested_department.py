from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("app_admindocuments", "0008_admpaperdocument_department"),
        ("app_documents", "0001_initial"),
    ]

    operations = [
        migrations.AlterField(
            model_name="admpaperdocument",
            name="requested_department",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                to="app_documents.shop",
            ),
        ),
    ]
