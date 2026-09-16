import hashlib
import json
from collections import Counter
from datetime import datetime, time

from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime

from app_documents.models import Shop
from app_document_campaigns.models import (
    Campaign,
    CampaignError,
    CampaignImportSource,
    CampaignStatusHistory,
    CampaignStagingRow,
    CampaignVersion,
)


class CampaignImportError(Exception):
    pass


NORMALIZED_FIELDS = (
    "source_key",
    "error_type",
    "source_object_id",
    "code",
    "shop_code",
    "contract_code",
    "customer_code",
    "customer_name",
    "employee_code",
    "employee_name",
    "business_type_name",
    "document_type_name",
    "checking_issue",
    "source_created_at",
)


def _text(value):
    if value is None:
        return ""
    return str(value).strip()


def _integer(value):
    text = _text(value)
    if not text:
        return None
    try:
        number = int(text)
    except (TypeError, ValueError):
        return None
    return number if str(number) == text else None


def _hash_payload(payload):
    serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _json_safe(payload):
    return json.loads(json.dumps(payload, ensure_ascii=False, default=str))


def _normalize_row(raw, shops_by_code):
    normalized = {field: _text(raw.get(field)) for field in NORMALIZED_FIELDS}
    normalized["source_object_id"] = _integer(raw.get("source_object_id"))
    shop_code = _integer(raw.get("shop_code"))
    normalized["shop_code"] = shop_code
    errors = []

    if not normalized["source_key"]:
        errors.append({"field": "source_key", "code": "required"})
    elif len(normalized["source_key"]) > 255:
        errors.append({"field": "source_key", "code": "max_length"})
    if normalized["error_type"] not in CampaignError.ErrorType.values:
        errors.append({"field": "error_type", "code": "invalid_choice"})
    if normalized["source_object_id"] is None:
        errors.append({"field": "source_object_id", "code": "invalid_integer"})
    if shop_code is None:
        errors.append({"field": "shop_code", "code": "invalid_integer"})
    elif shop_code not in shops_by_code:
        errors.append({"field": "shop_code", "code": "not_found"})
    else:
        shop = shops_by_code[shop_code]
        source_manager = raw.get("manager_snapshot")
        if not isinstance(source_manager, dict):
            source_manager = {
                key: _text(raw.get(key))
                for key in (
                    "shop_name",
                    "shop_email",
                    "qlkv_name",
                    "qlkv_email",
                    "qlv_name",
                    "qlv_email",
                    "region_name",
                )
                if _text(raw.get(key))
            }
        normalized.update(
            {
                "shop_id": shop.pk,
                "area_manager_id": shop.manager_id.areaManager_id,
                "region_id": shop.region_id_id,
                "manager_snapshot": source_manager,
            }
        )
    if not normalized["checking_issue"]:
        errors.append({"field": "checking_issue", "code": "required"})
    additional_errors = raw.get("_validation_errors", [])
    if isinstance(additional_errors, list):
        errors.extend(error for error in additional_errors if isinstance(error, dict))
    return normalized, errors


def _existing_payload(error):
    return {
        "source_key": error.source_key,
        "error_type": error.error_type,
        "source_object_id": error.source_object_id,
        "code": error.code,
        "shop_code": error.shop.shop_code,
        "contract_code": error.contract_code,
        "customer_code": error.customer_code,
        "customer_name": error.customer_name,
        "employee_code": error.employee_code,
        "employee_name": error.employee_name,
        "business_type_name": error.business_type_name,
        "document_type_name": error.document_type_name,
        "checking_issue": error.checking_issue,
        "source_created_at": error.source_created_at.isoformat() if error.source_created_at else "",
        "shop_id": error.shop_id,
        "area_manager_id": error.area_manager_id,
        "region_id": error.region_id,
        "manager_snapshot": error.manager_snapshot,
    }


def _source_datetime(value):
    if not value:
        return None
    if isinstance(value, datetime):
        result = value
    else:
        result = parse_datetime(str(value))
        if result is None:
            parsed_date = parse_date(str(value))
            result = datetime.combine(parsed_date, time.min) if parsed_date else None
    if result is not None and timezone.is_naive(result):
        result = timezone.make_aware(result)
    return result


@transaction.atomic
def stage_import_rows(*, source, rows):
    """Replace one source's staging rows and calculate a non-destructive preview."""
    source = (
        CampaignImportSource.objects.select_for_update()
        .select_related("version__campaign")
        .get(pk=source.pk)
    )
    if source.version.campaign.status == Campaign.Status.ACTIVE:
        raise CampaignImportError("Không được import đè campaign đang active.")
    if source.version.status == CampaignVersion.Status.PUBLISHED:
        raise CampaignImportError("Không được thay đổi version đã phát hành.")
    if not isinstance(rows, list):
        raise CampaignImportError("Dữ liệu import phải là một danh sách dòng.")

    shop_codes = {_integer(row.get("shop_code")) for row in rows if isinstance(row, dict)}
    shops_by_code = {
        shop.shop_code: shop
        for shop in Shop.objects.select_related("manager_id__areaManager", "region_id").filter(
            shop_code__in=[code for code in shop_codes if code is not None]
        )
    }
    prepared = []
    key_counts = Counter(
        _text(row.get("source_key")) for row in rows if isinstance(row, dict) and _text(row.get("source_key"))
    )
    for row_number, raw in enumerate(rows, start=2):
        if not isinstance(raw, dict):
            raw = {"_value": raw}
            normalized = {}
            errors = [{"field": "row", "code": "invalid_object"}]
        else:
            normalized, errors = _normalize_row(raw, shops_by_code)
            if normalized["source_key"] and key_counts[normalized["source_key"]] > 1:
                errors.append({"field": "source_key", "code": "duplicate_in_source"})
        prepared.append(
            CampaignStagingRow(
                source=source,
                row_number=row_number,
                source_key=normalized.get("source_key", ""),
                raw_payload=_json_safe(raw),
                normalized_payload=normalized,
                content_hash=_hash_payload(normalized) if normalized else "",
                validation_errors=errors,
            )
        )

    source.rows.all().delete()
    CampaignStagingRow.objects.bulk_create(prepared, batch_size=1000)

    valid = [row for row in prepared if not row.validation_errors]
    existing_by_key = {
        error.source_key: error
        for error in CampaignError.objects.select_related("shop").filter(
            campaign=source.version.campaign,
            source_key__in=[row.source_key for row in valid],
        )
    }
    summary = {"rows": len(prepared), "invalid": len(prepared) - len(valid), "added": 0, "updated": 0, "unchanged": 0}
    for row in valid:
        existing = existing_by_key.get(row.source_key)
        if existing is None:
            summary["added"] += 1
        elif _hash_payload(_existing_payload(existing)) == row.content_hash:
            summary["unchanged"] += 1
        else:
            summary["updated"] += 1

    source.row_count = len(prepared)
    source.invalid_count = summary["invalid"]
    source.preview_summary = summary
    source.status = (
        CampaignImportSource.Status.VALIDATED
        if not summary["invalid"]
        else CampaignImportSource.Status.STAGED
    )
    source.save(
        update_fields=["row_count", "invalid_count", "preview_summary", "status", "updated_at"]
    )
    return summary


@transaction.atomic
def publish_excel_version(*, version, confirmed_by):
    """Make a validated Excel source authoritative for a campaign version."""
    version = (
        CampaignVersion.objects.select_for_update()
        .select_related("campaign")
        .get(pk=version.pk)
    )
    campaign = Campaign.objects.select_for_update().select_related(
        "campaign_type"
    ).get(pk=version.campaign_id)
    if campaign.status == Campaign.Status.ACTIVE:
        raise CampaignImportError("Không được import đè campaign đang active.")
    if version.status not in (CampaignVersion.Status.DRAFT, CampaignVersion.Status.VALIDATED):
        raise CampaignImportError("Chỉ được xác nhận version nháp hoặc đã kiểm tra.")
    try:
        excel_source = CampaignImportSource.objects.select_for_update().get(
            version=version,
            source_type=CampaignVersion.SourceType.EXCEL,
            name="team-cleaning-excel",
        )
    except CampaignImportSource.DoesNotExist as exc:
        raise CampaignImportError("Version chưa có file Excel làm sạch.") from exc
    if excel_source.invalid_count or excel_source.status != CampaignImportSource.Status.VALIDATED:
        raise CampaignImportError("File Excel còn lỗi validation, chưa thể xác nhận.")

    rows = list(excel_source.rows.filter(validation_errors=[]).order_by("row_number"))
    selected_keys = {row.source_key for row in rows}
    if len(selected_keys) != len(rows):
        raise CampaignImportError("File Excel còn source_key trùng.")

    existing_by_key = {
        error.source_key: error
        for error in CampaignError.objects.select_for_update().filter(campaign=campaign)
    }
    added = 0
    updated = 0
    now = timezone.now()
    for row in rows:
        payload = row.normalized_payload
        defaults = {
            "version": version,
            "error_type": payload["error_type"],
            "source_object_id": payload["source_object_id"],
            "code": payload.get("code", ""),
            "shop_id": payload["shop_id"],
            "area_manager_id": payload.get("area_manager_id"),
            "region_id": payload.get("region_id"),
            "manager_snapshot": payload.get("manager_snapshot", {}),
            "contract_code": payload.get("contract_code", ""),
            "customer_code": payload.get("customer_code", ""),
            "customer_name": payload.get("customer_name", ""),
            "employee_code": payload.get("employee_code", ""),
            "employee_name": payload.get("employee_name", ""),
            "business_type_name": payload.get("business_type_name", ""),
            "document_type_name": payload.get("document_type_name", ""),
            "checking_issue": payload["checking_issue"],
            "checklist_template_id": campaign.campaign_type.shop_checklist_template_id,
            "source_created_at": _source_datetime(payload.get("source_created_at")),
            "status": CampaignError.Status.READY,
        }
        error = existing_by_key.get(row.source_key)
        if error is None:
            CampaignError.objects.create(campaign=campaign, source_key=row.source_key, **defaults)
            added += 1
        else:
            for field, value in defaults.items():
                setattr(error, field, value)
            error.save(update_fields=[*defaults.keys(), "updated_at"])
            updated += 1

    excluded = CampaignError.objects.filter(campaign=campaign).exclude(
        source_key__in=selected_keys
    ).exclude(status=CampaignError.Status.EXCLUDED).update(
        status=CampaignError.Status.EXCLUDED,
        updated_at=now,
    )
    if campaign.current_version_id and campaign.current_version_id != version.pk:
        CampaignVersion.objects.filter(pk=campaign.current_version_id).update(
            status=CampaignVersion.Status.SUPERSEDED
        )
    previous_campaign_status = campaign.status
    version.source_type = CampaignVersion.SourceType.EXCEL
    version.status = CampaignVersion.Status.PUBLISHED
    version.published_at = now
    version.import_summary = {
        **excel_source.preview_summary,
        "applied_added": added,
        "applied_updated": updated,
        "applied_excluded": excluded,
    }
    version.save(
        update_fields=["source_type", "status", "published_at", "import_summary"]
    )
    excel_source.status = CampaignImportSource.Status.CONFIRMED
    excel_source.save(update_fields=["status", "updated_at"])
    campaign.current_version = version
    campaign.status = Campaign.Status.READY
    campaign.save(update_fields=["current_version", "status", "updated_at"])
    CampaignStatusHistory.objects.create(
        campaign=campaign,
        from_status=previous_campaign_status,
        to_status=Campaign.Status.READY,
        reason=f"Xác nhận dữ liệu Excel version {version.version_number}",
        changed_by=confirmed_by,
    )
    return version.import_summary
