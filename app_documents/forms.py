# forms.py
from django import forms
from django.contrib.auth.forms import PasswordResetForm
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
from .models import  Package
import re

def validate_package_code(value):
    if not re.match(r'VH-\d{6}-\d{2}', value):
        raise ValidationError("Tên thùng phải tuân thủ đúng định dạng 'VH-yymmdd-xx'. Với yymmdd: là năm tháng ngày hiện tại, xx phải là chữ số thứ tự từ 01 - 99")
    if Package.objects.filter(package_code=value).exists():
        raise ValidationError("Thùng đã tồn tại trong hệ thống. Vui lòng nhập lại")

class CustomPasswordResetForm(PasswordResetForm):
    def clean_email(self):
        email = self.cleaned_data['email']
        if not User.objects.filter(email=email).exists():
            raise forms.ValidationError('Không tìm thấy tài khoản với Email này.') 
        return email

class PackageForm(forms.ModelForm):
    package_code = forms.CharField(validators=[validate_package_code])
    class Meta:
        model = Package
        fields = ['package_code']
