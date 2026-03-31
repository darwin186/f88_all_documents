from datetime import datetime

from django import forms
from django.utils import timezone

from app_documents.models import Region, Shop

from .models import (
    AdmAdministrativeDocument,
    AdmIncomingDispatchType,
    AdmIncomingDispatch,
    AdmParcelRecipientCatalog,
    AdmParcelRecipientImportBatch,
    AdmParcelAutoNotifySetting,
    AdmParcelReceipt,
    AdmParcelSenderSuggestion,
    AdmPaperDocument,
    AdmPaperType,
    AdmCourierCompany,
    AdmDocumentType,
    AdmContentType,
    AdmSignerRole,
    AdmDocumentStatus,
    AdmCompany,
    AdmDepartment,
)


class AdmAdministrativeDocumentForm(forms.ModelForm):
    attachment_link = forms.CharField(required=False, label="Link đính kèm")
    issue_date = forms.DateField(
        required=False,
        label="Ngày ban hành",
        input_formats=["%d/%m/%Y", "%Y-%m-%d"],
        widget=forms.DateInput(attrs={"type": "text"}),
    )
    effective_date = forms.DateField(
        required=False,
        label="Ngày hiệu lực",
        input_formats=["%d/%m/%Y", "%Y-%m-%d"],
        widget=forms.DateInput(attrs={"type": "text"}),
    )
    reference_document = forms.ModelChoiceField(
        queryset=AdmAdministrativeDocument.objects.none(),
        required=False,
        label="Tham chiếu tới văn bản",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        qs = AdmAdministrativeDocument.objects.order_by("-created_at")
        self.fields["reference_document"].queryset = qs
        self.fields["expiry_date"].input_formats = ["%d/%m/%Y", "%Y-%m-%d"]

    class Meta:
        model = AdmAdministrativeDocument
        fields = [
            "doc_type",
            "content_type",
            "reference_number",
            "reference_document",
            "is_reference_document",
            "title",
            "signer_role",
            "issuing_company",
            "issuing_department",
            "issue_date",
            "effective_date",
            "expiry_date",
            "attachment",
            "status",
            "ticket_code",
            "note",
        ]
        widgets = {
            "expiry_date": forms.DateInput(
                attrs={"type": "text"}, format="%d/%m/%Y"
            ),
            "note": forms.Textarea(attrs={"rows": 3}),
        }
        labels = {
            "doc_type": "Loại văn bản",
            "content_type": "Loại nội dung",
            "reference_number": "Số hiệu VB được sửa/thay thế",
            "title": "Tên văn bản",
            "signer_role": "Người ký",
            "issuing_company": "Công ty ban hành",
            "issuing_department": "Phòng ban ban hành",
            "effective_date": "Ngày hiệu lực",
            "expiry_date": "Ngày hết hiệu lực",
            "is_reference_document": "Đánh dấu văn bản tham chiếu",
            "attachment": "File đính kèm",
            "status": "Trạng thái văn bản",
            "ticket_code": "Mã ticket yêu cầu",
            "note": "Ghi chú",
        }

    def clean(self):
        cleaned = super().clean()
        ref_doc = cleaned.get("reference_document")
        ref_number = cleaned.get("reference_number")
        if ref_doc and not ref_number:
            cleaned["reference_number"] = ref_doc.document_number_full
        if ref_doc and self.instance.pk and ref_doc.pk == self.instance.pk:
            self.add_error("reference_document", "Không thể tham chiếu chính văn bản này.")
        doc_type = cleaned.get("doc_type")
        title = cleaned.get("title")
        reference_number = cleaned.get("reference_number")
        year_now = timezone.now().year

        if reference_number and doc_type:
            qs = AdmAdministrativeDocument.objects.filter(
                doc_type=doc_type,
                reference_number__iexact=reference_number,
                created_at__year=year_now,
            )
            if getattr(self, "instance", None) and self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                self.add_error(
                    "reference_number",
                    "Số hiệu đã tồn tại trong năm hiện tại cho loại văn bản này.",
                )

        if title and doc_type:
            qs2 = AdmAdministrativeDocument.objects.filter(
                doc_type=doc_type,
                title__iexact=title,
                created_at__year=year_now,
            )
            if getattr(self, "instance", None) and self.instance.pk:
                qs2 = qs2.exclude(pk=self.instance.pk)
            if qs2.exists():
                self.add_error(
                    "title",
                    "Tiêu đề trùng với một văn bản khác trong năm hiện tại.",
                )

        return cleaned


class AdmAdministrativeDocumentUpdateForm(forms.ModelForm):
    attachment_link = forms.CharField(required=False, label="Link đính kèm")
    issue_date = forms.DateField(
        required=False,
        label="Ngày ban hành",
        input_formats=["%d/%m/%Y", "%Y-%m-%d"],
        widget=forms.DateInput(attrs={"type": "text"}),
    )
    effective_date = forms.DateField(
        required=False,
        label="Ngày hiệu lực",
        input_formats=["%d/%m/%Y", "%Y-%m-%d"],
        widget=forms.DateInput(attrs={"type": "text"}),
    )
    reference_document = forms.ModelChoiceField(
        queryset=AdmAdministrativeDocument.objects.none(),
        required=False,
        label="Tham chiếu tới văn bản",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        qs = AdmAdministrativeDocument.objects.order_by("-created_at")
        if getattr(self, "instance", None) and self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        self.fields["reference_document"].queryset = qs
        self.fields["expiry_date"].input_formats = ["%d/%m/%Y", "%Y-%m-%d"]

    class Meta:
        model = AdmAdministrativeDocument
        fields = [
            "doc_type",
            "content_type",
            "reference_number",
            "reference_document",
            "is_reference_document",
            "title",
            "signer_role",
            "issuing_company",
            "issuing_department",
            "issue_date",
            "effective_date",
            "expiry_date",
            "attachment",
            "status",
            "ticket_code",
            "note",
        ]
        widgets = {
            "expiry_date": forms.DateInput(
                attrs={"type": "text"}, format="%d/%m/%Y"
            ),
            "note": forms.Textarea(attrs={"rows": 3}),
        }

    def clean(self):
        cleaned = super().clean()
        ref_doc = cleaned.get("reference_document")
        ref_number = cleaned.get("reference_number")
        if ref_doc and not ref_number:
            cleaned["reference_number"] = ref_doc.document_number_full
        if ref_doc and self.instance.pk and ref_doc.pk == self.instance.pk:
            self.add_error("reference_document", "Không thể tham chiếu chính văn bản này.")
        doc_type = cleaned.get("doc_type")
        title = cleaned.get("title")
        reference_number = cleaned.get("reference_number")
        year_now = timezone.now().year

        if reference_number and doc_type:
            qs = AdmAdministrativeDocument.objects.filter(
                doc_type=doc_type,
                reference_number__iexact=reference_number,
                created_at__year=year_now,
            )
            if getattr(self, "instance", None) and self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                self.add_error(
                    "reference_number",
                    "Số hiệu đã tồn tại trong năm hiện tại cho loại văn bản này.",
                )

        if title and doc_type:
            qs2 = AdmAdministrativeDocument.objects.filter(
                doc_type=doc_type,
                title__iexact=title,
                created_at__year=year_now,
            )
            if getattr(self, "instance", None) and self.instance.pk:
                qs2 = qs2.exclude(pk=self.instance.pk)
            if qs2.exists():
                self.add_error(
                    "title",
                    "Tiêu đề trùng với một văn bản khác trong năm hiện tại.",
                )
        return cleaned


class AdmPaperDocumentForm(forms.ModelForm):
    region = forms.ChoiceField(required=False, label="Miền")
    paper_type = forms.ModelChoiceField(
        queryset=AdmPaperType.objects.filter(is_active=True).order_by("name"),
        label="Loại giấy",
    )
    requested_department = forms.ModelChoiceField(
        queryset=Shop.objects.all().order_by("shop_name"),
        label="Phòng giao dịch",
        required=False,
    )
    department = forms.ModelChoiceField(
        queryset=AdmDepartment.objects.all().order_by("name"),
        required=False,
        label="Phòng ban nội bộ",
    )
    courier_company = forms.ModelChoiceField(
        queryset=AdmCourierCompany.objects.filter(is_active=True).order_by("name"),
        label="Đơn vị CPN",
        required=False,
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        region_choices = [("", "Chọn miền")]
        region_choices += [
            (region.region_name, region.region_name)
            for region in Region.objects.exclude(pk=3).order_by("region_name")
        ]
        self.fields["region"].choices = region_choices
        base_classes = "block w-full rounded-lg border border-gray-300 px-3 py-2 text-xs focus:outline-none focus:ring-2 focus:ring-green-200 focus:border-f88green"
        for name, field in self.fields.items():
            existing = field.widget.attrs.get("class", "")
            field.widget.attrs["class"] = f"{existing} {base_classes}".strip()
        self.fields["department"].empty_label = "Chọn phòng ban"
        self.fields["requested_department"].empty_label = "Phòng giao dịch"
        self.fields["courier_company"].empty_label = "Chọn đơn vị CPN"

    class Meta:
        model = AdmPaperDocument
        fields = [
            "paper_type",
            "region",
            "requested_department",
            "department",
            "ticket_code",
            "summary",
            "courier_company",
            "courier_tracking_code",
            "status",
            "note",
        ]
        widgets = {
            "note": forms.Textarea(attrs={"rows": 3}),
        }
        labels = {
            "region": "Miền",
            "ticket_code": "Mã ticket yêu cầu",
            "summary": "Nội dung",
            "courier_tracking_code": "Mã vận đơn CPN",
            "status": "Tình trạng",
            "note": "Ghi chú",
        }

    def clean(self):
        cleaned = super().clean()
        requested_department = cleaned.get("requested_department")
        internal_department = cleaned.get("department")
        if not requested_department and not internal_department:
            self.add_error(
                "requested_department",
                "Chọn Phòng giao dịch hoặc Phòng ban nội bộ (có thể chọn cả hai).",
            )
            self.add_error(
                "department",
                "Chọn Phòng ban nội bộ hoặc Phòng giao dịch (có thể chọn cả hai).",
            )
        return cleaned


class _BaseIncomingReceiptForm(forms.ModelForm):
    signer_name = forms.CharField(
        required=True,
        label="Người ký",
    )
    processing_department = forms.ModelChoiceField(
        queryset=AdmDepartment.objects.select_related("company")
        .filter(is_active=True)
        .order_by("company__code", "name"),
        required=True,
        label="Phòng ban xử lý",
    )
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        base_classes = "block w-full rounded-lg border border-gray-300 px-3 py-2 text-xs focus:outline-none focus:ring-2 focus:ring-green-200 focus:border-f88green"
        for field in self.fields.values():
            existing = field.widget.attrs.get("class", "")
            field.widget.attrs["class"] = f"{existing} {base_classes}".strip()

        self.fields["receiving_company"].queryset = (
            AdmCompany.objects.filter(is_active=True).order_by("name")
        )
        self.fields["receiving_company"].empty_label = "Chọn công ty nhận"
        self.fields["processing_department"].empty_label = "Chọn phòng ban xử lý"

    def clean_processing_department(self):
        department = self.cleaned_data.get("processing_department")
        if not department:
            raise forms.ValidationError("Cần chọn phòng ban xử lý.")
        return department

    def save(self, commit=True):
        instance = super().save(commit=False)
        department = self.cleaned_data.get("processing_department")
        if not (instance.document_number or "").strip():
            instance.document_number = None

        self._selected_processing_department = department

        if commit:
            instance.save()
            self._save_processing_department_m2m()
        else:
            self.save_m2m = self._save_m2m_with_processing_department
        return instance

    def _save_m2m_with_processing_department(self):
        self._save_m2m()
        self._save_processing_department_m2m()

    def _save_processing_department_m2m(self):
        department = getattr(self, "_selected_processing_department", None)
        if self.instance.pk and department is not None:
            self.instance.processing_departments.set([department])


def _apply_small_field_styles(form):
    base_classes = "block w-full rounded-lg border border-gray-300 px-3 py-2 text-xs focus:outline-none focus:ring-2 focus:ring-green-200 focus:border-f88green"
    checkbox_classes = "h-4 w-4 rounded border-gray-300 text-f88green focus:ring-2 focus:ring-green-200 focus:ring-offset-0"
    for field in form.fields.values():
        existing = field.widget.attrs.get("class", "")
        if isinstance(field.widget, forms.CheckboxInput):
            field.widget.attrs["class"] = f"{existing} {checkbox_classes}".strip()
            continue
        field.widget.attrs["class"] = f"{existing} {base_classes}".strip()


class AdmIncomingDispatchForm(_BaseIncomingReceiptForm):
    incoming_item_type = forms.ModelChoiceField(
        queryset=AdmIncomingDispatchType.objects.none(),
        required=True,
        label="Loại tiếp nhận",
        widget=forms.HiddenInput,
    )

    class Meta:
        model = AdmIncomingDispatch
        fields = [
            "document_number",
            "sending_unit",
            "signer_name",
            "summary",
            "incoming_item_type",
            "receiving_company",
        ]
        labels = {
            "document_number": "Số hiệu văn bản",
            "sending_unit": "Đơn vị gửi",
            "signer_name": "Người ký",
            "summary": "Tên trích yếu, nội dung",
            "receiving_company": "Công ty nhận",
        }
        widgets = {
            "summary": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        item_type_code = kwargs.pop("item_type_code", "")
        super().__init__(*args, **kwargs)
        self.fields["incoming_item_type"].queryset = (
            AdmIncomingDispatchType.objects.filter(
                is_active=True, code="cong_van"
            ).order_by("sort_order", "name")
        )
        if item_type_code:
            self.fields["incoming_item_type"].initial = item_type_code


class AdmParcelReceiptForm(forms.ModelForm):
    UNKNOWN_RECIPIENT_LABEL = "Chưa xác định"
    UNKNOWN_DEPARTMENT_VALUE = "__unknown__"

    recipient_department = forms.ChoiceField(
        required=False,
        label="Phòng ban",
    )
    recipient_directory = forms.ModelChoiceField(
        queryset=AdmParcelRecipientCatalog.objects.none(),
        required=False,
        label="Người nhận",
    )
    recipient_unknown = forms.BooleanField(required=False, widget=forms.HiddenInput())
    parcel_type = forms.ChoiceField(
        required=True,
        label="Loại bưu phẩm",
        choices=AdmParcelReceipt.ParcelType.choices,
    )

    class Meta:
        model = AdmParcelReceipt
        fields = [
            "recipient_department",
            "recipient_directory",
            "parcel_type",
            "sender_unit",
            "content",
            "tracking_code",
            "receiving_company",
        ]
        labels = {
            "sender_unit": "Đơn vị gửi",
            "content": "Nội dung",
            "tracking_code": "Mã vận đơn",
            "receiving_company": "Công ty nhận",
        }
        widgets = {
            "content": forms.TextInput(attrs={"maxlength": 255}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _apply_small_field_styles(self)
        parcel_field_classes = (
            "block w-full rounded-2xl border border-[#e6ebf2] bg-[#f7f9fc] px-4 py-3 "
            "text-[11px] text-slate-700 placeholder:text-[11px] placeholder:text-slate-400 "
            "focus:border-emerald-300 focus:outline-none focus:ring-4 focus:ring-emerald-100"
        )
        for field_name, field in self.fields.items():
            existing = field.widget.attrs.get("class", "")
            field.widget.attrs["class"] = f"{existing} {parcel_field_classes}".strip()
            if field_name in {"recipient_department", "recipient_directory", "parcel_type", "receiving_company"}:
                field.widget.attrs["class"] = f"{field.widget.attrs['class']} appearance-none".strip()
        self.fields["receiving_company"].queryset = (
            AdmCompany.objects.filter(is_active=True).order_by("name")
        )
        self.fields["receiving_company"].empty_label = "Chọn công ty nhận"

        current_batch = (
            AdmParcelRecipientImportBatch.objects.filter(is_current=True)
            .order_by("-created_at")
            .first()
        )
        departments = []
        seen = set()
        recipient_queryset = AdmParcelRecipientCatalog.objects.none()
        if current_batch:
            recipient_queryset = current_batch.recipients.filter(
                is_active_member=True
            ).exclude(department_name__exact="").order_by(
                "department_name", "full_name", "employee_code"
            )
        for recipient in recipient_queryset:
            department = (recipient.department_name or "").strip()
            if department and department not in seen:
                seen.add(department)
                departments.append((department, department))
        self.fields["recipient_department"].choices = [
            ("", "Chọn phòng ban"),
            (self.UNKNOWN_DEPARTMENT_VALUE, self.UNKNOWN_RECIPIENT_LABEL),
        ] + departments
        self.fields["recipient_directory"].queryset = recipient_queryset
        self.fields["recipient_directory"].empty_label = "Chọn người nhận"
        self.fields["recipient_directory"].label_from_instance = (
            lambda recipient: self._recipient_label(recipient)
        )
        self.fields["content"].widget.attrs["maxlength"] = 255
        self.fields["content"].help_text = "Tối đa 255 ký tự."
        self.sender_suggestions = list(
            AdmParcelSenderSuggestion.objects.filter(is_active=True)
            .order_by("sort_order", "name")
            .values_list("name", flat=True)
        )

        if self.instance.pk:
            self.initial["recipient_department"] = self.instance.recipient_department
            self.initial["recipient_unknown"] = self.instance.recipient_directory_id is None
        elif not self.is_bound:
            self.initial.setdefault(
                "parcel_type",
                AdmParcelReceipt.ParcelType.DOSSIER,
            )

    def _recipient_label(self, recipient):
        full_name = recipient.full_name or recipient.email or recipient.gapo_user_id
        employee_code = recipient.employee_code or ""
        department = recipient.department_name or ""
        label = full_name
        if employee_code:
            label = f"{full_name} - {employee_code}"
        if department:
            label = f"{label} ({department})"
        return label

    def _is_unknown_recipient_selected(self):
        if self.is_bound:
            raw_value = self.data.get(self.add_prefix("recipient_unknown"))
        else:
            raw_value = self.initial.get("recipient_unknown")
        return str(raw_value).strip().lower() in {"1", "true", "on", "yes"}

    def clean_recipient_department(self):
        department = (self.cleaned_data.get("recipient_department") or "").strip()
        if department == self.UNKNOWN_DEPARTMENT_VALUE:
            return self.UNKNOWN_RECIPIENT_LABEL
        if not department:
            raise forms.ValidationError("Cần chọn phòng ban hoặc Chưa xác định.")
        return department

    def clean_recipient_directory(self):
        recipient = self.cleaned_data.get("recipient_directory")
        if self._is_unknown_recipient_selected():
            return None
        if not recipient:
            raise forms.ValidationError("Cần chọn người nhận hoặc Chưa xác định.")
        if not (recipient.gapo_user_id or "").strip():
            raise forms.ValidationError("Người nhận chưa có GAPO ID.")
        return recipient

    def clean_sender_unit(self):
        sender_unit = (self.cleaned_data.get("sender_unit") or "").strip()
        if not sender_unit:
            raise forms.ValidationError("Cần nhập đơn vị gửi.")
        return sender_unit

    def clean_content(self):
        content = (self.cleaned_data.get("content") or "").strip()
        if len(content) > 255:
            raise forms.ValidationError("Nội dung tối đa 255 ký tự.")
        return content

    def clean(self):
        cleaned = super().clean()
        recipient_department = cleaned.get("recipient_department")
        recipient = cleaned.get("recipient_directory")
        if self._is_unknown_recipient_selected():
            cleaned["recipient_unknown"] = True
            cleaned["recipient_directory"] = None
            return cleaned
        actual_department = (getattr(recipient, "department_name", "") or "").strip()
        if recipient and recipient_department and actual_department != recipient_department:
            self.add_error(
                "recipient_directory",
                "Người nhận không thuộc phòng ban đã chọn.",
            )
        return cleaned

    def save(self, commit=True):
        instance = super().save(commit=False)
        recipient = self.cleaned_data.get("recipient_directory")
        instance.recipient_department = self.cleaned_data["recipient_department"]
        instance.recipient_directory = recipient
        if recipient is None:
            instance.recipient_name = self.UNKNOWN_RECIPIENT_LABEL
            instance.recipient_employee_code = ""
            instance.recipient_gapo_user_id = ""
        else:
            instance.recipient_name = recipient.full_name
            instance.recipient_employee_code = recipient.employee_code
            instance.recipient_gapo_user_id = recipient.gapo_user_id
        instance.recipient_user = None
        instance.document_number = None
        if commit:
            instance.save()
        return instance


class AdmParcelRecipientImportForm(forms.ModelForm):
    class Meta:
        model = AdmParcelRecipientImportBatch
        fields = ["file"]
        labels = {"file": "File danh sách người nhận"}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["file"].widget.attrs["accept"] = ".xlsx,.xlsm"
        self.fields["file"].widget.attrs["class"] = (
            "block w-full rounded-lg border border-gray-300 px-3 py-2 text-sm "
            "focus:outline-none focus:ring-2 focus:ring-green-200 focus:border-f88green"
        )

    def clean_file(self):
        file = self.cleaned_data["file"]
        name = (getattr(file, "name", "") or "").lower()
        if not name.endswith(".xlsx") and not name.endswith(".xlsm"):
            raise forms.ValidationError("Chỉ hỗ trợ file Excel .xlsx hoặc .xlsm.")
        return file


class AdmParcelAutoNotifySettingForm(forms.ModelForm):
    reminder_send_times = forms.CharField(
        label="Các khung giờ gửi tự động",
        help_text="Nhập nhiều giờ theo định dạng HH:MM, phân tách bằng dấu phẩy. Ví dụ: 09:00, 14:00, 16:30",
    )

    class Meta:
        model = AdmParcelAutoNotifySetting
        fields = ["name", "reminder_send_times", "skip_weekends", "is_active"]
        labels = {
            "name": "Tên cấu hình",
            "skip_weekends": "Bỏ qua thứ 7, chủ nhật",
            "is_active": "Đang áp dụng",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk and not self.is_bound:
            self.initial["reminder_send_times"] = self.instance.reminder_send_times_display
        _apply_small_field_styles(self)
        for field in self.fields.values():
            existing = field.widget.attrs.get("class", "")
            if isinstance(field.widget, forms.CheckboxInput):
                field.widget.attrs["class"] = (
                    f"{existing} h-4 w-4 rounded border-gray-300 text-f88green "
                    "focus:ring-2 focus:ring-green-200 focus:ring-offset-0"
                ).strip()
                continue
            field.widget.attrs["class"] = (
                f"{existing} block w-full rounded-lg border border-gray-300 px-3 py-2 "
                "focus:outline-none focus:ring-2 focus:ring-green-200 focus:border-f88green"
            ).strip()

    def clean_reminder_send_times(self):
        raw_value = (self.cleaned_data.get("reminder_send_times") or "").strip()
        if not raw_value:
            raise forms.ValidationError("Cần nhập ít nhất 1 khung giờ.")

        normalized_slots = []
        seen = set()
        for chunk in raw_value.replace(";", ",").split(","):
            value = chunk.strip()
            if not value:
                continue
            try:
                parsed = datetime.strptime(value, "%H:%M").time()
            except ValueError:
                raise forms.ValidationError(
                    f"Khung giờ '{value}' không đúng định dạng HH:MM."
                )
            slot_key = parsed.strftime("%H:%M")
            if slot_key in seen:
                continue
            seen.add(slot_key)
            normalized_slots.append(slot_key)

        if not normalized_slots:
            raise forms.ValidationError("Cần nhập ít nhất 1 khung giờ hợp lệ.")
        return ", ".join(normalized_slots)

    def save(self, commit=True):
        instance = super().save(commit=False)
        slots = instance.get_reminder_time_slots()
        if slots:
            instance.reminder_send_time = slots[0]
        if commit:
            instance.save()
        return instance


class _MasterBaseForm(forms.ModelForm):
    """Add consistent styling for small master data forms."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        base_classes = "block w-full rounded-lg border border-gray-300 px-3 py-2 focus:outline-none focus:ring-2 focus:ring-green-200 focus:border-f88green"
        for field in self.fields.values():
            existing = field.widget.attrs.get("class", "")
            field.widget.attrs["class"] = f"{existing} {base_classes}".strip()


class AdmDocumentTypeForm(_MasterBaseForm):
    class Meta:
        model = AdmDocumentType
        fields = ["code", "name", "is_active"]
        labels = {"code": "Mã", "name": "Tên loại", "is_active": "Đang dùng"}


class AdmContentTypeForm(_MasterBaseForm):
    class Meta:
        model = AdmContentType
        fields = ["code", "name", "is_active"]
        labels = {"code": "Mã", "name": "Tên loại", "is_active": "Đang dùng"}


class AdmSignerRoleForm(_MasterBaseForm):
    class Meta:
        model = AdmSignerRole
        fields = ["code", "title", "is_active"]
        labels = {
            "code": "Mã",
            "title": "Người ký",
            "is_active": "Đang dùng",
        }


class AdmDocumentStatusForm(_MasterBaseForm):
    class Meta:
        model = AdmDocumentStatus
        fields = ["code", "name", "is_active"]
        labels = {"code": "Mã", "name": "Tên trạng thái", "is_active": "Đang dùng"}


class AdmCompanyForm(_MasterBaseForm):
    class Meta:
        model = AdmCompany
        fields = [
            "code",
            "name",
            "badge_text_color",
            "badge_bg_color",
            "badge_logo_url",
            "is_active",
        ]
        labels = {
            "code": "Mã công ty",
            "name": "Tên công ty",
            "badge_text_color": "Màu chữ badge",
            "badge_bg_color": "Màu nền badge",
            "badge_logo_url": "Logo (URL)",
            "is_active": "Đang dùng",
        }
        widgets = {
            "badge_text_color": forms.TextInput(attrs={"type": "color"}),
            "badge_bg_color": forms.TextInput(attrs={"type": "color"}),
            "badge_logo_url": forms.URLInput(attrs={"placeholder": "https://..."}),
        }


class AdmDepartmentForm(_MasterBaseForm):
    class Meta:
        model = AdmDepartment
        fields = ["code", "name", "company", "is_active"]
        labels = {
            "code": "Mã phòng ban",
            "name": "Tên phòng ban",
            "company": "Công ty",
            "is_active": "Đang dùng",
        }


class AdmPaperTypeForm(_MasterBaseForm):
    class Meta:
        model = AdmPaperType
        fields = ["code", "name", "is_active"]
        labels = {"code": "Mã loại", "name": "Tên loại", "is_active": "Đang dùng"}


class AdmCourierCompanyForm(_MasterBaseForm):
    class Meta:
        model = AdmCourierCompany
        fields = ["name", "contact", "is_active"]
        labels = {
            "name": "Tên đơn vị",
            "contact": "Thông tin liên hệ",
            "is_active": "Đang dùng",
        }
