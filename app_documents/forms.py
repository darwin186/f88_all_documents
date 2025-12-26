from django import forms
from django.contrib.auth.forms import PasswordResetForm
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from .models import Package, GapoScheduledMessage
import re


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
    receiver_id = forms.CharField(
        label="GAPO User ID",
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "Nhập GAPO user id"}),
    )
    message = forms.CharField(
        label="Nội dung",
        widget=forms.Textarea(attrs={"class": "form-control", "rows": 4, "placeholder": "Soạn tin nhắn"}),
    )
    schedule_at = forms.DateTimeField(
        label="Thời gian gửi",
        widget=forms.TextInput(attrs={"type": "datetime-local", "class": "form-control"}),
        input_formats=["%Y-%m-%dT%H:%M"],
    )

    class Meta:
        model = GapoScheduledMessage
        fields = ["receiver_id", "message", "schedule_at"]

    def clean_schedule_at(self):
        schedule_at = self.cleaned_data["schedule_at"]
        if timezone.is_naive(schedule_at):
            schedule_at = timezone.make_aware(schedule_at, timezone.get_current_timezone())
        return schedule_at
