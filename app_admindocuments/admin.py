from django.contrib import admin
from django import forms
from django.templatetags.static import static
from django.utils.html import format_html

from .models import (
    AdmAdministrativeDocument,
    AdmCompany,
    AdmContentType,
    AdmCourierCompany,
    AdmDepartment,
    AdmDocumentStatus,
    AdmDocumentType,
    AdmDocumentCounter,
    AdmIncomingDispatchStatus,
    AdmIncomingDispatchType,
    AdmIncomingGapoGroup,
    AdmIncomingDispatch,
    AdmIncomingDispatchImage,
    AdmParcelAutoNotifySetting,
    AdmParcelDynamicTemplate,
    AdmParcelNotificationBatch,
    AdmParcelRecipientCatalog,
    AdmParcelRecipientImportBatch,
    AdmParcelReceipt,
    AdmParcelReceiptImage,
    AdmParcelReceiptLog,
    AdmParcelSenderSuggestion,
    AdmPaperDocument,
    AdmPaperType,
    AdmSignerRole,
)


class AdmParcelDynamicTemplateAdminForm(forms.ModelForm):
    class Meta:
        model = AdmParcelDynamicTemplate
        fields = "__all__"

    class Media:
        js = ("admindocuments/admin/parcel_dynamic_template_preview.js",)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        variable_help = (
            "Biến dùng được: {{recipient_name}}, {{parcel_count}}, "
            "{{primary_sender}}, {{company_name}}, {{confirm_url}}"
        )
        self.fields["title_template"].help_text = variable_help
        self.fields["body_template"].help_text = variable_help
        self.fields["button_text"].help_text = variable_help
        self.fields["hero_image_url"].help_text = (
            "Để trống sẽ dùng ảnh bưu kiện mặc định của hệ thống."
        )


def _parcel_dynamic_default_image():
    return static("admindocuments/parcel-notify-card.svg")


class AdmIncomingDispatchStatusAdminForm(forms.ModelForm):
    class Meta:
        model = AdmIncomingDispatchStatus
        fields = "__all__"
        widgets = {
            "badge_text_color": forms.TextInput(attrs={"type": "color"}),
            "badge_bg_color": forms.TextInput(attrs={"type": "color"}),
        }


@admin.register(AdmDocumentType)
class AdmDocumentTypeAdmin(admin.ModelAdmin):
    list_display = ("code", "name")
    verbose_name_plural = "Document Types (Loại văn bản)"


@admin.register(AdmContentType)
class AdmContentTypeAdmin(admin.ModelAdmin):
    list_display = ("code", "name")
    verbose_name_plural = "Content Types (Loại nội dung văn bản)"


@admin.register(AdmSignerRole)
class AdmSignerRoleAdmin(admin.ModelAdmin):
    list_display = ("code", "title", "is_active")
    list_filter = ("is_active",)
    search_fields = ("code", "title")
    verbose_name_plural = "Signer Roles (Người ký)"


@admin.register(AdmDocumentStatus)
class AdmDocumentStatusAdmin(admin.ModelAdmin):
    list_display = ("code", "name")


@admin.register(AdmCompany)
class AdmCompanyAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "badge_text_color", "badge_bg_color", "badge_logo_url", "is_active")
    verbose_name_plural = "Companies (Công ty)"


@admin.register(AdmDepartment)
class AdmDepartmentAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "company")


@admin.register(AdmAdministrativeDocument)
class AdmAdministrativeDocumentAdmin(admin.ModelAdmin):
    list_display = (
        "document_number_full",
        "title",
        "doc_type",
        "status",
        "issuing_company",
        "expiry_date",
    )
    list_filter = ("doc_type", "status", "issuing_company")
    search_fields = ("title", "ticket_code", "document_number_full")
    readonly_fields = ("document_number_full", "running_number", "created_at")


@admin.register(AdmDocumentCounter)
class AdmDocumentCounterAdmin(admin.ModelAdmin):
    list_display = ("doc_type", "company", "year", "next_number", "updated_at")
    list_filter = ("doc_type", "company", "year")
    search_fields = ("doc_type__name", "company__name")


@admin.register(AdmPaperDocument)
class AdmPaperDocumentAdmin(admin.ModelAdmin):
    list_display = ("document_number_full", "paper_type", "requested_department", "status", "created_at")
    list_filter = ("paper_type", "requested_department", "status")
    search_fields = ("ticket_code", "courier_tracking_code", "summary")


@admin.register(AdmIncomingDispatch)
class AdmIncomingDispatchAdmin(admin.ModelAdmin):
    list_display = (
        "document_number",
        "incoming_item_type",
        "responsible_user",
        "sending_unit",
        "signer_name",
        "received_date",
        "receiving_company",
        "gapo_group",
        "status",
    )
    list_filter = ("incoming_item_type", "status", "receiving_company", "gapo_group", "processing_departments")
    search_fields = ("document_number", "sending_unit", "summary", "signer_name")
    readonly_fields = ("responsible_user", "received_date", "created_at")


@admin.register(AdmIncomingDispatchType)
class AdmIncomingDispatchTypeAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "is_active", "sort_order")
    list_filter = ("is_active",)
    search_fields = ("code", "name")


@admin.register(AdmIncomingDispatchStatus)
class AdmIncomingDispatchStatusAdmin(admin.ModelAdmin):
    form = AdmIncomingDispatchStatusAdminForm
    list_display = ("code", "name", "badge_preview", "badge_text_color", "badge_bg_color", "is_active", "sort_order")
    list_filter = ("is_active",)
    search_fields = ("code", "name")

    def badge_preview(self, obj):
        bg = obj.badge_bg_color or "#F3F4F6"
        fg = obj.badge_text_color or "#374151"
        return format_html(
            '<span style="display:inline-flex;padding:4px 10px;border-radius:999px;background:{};color:{};font-size:12px;font-weight:600;">{}</span>',
            bg,
            fg,
            obj.name,
        )

    badge_preview.short_description = "Badge"


@admin.register(AdmIncomingGapoGroup)
class AdmIncomingGapoGroupAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "gapo_group_id", "is_active", "sort_order")
    list_filter = ("is_active",)
    search_fields = ("code", "name", "gapo_group_id")


@admin.register(AdmIncomingDispatchImage)
class AdmIncomingDispatchImageAdmin(admin.ModelAdmin):
    list_display = ("id", "dispatch", "uploaded_by", "uploaded_at")
    list_filter = ("uploaded_at",)
    search_fields = ("dispatch__document_number", "dispatch__sending_unit")


@admin.register(AdmParcelReceipt)
class AdmParcelReceiptAdmin(admin.ModelAdmin):
    list_display = (
        "document_number",
        "received_by",
        "recipient_department",
        "recipient_name",
        "recipient_employee_code",
        "parcel_type",
        "sender_unit",
        "received_at",
        "receiving_company",
        "status",
    )
    list_filter = ("status", "receiving_company", "recipient_department", "parcel_type")
    search_fields = (
        "document_number",
        "sender_unit",
        "content",
        "tracking_code",
        "recipient_name",
        "recipient_employee_code",
        "recipient_gapo_user_id",
        "recipient_user__username",
    )
    readonly_fields = ("received_by", "received_at", "created_at", "confirmation_token", "proxy_qr_token")


@admin.register(AdmParcelReceiptImage)
class AdmParcelReceiptImageAdmin(admin.ModelAdmin):
    list_display = ("id", "parcel_receipt", "uploaded_by", "uploaded_at")
    list_filter = ("uploaded_at",)
    search_fields = ("parcel_receipt__document_number", "parcel_receipt__sender_unit")


@admin.register(AdmParcelSenderSuggestion)
class AdmParcelSenderSuggestionAdmin(admin.ModelAdmin):
    list_display = ("name", "is_active", "sort_order")
    list_filter = ("is_active",)
    search_fields = ("name",)


@admin.register(AdmParcelRecipientImportBatch)
class AdmParcelRecipientImportBatchAdmin(admin.ModelAdmin):
    list_display = (
        "original_name",
        "sheet_name",
        "imported_rows",
        "active_rows",
        "is_current",
        "imported_by",
        "created_at",
    )
    list_filter = ("is_current", "has_errors", "created_at")
    search_fields = ("original_name", "sheet_name", "checksum")


@admin.register(AdmParcelRecipientCatalog)
class AdmParcelRecipientCatalogAdmin(admin.ModelAdmin):
    list_display = (
        "full_name",
        "employee_code",
        "department_name",
        "gapo_user_id",
        "is_active_member",
        "import_batch",
    )
    list_filter = ("is_active_member", "department_name", "import_batch")
    search_fields = ("full_name", "employee_code", "gapo_user_id", "email")


@admin.register(AdmParcelReceiptLog)
class AdmParcelReceiptLogAdmin(admin.ModelAdmin):
    list_display = ("parcel_receipt", "action", "from_status", "to_status", "actor", "created_at")
    list_filter = ("action", "from_status", "to_status")
    search_fields = ("parcel_receipt__document_number", "note", "actor__username")


@admin.register(AdmParcelNotificationBatch)
class AdmParcelNotificationBatchAdmin(admin.ModelAdmin):
    list_display = ("id", "recipient_name", "parcel_count", "status", "notified_at", "confirmed_at")
    list_filter = ("status", "notified_at", "confirmed_at")
    search_fields = ("recipient_name", "recipient_employee_code", "recipient_department", "message_text")


@admin.register(AdmParcelDynamicTemplate)
class AdmParcelDynamicTemplateAdmin(admin.ModelAdmin):
    form = AdmParcelDynamicTemplateAdminForm
    list_display = ("name", "template_type", "is_active", "updated_at")
    list_filter = ("template_type", "is_active")
    readonly_fields = ("preview_card", "created_at", "updated_at")
    fieldsets = (
        (
            "Template",
            {
                "fields": (
                    "template_type",
                    "name",
                    "is_active",
                    "title_template",
                    "body_template",
                    "button_text",
                    "hero_image_url",
                    "button_bg_color",
                    "button_text_color",
                    "card_border_color",
                )
            },
        ),
        ("Preview", {"fields": ("preview_card",)}),
        ("Audit", {"fields": ("created_at", "updated_at")}),
    )

    def preview_card(self, obj):
        template = obj or AdmParcelDynamicTemplate()
        sample = template.sample_context()
        image_url = template.hero_image_url or _parcel_dynamic_default_image()
        title = template.render_text(template.title_template, sample)
        body = template.render_text(template.body_template, sample)
        button_text = template.render_text(template.button_text, sample)
        return format_html(
            """
            <div id="parcel-dynamic-preview"
                 style="max-width:420px;border:1px solid {border};border-radius:16px;overflow:hidden;background:#fff;box-shadow:0 8px 24px rgba(15,23,42,.08);"
                 data-default-image="{default_image}">
              <img id="parcel-preview-image" src="{image}" alt="preview" style="display:block;width:100%;height:200px;object-fit:cover;background:#f3f4f6;" />
              <div style="padding:16px 16px 12px 16px;">
                <div id="parcel-preview-title" style="font-size:16px;font-weight:600;color:#10203A;line-height:1.4;">{title}</div>
                <div id="parcel-preview-body" style="margin-top:8px;font-size:14px;color:#5B667A;line-height:1.5;white-space:pre-line;">{body}</div>
              </div>
              <div style="padding:0 16px 16px 16px;">
                <div id="parcel-preview-button"
                     style="height:44px;border-radius:10px;background:{button_bg};color:{button_fg};display:flex;align-items:center;justify-content:center;font-size:16px;font-weight:600;">
                  <span id="parcel-preview-button-text">{button_text}</span>
                </div>
              </div>
            </div>
            """,
            border=template.card_border_color or "#DADDE1",
            default_image=_parcel_dynamic_default_image(),
            image=image_url,
            title=title,
            body=body,
            button_bg=template.button_bg_color or "#16A34A",
            button_fg=template.button_text_color or "#FFFFFF",
            button_text=button_text,
        )

    preview_card.short_description = "Preview"


@admin.register(AdmParcelAutoNotifySetting)
class AdmParcelAutoNotifySettingAdmin(admin.ModelAdmin):
    list_display = ("name", "reminder_time_slots", "skip_weekends", "is_active", "updated_at")
    list_filter = ("skip_weekends", "is_active")

    @admin.display(description="Khung giờ nhắc")
    def reminder_time_slots(self, obj):
        return obj.reminder_send_times_display


@admin.register(AdmPaperType)
class AdmPaperTypeAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "is_active")
    list_filter = ("is_active",)
    search_fields = ("code", "name")


@admin.register(AdmCourierCompany)
class AdmCourierCompanyAdmin(admin.ModelAdmin):
    list_display = ("name", "contact", "is_active")
    list_filter = ("is_active",)
    search_fields = ("name", "contact")
