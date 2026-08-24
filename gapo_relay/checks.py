from django.conf import settings
from django.core.checks import Error, Tags, register
from django.db import DatabaseError

from .models import GapoRelayCredential


def _secret_bytes(name: str) -> bytes:
    return str(getattr(settings, name, "") or "").encode("utf-8")


@register(Tags.security, deploy=True)
def check_relay_secrets(app_configs, **kwargs):
    errors = []
    ingress = _secret_bytes("GAPO_RELAY_INGRESS_SECRET")
    delivery = _secret_bytes("GAPO_RELAY_DELIVERY_TOKEN")
    try:
        managed_kinds = set(
            GapoRelayCredential.objects.exclude(secret_hash="").values_list(
                "kind", flat=True
            )
        )
    except DatabaseError:
        # During an initial deploy the credential table may not exist yet.
        managed_kinds = set()

    ingress_is_managed = GapoRelayCredential.Kind.INGRESS in managed_kinds
    delivery_is_managed = GapoRelayCredential.Kind.DELIVERY in managed_kinds
    if not ingress_is_managed and len(ingress) < 32:
        errors.append(
            Error(
                "GAPO_RELAY_INGRESS_SECRET must contain at least 32 bytes.",
                id="gapo_relay.E001",
            )
        )
    if not delivery_is_managed and len(delivery) < 32:
        errors.append(
            Error(
                "GAPO_RELAY_DELIVERY_TOKEN must contain at least 32 bytes.",
                id="gapo_relay.E002",
            )
        )
    if (
        not ingress_is_managed
        and not delivery_is_managed
        and ingress
        and delivery
        and ingress == delivery
    ):
        errors.append(
            Error(
                "GAPO relay ingress and delivery credentials must be different.",
                id="gapo_relay.E003",
            )
        )
    return errors
