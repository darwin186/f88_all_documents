"""Prefect flow: Oracle orgchart -> staged master-data intake API.

This is the HTTP replacement for ``maintain_documents_master_data.py``.  It
maintains RegionManager, AreaManager, Manager and Shop through one complete,
idempotent monthly snapshot instead of writing directly to PostgreSQL.
"""
from datetime import date, datetime

import oracledb
import requests
try:
    from prefect import flow, task
except ImportError:
    def task(*args, **kwargs):
        return lambda function: function

    def flow(*args, **kwargs):
        return lambda function: function


CHUNK_SIZE = 500

ORACLE_ORGCHART_SQL = """
WITH EMAIL_LIST AS (
    SELECT emp1.employee_code,
           MAX(emp1.email) AS emp_email,
           MAX(emp1.employee_nm) AS emp_name,
           MAX(emp2.gender) AS emp_gender
    FROM F88DWH.VW_BIZ_W_EMPLOYEE_D emp1
    LEFT JOIN F88DWH.VW_W_EMPLOYEE_D emp2
      ON emp1.employee_wid = emp2.employee_wid
    WHERE emp1.CRN_ROW_IND = '1'
      AND emp1.email IS NOT NULL
    GROUP BY emp1.employee_code
),
ORCHART_LIST AS (
    SELECT QLV.emp_name AS qlv,
           QLV.emp_email AS region_manager_email,
           TRIM(QLV.emp_gender) AS region_manager_gender,
           QLKV.emp_name AS qlkv,
           QLKV.emp_email AS area_manager_email,
           TRIM(QLKV.emp_gender) AS area_manager_gender,
           org.shop_id,
           org.shop_name,
           org.qlv_user_code,
           CASE WHEN org.qlkv_user_code IS NULL
                THEN org.qlv_user_code ELSE org.qlkv_user_code END AS qlkv_user_code,
           org.region,
           org.flag AS status
    FROM F88DWH.W_AREA_MANAGER_D org
    LEFT JOIN EMAIL_LIST QLV ON QLV.employee_code = org.qlv_user_code
    LEFT JOIN EMAIL_LIST QLKV ON QLKV.employee_code = org.qlkv_user_code
    WHERE org.flag IN ('Active', 'Closed')
)
SELECT CAST(TRIM(ORCHART_LIST.shop_id) AS INTEGER) AS shop_code,
       ORCHART_LIST.shop_name,
       qlv AS region_manager_name,
       qlkv AS area_manager_name,
       qlv_user_code || qlkv_user_code AS manager_code,
       qlv_user_code AS region_manager_code,
       qlkv_user_code AS area_manager_code,
       CASE
         WHEN LOWER(TRIM(region)) = 'miền bắc' THEN '1'
         WHEN LOWER(TRIM(region)) IN ('miền nam', 'miền trung') THEN '2'
       END AS region_code,
       region_manager_email,
       area_manager_email,
       region_manager_gender,
       area_manager_gender,
       D.close_date AS shop_closed_date,
       ORCHART_LIST.status
FROM ORCHART_LIST
LEFT JOIN F88DWH.W_AREA_MANAGER_MONTHLY_D D
  ON D.shop_id = CAST(TRIM(ORCHART_LIST.shop_id) AS INTEGER)
 AND D.year_num = :year_num
 AND D.month_num = :month_num
WHERE qlv IS NOT NULL
"""


def _text(value):
    return "" if value is None else str(value).strip()


def _iso_date(value):
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return date.fromisoformat(str(value)[:10]).isoformat()


def _api(method, base_url, token, path, **kwargs):
    response = requests.request(
        method,
        f"{base_url.rstrip('/')}{path}",
        headers={"Authorization": f"Bearer {token}"},
        timeout=60,
        **kwargs,
    )
    response.raise_for_status()
    return response.json()


@task(retries=3, retry_delay_seconds=30)
def load_oracle_orgchart(target_month: date, oracle_user: str, oracle_password: str, oracle_dsn: str):
    connection = oracledb.connect(user=oracle_user, password=oracle_password, dsn=oracle_dsn)
    try:
        cursor = connection.cursor()
        cursor.execute(ORACLE_ORGCHART_SQL, {
            "year_num": target_month.year,
            "month_num": target_month.month,
        })
        columns = [column[0].lower() for column in cursor.description]
        return [dict(zip(columns, row)) for row in cursor]
    finally:
        connection.close()


def transform_orgchart(rows, deactivate_missing_shops=True):
    """Build one complete snapshot and a non-sensitive cleaning report."""
    output_by_shop = {}
    rejected = []
    for row in rows:
        shop_code = _text(row.get("shop_code"))
        status = _text(row.get("status")).lower()
        manager_code = _text(row.get("manager_code"))
        required = {
            "shop_code": shop_code,
            "shop_name": _text(row.get("shop_name")),
            "manager_code": manager_code,
            "region_manager_code": _text(row.get("region_manager_code")),
            "region_manager_name": _text(row.get("region_manager_name")),
            "area_manager_code": _text(row.get("area_manager_code")),
            "area_manager_name": _text(row.get("area_manager_name")),
            "region_code": _text(row.get("region_code")),
        }
        missing = [field for field, value in required.items() if not value]
        if missing or status not in {"active", "closed"}:
            rejected.append({
                "shop_code": shop_code,
                "reason": (
                    f"Thiếu trường: {', '.join(missing)}" if missing
                    else f"Trạng thái không hợp lệ: {status}"
                ),
            })
            continue
        record = {
            "entity": "orgchart_shop",
            "shop_code": int(shop_code),
            "shop_name": required["shop_name"],
            "manager_code": manager_code,
            "region_manager_code": required["region_manager_code"],
            "region_manager_name": required["region_manager_name"],
            "region_manager_email": _text(row.get("region_manager_email")) or None,
            "region_manager_gender": _text(row.get("region_manager_gender")) or None,
            "area_manager_code": required["area_manager_code"],
            "area_manager_name": required["area_manager_name"],
            "area_manager_email": _text(row.get("area_manager_email")) or None,
            "area_manager_gender": _text(row.get("area_manager_gender")) or None,
            "region_code": required["region_code"],
            "status": status,
            "shop_closed_date": _iso_date(row.get("shop_closed_date")),
        }
        # Oracle should be unique by shop. If it is not, Closed wins because the
        # legacy sync applies inactive rows after active rows.
        previous = output_by_shop.get(record["shop_code"])
        if previous is None or record["status"] == "closed":
            output_by_shop[record["shop_code"]] = record
    records = list(output_by_shop.values())
    records.append({
        "entity": "orgchart_snapshot",
        "snapshot_complete": not rejected,
        "deactivate_missing_shops": bool(deactivate_missing_shops),
        "source_rows": len(rows),
        "shop_rows": len(output_by_shop),
    })
    return records, rejected


@task(retries=4, retry_delay_seconds=20)
def send_master_snapshot(api_url, api_token, batch_key, business_date, records, finalize=True):
    chunks = [records[index:index + CHUNK_SIZE] for index in range(0, len(records), CHUNK_SIZE)]
    _api("POST", api_url, api_token, "/api/integrations/v1/batches/", json={
        "batch_key": batch_key,
        "kind": "master_data",
        "business_date": business_date.isoformat(),
        "source": "oracle-orgchart-prefect",
        "schema_version": "v2",
        "expected_records": len(records),
        "expected_chunks": len(chunks),
    })
    for number, chunk in enumerate(chunks, 1):
        _api(
            "POST", api_url, api_token,
            f"/api/integrations/v1/batches/{batch_key}/chunks/",
            json={"chunk_no": number, "records": chunk},
        )
    if finalize:
        return _api(
            "POST", api_url, api_token,
            f"/api/integrations/v1/batches/{batch_key}/finalize/",
            json={},
        )
    return {"ok": True, "status": "uploaded_not_finalized"}


@flow(name="oracle-document-master-data-intake")
def oracle_document_master_data_intake(
    target_month: date,
    api_url: str,
    api_token: str,
    oracle_user: str,
    oracle_password: str,
    oracle_dsn: str,
    run_key: str = "monthly",
    deactivate_missing_shops: bool = True,
):
    rows = load_oracle_orgchart(target_month, oracle_user, oracle_password, oracle_dsn)
    records, rejected = transform_orgchart(rows, deactivate_missing_shops)
    if rejected:
        raise ValueError(
            f"Orgchart có {len(rejected)} dòng không hợp lệ; không gửi snapshot để tránh deactivate sai PGD"
        )
    batch_key = f"oracle-orgchart-{target_month:%Y%m}-{run_key}"
    return send_master_snapshot(
        api_url, api_token, batch_key, target_month, records, finalize=True
    )

