from io import BytesIO, StringIO
from datetime import datetime, timedelta
import csv
from functools import lru_cache
import math
import re
import unicodedata

import pandas as pd
import requests
from django.db import transaction
from django.utils import dateparse

from .models import (
    CollateralRegistration,
    CollateralRegistrationExternalIdentity,
    CollateralRegistrationImportBatch,
    CollateralRegistrationLog,
    CollateralRegistrationStatus,
)


COLUMN_ALIASES = {
    "contract_code": ["Mã hợp đồng", "Ma hop dong", "contract_code", "contractCode"],
    "license_plate": ["Biển số xe", "Bien so xe", "license_plate", "licensePlate"],
    "chassis_number": ["Số khung", "So khung", "chassis_number", "chassisNumber"],
    "engine_number": ["Số máy", "So may", "engine_number", "engineNumber"],
    "gddb_status": ["Trạng thái GDĐB", "Trang thai GDDB", "Trạng thái GDDB", "gddb_status", "gddbStatus"],
    "contract_status": ["Trạng thái hợp đồng", "Trang thai hop dong", "contract_status", "contractStatus"],
    "source_created_date": ["Ngày tạo", "Ngay tao", "source_created_date", "createdDate"],
    "disbursement_date": ["Ngày giải ngân", "Ngay giai ngan", "disbursement_date", "disbursementDate"],
    "shop_name": ["Cửa hàng", "Cua hang", "shop_name", "shopName"],
    "disbursement_source": ["Nguồn giải ngân", "Nguon giai ngan", "disbursement_source", "disbursementSource"],
    "post_update_status": ["Trạng thái sau cập nhật", "Trang thai sau cap nhat", "post_update_status"],
    "postmini_updated": ["Cập nhật PosMini", "Cap nhat PosMini", "postmini_updated"],
    "source_user": ["User đăng ký", "USER đăng ký", "User", "source_user", "sourceUser"],
    "reason": ["Lý do", "Ly do", "reason"],
    "note": ["Ghi chú", "Ghi chu", "note"],
    "previous_application_no": ["Số đơn ĐK GDĐB trước đó", "Số đơn ĐK GDDB trước đó", "So don DK GDDB truoc do", "previous_application_no"],
    "previous_registration_date": ["Ngày ĐK GDĐB trước đó", "Ngày ĐK GDDB trước đó", "Ngay DK GDDB truoc do", "previous_registration_date"],
    "registered_by_name": ["User thực hiện đăng ký", "USER thực hiện đăng ký", "USER thuc hien dang ky", "registered_by_name"],
    "it_ticket_code": ["Mã Ticket gửi IT xử lý", "Ma Ticket gui IT xu ly", "it_ticket_code"],
    "pgd_note": ["Note cho PGD", "pgd_note"],
    "source_system": ["source_system", "sourceSystem"],
    "external_ref": ["external_ref", "externalRef", "STT", "ID", "Mã dòng", "Ma dong"],
}

WRITABLE_INTAKE_FIELDS = [
    "contract_code",
    "license_plate",
    "chassis_number",
    "engine_number",
    "gddb_status",
    "contract_status",
    "source_created_date",
    "disbursement_date",
    "shop_name",
    "disbursement_source",
    "post_update_status",
    "postmini_updated",
    "source_user",
    "reason",
    "note",
    "previous_application_no",
    "previous_registration_date",
    "registered_by_name",
    "it_ticket_code",
    "pgd_note",
    "source_system",
    "external_ref",
]

PASTED_CORE_FIELDS = [
    "contract_code",
    "license_plate",
    "chassis_number",
    "engine_number",
    "gddb_status",
    "contract_status",
    "source_created_date",
    "disbursement_date",
    "shop_name",
    "disbursement_source",
]

PASTED_EXPORT_FIELDS = PASTED_CORE_FIELDS + [
    "post_update_status",
    "postmini_updated",
    "source_user",
    "registered_by_name",
]

PASTED_POSITIONAL_SCHEMAS = {
    10: PASTED_CORE_FIELDS,
    11: ["external_ref", *PASTED_CORE_FIELDS],
    14: PASTED_EXPORT_FIELDS,
    15: ["external_ref", *PASTED_EXPORT_FIELDS],
}


def _normalize_column_name(value):
    text = unicodedata.normalize("NFD", clean_value(value).casefold())
    text = "".join(character for character in text if unicodedata.category(character) != "Mn")
    return re.sub(r"[^a-z0-9]+", "", text)


@lru_cache(maxsize=1)
def _manual_header_map():
    result = {}
    for field, aliases in COLUMN_ALIASES.items():
        for alias in [field, *aliases]:
            result[_normalize_column_name(alias)] = field
    return result


def resolve_intake_field_name(value):
    """Resolve a pasted column to the canonical intake field used by the importer."""
    return _manual_header_map().get(_normalize_column_name(value))


def _convert_mdy_dates(records):
    date_fields = ("source_created_date", "disbursement_date", "previous_registration_date")
    date_values = [clean_value(record.get(field)) for record in records for field in date_fields]
    slash_parts = [value.split("/") for value in date_values if re.fullmatch(r"\d{1,2}/\d{1,2}/\d{4}", value)]
    use_mdy = any(int(parts[1]) > 12 for parts in slash_parts) and not any(int(parts[0]) > 12 for parts in slash_parts)
    if not use_mdy:
        return
    for record in records:
        for field in date_fields:
            value = clean_value(record.get(field))
            if re.fullmatch(r"\d{1,2}/\d{1,2}/\d{4}", value):
                record[field] = datetime.strptime(value, "%m/%d/%Y").date().isoformat()


def parse_pasted_tabular_records(raw_payload, *, include_mapping=False):
    """Parse data copied from Excel/Sheets or delimited text into intake records."""
    lines = [line for line in raw_payload.replace("\r\n", "\n").replace("\r", "\n").split("\n") if line.strip()]
    if not lines:
        raise ValueError("Không có dữ liệu để import.")

    if "\t" in lines[0]:
        delimiter = "\t"
    else:
        try:
            delimiter = csv.Sniffer().sniff("\n".join(lines[:10]), delimiters=",;|").delimiter
        except csv.Error as exc:
            raise ValueError("Không nhận diện được cột. Hãy copy trực tiếp từ Excel/Google Sheets hoặc dùng CSV.") from exc

    rows = []
    for row in csv.reader(StringIO("\n".join(lines)), delimiter=delimiter):
        cleaned_row = [clean_value(value) for value in row]
        while cleaned_row and not cleaned_row[-1]:
            cleaned_row.pop()
        if any(cleaned_row):
            rows.append(cleaned_row)
    if not rows:
        raise ValueError("Không có dòng dữ liệu hợp lệ.")

    aliases = _manual_header_map()
    first_row_fields = [aliases.get(_normalize_column_name(value)) for value in rows[0]]
    recognized_header_count = sum(field is not None for field in first_row_fields)
    if recognized_header_count >= 2 and "contract_code" not in first_row_fields:
        raise ValueError("Dòng tiêu đề chưa có cột Mã hợp đồng.")
    has_header = "contract_code" in first_row_fields and recognized_header_count >= 2
    records = []
    column_mapping = []
    if has_header:
        mapped_indexes = {}
        for index, field in enumerate(first_row_fields):
            if not field:
                continue
            if field in mapped_indexes:
                raise ValueError(f"Tiêu đề bị lặp trường '{field}'.")
            mapped_indexes[field] = index
            column_mapping.append({"source": rows[0][index], "field": field})
        for row_number, row in enumerate(rows[1:], start=2):
            if len(row) > len(rows[0]):
                raise ValueError(f"Dòng {row_number} có nhiều cột hơn dòng tiêu đề.")
            records.append({field: row[index] if index < len(row) else "" for field, index in mapped_indexes.items()})
        mode = "Có tiêu đề"
    else:
        column_count = len(rows[0])
        fields = PASTED_POSITIONAL_SCHEMAS.get(column_count)
        if not fields:
            raise ValueError(
                f"Dữ liệu không có tiêu đề đang có {column_count} cột; hệ thống hỗ trợ 10, 11, 14 hoặc 15 cột."
            )
        for row_number, row in enumerate(rows, start=1):
            if len(row) != column_count:
                raise ValueError(f"Dòng {row_number} có {len(row)} cột, cần đủ {column_count} cột.")
            records.append(dict(zip(fields, row)))
        column_mapping = [
            {"source": f"Cột {index}", "field": field}
            for index, field in enumerate(fields, start=1)
        ]
        mode = f"Không tiêu đề · {column_count} cột"

    if not records:
        raise ValueError("Có tiêu đề nhưng chưa có dòng dữ liệu.")
    _convert_mdy_dates(records)
    if include_mapping:
        return records, mode, column_mapping
    return records, mode


def clean_value(value):
    if value is None:
        return ""
    if isinstance(value, float) and math.isnan(value):
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    text = str(value).strip()
    return "" if text.lower() == "nan" else text


def parse_date_value(value):
    if value is None or value == "":
        return None
    if hasattr(value, "date"):
        return value.date()
    if isinstance(value, (int, float)) and value > 0:
        return (datetime(1899, 12, 30) + timedelta(days=int(value))).date()
    text = clean_value(value)
    if not text:
        return None
    if text.replace(".", "", 1).isdigit():
        return (datetime(1899, 12, 30) + timedelta(days=int(float(text)))).date()
    parsed = dateparse.parse_date(text)
    if parsed:
        return parsed
    parsed_dt = dateparse.parse_datetime(text)
    if parsed_dt:
        return parsed_dt.date()
    for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%Y/%m/%d"):
        parsed_dt = datetime.strptime(text, fmt) if _matches_date_format(text, fmt) else None
        if parsed_dt:
            return parsed_dt.date()
    return None


def _matches_date_format(value, fmt):
    try:
        datetime.strptime(value, fmt)
        return True
    except ValueError:
        return False


def normalize_status(value):
    text = clean_value(value).lower()
    if text in ("registered", "da dang ki", "da dang ky", "đã đăng kí", "đã đăng ký"):
        return CollateralRegistrationStatus.REGISTERED
    if text in ("not_registered", "khong dang ki", "khong dang ky", "không đăng kí", "không đăng ký"):
        return CollateralRegistrationStatus.NOT_REGISTERED
    return CollateralRegistrationStatus.PENDING


def normalize_record(record):
    source = {}
    for key, value in record.items():
        field = resolve_intake_field_name(key)
        if field and field not in source:
            source[field] = value
    normalized = {}
    for field in COLUMN_ALIASES:
        value = source.get(field, "")
        if field in ("source_created_date", "disbursement_date", "previous_registration_date"):
            normalized[field] = parse_date_value(value)
        elif field == "gddb_status":
            normalized[field] = normalize_status(value)
        else:
            normalized[field] = clean_value(value)
    if normalized.get("post_update_status"):
        normalized["gddb_status"] = normalize_status(normalized["post_update_status"])
    normalized["raw_payload"] = record
    return normalized


def load_records_from_excel_url(excel_url):
    response = requests.get(excel_url, timeout=60)
    response.raise_for_status()
    frame = pd.read_excel(BytesIO(response.content))
    return frame.fillna("").to_dict(orient="records")


def find_registered_duplicate(data):
    qs = CollateralRegistration.objects.filter(gddb_status=CollateralRegistrationStatus.REGISTERED)
    contract_code = data.get("contract_code")
    license_plate = data.get("license_plate")
    chassis_number = data.get("chassis_number")
    engine_number = data.get("engine_number")
    if contract_code:
        qs = qs.filter(contract_code__iexact=contract_code)
    if license_plate:
        duplicate = qs.filter(license_plate__iexact=license_plate).first()
        if duplicate:
            return duplicate
    if chassis_number:
        duplicate = qs.filter(chassis_number__iexact=chassis_number).first()
        if duplicate:
            return duplicate
    if engine_number:
        duplicate = qs.filter(engine_number__iexact=engine_number).first()
        if duplicate:
            return duplicate
    return None


@transaction.atomic
def import_collateral_registrations(records, *, user=None, source_type="api", source_url=""):
    batch = CollateralRegistrationImportBatch.objects.create(
        source_type=source_type,
        source_url=source_url,
        total_rows=len(records),
        created_by=user if getattr(user, "is_authenticated", False) else None,
    )
    counters = {
        "created_rows": 0,
        "updated_rows": 0,
        "skipped_rows": 0,
        "duplicate_rows": 0,
        "error_rows": 0,
    }
    errors = []

    for index, raw_record in enumerate(records, start=1):
        data = normalize_record(raw_record)
        if not data.get("contract_code"):
            counters["error_rows"] += 1
            errors.append({"row": index, "error": "Thiếu mã hợp đồng"})
            continue

        dedupe_key = CollateralRegistration.build_dedupe_key(
            data.get("contract_code")
        )
        existing = CollateralRegistration.objects.filter(dedupe_key=dedupe_key).first()
        if existing:
            if existing.gddb_status == CollateralRegistrationStatus.REGISTERED:
                counters["skipped_rows"] += 1
                continue
            for field in WRITABLE_INTAKE_FIELDS:
                if field == "gddb_status":
                    continue
                if field == "postmini_updated" and not data.get(field):
                    continue
                setattr(existing, field, data.get(field))
            existing.raw_payload = raw_record
            existing.import_batch = batch
            if data.get("registered_by_name"):
                existing.registered_identity = CollateralRegistrationExternalIdentity.objects.filter(
                    external_code__iexact=data["registered_by_name"]
                ).first()
            existing.updated_by = user if getattr(user, "is_authenticated", False) else None
            existing.save()
            counters["updated_rows"] += 1
            continue

        duplicate = find_registered_duplicate(data)
        if duplicate:
            counters["duplicate_rows"] += 1
            continue

        intake_fields = {field: data.get(field) for field in WRITABLE_INTAKE_FIELDS}
        intake_fields["postmini_updated"] = intake_fields.get("postmini_updated") or "Chưa cập nhật"
        obj = CollateralRegistration(
            import_batch=batch,
            created_by=user if getattr(user, "is_authenticated", False) else None,
            updated_by=user if getattr(user, "is_authenticated", False) else None,
            **intake_fields,
            raw_payload=raw_record,
        )
        if data.get("registered_by_name"):
            obj.registered_identity = CollateralRegistrationExternalIdentity.objects.filter(
                external_code__iexact=data["registered_by_name"]
            ).first()
        obj.save()
        CollateralRegistrationLog.objects.create(
            registration=obj,
            action="intake",
            to_status=obj.gddb_status,
            note="Nhận dữ liệu GDDB",
            created_by=user if getattr(user, "is_authenticated", False) else None,
        )
        counters["created_rows"] += 1

    for field, value in counters.items():
        setattr(batch, field, value)
    batch.summary = {"errors": errors[:50]}
    batch.save(update_fields=[*counters.keys(), "summary"])
    return batch
