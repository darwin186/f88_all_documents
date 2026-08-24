from django.db import models
from django.db.models import Q
from django.conf import settings


class GapoRelayEvent(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        LEASED = "leased", "Processing"
        DELIVERED = "delivered", "Delivered"
        DEAD_LETTER = "dead_letter", "Failed"

    event_id = models.TextField(primary_key=True)
    event_type = models.CharField(max_length=100, default="unknown")
    thread_id = models.TextField(null=True, blank=True)
    message_id = models.TextField(null=True, blank=True)
    received_at = models.DateTimeField()
    raw_payload = models.JSONField()
    payload_sha256 = models.CharField(max_length=64)
    delivery_status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
    )
    attempt_count = models.PositiveIntegerField(default=0)
    next_attempt_at = models.DateTimeField()
    lease_token = models.UUIDField(null=True, blank=True)
    lease_until = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    last_http_status = models.IntegerField(null=True, blank=True)
    last_error = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "gapo_relay_events"
        ordering = ["received_at", "event_id"]
        indexes = [
            models.Index(
                fields=["delivery_status", "next_attempt_at", "received_at"],
                name="ix_gapo_relay_claim",
            ),
        ]
        constraints = [
            models.CheckConstraint(
                check=Q(
                    delivery_status__in=[
                        "pending",
                        "leased",
                        "delivered",
                        "dead_letter",
                    ]
                ),
                name="gapo_relay_valid_status",
            ),
        ]

    def __str__(self):
        return self.event_id


class GapoRelayCredential(models.Model):
    class Kind(models.TextChoices):
        INGRESS = "ingress", "GAPO ingress secret"
        DELIVERY = "delivery", "Project Ops delivery token"

    kind = models.CharField(max_length=20, choices=Kind.choices, primary_key=True)
    secret_hash = models.CharField(max_length=64)
    fingerprint = models.CharField(max_length=20)
    previous_secret_hash = models.CharField(max_length=64, blank=True, default="")
    previous_fingerprint = models.CharField(max_length=20, blank=True, default="")
    previous_valid_until = models.DateTimeField(null=True, blank=True)
    rotated_at = models.DateTimeField()
    rotated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="gapo_relay_credentials_rotated",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "gapo_relay_credentials"
        verbose_name = "GAPO relay credential"
        verbose_name_plural = "GAPO relay credentials"
        constraints = [
            models.CheckConstraint(
                check=Q(kind__in=["ingress", "delivery"]),
                name="gapo_relay_valid_credential_kind",
            ),
        ]

    def __str__(self):
        return self.get_kind_display()
