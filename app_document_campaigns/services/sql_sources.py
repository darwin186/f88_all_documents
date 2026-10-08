import hashlib
import json
from calendar import monthrange
from datetime import date

from django.db import connections

from app_document_campaigns.models import CampaignError, CampaignImportSource, CampaignVersion
from app_document_campaigns.services.imports import CampaignImportError, stage_import_rows


FOLDER_SOURCE_NAME = "folder-fail-sql"
DOCUMENT_SOURCE_NAME = "document-fail-sql"
CARRYOVER_SOURCE_NAME = "suspended-carryover"
BUSINESS_TYPES = (
    "HĐ quá hạn 180 ngày",
    "Đóng HĐCC nợ xấu chủ động",
    "Đóng HĐCC chủ động",
)


FOLDER_ERROR_SQL = r"""
SELECT
    CONCAT(
        'folder:', folder.folder_id,
        ':contract:', COALESCE(ctr.contract_code, 'unknown')
    ) AS source_key,
    'folder' AS error_type,
    folder.folder_id AS source_object_id,
    folder.folder_code AS code,
    folder.folder_created_date AS source_created_at,
    shop.shop_code,
    shop.shop_name,
    shop.shop_email,
    man.qlkv_name,
    man.qlkv_email,
    man.qlv_name,
    man.qlv_email,
    region.region_name,
    ctr.contract_code,
    cus.customer_code,
    cus.customer_name,
    emp.employee_code,
    emp.employee_name,
    STRING_AGG(DISTINCT bus.business_type_name, E'\n') AS business_type_name,
    STRING_AGG(DISTINCT doctype.document_type_name, E'\n') AS document_type_name,
    'Thiếu tất cả các chứng từ - Gửi chứng từ không đúng thời gian quy định' AS checking_issue
FROM "f_FolderDetail" folder
JOIN "f_DocumentsDetail" doc ON doc.folder_id = folder.folder_id
LEFT JOIN "d_Shops" shop ON shop.shop_id = folder.shop_id
LEFT JOIN "d_Manager" man ON man.manager_id = folder.manager_id
LEFT JOIN "d_Region" region ON region.region_id = shop.region_id
LEFT JOIN "d_DocumentType" doctype ON doctype.document_type_id = doc.document_type_id
LEFT JOIN "d_ContractDetail" ctr ON ctr.contract_id = doc.contract_id
LEFT JOIN "d_Employee" emp ON emp.employee_id = ctr.employee_id
LEFT JOIN "d_LoanCustomer" cus ON cus.customer_id = ctr.customer_id
LEFT JOIN "d_BusinessType" bus ON bus.business_type_id = doc.business_type_id
LEFT JOIN vw_filtered_documents vfd ON doc.documents_id = vfd.documents_id
WHERE folder.is_issue IS TRUE
  AND folder.is_original IS TRUE
  AND folder.lastest_received_date IS NULL
  AND folder.folder_created_date >= %s
  AND folder.folder_created_date < %s
  AND doc.documents_created_date >= %s
  AND doc.documents_created_date < %s
  AND vfd.documents_id IS NULL
  AND bus.business_type_name IN (%s, %s, %s)
GROUP BY
    folder.folder_id,
    folder.folder_code,
    folder.folder_created_date,
    shop.shop_code,
    shop.shop_name,
    shop.shop_email,
    man.qlkv_name,
    man.qlkv_email,
    man.qlv_name,
    man.qlv_email,
    region.region_name,
    ctr.contract_code,
    cus.customer_code,
    cus.customer_name,
    emp.employee_code,
    emp.employee_name
ORDER BY folder.folder_id
"""


DOCUMENT_ERROR_SQL = r"""
SELECT DISTINCT ON (doc.documents_id)
    CONCAT('document:', doc.documents_id) AS source_key,
    'document' AS error_type,
    doc.documents_id AS source_object_id,
    doc.documents_code AS code,
    doc.documents_created_date AS source_created_at,
    shop.shop_code,
    shop.shop_name,
    shop.shop_email,
    man.qlkv_name,
    man.qlkv_email,
    man.qlv_name,
    man.qlv_email,
    reg.region_name,
    ctr.contract_code,
    cus.customer_code,
    cus.customer_name,
    emp.employee_code,
    emp.employee_name,
    dbt.business_type_name,
    ddt.document_type_name,
    fcs.checking_status_name AS checking_issue
FROM "f_DocumentsDetail" doc
LEFT JOIN "d_DocumentType" ddt ON ddt.document_type_id = doc.document_type_id
LEFT JOIN "f_CheckingStatus" fcs ON fcs.status_id = doc.check_status_id
LEFT JOIN "d_Shops" shop ON shop.shop_id = doc.shop_id
LEFT JOIN "d_Region" reg ON reg.region_id = shop.region_id
LEFT JOIN "d_Manager" man ON man.manager_id = doc.manager_id
LEFT JOIN "d_BusinessType" dbt ON dbt.business_type_id = doc.business_type_id
LEFT JOIN vw_descend_document vdd ON vdd.documents_id = doc.documents_id
LEFT JOIN "d_ContractDetail" ctr ON ctr.contract_id = doc.contract_id
LEFT JOIN "d_Employee" emp ON emp.employee_id = ctr.employee_id
LEFT JOIN "d_LoanCustomer" cus ON cus.customer_id = ctr.customer_id
WHERE doc.documents_created_date >= %s
  AND doc.documents_created_date < %s
  AND doc.check_status_id != 1
  AND vdd.documents_id IS NULL
  AND dbt.business_type_name IN (%s, %s, %s)
ORDER BY doc.documents_id
"""


def _month_bounds(report_month):
    if not isinstance(report_month, date) or report_month.day != 1:
        raise CampaignImportError("Tháng chiến dịch phải là ngày đầu tiên của tháng.")
    last_day = monthrange(report_month.year, report_month.month)[1]
    month_end = report_month.replace(day=last_day)
    next_month = date.fromordinal(month_end.toordinal() + 1)
    return report_month, next_month


def _fetch_rows(sql, params, *, using="default"):
    with connections[using].cursor() as cursor:
        cursor.execute(sql, params)
        columns = [column[0] for column in cursor.description]
        return [dict(zip(columns, values)) for values in cursor.fetchall()]


def fetch_folder_error_rows(report_month, *, using="default"):
    month_start, next_month = _month_bounds(report_month)
    return _fetch_rows(
        FOLDER_ERROR_SQL,
        [month_start, next_month, month_start, next_month, *BUSINESS_TYPES],
        using=using,
    )


def fetch_document_error_rows(report_month, *, using="default"):
    month_start, next_month = _month_bounds(report_month)
    return _fetch_rows(DOCUMENT_ERROR_SQL, [month_start, next_month, *BUSINESS_TYPES], using=using)


def _rows_checksum(rows):
    payload = json.dumps(rows, ensure_ascii=False, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def sql_source_options(campaign=None):
    options = [(name, label) for name, label, _ in sql_source_specs()]
    if campaign and campaign.carryover_source_id:
        options.append((CARRYOVER_SOURCE_NAME, f"Lỗi treo từ kỳ {campaign.carryover_source.code}"))
    return options


def suspended_carryover_rows(campaign):
    """Snapshot eligible held errors into the same reviewable Excel pipeline as SQL."""
    if not campaign.carryover_source_id:
        raise CampaignImportError("Chiến dịch chưa chọn kỳ nguồn lỗi treo.")
    source = campaign.carryover_source
    if source.campaign_type_id != campaign.campaign_type_id or source.report_month >= campaign.report_month:
        raise CampaignImportError("Kỳ nguồn lỗi treo phải cũ hơn và cùng loại book lỗi.")
    rows = []
    held = CampaignError.objects.filter(campaign=source, status=CampaignError.Status.SUSPENDED).exclude(
        carried_errors__campaign__report_month__lt=campaign.report_month
    ).select_related("shop", "carried_from")
    for error in held.iterator(chunk_size=500):
        original_key = error.carried_from.source_key if error.carried_from_id else error.source_key
        rows.append({
            "source_key": f"carryover:{error.error_uid.hex}",
            "error_type": error.error_type,
            "source_object_id": error.source_object_id or error.folder_id or error.document_id,
            "code": error.code,
            "source_created_at": error.source_created_at.isoformat() if error.source_created_at else "",
            "shop_code": error.shop.shop_code,
            "contract_code": error.contract_code,
            "customer_code": error.customer_code,
            "customer_name": error.customer_name,
            "employee_code": error.employee_code,
            "employee_name": error.employee_name,
            "business_type_name": error.business_type_name,
            "document_type_name": error.document_type_name,
            "checking_issue": error.checking_issue,
            "manager_snapshot": error.manager_snapshot,
            "_original_source_key": original_key,
        })
    return rows


def sql_source_specs():
    return [(FOLDER_SOURCE_NAME, "Lỗi quyển chứng từ", fetch_folder_error_rows), (DOCUMENT_SOURCE_NAME, "Lỗi chứng từ", fetch_document_error_rows)]


def stage_monthly_sql_sources(*, version, created_by, using="default", progress_callback=None, source_names=None):
    """Run both legacy report sources and stage their normalized results."""
    version = CampaignVersion.objects.select_related("campaign__campaign_type").get(pk=version.pk)
    if version.campaign.campaign_type.code != "hardcopy-document-error":
        raise CampaignImportError(
            "Loại chiến dịch này chưa có bộ truy xuất dữ liệu SQL tương ứng."
        )
    source_specs = tuple((name, fetcher) for name, _, fetcher in sql_source_specs())
    if version.campaign.carryover_source_id and source_names is not None:
        source_specs += ((CARRYOVER_SOURCE_NAME, lambda month, using="default": suspended_carryover_rows(version.campaign)),)
    if source_names is not None:
        if not source_names or set(source_names) - {name for name, _ in source_specs}:
            raise CampaignImportError("Nguồn dữ liệu được chọn không hợp lệ.")
        source_specs = tuple(spec for spec in source_specs if spec[0] in source_names)
    result = {}
    for step, (source_name, fetcher) in enumerate(source_specs, start=1):
        rows = fetcher(version.campaign.report_month, using=using)
        source, _ = CampaignImportSource.objects.get_or_create(
            version=version,
            name=source_name,
            defaults={
                "source_type": CampaignVersion.SourceType.SQL,
                "created_by": created_by,
            },
        )
        if source.source_type != CampaignVersion.SourceType.SQL:
            raise CampaignImportError(f"Source {source_name} không phải nguồn SQL.")
        summary = stage_import_rows(source=source, rows=rows)
        source.source_checksum = _rows_checksum(rows)
        source.save(update_fields=["source_checksum", "updated_at"])
        result[source_name] = summary
        if progress_callback:
            progress_callback(source_name, step, summary)
    return result
