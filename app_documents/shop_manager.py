"""Validation for the current branch manager contact on a Shop."""

import re

from django.core.exceptions import ValidationError
from django.core.validators import validate_email


def validate_shop_manager_contact(name, employee_code, email):
    values = (name, employee_code, email)
    if any(not isinstance(value, str) for value in values):
        raise ValueError("Thông tin trưởng PGD phải là chuỗi.")
    name, employee_code, email = (value.strip() for value in values)
    if len(name) > 255 or len(employee_code) > 100 or len(email) > 254:
        raise ValueError("Thông tin trưởng PGD vượt quá độ dài cho phép.")
    if employee_code and not re.fullmatch(r"F[0-9A-Za-z-]+", employee_code, re.IGNORECASE):
        raise ValueError("Mã nhân viên trưởng PGD phải bắt đầu bằng F và không có khoảng trắng.")
    if email:
        try:
            validate_email(email)
        except ValidationError as exc:
            raise ValueError("Email trưởng PGD không đúng định dạng.") from exc
        if not name or not employee_code:
            raise ValueError("Cần nhập tên và mã nhân viên trước khi đặt email trưởng PGD.")
    return name, employee_code.upper(), email
