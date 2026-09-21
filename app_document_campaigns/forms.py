from datetime import date, timedelta

from django import forms
from django.db.models import Q

from app_document_campaigns.models import Campaign, CampaignType, CampaignResponseOption, ShopResponseOption, ShopResponse


class CampaignResponseChoicesMixin:
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        selected = list(self.instance.response_options.all()) if self.instance.pk else []
        ids = {choice.option_id for choice in selected}
        self.fields["response_options"] = forms.ModelMultipleChoiceField(label="Danh sách phản hồi PGD", queryset=ShopResponseOption.objects.filter(Q(is_active=True) | Q(pk__in=ids)), widget=forms.CheckboxSelectMultiple(), required=True, help_text="Tick lựa chọn áp dụng cho kỳ này. Khi đang phản hồi chỉ được thêm, không được bỏ bớt.")
        self.initial["response_options"] = list(ids) if self.instance.pk else list(ShopResponseOption.objects.filter(is_active=True).values_list("pk", flat=True))
        snapshots = {choice.option_id: choice.label for choice in selected}
        self.fields["response_options"].label_from_instance = lambda option: snapshots.get(option.pk, option.label)

    def clean(self):
        cleaned = super().clean()
        selected = cleaned.get("response_options")
        if self.instance.pk and selected is not None:
            old = list(self.instance.response_options.all())
            ids = {option.pk for option in selected}
            removed = [choice for choice in old if choice.option_id not in ids]
            if self.instance.status == Campaign.Status.ACTIVE and removed:
                self.add_error("response_options", "Chiến dịch đang phản hồi: chỉ được thêm lựa chọn, không được bỏ bớt.")
            elif self.instance.status in (Campaign.Status.CLOSED, Campaign.Status.CANCELLED) and ids != {choice.option_id for choice in old}:
                self.add_error("response_options", "Chiến dịch đã chốt/hủy: không được thay đổi danh sách phản hồi.")
            elif removed and ShopResponse.objects.filter(error__campaign=self.instance, answer_code__in=[choice.value for choice in removed]).exists():
                self.add_error("response_options", "Không được bỏ lựa chọn đã có PGD sử dụng.")
        return cleaned

    def save_response_options(self):
        selected = list(self.cleaned_data["response_options"])
        ids = {option.pk for option in selected}
        self.instance.response_options.exclude(option_id__in=ids).delete()
        for option in selected:
            CampaignResponseOption.objects.get_or_create(campaign=self.instance, option=option, defaults={"value": option.code, "label": option.label, "sort_order": option.sort_order})


class CampaignTypeSelect(forms.Select):
    def create_option(self, name, value, label, selected, index, subindex=None, attrs=None):
        option = super().create_option(name, value, label, selected, index, subindex, attrs)
        instance = getattr(value, "instance", None)
        if instance is not None:
            option["attrs"]["data-code-prefix"] = instance.code_prefix
        return option


class CampaignCreateForm(CampaignResponseChoicesMixin, forms.ModelForm):
    report_month = forms.CharField(
        label="Tháng chứng từ",
        widget=forms.TextInput(
            attrs={
                "type": "text",
                "data-campaign-month": "",
                "placeholder": "Chọn tháng chứng từ",
                "autocomplete": "off",
            }
        ),
    )
    response_deadline = forms.DateTimeField(
        label="Hạn cuối PGD phản hồi",
        input_formats=["%Y-%m-%dT%H:%M"],
        widget=forms.DateTimeInput(
            format="%Y-%m-%dT%H:%M",
            attrs={
                "type": "text",
                "data-campaign-deadline": "",
                "placeholder": "Chọn ngày và giờ hết hạn",
                "autocomplete": "off",
            },
        ),
        help_text="Sau thời điểm này, link PGD chuyển sang chỉ đọc.",
    )

    class Meta:
        model = Campaign
        fields = ("campaign_type", "name", "report_month", "response_deadline", "shop_instructions", "area_manager_instructions")
        labels = {
            "campaign_type": "Loại book lỗi",
            "name": "Tên chiến dịch",
        }
        widgets = {
            "campaign_type": CampaignTypeSelect(),
            "name": forms.TextInput(),
            "shop_instructions": forms.Textarea(attrs={"rows": 5, "placeholder": "Nhập hướng dẫn phản hồi cho PGD…"}),
            "area_manager_instructions": forms.Textarea(attrs={"rows": 5, "placeholder": "Nhập thông điệp dành cho Quản lý khu vực…"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            if isinstance(field.widget, forms.CheckboxSelectMultiple):
                continue
            field.widget.attrs["class"] = (
                "w-full rounded-lg border border-gray-300 px-3 py-2 text-sm "
                "focus:border-emerald-600 focus:ring-emerald-600"
            )
        self.fields["campaign_type"].queryset = CampaignType.objects.filter(is_active=True)
        self.fields["campaign_type"].empty_label = "Chọn loại book lỗi"

    def clean_report_month(self):
        value = self.cleaned_data["report_month"]
        try:
            year, month = (int(part) for part in value.split("-", 1))
            return date(year, month, 1)
        except (TypeError, ValueError) as exc:
            raise forms.ValidationError("Tháng chứng từ không hợp lệ.") from exc

    def save(self, commit=True):
        campaign = super().save(commit=False)
        campaign.link_expires_at = campaign.response_deadline + timedelta(days=31)
        if commit:
            campaign.save()
            self.save_response_options()
        return campaign


class CampaignDeadlineForm(forms.ModelForm):
    response_deadline = forms.DateTimeField(
        label="Hạn cuối PGD phản hồi",
        input_formats=["%Y-%m-%dT%H:%M"],
        widget=forms.DateTimeInput(
            format="%Y-%m-%dT%H:%M",
            attrs={"type": "datetime-local", "class": "dec-deadline-input"},
        ),
    )

    class Meta:
        model = Campaign
        fields = ("response_deadline",)

    def clean(self):
        cleaned_data = super().clean()
        deadline = cleaned_data.get("response_deadline")
        if deadline:
            # Keep the model-level deadline/expiry validation consistent during ModelForm validation.
            self.instance.link_expires_at = deadline + timedelta(days=31)
        return cleaned_data

    def save(self, commit=True):
        campaign = super().save(commit=False)
        campaign.link_expires_at = campaign.response_deadline + timedelta(days=31)
        if commit:
            campaign.save(update_fields=["response_deadline", "link_expires_at", "updated_at"])
        return campaign


class CampaignSettingsForm(CampaignResponseChoicesMixin, CampaignDeadlineForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.original_expiry = self.instance.link_expires_at

    def clean(self):
        deadline = self.cleaned_data.get("response_deadline")
        original = self.initial.get("response_deadline")
        if deadline and original and deadline.replace(second=0, microsecond=0) == original.replace(second=0, microsecond=0):
            self.cleaned_data["response_deadline"] = original
            if "response_deadline" in self.changed_data:
                self.changed_data.remove("response_deadline")
        cleaned = super().clean()
        if "response_deadline" not in self.changed_data:
            self.instance.link_expires_at = self.original_expiry
        return cleaned

    class Meta:
        model = Campaign
        fields = ("name", "response_deadline", "shop_instructions", "area_manager_instructions")
        labels = {"name": "Tên chiến dịch"}
        widgets = {
            "name": forms.TextInput(attrs={"class": "dec-settings-input"}),
            "shop_instructions": forms.Textarea(attrs={"class": "dec-settings-input", "rows": 5, "placeholder": "Nhập hướng dẫn phản hồi cho PGD…"}),
            "area_manager_instructions": forms.Textarea(attrs={"class": "dec-settings-input", "rows": 5, "placeholder": "Nhập thông điệp dành cho Quản lý khu vực…"}),
        }

    def save(self, commit=True):
        campaign = forms.ModelForm.save(self, commit=False)
        campaign.link_expires_at = campaign.response_deadline + timedelta(days=31) if "response_deadline" in self.changed_data else self.original_expiry
        if commit:
            campaign.save(
                update_fields=["name", "response_deadline", "shop_instructions", "area_manager_instructions", "link_expires_at", "updated_at"]
            )
            self.save_response_options()
        return campaign
