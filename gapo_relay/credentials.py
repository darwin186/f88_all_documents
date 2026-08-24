from __future__ import annotations

import hashlib
import hmac
import secrets
from dataclasses import dataclass
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from .models import GapoRelayCredential


@dataclass(frozen=True)
class RotationResult:
    credential: GapoRelayCredential
    plaintext: str
    created: bool


def hash_secret(plaintext: str) -> str:
    return hashlib.sha256(plaintext.encode("utf-8")).hexdigest()


def secret_fingerprint_from_hash(secret_hash: str) -> str:
    if not secret_hash:
        return ""
    return f"{secret_hash[:8]}…{secret_hash[-8:]}"


def secret_fingerprint(plaintext: str) -> str:
    return secret_fingerprint_from_hash(hash_secret(plaintext))


def generate_relay_secret(kind: str) -> str:
    prefixes = {
        GapoRelayCredential.Kind.INGRESS: "gri_",
        GapoRelayCredential.Kind.DELIVERY: "grd_",
    }
    try:
        prefix = prefixes[kind]
    except KeyError as exc:
        raise ValueError("Unsupported relay credential kind") from exc
    return prefix + secrets.token_hex(32)


def fallback_secret(kind: str) -> str:
    setting_names = {
        GapoRelayCredential.Kind.INGRESS: "GAPO_RELAY_INGRESS_SECRET",
        GapoRelayCredential.Kind.DELIVERY: "GAPO_RELAY_DELIVERY_TOKEN",
    }
    try:
        setting_name = setting_names[kind]
    except KeyError as exc:
        raise ValueError("Unsupported relay credential kind") from exc
    return str(getattr(settings, setting_name, "") or "")


def verify_relay_secret(kind: str, supplied: str) -> bool:
    if not supplied:
        return False
    supplied_hash = hash_secret(supplied)
    credential = (
        GapoRelayCredential.objects.filter(kind=kind)
        .only("secret_hash", "previous_secret_hash", "previous_valid_until")
        .first()
    )
    if credential is None:
        expected = fallback_secret(kind)
        return bool(expected) and hmac.compare_digest(supplied_hash, hash_secret(expected))

    if hmac.compare_digest(supplied_hash, credential.secret_hash):
        return True
    previous_is_active = (
        bool(credential.previous_secret_hash)
        and credential.previous_valid_until is not None
        and credential.previous_valid_until > timezone.now()
    )
    return previous_is_active and hmac.compare_digest(
        supplied_hash, credential.previous_secret_hash
    )


def rotate_relay_credential(kind: str, user=None) -> RotationResult:
    if kind not in GapoRelayCredential.Kind.values:
        raise ValueError("Unsupported relay credential kind")
    plaintext = generate_relay_secret(kind)
    new_hash = hash_secret(plaintext)
    now = timezone.now()
    grace_seconds = max(
        0, int(getattr(settings, "GAPO_RELAY_SECRET_GRACE_SECONDS", 86400))
    )

    with transaction.atomic():
        credential = (
            GapoRelayCredential.objects.select_for_update().filter(kind=kind).first()
        )
        created = credential is None
        if created:
            credential = GapoRelayCredential(kind=kind)
            environment_secret = fallback_secret(kind)
            old_hash = hash_secret(environment_secret) if environment_secret else ""
        else:
            old_hash = credential.secret_hash

        credential.previous_secret_hash = old_hash if grace_seconds and old_hash else ""
        credential.previous_fingerprint = (
            secret_fingerprint_from_hash(old_hash)
            if credential.previous_secret_hash
            else ""
        )
        credential.previous_valid_until = (
            now + timedelta(seconds=grace_seconds)
            if credential.previous_secret_hash
            else None
        )
        credential.secret_hash = new_hash
        credential.fingerprint = secret_fingerprint_from_hash(new_hash)
        credential.rotated_at = now
        credential.rotated_by = user if getattr(user, "is_authenticated", False) else None
        credential.save()

    return RotationResult(
        credential=credential,
        plaintext=plaintext,
        created=created,
    )
