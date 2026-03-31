import json
import re

from django import forms
from django.contrib.auth.forms import PasswordResetForm
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from .models import Package, GapoScheduledMessage


def validate_package_code(value):
    """
    Định dạng: {FOLDER_TYPE}-{yyMMdd}-{region_code}{bb}
    - FOLDER_TYPE: CIMB | NH | VH
    - yyMMdd: 6 chữ số (ngày tạo, dạng năm-tháng-ngày)
    - region_code: 1 ký tự (chữ hoặc số) theo mã vùng
    - bb: số thứ tự 2 chữ số (01-99)
    """
    pattern = r"^(CIMB|NH|VH)-(\d{6})-([A-Za-z0-9]{1})(\d{2})$"
    match = re.match(pattern, value)
    if not match:
        raise ValidationError(
            "Tên thùng phải tuân thủ định dạng '{FOLDER_TYPE}-{yyMMdd}-{region_code}{bb}' "
            "ví dụ: VH-241001-301. FOLDER_TYPE: CIMB/NH/VH; region_code: 1 ký tự (chữ/số); bb: 01-99."
        )
    if Package.objects.filter(package_code=value).exists():
        raise ValidationError("Thùng đã tồn tại trong hệ thống. Vui lòng nhập lại")


class CustomPasswordResetForm(PasswordResetForm):
    def clean_email(self):
        email = self.cleaned_data["email"]
        if not User.objects.filter(email=email).exists():
            raise forms.ValidationError("Không tìm thấy tài khoản với Email này.")
        return email


class PackageForm(forms.ModelForm):
    package_code = forms.CharField(validators=[validate_package_code])

    class Meta:
        model = Package
        fields = ["package_code"]


class GapoPasswordResetForm(forms.Form):
    username = forms.CharField(max_length=150, label="Tài khoản (username)")
    email = forms.EmailField(label="Email đã đăng ký")

    def clean(self):
        cleaned = super().clean()
        username = cleaned.get("username")
        email = cleaned.get("email")
        if not username or not email:
            return cleaned
        try:
            user = User.objects.get(username=username, email=email)
        except User.DoesNotExist:
            raise forms.ValidationError("Không tìm thấy tài khoản với username và email này.")
        cleaned["user_instance"] = user
        return cleaned

    def get_user(self):
        return self.cleaned_data.get("user_instance")


class GapoScheduleForm(forms.ModelForm):
    target_type = forms.ChoiceField(
        label="Kiểu đích nhận",
        choices=GapoScheduledMessage.TargetType.choices,
        widget=forms.Select(attrs={"class": "form-control"}),
    )
    target_value = forms.CharField(
        label="ID đích nhận",
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "placeholder": "Nhập receiver_id, thread_id hoặc collab_id",
            }
        ),
    )
    body_type = forms.ChoiceField(
        label="Loại tin nhắn",
        choices=GapoScheduledMessage.BodyType.choices,
        widget=forms.Select(attrs={"class": "form-control"}),
    )
    message = forms.CharField(
        label="Text hiển thị",
        widget=forms.Textarea(attrs={"class": "form-control", "rows": 4, "placeholder": "Soạn tin nhắn"}),
    )
    body_metadata = forms.CharField(
        label="Metadata JSON",
        required=False,
        widget=forms.Textarea(
            attrs={
                "class": "form-control font-monospace",
                "rows": 8,
                "placeholder": '{"metadata": {"layout": {...}}}',
            }
        ),
    )
    schedule_at = forms.DateTimeField(
        label="Thời gian gửi",
        widget=forms.TextInput(attrs={"type": "datetime-local", "class": "form-control"}),
        input_formats=["%Y-%m-%dT%H:%M"],
    )

    class Meta:
        model = GapoScheduledMessage
        fields = ["message", "schedule_at", "body_type", "body_metadata"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            self.initial["target_type"] = self.instance.target_type
            self.initial["target_value"] = self.instance.target_value
            self.initial["body_type"] = self.instance.body_type
            if self.instance.body_metadata:
                self.initial["body_metadata"] = json.dumps(
                    self.instance.body_metadata,
                    ensure_ascii=False,
                    indent=2,
                )
        else:
            self.initial.setdefault("target_type", GapoScheduledMessage.TargetType.RECEIVER)
            self.initial.setdefault("body_type", GapoScheduledMessage.BodyType.TEXT)

    def clean_body_metadata(self):
        raw = (self.cleaned_data.get("body_metadata") or "").strip()
        if not raw:
            return {}
        try:
            value = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise forms.ValidationError(f"Metadata JSON không hợp lệ: {exc.msg}.") from exc
        if not isinstance(value, dict):
            raise forms.ValidationError("Metadata JSON phải là object.")
        return value

    def clean_schedule_at(self):
        schedule_at = self.cleaned_data["schedule_at"]
        if timezone.is_naive(schedule_at):
            schedule_at = timezone.make_aware(schedule_at, timezone.get_current_timezone())
        return schedule_at

    def clean(self):
        cleaned = super().clean()
        target_type = cleaned.get("target_type")
        target_value = (cleaned.get("target_value") or "").strip()
        body_type = cleaned.get("body_type")
        body_metadata = cleaned.get("body_metadata") or {}

        if not target_value:
            self.add_error("target_value", "Cần nhập ID đích nhận.")
        elif target_type in {
            GapoScheduledMessage.TargetType.RECEIVER,
            GapoScheduledMessage.TargetType.THREAD,
        } and not target_value.isdigit():
            self.add_error("target_value", "Giá trị phải là số cho receiver_id hoặc thread_id.")

        if body_type == GapoScheduledMessage.BodyType.DYNAMIC:
            layout = (body_metadata.get("metadata") or {}).get("layout")
            if not isinstance(layout, dict):
                self.add_error(
                    "body_metadata",
                    "Dynamic message cần `metadata.layout` theo đúng JSON từ Gapo.",
                )
        elif body_type == GapoScheduledMessage.BodyType.QUICK_REPLIES:
            options = (body_metadata.get("metadata") or {}).get("options")
            if not isinstance(options, list) or not options:
                self.add_error(
                    "body_metadata",
                    "Quick replies cần `metadata.options` là mảng không rỗng.",
                )
        elif body_type == GapoScheduledMessage.BodyType.CAROUSEL:
            cards = (body_metadata.get("metadata") or {}).get("carousel_cards")
            if not isinstance(cards, list) or not cards:
                self.add_error(
                    "body_metadata",
                    "Carousel cần `metadata.carousel_cards` là mảng không rỗng.",
                )

        return cleaned

    def save(self, commit=True):
        instance = super().save(commit=False)
        target_type = self.cleaned_data["target_type"]
        target_value = (self.cleaned_data["target_value"] or "").strip()
        instance.receiver_id = ""
        instance.thread_id = None
        instance.collab_id = ""
        if target_type == GapoScheduledMessage.TargetType.RECEIVER:
            instance.receiver_id = target_value
        elif target_type == GapoScheduledMessage.TargetType.THREAD:
            instance.thread_id = int(target_value)
        else:
            instance.collab_id = target_value
        instance.body_metadata = self.cleaned_data["body_metadata"]
        if commit:
            instance.save()
        return instance
