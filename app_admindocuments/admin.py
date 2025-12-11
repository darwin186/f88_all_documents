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
    list_display = ("code", "title")
    verbose_name_plural = "Signer Roles (Người ký)"


@admin.register(AdmDocumentStatus)
class AdmDocumentStatusAdmin(admin.ModelAdmin):
    list_display = ("code", "name")


@admin.register(AdmCompany)
class AdmCompanyAdmin(admin.ModelAdmin):
    list_display = ("code", "name")
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
