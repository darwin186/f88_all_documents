from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("app_admindocuments", "0035_update_parcel_dynamic_body_confirm_text"),
    ]

    operations = [
        migrations.CreateModel(
            name="AdmParcelReceiveLocation",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=255, unique=True)),
                ("address", models.CharField(blank=True, default="", max_length=500)),
                ("note", models.TextField(blank=True, default="")),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name": "Parcel Receive Location",
                "verbose_name_plural": "Parcel Receive Locations",
                "db_table": "adm_parcel_receive_location",
                "ordering": ["name"],
            },
        ),
        migrations.AddField(
            model_name="admparcelreceipt",
            name="receive_location",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="parcel_receipts",
                to="app_admindocuments.admparcelreceivelocation",
            ),
        ),
    ]
