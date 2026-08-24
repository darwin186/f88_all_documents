from django.conf import settings
from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.http import HttpResponseRedirect
from django.template.response import TemplateResponse
from django.urls import reverse
from django.utils import timezone

from .credentials import fallback_secret, rotate_relay_credential
from .models import GapoRelayCredential, GapoRelayEvent


def _can_view_raw_payload(user) -> bool:
    return user.is_superuser or user.groups.filter(name="gapo_relay_technical").exists()


def _can_manage_credentials(user) -> bool:
    return (
        user.is_active
        and user.is_staff
        and (
            user.is_superuser
            or (
                user.groups.filter(name="gapo_relay_technical").exists()
                and user.has_perm("gapo_relay.change_gaporelaycredential")
            )
        )
    )


@admin.register(GapoRelayEvent)
class GapoRelayEventAdmin(admin.ModelAdmin):
    list_display = (
        "event_id",
        "event_type",
        "thread_id",
        "message_id",
        "delivery_status",
        "attempt_count",
        "received_at",
        "next_attempt_at",
    )
    list_filter = ("delivery_status", "event_type", "received_at")
    search_fields = ("event_id", "thread_id", "message_id")
    date_hierarchy = "received_at"
    ordering = ("-received_at",)
    actions = ("retry_dead_letter_events",)
    readonly_fields = tuple(field.name for field in GapoRelayEvent._meta.fields)

    def get_exclude(self, request, obj=None):
        if _can_view_raw_payload(request.user):
            return ()
        return ("raw_payload", "payload_sha256")

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def get_actions(self, request):
        actions = super().get_actions(request)
        if not _can_view_raw_payload(request.user):
            actions.pop("retry_dead_letter_events", None)
        return actions

    @admin.action(description="Retry selected dead-letter events")
    def retry_dead_letter_events(self, request, queryset):
        retried = 0
        now = timezone.now()
        with transaction.atomic():
            events = list(
                queryset.select_for_update().filter(
                    delivery_status=GapoRelayEvent.Status.DEAD_LETTER
                )
            )
            for event in events:
                event.delivery_status = GapoRelayEvent.Status.PENDING
                event.attempt_count = 0
                event.next_attempt_at = now
                event.lease_token = None
                event.lease_until = None
                event.last_error = ""
                event.last_http_status = None
                event.updated_at = now
                event.save(
                    update_fields=[
                        "delivery_status",
                        "attempt_count",
                        "next_attempt_at",
                        "lease_token",
                        "lease_until",
                        "last_error",
                        "last_http_status",
                        "updated_at",
                    ]
                )
                self.log_change(request, event, "Retried dead-letter relay event")
                retried += 1
        self.message_user(
            request,
            f"Queued {retried} dead-letter event(s) for retry.",
            level=messages.SUCCESS,
        )


@admin.register(GapoRelayCredential)
class GapoRelayCredentialAdmin(admin.ModelAdmin):
    change_list_template = "admin/gapo_relay/credential/change_list.html"

    def has_module_permission(self, request):
        return _can_view_raw_payload(request.user)

    def has_view_permission(self, request, obj=None):
        return _can_view_raw_payload(request.user)

    def has_change_permission(self, request, obj=None):
        return _can_manage_credentials(request.user)

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def change_view(self, request, object_id, form_url="", extra_context=None):
        return HttpResponseRedirect(reverse("admin:gapo_relay_gaporelaycredential_changelist"))

    def add_view(self, request, form_url="", extra_context=None):
        return HttpResponseRedirect(reverse("admin:gapo_relay_gaporelaycredential_changelist"))

    def changelist_view(self, request, extra_context=None):
        if not self.has_view_permission(request):
            raise PermissionDenied

        generated_secret = None
        generated_ingress_url = None
        generated_kind = None
        form_error = None
        if request.method == "POST":
            if not self.has_change_permission(request):
                raise PermissionDenied
            kind = request.POST.get("kind", "")
            confirmation = request.POST.get("confirmation", "")
            current_password = request.POST.get("current_password", "")
            if kind not in GapoRelayCredential.Kind.values:
                form_error = "Loại credential không hợp lệ."
            elif confirmation != "ROTATE":
                form_error = 'Nhập chính xác "ROTATE" để xác nhận.'
            elif request.user.has_usable_password() and not request.user.check_password(
                current_password
            ):
                form_error = "Mật khẩu hiện tại không đúng."
            else:
                result = rotate_relay_credential(kind, request.user)
                generated_secret = result.plaintext
                generated_kind = kind
                if kind == GapoRelayCredential.Kind.INGRESS:
                    ingress_path = reverse(
                        "gapo_relay:ingress", args=[result.plaintext]
                    )
                    public_base_url = str(
                        getattr(settings, "PUBLIC_APP_BASE_URL", "") or ""
                    ).rstrip("/")
                    generated_ingress_url = (
                        f"{public_base_url}{ingress_path}"
                        if public_base_url
                        else request.build_absolute_uri(ingress_path)
                    )
                audit_message = (
                    f"Generated {result.credential.get_kind_display()}; "
                    "plaintext was displayed once and was not stored."
                )
                if result.created:
                    self.log_addition(request, result.credential, audit_message)
                else:
                    self.log_change(request, result.credential, audit_message)

        credentials = {
            credential.kind: credential
            for credential in GapoRelayCredential.objects.select_related("rotated_by")
        }
        rows = []
        now = timezone.now()
        for kind, label in GapoRelayCredential.Kind.choices:
            credential = credentials.get(kind)
            env_configured = bool(fallback_secret(kind))
            rows.append(
                {
                    "kind": kind,
                    "label": label,
                    "credential": credential,
                    "source": (
                        "Managed database"
                        if credential
                        else "Environment fallback"
                        if env_configured
                        else "Not configured"
                    ),
                    "previous_active": bool(
                        credential
                        and credential.previous_secret_hash
                        and credential.previous_valid_until
                        and credential.previous_valid_until > now
                    ),
                }
            )

        context = {
            **self.admin_site.each_context(request),
            "opts": self.model._meta,
            "title": "GAPO relay credential management",
            "rows": rows,
            "can_manage": self.has_change_permission(request),
            "password_required": request.user.has_usable_password(),
            "generated_secret": generated_secret,
            "generated_ingress_url": generated_ingress_url,
            "generated_kind": generated_kind,
            "form_error": form_error,
            "grace_seconds": int(
                getattr(settings, "GAPO_RELAY_SECRET_GRACE_SECONDS", 86400)
            ),
            **(extra_context or {}),
        }
        response = TemplateResponse(request, self.change_list_template, context)
        response["Cache-Control"] = "no-store, no-cache, must-revalidate, private"
        response["Pragma"] = "no-cache"
        return response
