# Generated manually for the GAPO relay app.

from django.db import migrations, models
import django.db.models


class Migration(migrations.Migration):
    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="GapoRelayEvent",
            fields=[
                ("event_id", models.TextField(primary_key=True, serialize=False)),
                ("event_type", models.CharField(default="unknown", max_length=100)),
                ("thread_id", models.TextField(blank=True, null=True)),
                ("message_id", models.TextField(blank=True, null=True)),
                ("received_at", models.DateTimeField()),
                ("raw_payload", models.JSONField()),
                ("payload_sha256", models.CharField(max_length=64)),
                (
                    "delivery_status",
                    models.CharField(
                        choices=[
                            ("pending", "Pending"),
                            ("leased", "Leased"),
                            ("delivered", "Delivered"),
                            ("dead_letter", "Dead letter"),
                        ],
                        default="pending",
                        max_length=20,
                    ),
                ),
                ("attempt_count", models.PositiveIntegerField(default=0)),
                ("next_attempt_at", models.DateTimeField()),
                ("lease_token", models.UUIDField(blank=True, null=True)),
                ("lease_until", models.DateTimeField(blank=True, null=True)),
                ("delivered_at", models.DateTimeField(blank=True, null=True)),
                ("last_http_status", models.IntegerField(blank=True, null=True)),
                ("last_error", models.TextField(blank=True, default="")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "db_table": "gapo_relay_events",
                "ordering": ["received_at", "event_id"],
                "indexes": [
                    models.Index(
                        fields=["delivery_status", "next_attempt_at", "received_at"],
                        name="ix_gapo_relay_claim",
                    )
                ],
                "constraints": [
                    models.CheckConstraint(
                        check=django.db.models.Q(
                            ("delivery_status__in", [
                                "pending",
                                "leased",
                                "delivered",
                                "dead_letter",
                            ])
                        ),
                        name="gapo_relay_valid_status",
                    )
                ],
            },
        ),
    ]
