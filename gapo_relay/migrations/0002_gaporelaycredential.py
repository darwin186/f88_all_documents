from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("gapo_relay", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="GapoRelayCredential",
            fields=[
                (
                    "kind",
                    models.CharField(
                        choices=[
                            ("ingress", "GAPO ingress secret"),
                            ("delivery", "Project Ops delivery token"),
                        ],
                        max_length=20,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("secret_hash", models.CharField(max_length=64)),
                ("fingerprint", models.CharField(max_length=20)),
                (
                    "previous_secret_hash",
                    models.CharField(blank=True, default="", max_length=64),
                ),
                (
                    "previous_fingerprint",
                    models.CharField(blank=True, default="", max_length=20),
                ),
                ("previous_valid_until", models.DateTimeField(blank=True, null=True)),
                ("rotated_at", models.DateTimeField()),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "rotated_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="gapo_relay_credentials_rotated",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name": "GAPO relay credential",
                "verbose_name_plural": "GAPO relay credentials",
                "db_table": "gapo_relay_credentials",
                "constraints": [
                    models.CheckConstraint(
                        check=models.Q(("kind__in", ["ingress", "delivery"])),
                        name="gapo_relay_valid_credential_kind",
                    )
                ],
            },
        ),
    ]
