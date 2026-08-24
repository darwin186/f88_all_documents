from django.apps import AppConfig


class GapoRelayConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "gapo_relay"
    verbose_name = "GAPO Webhook Relay"

    def ready(self):
        # Register deployment-only checks without touching the database at import time.
        from . import checks  # noqa: F401
