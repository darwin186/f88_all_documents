from datetime import date, timedelta

from django import forms

from app_document_campaigns.models import Campaign, CampaignType


class CampaignTypeSelect(forms.Select):
    def create_option(self, name, value, label, selected, index, subindex=None, attrs=None):
        option = super().create_option(name, value, label, selected, index, subindex, attrs)
        instance = getattr(value, "instance", None)
        if instance is not None:
            option["attrs"]["data-code-prefix"] = instance.code_prefix
        return option


class CampaignCreateForm(forms.ModelForm):
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
        fields = ("campaign_type", "name", "report_month", "response_deadline")
        labels = {
            "campaign_type": "Loại book lỗi",
            "name": "Tên chiến dịch",
        }
        widgets = {
            "campaign_type": CampaignTypeSelect(),
            "name": forms.TextInput(),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
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


class CampaignSettingsForm(CampaignDeadlineForm):
    class Meta:
        model = Campaign
        fields = ("name", "response_deadline")
        labels = {"name": "Tên chiến dịch"}
        widgets = {
            "name": forms.TextInput(attrs={"class": "dec-settings-input"}),
        }

    def save(self, commit=True):
        campaign = forms.ModelForm.save(self, commit=False)
        campaign.link_expires_at = campaign.response_deadline + timedelta(days=31)
        if commit:
            campaign.save(
                update_fields=["name", "response_deadline", "link_expires_at", "updated_at"]
            )
        return campaign
