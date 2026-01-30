from django import forms
from django.utils import timezone

from app_documents.models import Region, Shop

from .models import (
    AdmAdministrativeDocument,
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
        base_classes = "block w-full rounded-lg border border-gray-300 px-3 py-2 focus:outline-none focus:ring-2 focus:ring-green-200 focus:border-f88green"
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
        labels = {"code": "Mã", "title": "Chức danh", "is_active": "Đang dùng"}


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
