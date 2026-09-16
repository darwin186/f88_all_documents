from django import forms
from django.contrib import admin

from app_document_campaigns.models import (
    AreaConfirmation,
    Campaign,
    CampaignType,
    CampaignError,
    CampaignImportSource,
    CampaignImportJob,
    CampaignSnapshot,
    CampaignSnapshotMetric,
    CampaignStagingRow,
    CampaignVersion,
    ChecklistQuestion,
    ChecklistTemplate,
    ShopAccessLink,
    ShopResponse,
    ShopSubmission,
    TeamReview,
)


@admin.register(Campaign)
class CampaignAdmin(admin.ModelAdmin):
    list_display = ("code", "campaign_type", "name", "report_month", "status", "response_deadline", "link_expires_at")
    list_filter = ("campaign_type", "status", "report_month")
    search_fields = ("code", "name")


@admin.register(CampaignError)
class CampaignErrorAdmin(admin.ModelAdmin):
    list_display = ("error_uid", "campaign", "shop", "error_type", "status")
    list_filter = ("campaign", "error_type", "status", "region", "area_manager")
    search_fields = ("source_key", "contract_code", "shop__shop_name")
    raw_id_fields = ("shop", "folder", "document")


admin.site.register(CampaignVersion)


class ChecklistQuestionAdminForm(forms.ModelForm):
    error_type = forms.ChoiceField(
        label="Áp dụng cho loại lỗi",
        choices=[("", "Tất cả loại lỗi"), *CampaignError.ErrorType.choices],
        required=False,
    )
    options_text = forms.CharField(
        label="Các lựa chọn trong dropdown",
        required=False,
        widget=forms.Textarea(attrs={"rows": 5, "placeholder": "Mỗi lựa chọn nhập trên một dòng"}),
        help_text="Mỗi dòng là một lựa chọn PGD nhìn thấy. Không cần nhập JSON.",
    )

    class Meta:
        model = ChecklistQuestion
        exclude = ("options",)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            lines = []
            for option in self.instance.options or []:
                if isinstance(option, dict):
                    value = str(option.get("value", "")).strip()
                    label = str(option.get("label", value)).strip()
                    lines.append(label if label == value else f"{value} | {label}")
                else:
                    lines.append(str(option))
            self.fields["options_text"].initial = "\n".join(lines)

    def clean_options_text(self):
        lines = [line.strip() for line in self.cleaned_data.get("options_text", "").splitlines()]
        return [line for line in lines if line]

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.options = self.cleaned_data["options_text"]
        if commit:
            instance.save()
            self.save_m2m()
        return instance


class ChecklistQuestionInline(admin.StackedInline):
    model = ChecklistQuestion
    form = ChecklistQuestionAdminForm
    extra = 0
    fields = (
        "code",
        "label",
        "question_type",
        "error_type",
        "options_text",
        "is_required",
        "sort_order",
        "is_active",
    )


@admin.register(CampaignType)
class CampaignTypeAdmin(admin.ModelAdmin):
    list_display = ("code", "code_prefix", "name", "shop_checklist_template", "is_active", "sort_order")
    list_editable = ("is_active", "sort_order")
    autocomplete_fields = ("shop_checklist_template",)
admin.site.register(CampaignImportSource)
admin.site.register(CampaignImportJob)
admin.site.register(CampaignStagingRow)
@admin.register(ChecklistTemplate)
class ChecklistTemplateAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "version_number", "is_active", "created_at")
    list_filter = ("is_active",)
    search_fields = ("code", "name")
    readonly_fields = ("created_by", "created_at")
    inlines = (ChecklistQuestionInline,)

    def save_model(self, request, obj, form, change):
        if not obj.created_by_id:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)


@admin.register(ChecklistQuestion)
class ChecklistQuestionAdmin(admin.ModelAdmin):
    form = ChecklistQuestionAdminForm
    list_display = ("code", "label", "template", "question_type", "error_type", "is_active", "sort_order")
    list_filter = ("template", "question_type", "error_type", "is_active")
    search_fields = ("code", "label", "template__name")
admin.site.register(ShopAccessLink)
admin.site.register(ShopResponse)
admin.site.register(ShopSubmission)
admin.site.register(TeamReview)
admin.site.register(AreaConfirmation)
admin.site.register(CampaignSnapshot)
admin.site.register(CampaignSnapshotMetric)
