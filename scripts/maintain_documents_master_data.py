import psycopg2
from psycopg2.extras import execute_values
from psycopg2 import sql
from sqlalchemy import text
import pandas as pd
import yaml
from yaml.loader import SafeLoader
import oracledb
from urllib.parse import urlencode
from urllib.parse import quote_plus
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from sqlalchemy import create_engine
from sqlalchemy.engine.base import Engine
import logging

# --- Cấu hình ngày ---
TODAY = datetime.today()
YESTERDAY = TODAY - timedelta(days=1)

YESTERDAY_STR = YESTERDAY.strftime('%Y-%m-%d')
YEAR_NUM = YESTERDAY.year
MONTH_NUM = YESTERDAY.month
DATE_PARAM = {
    'year_num': YEAR_NUM,
    'month_num': MONTH_NUM
}

# --- Thông tin môi trường ---
ENV_POSGREST_CREDENTIAL = 'connectionDocumentationPRODUCTION'
ENV_ORACLE_CREDENTIAL = 'connectionf88dwh'

# --- Defination ---pip
def open_yaml_file(file_path: str) -> Dict[str, Any]:
    """Load YAML file containing credentials."""
    with open(file_path, encoding='utf-8') as file:
        credentials = yaml.load(file, Loader=SafeLoader)
    return credentials

# --- Lấy dữ liệu từ Oracle ---
def get_data_from_oracle(user: str, password: str, dns: str, sql: str, param: Optional[Dict] = None) -> pd.DataFrame:
    """Query Oracle and return result as a DataFrame."""
    data = []
    connection = None
    cur = None
    try:
        connection = oracledb.connect(user=user, password=password, dsn=dns)
        cur = connection.cursor()
        if param:
            cur.execute(sql, param)
        else:
            cur.execute(sql)
        columns = [col[0].lower() for col in cur.description]
        data = [dict(zip(columns, row)) for row in cur]
    except oracledb.DatabaseError as e:
        print("Oracle error:", e)
    finally:
        if cur:
            cur.close()
        if connection:
            connection.close()
    return pd.DataFrame(data)

def postgres_create_connection(credentials: dict, connection_name: str):
    conn = credentials[connection_name]
    user = quote_plus(conn["user"])
    password = quote_plus(conn["password"])  # vì password có thể chứa @ hoặc ký tự đặc biệt
    host = conn["host"]
    port = conn["port"]
    dbname = conn["dbname"]

    connection_str = f"postgresql+psycopg2://{user}:{password}@{host}:{port}/{dbname}"
    return create_engine(connection_str)

# --- Hàm lấy dữ liệu từ PostgreSQL database ---
def get_df_from_postgres_db(engine, query: str) -> pd.DataFrame:
    try:
        with engine.connect() as conn:
            df = pd.read_sql_query(query, conn)
        return df
    except Exception as e:
        print(f"[ERROR] Query failed: {e}")
        return pd.DataFrame()

# --- Lấy max area_manager_id để gán khóa chính thủ công ---
def get_max_area_manager_id(engine) -> int:
    """Return current max area_manager_id, default 0 when table is empty."""
    df_max = get_df_from_postgres_db(engine, 'SELECT COALESCE(MAX(area_manager_id), 0) AS max_id FROM "d_AreaManager"')
    if df_max.empty:
        return 0
    return int(df_max.iloc[0]["max_id"])

# Get reference data Từ POSTGRESQL
queries = {
    "regions": "SELECT region_name, region_id, region_code FROM \"d_Region\"",
    "managers": "SELECT manager_code, manager_id FROM \"d_Manager\"",
    "shops": "SELECT shop_code, shop_id FROM \"d_Shops\""
}

# --- Hàm insert Region Managers vào PostgreSQL ---
def insert_region_managers(engine, df):
    if df.empty:
        return
    insert_query = text("""
        INSERT INTO "d_RegionManager" (region_manager_code, region_manager_name, region_manager_email, gender_id, is_active)
        VALUES (:code, :name, :email, 
                (SELECT id FROM "d_Gender" WHERE description = :gender), 
                TRUE)
        ON CONFLICT (region_manager_code) DO NOTHING;
    """)

    with engine.begin() as conn:
        for _, row in df.iterrows():
            conn.execute(insert_query, {
                "code": row["region_manager_code"],
                "name": row["region_manager_name"],
                "email": row["region_manager_email"],
                "gender": row["region_manager_gender"]
            })
    print(f"Inserted {len(df)} new region managers into the database.")


# --- Hàm insert Area Managers vào PostgreSQL ---
def insert_area_managers(engine, df):
    if df.empty:
        return
    insert_query = text("""
        INSERT INTO "d_AreaManager" (area_manager_id, area_manager_code, area_manager_name, area_manager_email, gender_id, is_active)
        VALUES (:id, :code, :name, :email, 
                (SELECT id FROM "d_Gender" WHERE description = :gender), 
                TRUE)
        ON CONFLICT (area_manager_code) DO NOTHING;
    """)

    with engine.begin() as conn:
        for _, row in df.iterrows():
            conn.execute(insert_query, {
                "id": row["area_manager_id"],
                "code": row["area_manager_code"],
                "name": row["area_manager_name"],
                "email": row["area_manager_email"],
                "gender": row["area_manager_gender"]
            })
    print(f"Inserted {len(df)} new area managers into the database.")

# --- Hàm insert Manager dùng SQLAlchemy ---
def insert_managers(engine, df):
    if df.empty:
        return
    insert_query = text("""
        INSERT INTO "d_Manager" (
            manager_code, region_manager_id, area_manager_id, 
            qlkv_code, qlkv_name, qlkv_email, qlv_code, qlv_name, qlv_email, 
            valid_from, is_valid
        )
        VALUES (
            :manager_code, :region_manager_id, :area_manager_id,
            :qlkv_code, :qlkv_name, :qlkv_email, :qlv_code, :qlv_name, :qlv_email,
            NOW(), TRUE
        )
        ON CONFLICT (manager_code) DO NOTHING;
    """)

    with engine.begin() as conn:
        for _, row in df.iterrows():
            conn.execute(insert_query, {
                "manager_code": row["manager_code"],
                "region_manager_id": row["region_manager_id"],
                "area_manager_id": row["area_manager_id"],
                "qlkv_code": row["area_manager_code"],
                "qlkv_name": row["area_manager_name"],
                "qlkv_email": row["area_manager_email"],
                "qlv_code": row["region_manager_code"],
                "qlv_name": row["region_manager_name"],
                "qlv_email": row["region_manager_email"]
            })
    print(f"Inserted {len(df)} new managers into the database.")


## Maintain ORGCHART
orgchart_scripts = '''
WITH EMAIL_LIST AS (
	SELECT 
		emp1.employee_code
	, 	max(emp1.email) AS emp_email  
	,	max(emp1.employee_nm ) AS emp_name
	,	max(emp2.gender) AS emp_gender
	FROM f88dwh.VW_BIZ_W_EMPLOYEE_D emp1
	LEFT JOIN F88DWH.VW_W_EMPLOYEE_D emp2 ON emp1.employee_wid = emp2.employee_wid
	WHERE emp1.CRN_ROW_IND = '1' AND emp1.email IS NOT NULL 
	GROUP BY emp1.employee_code
),
ORCHART_LIST AS (
    SELECT 
      QLV.emp_name AS qlv
    ,	QLV.emp_email AS regionManager_email   
    ,	trim(QLV.emp_gender) AS regionManager_gender
    ,	QLKV.emp_name AS qlkv
    ,	QLKV.emp_email AS areaManager_email
    ,	trim(QLKV.emp_gender) AS areaManager_gender 
    ,	org.shop_id 
    ,	org.shop_name 
    ,	org.qlv_user_code
    ,	CASE WHEN org.qlkv_user_code IS NULL THEN org.qlv_user_code ELSE org.qlkv_user_code END AS qlkv_user_code
    ,	org.region
    ,	ORG.flag AS status
    FROM F88DWH.W_AREA_MANAGER_D ORG 
    LEFT JOIN EMAIL_LIST QLV ON QLV.employee_code = ORG.qlv_user_code 
    LEFT JOIN EMAIL_LIST QLKV ON QLKV.employee_code = ORG.qlkv_user_code 
    WHERE flag IN ('Active','Closed')
 )
SELECT 
	cast(trim(ORCHART_LIST.shop_id) as integer) AS shop_code 
,	ORCHART_LIST.shop_name
,	qlv AS region_manager_name
,	qlkv AS area_manager_name
,	concat(qlv_user_code ,qlkv_user_code) AS manager_code
,	qlv_user_code as region_manager_code 
,	qlkv_user_code as area_manager_code
,	CASE 
		WHEN lower(trim(region)) = 'miền bắc' THEN 1
		WHEN lower(trim(region)) = 'miền nam' THEN 2
		WHEN lower(trim(region)) = 'miền trung' THEN 2
	END AS region_id
,	regionManager_email as region_manager_email
,	areaManager_email as area_manager_email
,	regionManager_gender as region_manager_gender
,	areaManager_gender as area_manager_gender
,	D.close_date
,	ORCHART_LIST.status
FROM ORCHART_LIST  LEFT JOIN F88DWH.W_AREA_MANAGER_MONTHLY_D  D ON D.shop_id = cast(trim(ORCHART_LIST.shop_id) as integer) AND D.YEAR_Num = :year_num AND D.month_num = :month_num
WHERE qlv is not NULL 
'''

# Load credentials from YAML file
my_credentials = open_yaml_file(r'C:\Users\datnm\f88doc\credential.yml')
# Oracle Connection
oracle_config = my_credentials[ENV_ORACLE_CREDENTIAL]
orcl_dns = oracle_config['dns']
orcl_port = oracle_config['port']
orcl_sid = oracle_config['sid']
orcl_user = oracle_config['user']
orcl_password = oracle_config['pass']

# Tính năm/tháng của kỳ t-1
target_date = (datetime.now().replace(day=1) - timedelta(days=1)).date()
year_num = target_date.year
month_num = target_date.month

# --- Truy vấn Oracle orgchart ---
df_orgchart = get_data_from_oracle(
    orcl_user,
    orcl_password,
    orcl_dns,
    sql=orgchart_scripts,
    param={'year_num': year_num, 'month_num': month_num}
)

# Chuẩn hóa ngày đóng cửa
df_orgchart['shop_closed_date'] = (
    pd.to_datetime(df_orgchart['close_date'], errors='coerce')
      .dt.date
      .astype('object')
      .where(lambda x: x.notna(), None)
)
# Chuẩn hóa status (active/inactive/closed)
df_orgchart['status'] = df_orgchart['status'].fillna('').str.strip().str.lower()
df_orgchart['is_shop_closed'] = df_orgchart['status'] == 'closed'
df_orgchart['is_shop_active'] = df_orgchart['status'] == 'active'
# Default for_borrow_only
df_orgchart['for_borrow_only'] = False

# --- Tạo kết nối PostgreSQL ---
engine = postgres_create_connection(my_credentials, ENV_POSGREST_CREDENTIAL)

# --- Load dữ liệu hiện tại từ PostgreSQL ---
df_existing_region_managers = get_df_from_postgres_db(engine, 'SELECT region_manager_code FROM "d_RegionManager"')
df_existing_area_manager = get_df_from_postgres_db(engine, 'SELECT area_manager_code FROM "d_AreaManager"')
df_manager = get_df_from_postgres_db(engine, 'SELECT manager_code FROM "d_Manager"')
df_shops = get_df_from_postgres_db(engine, 'SELECT shop_code FROM "d_Shops"')

# Quản lý vùng mới xuất hiện nếu không có trong danh sách hiện tại (2)
new_region_managers = df_orgchart[~df_orgchart['region_manager_code'].isin(df_existing_region_managers['region_manager_code'])][['region_manager_code', 'region_manager_name', 'region_manager_email', 'region_manager_gender']].drop_duplicates()
print(f"Tổng số Quản lý vùng mới xuất hiện: {len(new_region_managers)}")
logging.info(f"Tổng số Quản lý vùng mới xuất hiện: {len(new_region_managers)}")

# --- Insert các Region Manager mới vào PostgreSQL ---
if not new_region_managers.empty:
    insert_region_managers(engine, new_region_managers)

# Quản lý khu vực mới xuất hiện nếu không có trong danh sách hiện tại (2)
new_area_managers = df_orgchart[~df_orgchart['area_manager_code'].isin(df_existing_area_manager['area_manager_code'])][['area_manager_code', 'area_manager_name', 'area_manager_email', 'area_manager_gender']].drop_duplicates()
print(f"Tổng số Quản lý khu vực mới xuất hiện: {len(new_area_managers)}")
logging.info(f"Tổng số Quản lý khu vực mới xuất hiện: {len(new_area_managers)}")

# --- Insert các Area Manager mới vào PostgreSQL ---
if not new_area_managers.empty:
    # Gán area_manager_id thủ công vì cột không có default/identity
    new_area_managers = new_area_managers.reset_index(drop=True)
    current_max_area_manager_id = get_max_area_manager_id(engine)
    new_area_managers['area_manager_id'] = range(current_max_area_manager_id + 1,
                                                 current_max_area_manager_id + 1 + len(new_area_managers))
    insert_area_managers(engine, new_area_managers)

# --- Lấy dữ liệu đầy đủ Region và Area Manager sau insert ---
df_region_managers_full = get_df_from_postgres_db(engine, 'SELECT region_manager_id, region_manager_code FROM "d_RegionManager"')
df_area_managers_full = get_df_from_postgres_db(engine, 'SELECT area_manager_id, area_manager_code FROM "d_AreaManager"')

# --- Kiểm tra và lấy Managers mới ---
new_managers = df_orgchart[~df_orgchart['manager_code'].isin(df_manager['manager_code'])].copy()
new_managers = new_managers.merge(df_region_managers_full, on='region_manager_code', how='left')
new_managers = new_managers.merge(df_area_managers_full, on='area_manager_code', how='left')

new_managers_final = new_managers[[
    'manager_code', 'region_manager_id', 'area_manager_id',
    'area_manager_code', 'area_manager_name', 'area_manager_email',
    'region_manager_code', 'region_manager_name', 'region_manager_email'
]]

print(f"Số Manager mới: {len(new_managers_final)}")

# --- Insert các Manager mới vào PostgreSQL ---
if not new_managers_final.empty:
    insert_managers(engine, new_managers_final)


# --- Hàm insert Shops dùng SQLAlchemy ---
def insert_df_to_shops_postgres_db(engine, df):
    if df.empty:
        return
    insert_query = text("""
        INSERT INTO "d_Shops" (
            shop_code, shop_name, shop_email, is_shop_active, manager_id, region_id, created_date, shop_closed_date, for_borrow_only
        )
        VALUES (
            :shop_code, :shop_name, :shop_email, :is_shop_active, :manager_id, :region_id, :created_date, :shop_closed_date, :for_borrow_only
        )
        ON CONFLICT (shop_code) DO NOTHING;
    """)

    with engine.begin() as conn:
        for _, row in df.iterrows():
            conn.execute(insert_query, {
                "shop_code": row["shop_code"],
                "shop_name": row["shop_name"],
                "shop_email": row["shop_email"],
                "is_shop_active": row["is_shop_active"],
                "manager_id": row["manager_id"],
                "region_id": row["region_id"],
                "created_date": row["created_date"],
                "shop_closed_date": None if pd.isna(row["shop_closed_date"]) else row["shop_closed_date"],
                "for_borrow_only": row["for_borrow_only"]
            })
    print(f"Inserted {len(df)} new shops into the database.")


# Hàm update các shop đã tồn tại
def update_shops_postgres_db(engine, df):
    if df.empty:
        return
    df = df.copy()
    df['shop_closed_date'] = pd.to_datetime(df['shop_closed_date'], errors='coerce').dt.date
    df['shop_closed_date'] = df['shop_closed_date'].astype('object').where(pd.notna(df['shop_closed_date']), None)
    update_query = text("""

        UPDATE "d_Shops"
        SET shop_name = :shop_name,
            is_shop_active = :is_shop_active,
            manager_id = :manager_id,
            region_id = :region_id,
            shop_closed_date = :shop_closed_date,
            for_borrow_only = :for_borrow_only
        WHERE shop_code = :shop_code;
    """)
    with engine.begin() as conn:
        for _, row in df.iterrows():
            conn.execute(update_query, {
                'shop_code': row['shop_code'],
                'shop_name': row['shop_name'],
                'is_shop_active': bool(row['is_shop_active']),
                'manager_id': row['manager_id'],
                'region_id': row['region_id'],
                'shop_closed_date': None if pd.isna(row['shop_closed_date']) else row['shop_closed_date'],
                'for_borrow_only': False
            })
    print(f"Updated {len(df)} shops in the database.")


# Đồng bộ trạng thái active/inactive của shop dựa trên orgchart
def sync_shop_active_status(engine, df_shop_in_db, df_orgchart):
    if df_shop_in_db.empty:
        print("[WARNING] Khong co shop nao trong he thong de dong bo trang thai.")
        return
    df_shop_in_db = df_shop_in_db.copy()
    df_shop_in_db['shop_code'] = df_shop_in_db['shop_code'].astype(str)

    df_orgchart_local = df_orgchart.copy()
    df_orgchart_local['shop_code'] = df_orgchart_local['shop_code'].astype(str)
    df_orgchart_local['shop_closed_date'] = pd.to_datetime(
        df_orgchart_local['shop_closed_date'], errors='coerce'
    ).dt.date

    active_shop_codes = df_orgchart_local.loc[df_orgchart_local['is_shop_active'], 'shop_code'].dropna().unique().tolist()

    inactive_rows = df_orgchart_local.loc[~df_orgchart_local['is_shop_active'], ['shop_code', 'shop_name', 'shop_closed_date', 'status']].dropna(subset=['shop_code'])
    inactive_rows['shop_code'] = inactive_rows['shop_code'].astype(str)
    # Normalize NaT/NaN to None to avoid invalid timestamp
    inactive_rows['shop_closed_date'] = inactive_rows['shop_closed_date'].apply(lambda x: None if pd.isna(x) else x)
    inactive_shop_map = {row.shop_code: row.shop_closed_date for _, row in inactive_rows.iterrows()}
    closed_missing_date = inactive_rows[(inactive_rows['status'] == 'closed') & (inactive_rows['shop_closed_date'].isna())]['shop_name'].dropna().unique().tolist()

    missing_orgchart_codes = df_shop_in_db[~df_shop_in_db['shop_code'].isin(df_orgchart_local['shop_code'])]['shop_code'].tolist()
    for code in missing_orgchart_codes:
        inactive_shop_map.setdefault(code, None)

    with engine.begin() as conn:
        if active_shop_codes:
            conn.execute(
                text('UPDATE "d_Shops" SET is_shop_active = TRUE, shop_closed_date = NULL WHERE shop_code::text = ANY(:shop_codes)'),
                {"shop_codes": active_shop_codes}
            )
        for shop_code, closed_date in inactive_shop_map.items():
            closed_date = None if pd.isna(closed_date) else closed_date
            conn.execute(
                text('UPDATE "d_Shops" SET is_shop_active = FALSE, shop_closed_date = COALESCE(:shop_closed_date, shop_closed_date) WHERE shop_code = :shop_code'),
                {"shop_code": shop_code, "shop_closed_date": closed_date}
            )
    print(f"Da dong bo trang thai: active {len(active_shop_codes)} PGD theo orgchart, inactive {len(inactive_shop_map)} PGD khong co trong hoac ngoai orgchart.")
    if closed_missing_date:
        print("[WARNING] Shop status 'closed' nhung chua co shop_closed_date tu orgchart:", "; ".join(closed_missing_date))

# MAINTAIN SHOPS
# Tạo shop mới
# Láy ra danh sách shop từ Database
df_shop = get_df_from_postgres_db(engine, 'SELECT shop_code FROM "d_Shops"')
# Lấy danh sách Manager từ Database sau khi đã chạy xong df_manager_new
df_manager = get_df_from_postgres_db(engine, 'SELECT manager_id, manager_code FROM "d_Manager"')
# Lấy các shop_code từ df_orgchart chưa có trong df_shop
new_shop_codes = df_orgchart[~df_orgchart['shop_code'].isin(df_shop['shop_code'])]['shop_code'].unique()
# Lọc các dòng trong df_orgchart có shop_code nằm trong new_shop_codes
new_shop_df = df_orgchart[df_orgchart['shop_code'].isin(new_shop_codes)].copy()
new_shop_df = new_shop_df.merge(df_manager[['manager_id', 'manager_code']], left_on='manager_code', right_on='manager_code', how='left')
# Đổi tên các cột cho phù hợp với df_manager
new_shop_df = new_shop_df.rename(columns={
    'shop_code': 'shop_code',
    'shop_name': 'shop_name',
    'shop_email': 'shop_email',
    'region_id': 'region_id',
    'manager_id': 'manager_id',
    'is_shop_active': 'is_shop_active',
    'for_borrow_only': 'for_borrow_only'
})
new_shop_df['shop_email'] = 'bosungsau@f88.vn'
new_shop_df['is_shop_active'] = new_shop_df['is_shop_active']
new_shop_df['created_date'] = datetime.now().date()
new_shop_df['for_borrow_only'] = False
new_shop_df['shop_closed_date'] = pd.to_datetime(new_shop_df['shop_closed_date'], errors='coerce').dt.date
new_shop_df['shop_closed_date'] = new_shop_df['shop_closed_date'].astype('object').where(pd.notna(new_shop_df['shop_closed_date']), None)

# Chuẩn bị tập shop đã tồn tại để cập nhật thông tin và for_borrow_only
existing_shop_df = df_orgchart[df_orgchart['shop_code'].isin(df_shop['shop_code'])].copy()
existing_shop_df = existing_shop_df.merge(df_manager[['manager_id', 'manager_code']], left_on='manager_code', right_on='manager_code', how='left')
existing_shop_df['for_borrow_only'] = False
existing_shop_df['shop_closed_date'] = pd.to_datetime(existing_shop_df['shop_closed_date'], errors='coerce').dt.date
existing_shop_df['shop_closed_date'] = existing_shop_df['shop_closed_date'].astype('object').where(pd.notna(existing_shop_df['shop_closed_date']), None)
# Cập nhật các shop đã có
update_shops_postgres_db(engine, existing_shop_df[['shop_code', 'shop_name', 'is_shop_active', 'manager_id', 'region_id', 'shop_closed_date', 'for_borrow_only']])

# Tạo các SHOP trên database nếu có
insert_df_to_shops_postgres_db(engine, new_shop_df[['shop_code', 'shop_name', 'shop_email', 'is_shop_active', 'manager_id', 'region_id', 'created_date', 'shop_closed_date', 'for_borrow_only']])
sync_shop_active_status(engine, df_shop, df_orgchart)
