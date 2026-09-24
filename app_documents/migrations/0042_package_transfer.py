import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("app_documents", "0041_shopcatalogjob_one_active"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="package",
            name="replaced_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="package",
            name="replaced_by",
            field=models.ForeignKey(
                blank=True,
                db_column="replaced_by_id",
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="replacement_sources",
                to="app_documents.package",
            ),
        ),
        migrations.AddField(
            model_name="package",
            name="replaced_by_user",
            field=models.ForeignKey(
                blank=True,
                db_column="replaced_by_user_id",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="package_replacements",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.CreateModel(
            name="PackageTransfer",
            fields=[
                ("transfer_id", models.AutoField(primary_key=True, serialize=False)),
                (
                    "transfer_type",
                    models.CharField(
                        choices=[("replacement", "Đổi thùng")],
                        default="replacement",
                        max_length=30,
                    ),
                ),
                ("reason", models.TextField()),
                ("folder_count", models.PositiveIntegerField(default=0)),
                ("document_count", models.PositiveIntegerField(default=0)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "created_by",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="package_transfers",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "source_package",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="outgoing_transfers",
                        to="app_documents.package",
                    ),
                ),
                (
                    "target_package",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="incoming_transfers",
                        to="app_documents.package",
                    ),
                ),
            ],
            options={
                "db_table": "f_PackageTransfer",
                "ordering": ["-created_at", "-transfer_id"],
            },
        ),
        migrations.AddConstraint(
            model_name="packagetransfer",
            constraint=models.UniqueConstraint(
                fields=("source_package",),
                name="one_replacement_per_source_package",
            ),
        ),
        migrations.AddConstraint(
            model_name="packagetransfer",
            constraint=models.CheckConstraint(
                check=~models.Q(source_package=models.F("target_package")),
                name="package_transfer_source_target_differ",
            ),
        ),
        migrations.AddField(
            model_name="packagedocumenthistory",
            name="transfer",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="document_history",
                to="app_documents.packagetransfer",
            ),
        ),
        migrations.AddField(
            model_name="packagefolderhistory",
            name="transfer",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="folder_history",
                to="app_documents.packagetransfer",
            ),
        ),
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
                db_index=True,
                default="assigned",
                max_length=20,
            ),
        ),
    ]
