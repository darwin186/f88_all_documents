from datetime import date, timedelta

from django import forms
from django.db.models import Q

from django.core.exceptions import ValidationError
from django.core.validators import validate_email

from app_document_campaigns.models import Campaign, CampaignAreaEmailConfig, CampaignEmailConfig, CampaignType, CampaignErrorBooking, CampaignResponseOption, ResponseGuidanceTemplate, RiskErrorCode, ShopResponseOption, ShopResponse
from app_document_campaigns.services.email_templates import EmailTemplateError, validate_area_templates, validate_templates
from app_document_campaigns.services.email_html import sanitize_email_template


def _email_list(value):
    values = []
    seen = set()
    for item in (value or "").replace(";", ",").replace("\n", ",").split(","):
        email = item.strip()
        if not email:
            continue
        try:
            validate_email(email)
        except ValidationError as exc:
            raise forms.ValidationError(f"Email không hợp lệ: {email}") from exc
        if email.lower() not in seen:
            seen.add(email.lower())
            values.append(email)
    if len(values) > 20:
        raise forms.ValidationError("Mỗi danh sách chỉ được tối đa 20 email.")
    return values


class CampaignEmailConfigForm(forms.ModelForm):
    cc_emails_text = forms.CharField(label="CC bổ sung (nhiều email)", required=False, widget=forms.Textarea(attrs={"rows": 2, "placeholder": "email1@f88.vn, email2@f88.vn"}))
    bcc_emails_text = forms.CharField(label="BCC nội bộ (nhiều email)", required=False, widget=forms.Textarea(attrs={"rows": 2, "placeholder": "audit@f88.vn, control@f88.vn"}))

    class Meta:
        model = CampaignEmailConfig
        fields = ("from_name", "subject_template", "body_template", "cc_area_manager", "support_email")
        labels = {
            "from_name": "Tên hiển thị người gửi",
            "subject_template": "Subject",
            "body_template": "Nội dung email",
            "cc_area_manager": "Tự động CC Quản lý khu vực",
            "support_email": "Email hỗ trợ",
        }
        widgets = {
            "body_template": forms.Textarea(attrs={"rows": 11}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["cc_emails_text"].initial = ", ".join(self.instance.cc_emails or [])
        self.fields["bcc_emails_text"].initial = ", ".join(self.instance.bcc_emails or [])

    def clean_cc_emails_text(self):
        return _email_list(self.cleaned_data.get("cc_emails_text"))

    def clean_bcc_emails_text(self):
        return _email_list(self.cleaned_data.get("bcc_emails_text"))

    def clean(self):
        cleaned = super().clean()
        cleaned["body_template"] = sanitize_email_template(cleaned.get("body_template"))
        try:
            validate_templates(cleaned.get("subject_template"), cleaned.get("body_template"))
        except EmailTemplateError as exc:
            raise forms.ValidationError(str(exc)) from exc
        return cleaned

    def save(self, commit=True, *, updated_by=None):
        config = super().save(commit=False)
        config.cc_emails = self.cleaned_data["cc_emails_text"]
        config.bcc_emails = self.cleaned_data["bcc_emails_text"]
        if self.changed_data and config.pk:
            config.template_version += 1
        config.updated_by = updated_by
        if commit:
            config.save()
        return config


class CampaignAreaEmailConfigForm(forms.ModelForm):
    cc_emails_text = forms.CharField(label="CC bổ sung (nhiều email)", required=False, widget=forms.Textarea(attrs={"rows": 2, "placeholder": "email1@f88.vn, email2@f88.vn"}))
    bcc_emails_text = forms.CharField(label="BCC nội bộ (nhiều email)", required=False, widget=forms.Textarea(attrs={"rows": 2, "placeholder": "audit@f88.vn, control@f88.vn"}))

    class Meta:
        model = CampaignAreaEmailConfig
        fields = (
            "from_name", "monitoring_subject_template", "monitoring_body_template",
            "confirmation_subject_template", "confirmation_body_template", "support_email",
        )
        labels = {
            "from_name": "Tên hiển thị người gửi",
            "monitoring_subject_template": "Subject theo dõi PGD",
            "monitoring_body_template": "Nội dung theo dõi PGD",
            "confirmation_subject_template": "Subject xác nhận lỗi",
            "confirmation_body_template": "Nội dung xác nhận lỗi",
            "support_email": "Email hỗ trợ",
        }
        widgets = {
            "monitoring_body_template": forms.Textarea(attrs={"rows": 8}),
            "confirmation_body_template": forms.Textarea(attrs={"rows": 8}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["cc_emails_text"].initial = ", ".join(self.instance.cc_emails or [])
        self.fields["bcc_emails_text"].initial = ", ".join(self.instance.bcc_emails or [])

    def clean_cc_emails_text(self):
        return _email_list(self.cleaned_data.get("cc_emails_text"))

    def clean_bcc_emails_text(self):
        return _email_list(self.cleaned_data.get("bcc_emails_text"))

    def clean(self):
        cleaned = super().clean()
        cleaned["monitoring_body_template"] = sanitize_email_template(cleaned.get("monitoring_body_template"))
        cleaned["confirmation_body_template"] = sanitize_email_template(cleaned.get("confirmation_body_template"))
        try:
            validate_area_templates(
                cleaned.get("monitoring_subject_template"), cleaned.get("monitoring_body_template"),
                cleaned.get("confirmation_subject_template"), cleaned.get("confirmation_body_template"),
            )
        except EmailTemplateError as exc:
            raise forms.ValidationError(str(exc)) from exc
        return cleaned

    def save(self, commit=True, *, updated_by=None):
        config = super().save(commit=False)
        config.cc_emails = self.cleaned_data["cc_emails_text"]
        config.bcc_emails = self.cleaned_data["bcc_emails_text"]
        if self.changed_data and config.pk:
            config.template_version += 1
        config.updated_by = updated_by
        if commit:
            config.save()
        return config


class CampaignResponseChoicesMixin:
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        selected = list(self.instance.response_options.all()) if self.instance.pk else []
        ids = {choice.option_id for choice in selected}
        available = list(ShopResponseOption.objects.filter(Q(is_active=True) | Q(pk__in=ids)).order_by("sort_order", "id"))
        self.fields["response_options"] = forms.ModelMultipleChoiceField(label="Danh sách phản hồi PGD", queryset=ShopResponseOption.objects.filter(pk__in=[option.pk for option in available]).order_by("sort_order", "id"), widget=forms.CheckboxSelectMultiple(), required=True, help_text="Tick lựa chọn áp dụng cho kỳ này. Khi đang phản hồi chỉ được thêm, không được bỏ bớt.")
        self.initial["response_options"] = list(ids) if self.instance.pk else list(ShopResponseOption.objects.filter(is_active=True).values_list("pk", flat=True))
        snapshots = {choice.option_id: choice.label for choice in selected}
        self.fields["response_options"].label_from_instance = lambda option: snapshots.get(option.pk, option.label)
        selected_guidance_ids = {
            choice.guidance_template_id for choice in selected if choice.guidance_template_id
        }
        guidance_by_option = {choice.option_id: choice.guidance_template_id for choice in selected}
        guidance_templates = ResponseGuidanceTemplate.objects.filter(
            Q(is_active=True) | Q(pk__in=selected_guidance_ids)
        ).order_by("sort_order", "id")
        self.response_guidance_fields = []
        self.response_guidance_field_names = []
        for option in available:
            field_name = f"response_guidance_{option.pk}"
            self.fields[field_name] = forms.ModelChoiceField(
                queryset=guidance_templates,
                required=False,
                label=snapshots.get(option.pk, option.label),
                initial=guidance_by_option.get(option.pk),
                empty_label="— Không hiển thị cảnh báo —",
                widget=forms.Select(
                    attrs={
                        "data-response-guidance-input": str(option.pk),
                    }
                ),
            )
            self.response_guidance_field_names.append(field_name)
            self.response_guidance_fields.append(
                {"option_id": option.pk, "option_label": snapshots.get(option.pk, option.label), "field": self[field_name]}
            )

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


class CampaignAreaChoicesMixin:
    def save_response_options(self):
        selected = list(self.cleaned_data["response_options"])
        ids = {option.pk for option in selected}
        self.instance.response_options.exclude(option_id__in=ids).delete()
        for option in selected:
            choice, _ = CampaignResponseOption.objects.get_or_create(
                campaign=self.instance,
                option=option,
                defaults={"value": option.code, "label": option.label, "sort_order": option.sort_order},
            )
            guidance_template = self.cleaned_data.get(f"response_guidance_{option.pk}")
            guidance_text = guidance_template.guidance_text if guidance_template else ""
            if (
                choice.guidance_template_id != getattr(guidance_template, "pk", None)
                or choice.guidance_text != guidance_text
            ):
                choice.guidance_template = guidance_template
                choice.guidance_text = guidance_text
                choice.save(update_fields=["guidance_template", "guidance_text"])


class CampaignRiskCodesMixin:
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._risk_codes_instance_was_new = not self.instance.pk
        self._risk_codes_submitted = self._risk_codes_instance_was_new or (
            self.is_bound and ("risk_error_codes_present" in self.data or "risk_error_codes" in self.data)
        )
        selected_ids = set(self.instance.risk_error_codes.values_list("pk", flat=True)) if self.instance.pk else set()
        available = RiskErrorCode.objects.filter(Q(is_active=True) | Q(pk__in=selected_ids)).order_by("sort_order", "code")
        self.fields["risk_error_codes"] = forms.ModelMultipleChoiceField(
            label="Mã lỗi QTRR áp dụng",
            queryset=available,
            widget=forms.CheckboxSelectMultiple(),
            required=False,
            help_text="Chọn các mã được phép mapping trên web và trong dropdown Excel ở Step 6.",
        )
        self.initial["risk_error_codes"] = list(selected_ids) if self.instance.pk else list(
            available.values_list("pk", flat=True)
        )

    def clean(self):
        cleaned = super().clean()
        selected = cleaned.get("risk_error_codes")
        if self.instance.pk and self._risk_codes_submitted and selected is not None:
            selected_ids = set(selected.values_list("pk", flat=True))
            used_ids = set(
                CampaignErrorBooking.objects.filter(error__campaign=self.instance)
                .values_list("risk_code_id", flat=True)
            )
            if not used_ids.issubset(selected_ids):
                self.add_error("risk_error_codes", "Không được bỏ mã lỗi đã được dùng để book lỗi trong kỳ này.")
        return cleaned

    def save_risk_error_codes(self):
        if self._risk_codes_submitted:
            self.instance.risk_error_codes.set(self.cleaned_data.get("risk_error_codes") or [])


class CampaignTypeSelect(forms.Select):
    def create_option(self, name, value, label, selected, index, subindex=None, attrs=None):
        option = super().create_option(name, value, label, selected, index, subindex, attrs)
        instance = getattr(value, "instance", None)
        if instance is not None:
            option["attrs"]["data-code-prefix"] = instance.code_prefix
        return option


class CampaignCreateForm(CampaignRiskCodesMixin, CampaignResponseChoicesMixin, CampaignAreaChoicesMixin, forms.ModelForm):
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
    area_response_deadline = forms.DateTimeField(
        label="Hạn cuối QLKV xác nhận",
        required=False,
        input_formats=["%Y-%m-%dT%H:%M"],
        widget=forms.DateTimeInput(
            format="%Y-%m-%dT%H:%M",
            attrs={
                "type": "datetime-local",
                "placeholder": "Chọn hạn QLKV xác nhận sau Team review",
            },
        ),
        help_text="Dùng cho link xác nhận QLKV ở Step 5, sau khi Team hoàn tất Step 4.",
    )

    class Meta:
        model = Campaign
        fields = ("campaign_type", "name", "report_month", "response_deadline", "area_response_deadline", "shop_instructions", "area_manager_instructions")
        labels = {
            "campaign_type": "Loại book lỗi",
            "name": "Tên chiến dịch",
            "area_manager_instructions": "Hướng dẫn QLKV",
        }
        widgets = {
            "campaign_type": CampaignTypeSelect(),
            "name": forms.TextInput(),
            "shop_instructions": forms.Textarea(attrs={"rows": 5, "placeholder": "Nhập hướng dẫn phản hồi cho PGD…"}),
            "area_manager_instructions": forms.Textarea(attrs={"rows": 5, "placeholder": "Nhập hướng dẫn hiển thị trên link xác nhận của QLKV…"}),
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
            self.save_risk_error_codes()
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
    # Keep the related deadline in this narrow ModelForm so model.clean() can
    # attach its cross-field validation error without Django raising ValueError.
    # The popup does not render or allow changing this field.
    area_response_deadline = forms.DateTimeField(
        required=False,
        disabled=True,
        widget=forms.HiddenInput(),
    )

    class Meta:
        model = Campaign
        fields = ("response_deadline", "area_response_deadline")

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


class CampaignSettingsForm(CampaignRiskCodesMixin, CampaignResponseChoicesMixin, CampaignAreaChoicesMixin, CampaignDeadlineForm):
    area_response_deadline = forms.DateTimeField(
        label="Hạn cuối QLKV xác nhận",
        required=False,
        input_formats=["%Y-%m-%dT%H:%M"],
        widget=forms.DateTimeInput(
            format="%Y-%m-%dT%H:%M",
            attrs={"type": "datetime-local", "class": "dec-deadline-input"},
        ),
        help_text="Khóa xác nhận QLKV ở Step 5 sau thời điểm này.",
    )

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
        fields = ("name", "response_deadline", "area_response_deadline", "shop_instructions", "area_manager_instructions")
        labels = {
            "name": "Tên chiến dịch",
            "area_manager_instructions": "Hướng dẫn QLKV",
        }
        widgets = {
            "name": forms.TextInput(attrs={"class": "dec-settings-input"}),
            "shop_instructions": forms.Textarea(attrs={"class": "dec-settings-input", "rows": 5, "placeholder": "Nhập hướng dẫn phản hồi cho PGD…"}),
            "area_manager_instructions": forms.Textarea(attrs={"class": "dec-settings-input", "rows": 5, "placeholder": "Nhập hướng dẫn hiển thị trên link xác nhận của QLKV…"}),
        }

    def save(self, commit=True):
        campaign = forms.ModelForm.save(self, commit=False)
        campaign.link_expires_at = campaign.response_deadline + timedelta(days=31) if "response_deadline" in self.changed_data else self.original_expiry
        if commit:
            campaign.save(
                update_fields=["name", "response_deadline", "area_response_deadline", "shop_instructions", "area_manager_instructions", "link_expires_at", "updated_at"]
            )
            self.save_response_options()
            self.save_risk_error_codes()
        return campaign
