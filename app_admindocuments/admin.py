from django.contrib import admin

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
    AdmPaperDocument,
    AdmPaperType,
    AdmSignerRole,
)


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
    list_display = ("code", "name", "is_active", "sort_order")
    list_filter = ("is_active",)
    search_fields = ("code", "name")


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
