from django import forms
from django.utils import timezone

from app_documents.models import Region, Shop

from .models import (
    AdmAdministrativeDocument,
    AdmPaperDocument,
    AdmPaperType,
    AdmCourierCompany,
)


class AdmAdministrativeDocumentForm(forms.ModelForm):
    attachment_link = forms.CharField(required=False, label="Link đính kèm")

    class Meta:
        model = AdmAdministrativeDocument
        fields = [
            "doc_type",
            "content_type",
            "reference_number",
            "title",
            "signer_role",
            "issuing_company",
            "issuing_department",
            "expiry_date",
            "attachment",
            "ticket_code",
            "note",
        ]
        widgets = {
            "expiry_date": forms.DateInput(attrs={"type": "date"}),
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
            "expiry_date": "Ngày hết hiệu lực",
            "attachment": "File đính kèm",
            "status": "Trạng thái văn bản",
            "ticket_code": "Mã ticket yêu cầu",
            "note": "Ghi chú",
        }

    def clean(self):
        cleaned = super().clean()
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

    class Meta:
        model = AdmAdministrativeDocument
        fields = [
            "doc_type",
            "content_type",
            "reference_number",
            "title",
            "signer_role",
            "issuing_company",
            "issuing_department",
            "expiry_date",
            "attachment",
            "status",
            "ticket_code",
            "note",
        ]
        widgets = {
            "expiry_date": forms.DateInput(attrs={"type": "date"}),
            "note": forms.Textarea(attrs={"rows": 3}),
        }

    def clean(self):
        cleaned = super().clean()
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
        label="Phòng/PGD yêu cầu",
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
            for region in Region.objects.all().order_by("region_name")
        ]
        self.fields["region"].choices = region_choices
        base_classes = "block w-full rounded-lg border border-gray-300 px-3 py-2 focus:outline-none focus:ring-2 focus:ring-green-200 focus:border-f88green"
        for name, field in self.fields.items():
            existing = field.widget.attrs.get("class", "")
            field.widget.attrs["class"] = f"{existing} {base_classes}".strip()

    class Meta:
        model = AdmPaperDocument
        fields = [
            "paper_type",
            "region",
            "responsible_person",
            "requested_department",
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
            "responsible_person": "Người phụ trách",
            "ticket_code": "Mã ticket yêu cầu",
            "summary": "Tên, trích yếu nội dung",
            "courier_tracking_code": "Mã vận đơn CPN",
            "status": "Tình trạng",
            "note": "Ghi chú",
        }
