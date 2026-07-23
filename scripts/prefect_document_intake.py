"""Prefect flow: Oracle document source -> validated Intake API batch.

This replaces the direct PostgreSQL writes in ``maintain document data 3.py``.
Customer/employee fields required by the legacy data model are sent through the
authenticated HTTPS API, while local and API rejection reports redact PII.
"""
from collections import defaultdict
from datetime import date
import time

import oracledb
import requests
try:
    from prefect import flow, get_run_logger, task
except ImportError:  # Lets the transformer be smoke-tested outside the Prefect runtime.
    def task(*args, **kwargs):
        return lambda function: function

    def flow(*args, **kwargs):
        return lambda function: function

    def get_run_logger():
        import logging
        return logging.getLogger(__name__)


CHUNK_SIZE = 1000


# Same source query as scripts/maintenance/maintain_document_data.py, with a
# day bind added so a daily deployment does not scan the entire month repeatedly.
ORACLE_DOCUMENT_SQL = """
WITH DOCUMENT AS (
    SELECT to_char(DOC.year_num) AS created_year,
           CASE WHEN LENGTH(DOC.month_num) = 1 THEN LPAD(DOC.month_num, 2, '0') ELSE TO_CHAR(DOC.month_num) END AS created_month,
           SUBSTR(DOC.date_wid,7,2) AS created_day,
           COALESCE(TO_CHAR(DOC.code_no), TO_CHAR(DOC.contract_code), TO_CHAR(DOC.id), '999') || ID AS parent_document_code,
           DOC.trans_shop_code AS shop_code,
           TRIM(DOC.document_type) AS folder_type,
           DOC.doc_grp,
           DOC.transaction_type AS business_type,
           DOC.action_code,
           NVL(SHOP.shop_nm, DOC.shop_name) AS shop_name,
           DOC.code_no AS loan_code,
           DOC.contract_code AS contract_code,
           CASE WHEN DOC.employee_code IN ('SYS000005','STS000002','cvkd_test_1149','sysf88mobile','losapiv2')
                THEN AREA_CURRENT.mnv_tpgd ELSE DOC.employee_code END AS employee_code,
           CASE WHEN DOC.employee_code IN ('SYS000005','STS000002','cvkd_test_1149','sysf88mobile','losapiv2')
                THEN AREA_CURRENT.tpgd ELSE DOC.employee_nm END AS employee_name,
           DOC.customer_code AS customer_code,
           DOC.customer_nm AS customer_name,
           CASE WHEN LOWER(TRIM(AREA.mien)) = 'miền trung' THEN 'Miền Nam' ELSE AREA.mien END AS region,
           AREA.qlv_nm AS qlv,
           AREA.qlkv_nm AS qlkv,
           AREA.qlv_code AS qlv_user_code,
           CASE WHEN AREA.qlkv_code IS NULL THEN AREA.qlv_code ELSE AREA.qlkv_code END AS qlkv_user_code
    FROM F88DWH.W_RPT_TRANSACTION_DOCUMENT DOC
    LEFT JOIN F88DWH.W_SHOP_D SHOP
      ON SHOP.shop_code = DOC.trans_shop_code AND SHOP.shop_type = 'F88' AND SHOP.crn_row_ind = 1
    LEFT JOIN F88DWH.W_AREA_MANAGER_D AREA_CURRENT
      ON TRIM(TO_CHAR(AREA_CURRENT.shop_id)) = DOC.trans_shop_code
    LEFT JOIN F88DWH.W_AREA_MANAGER_MONTHLY_D AREA
      ON TO_CHAR(AREA.shop_id) = DOC.trans_shop_code
     AND DOC.year_num = AREA.year_num AND DOC.month_num = AREA.month_num
    WHERE DOC.year_num = :year_num
      AND DOC.month_num = :month_num
      AND SUBSTR(DOC.date_wid,7,2) = :day_num
      AND DOC.document_type != 'Chứng từ lưu trữ tại PGD'
      AND DOC.doc_grp != 'Không phát sinh bộ chứng từ bản giấy'
      AND DOC.trans_shop_code NOT IN ('1099', '2999', '1149', '1052', '9401')
      AND NVL(DOC.trans_shop_code, '0') != '0'
)
SELECT * FROM DOCUMENT
"""


def _text(value):
    return "" if value is None else str(value).strip()


def _api(method, url, token, path, **kwargs):
    response = requests.request(
        method, f"{url.rstrip('/')}{path}", timeout=60,
        headers={"Authorization": f"Bearer {token}"}, **kwargs,
    )
    response.raise_for_status()
    return response.json()


@task(retries=3, retry_delay_seconds=30)
def load_oracle_rows(business_date: date, oracle_user: str, oracle_password: str, oracle_dsn: str):
    connection = oracledb.connect(user=oracle_user, password=oracle_password, dsn=oracle_dsn)
    try:
        cursor = connection.cursor()
        cursor.execute(ORACLE_DOCUMENT_SQL, {
            "year_num": business_date.year, "month_num": business_date.month,
            "day_num": f"{business_date.day:02d}",
        })
        columns = [column[0].lower() for column in cursor.description]
        return [dict(zip(columns, row)) for row in cursor]
    finally:
        connection.close()


@task(retries=3, retry_delay_seconds=15)
def load_catalog(api_url: str, api_token: str):
    return _api("GET", api_url, api_token, "/api/integrations/v1/catalog/")


def transform_rows(rows, catalog, business_date: date):
    """Return API-ready records plus a PII-free rejection report."""
    folder_by_name = {_text(x["folder_type_name"]): x for x in catalog["folder_types"]}
    document_by_name = {_text(x["document_type_name"]): x for x in catalog["document_types"]}
    shop_codes = {_text(x["shop_code"]) for x in catalog["shops"]}
    business_by_name = defaultdict(list)
    for item in catalog["business_types"]:
        business_by_name[_text(item["business_type_name"])].append(item)

    output, rejected = [], []
    for row in rows:
        source_record_id = _text(row.get("parent_document_code"))
        reason = None
        if not source_record_id:
            reason = "Thiếu parent_document_code"
        shop_code = _text(row.get("shop_code"))
        folder_type = folder_by_name.get(_text(row.get("folder_type")))
        if not reason and shop_code not in shop_codes:
            reason = f"PGD {shop_code} chưa tồn tại hoặc là PGD chỉ dùng cho mượn chứng từ"
        if not reason and not folder_type:
            reason = f"Không map được loại quyển: {_text(row.get('folder_type'))}"

        business_match = None
        action_code = _text(row.get("action_code")).upper()
        if not reason and _text(row.get("business_type")):
            candidates = business_by_name.get(_text(row.get("business_type")), [])
            action_matches = [
                x for x in candidates
                if x["need_action_code"] and _text(x["action_code"]).upper() == action_code
            ]
            plain_matches = [x for x in candidates if not x["need_action_code"]]
            business_match = action_matches[0] if action_matches else (plain_matches[0] if plain_matches else None)
            if business_match:
                action_code = _text(business_match["action_code"]).upper() if business_match["need_action_code"] else ""
        if reason:
            rejected.append({
                "source_record_id": source_record_id, "reason": reason,
                "shop_code": shop_code, "folder_type": _text(row.get("folder_type")),
                "doc_grp": _text(row.get("doc_grp")), "business_type": _text(row.get("business_type")),
                "action_code": _text(row.get("action_code")),
            })
            continue
        # The legacy job explodes a comma-space separated doc_grp into one
        # DocumentsDetail per document type before generating documents_code.
        document_names = [_text(value) for value in _text(row.get("doc_grp")).split(", ") if _text(value)]
        mapped_document_count = 0
        for document_name in document_names:
            document_type = document_by_name.get(document_name)
            if not document_type:
                rejected.append({
                    "source_record_id": source_record_id,
                    "reason": f"Không map được loại chứng từ: {document_name}",
                    "shop_code": shop_code, "folder_type": _text(row.get("folder_type")),
                    "doc_grp": document_name, "business_type": _text(row.get("business_type")),
                    "action_code": _text(row.get("action_code")),
                })
                continue
            business_id_part = str(business_match["business_type_id"]) if business_match else "<NA>"
            final_document_code = (
                f"{business_date:%Y%m%d}{shop_code}{source_record_id}"
                f"{business_id_part}{document_type['document_type_id']}"
            )
            pending = business_match is None
            record = {
                "source_record_id": final_document_code,
                "source_parent_document_code": source_record_id,
                "documents_created_date": business_date.isoformat(),
                "shop_code": int(shop_code),
                "document_type_code": _text(document_type["document_type_code"]),
                "folder_type_code": _text(folder_type["folder_type_code"]),
                "contract_code": _text(row.get("contract_code")) or None,
                "loan_code": _text(row.get("loan_code")) or None,
                "customer_code": _text(row.get("customer_code")) or None,
                "customer_name": _text(row.get("customer_name")) or None,
                "employee_code": _text(row.get("employee_code")) or None,
                "employee_name": _text(row.get("employee_name")) or None,
                "source_shop_name": _text(row.get("shop_name")) or None,
                "source_qlv_name": _text(row.get("qlv")) or None,
                "source_qlkv_name": _text(row.get("qlkv")) or None,
                "manager_code": _text(row.get("qlv_user_code")) + _text(row.get("qlkv_user_code")),
                "region_name": _text(row.get("region")),
                "is_pending_metadata": pending,
                "pending_metadata_note": (
                    f"Loại nghiệp vụ: {_text(row.get('business_type'))}" if pending else None
                ),
            }
            if business_match:
                record["business_type_code"] = _text(business_match["business_type_code"])
                if action_code:
                    record["action_code"] = action_code
            output.append(record)
            mapped_document_count += 1
        # The legacy job maintains employee/customer/contract/loan before it
        # drops unknown document types. Keep that behavior with a dimension-only
        # record when no DocumentsDetail can be produced.
        if mapped_document_count == 0:
            output.append({
                "record_type": "dimension_only",
                "source_record_id": f"DIM-{business_date:%Y%m%d}-{source_record_id}",
                "source_parent_document_code": source_record_id,
                "documents_created_date": business_date.isoformat(),
                "shop_code": int(shop_code),
                "contract_code": _text(row.get("contract_code")) or None,
                "loan_code": _text(row.get("loan_code")) or None,
                "customer_code": _text(row.get("customer_code")) or None,
                "customer_name": _text(row.get("customer_name")) or None,
                "employee_code": _text(row.get("employee_code")) or None,
                "employee_name": _text(row.get("employee_name")) or None,
                "source_shop_name": _text(row.get("shop_name")) or None,
                "source_qlv_name": _text(row.get("qlv")) or None,
                "source_qlkv_name": _text(row.get("qlkv")) or None,
                "manager_code": _text(row.get("qlv_user_code")) + _text(row.get("qlkv_user_code")),
                "region_name": _text(row.get("region")),
            })
    return output, rejected


@task(retries=4, retry_delay_seconds=20)
def send_batch(api_url, api_token, batch_key, business_date, records, finalize=True):
    chunks = [records[index:index + CHUNK_SIZE] for index in range(0, len(records), CHUNK_SIZE)]
    _api("POST", api_url, api_token, "/api/integrations/v1/batches/", json={
        "batch_key": batch_key, "kind": "documents", "business_date": business_date.isoformat(),
        "source": "oracle-prefect", "schema_version": "v1",
        "expected_records": len(records), "expected_chunks": len(chunks),
    })
    for chunk_no, chunk in enumerate(chunks, 1):
        _api("POST", api_url, api_token, f"/api/integrations/v1/batches/{batch_key}/chunks/",
             json={"chunk_no": chunk_no, "records": chunk})
    if finalize:
        return _api("POST", api_url, api_token, f"/api/integrations/v1/batches/{batch_key}/finalize/", json={})
    return {"ok": True, "status": "uploaded_not_finalized"}


@flow(name="oracle-document-intake")
def oracle_document_intake(
    business_date: date, api_url: str, api_token: str,
    oracle_user: str, oracle_password: str, oracle_dsn: str, run_key: str = "daily-v1",
):
    logger = get_run_logger()
    catalog = load_catalog(api_url, api_token)
    raw_rows = load_oracle_rows(business_date, oracle_user, oracle_password, oracle_dsn)
    records, rejected = transform_rows(raw_rows, catalog, business_date)
    logger.info("Oracle rows=%s, valid=%s, rejected_before_send=%s", len(raw_rows), len(records), len(rejected))
    if not raw_rows:
        logger.info("Oracle không có dữ liệu cho ngày %s; không tạo batch.", business_date)
        return {"business_date": business_date.isoformat(), "oracle_rows": 0, "sent_records": 0}
    batch_key = f"oracle-documents-{business_date:%Y%m%d}-{run_key}"
    result = send_batch(api_url, api_token, batch_key, business_date, records)
    return {"batch_key": batch_key, "oracle_rows": len(raw_rows), "sent_records": len(records),
            "rejected_before_send": rejected, "finalize": result}
