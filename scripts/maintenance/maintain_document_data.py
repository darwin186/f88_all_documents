import argparse
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Optional

import oracledb
import pandas as pd
import psycopg2
import yaml
from sqlalchemy import create_engine, text
from sqlalchemy.engine.base import Engine
from urllib.parse import quote_plus
from yaml.loader import SafeLoader

logger = logging.getLogger(__name__)
# --- Defination ---
def open_yaml_file(file_path: str) -> Dict[str, Any]:
    """Load YAML file containing credentials."""
    with open(file_path, encoding='utf-8') as file:
        credentials = yaml.load(file, Loader=SafeLoader)
    return credentials

# Biến log kết quả insert
insert_log = []

# Hàm xử lý ghi log lưu file theo ngày
def log_insert_summary(date_str, folder_count, document_count):
    insert_log.append({
        'date': date_str,
        'folders_inserted': folder_count,
        'documents_inserted': document_count
    })

# Hàm lưu log insert ra file excel
def save_insert_log(path: Path):
    df_log = pd.DataFrame(insert_log)
    path.parent.mkdir(parents=True, exist_ok=True)
    df_log.to_excel(path, index=False)
    logger.info("📄 Log insert đã lưu tại: %s", path)

# Hàm xử lý null
def save_null_records(df, date_str, output_dir: Path):
    df_null_critical = df[df[['shop_id', 'folder_type_id', 'manager_id', 'region_id']].isnull().any(axis=1)]
    if not df_null_critical.empty:
        output_dir.mkdir(parents=True, exist_ok=True)
        file_null_path = output_dir / f'check_null_{date_str}.xlsx'
        df_null_critical.to_excel(file_null_path, index=False)
        logger.warning("[WARNING] Ngày %s có %s dòng null. Đã lưu tại %s", date_str, len(df_null_critical), file_null_path)
        
# --- Lấy dữ liệu từ Oracle ---
def get_data_from_oracle(user: str, password: str, dns: str, sql: str, param: Optional[Dict] = None) -> pd.DataFrame:
    """
    Query Oracle and return result as a DataFrame.
    
    :param user: Oracle username
    :param password: Oracle password
    :param dns: Oracle DSN string
    :param sql: SQL query string
    :param param: Optional dictionary of parameters
    :return: pd.DataFrame
    """
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
        logger.error("Oracle error: %s", e)
    finally:
        if cur:
            cur.close()
        if connection:
            connection.close()
    return pd.DataFrame(data)

# Tạo engine
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
        logger.error("[ERROR] Query failed: %s", e)
        return pd.DataFrame()
    
# Get reference data từ hệ thống chứng từ 
queries = {
    "regions": "SELECT region_name, region_id, region_code FROM \"d_Region\"",
    "managers": "SELECT manager_code, manager_id FROM \"d_Manager\"",
    "shops": "SELECT shop_code, shop_id FROM \"d_Shops\"",
    "folder_types": "SELECT folder_type_code, folder_type_id FROM \"d_FolderType\"",
    "business_types": "SELECT business_type_name, business_type_id, action_code, need_action_code FROM \"d_BusinessType\"",
    "document_types": "SELECT document_type_name, document_type_id FROM \"d_DocumentType\"",
    "folder_group": "SELECT * FROM \"d_Folder_group\" where is_active = true "
    }
#---DOCUMENT_TRANSACTION
source_document_scripts= f'''
WITH DOCUMENT AS ( 
    SELECT 
            to_char(DOC.year_num) AS created_year
        ,	CASE WHEN LENGTH(Doc.month_num) = 1 THEN LPAD(Doc.month_num, 2, '0')  ELSE TO_CHAR(DOC.month_num) END AS created_month 
        ,	SUBSTR(DOC.date_wid,7,2 )  AS created_day
        ,	COALESCE(TO_CHAR(DOC.code_no) , TO_CHAR(DOC.contract_code) , TO_CHAR(DOC.id) , '999' )||ID AS  parent_document_code
        ,	DOC.trans_shop_code AS shop_code 
        ,	TRIM(DOC.document_type) AS folder_type
        ,	DOC.doc_grp 
        ,   DOC.transaction_type as business_type
        ,   DOC.action_code
        ,	NVL(SHOP.shop_nm, DOC.shop_name) AS shop_name
        ,	DOC.code_no AS loan_code
        ,	DOC.contract_code AS contract_code
        ,	CASE WHEN DOC.employee_code IN ('SYS000005','STS000002','cvkd_test_1149','sysf88mobile','losapiv2' ) THEN AREA_CURRENT.mnv_tpgd ELSE DOC.employee_code  END AS employee_code
        ,	CASE WHEN DOC.employee_code  IN ('SYS000005','STS000002','cvkd_test_1149','sysf88mobile','losapiv2' ) THEN AREA_CURRENT.tpgd  ELSE DOC.employee_nm  END  AS employee_name
        ,   DOC.customer_code AS customer_code
        ,	DOC.customer_nm AS customer_name
        ,	CASE WHEN LOWER(TRIM(AREA.mien)) = 'miền trung' THEN 'Miền Nam' ELSE AREA.mien END AS region 
        ,	AREA.qlv_nm AS qlv
        ,	AREA.QLKV_nm AS qlkv 
        ,	AREA.qlv_code AS qlv_user_code  
        ,	CASE WHEN AREA.qlkv_code IS NULL THEN AREA.qlv_code ELSE AREA.qlkv_code END AS qlkv_user_code
        FROM F88DWH.W_RPT_TRANSACTION_DOCUMENT DOC  
        LEFT JOIN F88DWH.W_SHOP_D SHOP ON SHOP.shop_code = DOC.trans_shop_code AND SHOP.shop_type = 'F88' AND SHOP.crn_row_ind = 1
        LEFT JOIN F88DWH.W_AREA_MANAGER_MONTHLY_D AREA ON TO_CHAR(AREA.shop_id)  = DOC.trans_shop_code AND DOC.year_num = AREA.year_num AND DOC.month_num = AREA.month_num 
        LEFT JOIN F88DWH.W_AREA_MANAGER_D AREA_CURRENT ON  TRIM(TO_CHAR(AREA_CURRENT.shop_id))  = DOC.trans_shop_code 
        WHERE 
            DOC.year_num= :year_num AND 
            DOC.month_num= :month_num AND 
            DOC.document_type != 'Chứng từ lưu trữ tại PGD' AND 
            DOC.doc_grp != 'Không phát sinh bộ chứng từ bản giấy' AND 
            DOC.trans_shop_code not in ('1099','2999', '1149','1052','9401')
            and NVL(DOC.trans_shop_code, '0') != '0'
) SELECT 
    DOCUMENT.*
,   created_year||created_month||created_day||shop_code AS parent_folder_code
FROM DOCUMENT
'''
# Insert data vào bảng d_Employee
def insert_and_get_employee(engine, df):
    if df.empty:
        return pd.DataFrame(columns=['employee_id', 'employee_code'])

    insert_query = text("""
        INSERT INTO "d_Employee" (employee_code, employee_name)
        VALUES (:employee_code, :employee_name)
        ON CONFLICT (employee_code) DO NOTHING;
    """)

    with engine.begin() as conn:
        for _, row in df.iterrows():
            conn.execute(insert_query, {
                "employee_code": row['employee_code'],
                "employee_name": row['employee_name']
            })

    if len(df) <= 1000:
        placeholders = ','.join([f"'{x}'" for x in df['employee_code'].tolist()])
        select_query = f'SELECT employee_id, employee_code FROM "d_Employee" WHERE employee_code IN ({placeholders})'
        df_employee_id = get_df_from_postgres_db(engine, select_query)
    else:
        chunks = []
        codes = df['employee_code'].tolist()
        for i in range(0, len(codes), 1000):
            sublist = codes[i:i+1000]
            placeholders = ','.join([f"'{x}'" for x in sublist])
            select_query = f'SELECT employee_id, employee_code FROM "d_Employee" WHERE employee_code IN ({placeholders})'
            chunk_df = get_df_from_postgres_db(engine, select_query)
            chunks.append(chunk_df)
        df_employee_id = pd.concat(chunks, ignore_index=True)
    return df_employee_id

# Insert data vào bảng d_LoanCustomer
def insert_and_get_customer(engine, df):
    if df.empty:
        return pd.DataFrame(columns=['customer_id', 'customer_code'])

    insert_query = text("""
        INSERT INTO "d_LoanCustomer" (customer_code, customer_name)
        VALUES (:customer_code, :customer_name)
        ON CONFLICT (customer_code) DO NOTHING;
    """)

    with engine.begin() as conn:
        for _, row in df.iterrows():
            conn.execute(insert_query, {
                "customer_code": row['customer_code'],
                "customer_name": row['customer_name']
            })

    if len(df) <= 1000:
        placeholders = ','.join([f"'{x}'" for x in df['customer_code'].tolist()])
        select_query = f'SELECT customer_id, customer_code FROM "d_LoanCustomer" WHERE customer_code IN ({placeholders})'
        df_customer_id = get_df_from_postgres_db(engine, select_query)
    else:
        chunks = []
        codes = df['customer_code'].tolist()
        for i in range(0, len(codes), 1000):
            sublist = codes[i:i+1000]
            placeholders = ','.join([f"'{x}'" for x in sublist])
            select_query = f'SELECT customer_id, customer_code FROM "d_LoanCustomer" WHERE customer_code IN ({placeholders})'
            chunk_df = get_df_from_postgres_db(engine, select_query)
            chunks.append(chunk_df)
        df_customer_id = pd.concat(chunks, ignore_index=True)

    return df_customer_id

# --- Insert folder và lấy folder_id bằng SQLAlchemy ---
def insert_folders_with_return(engine, df):
    if df.empty:
        return []

    insert_sql = text("""
        INSERT INTO "f_FolderDetail" 
        (folder_code, shop_id, folder_type_id, folder_status_id, manager_id, folder_created_date, is_original, is_issue, row_created_date, group_id, is_out_of_group)
        VALUES (:folder_code, :shop_id, :folder_type_id, 1, :manager_id, :folder_created_date, :is_original, :is_issue, NOW(), :group_id, :is_out_of_group)
        ON CONFLICT (folder_code) DO UPDATE SET folder_code = EXCLUDED.folder_code
        RETURNING folder_id, folder_code;
    """)

    results = []
    with engine.begin() as conn:
        for _, row in df.iterrows():
            result = conn.execute(insert_sql, {
                'folder_code': row['folder_code'],
                'shop_id': row['shop_id'],
                'folder_type_id': row['folder_type_id'],
                'manager_id': row['manager_id'],
                'folder_created_date': row['created_date'],
                'is_original': row['is_original'],
                'is_issue': row['is_issue'],
                'group_id': row['group_id'],
                'is_out_of_group': row['is_out_of_group']
            }).fetchone()
            if result:
                results.append(result)
    return results

#--- Insert documents dùng SQLAlchemy ---
def insert_documents(engine, df):
    if df.empty:
        return

    insert_sql = text("""
        INSERT INTO "f_DocumentsDetail" 
        (documents_code, document_type_id, shop_id, loan_id, contract_id, documents_created_date, folder_id, business_type_id, manager_id, is_pending_metadata, note)
        VALUES (:documents_code, :document_type_id, :shop_id, :loan_id, :contract_id, :documents_created_date, :folder_id, :business_type_id, :manager_id, :is_pending_metadata, :note)
        ON CONFLICT (documents_code) DO NOTHING;
    """)

    with engine.begin() as conn:
        for _, row in df.iterrows():
            # Với trường hợp không có business_type_id và document_type_id null thì sẽ vẫn insert vào database 
            # nhưng sẽ đánh dấu là is_pending_metadata = True và note là tên của document_type_name và business_type_name nếu có 
            
            note = ""  # Initialize note as an empty string
            is_pending_metadata = False  # Default value

            if pd.isna(row['business_type_id']): 
                is_pending_metadata = True
                note += f"Loại nghiệp vụ: {row['business_type_name']}\n"
            if pd.isna(row['document_type_id']): 
                is_pending_metadata = True
                note += f"Loại chứng từ: {row['document_type_name']}"
            if not is_pending_metadata:
                note = None  # Set note to None if no metadata is pending
                
            conn.execute(insert_sql, {
                'documents_code': str(row['parent_document_code']),
                'document_type_id': None if pd.isna(row['document_type_id']) else row['document_type_id'],
                'shop_id': row['shop_id'],
                'loan_id': None if pd.isna(row['loan_id']) else row['loan_id'] ,
                'contract_id': None if pd.isna(row['contract_id']) else row['contract_id']  ,
                'documents_created_date': row['created_date'],
                'folder_id': row['folder_id'],
                'business_type_id':  None if pd.isna(row['business_type_id']) else row['business_type_id'] ,
                'manager_id': row['manager_id'] ,
                'is_pending_metadata': False,
                'note': note
            })

# Xử lý biến và môi trường
def run_job(
    start_date: datetime,
    end_date: datetime,
    engine: Engine,
    oracle_user: str,
    oracle_password: str,
    oracle_dsn: str,
    null_output_dir: Path,
    summary_output_dir: Path,
):
    insert_log.clear()
    for single_date in pd.date_range(start=start_date, end=end_date):
        logger.info("=== Đang xử lý ngày: %s ===", single_date.strftime('%Y-%m-%d'))
        
         # Tạo DATE_PARAM cho từng ngày
        YEAR_NUM = single_date.year
        MONTH_NUM = single_date.month
        DAY_NUM = single_date.day
        DATE_PARAM = {'year_num': YEAR_NUM, 'month_num': MONTH_NUM}
    # --- Thông tin môi trường ---
        # --- Truy vấn Oracle documents ---
        df_documents_data = get_data_from_oracle(oracle_user, oracle_password, oracle_dsn, source_document_scripts, DATE_PARAM)
        if df_documents_data.empty:
            logger.info("[INFO] Không có dữ liệu cho ngày %s", single_date.strftime('%Y-%m-%d'))
            # Ensure required columns exist to prevent KeyError later
            df_documents_data['folder_type_code'] = pd.Series(dtype='Int64')
            continue
        # Lọc lấy ngày  
        df_documents_data = df_documents_data[df_documents_data['created_year'] == str(YEAR_NUM)]
        df_documents_data = df_documents_data[df_documents_data['created_month'] == str(MONTH_NUM).zfill(2)]
        df_documents_data = df_documents_data[df_documents_data['created_day'] == str(DAY_NUM).zfill(2)] 
        if df_documents_data.empty:
            # Khong co du lieu thi pass luon 
            logger.info("[INFO] Không có dữ liệu cho ngày %s sau khi lọc ngày.", single_date.strftime('%Y-%m-%d'))
            # Ensure required columns exist to prevent KeyError later
            df_documents_data['folder_type_code'] = pd.Series(dtype='Int64')
            continue
    # Dict dùng để phân loại ( lấy từ datawarehouse hệ thống chứng từ )
        df_documents_data = df_documents_data[df_documents_data['shop_code'] != 'NULL']
    
        # MAINTAIN FOLDER_TYPE
        df_documents_data['folder_type'] = df_documents_data['folder_type'].str.strip()
        mapping_folder_type = {"Chứng từ Vận hành hàng ngày": 1,"Chứng từ CIMB hàng ngày": 2, "Chứng từ Ngân hàng hàng ngày":3 } # Dùng code ( không dùng id)
        # folder_type_code mapping
        df_documents_data['folder_type_code'] = df_documents_data['folder_type'].map(mapping_folder_type)
    
        # Ngày chứng từ documents_created_date, ngày quyển folder_created_date
        df_documents_data['created_date'] = df_documents_data['created_year']+"-"+df_documents_data['created_month']+"-"+df_documents_data['created_day']
    
        # Gen mã quyển theo cú pháp: folder_type_code + shop_code + created_year + created_month + created_day
        # THay đổi: gen mã quyền theo cú pháp folder_parent_Code + folder_type_code = folder_code   
        df_documents_data['folder_code'] = (df_documents_data['parent_folder_code'].astype('str') + df_documents_data['folder_type_code'].astype('str')).astype('str')
        columns= ['created_year', 'created_month', 'created_day', 'shop_code', 'folder_type', 'doc_grp', 'shop_name', 'loan_code', 'employee_code', 'employee_name', 'customer_code', 'customer_name', 'region', 'qlv', 'qlkv', 'qlv_user_code', 'qlkv_user_code']
        df_documents_data = df_documents_data.sort_values(by=['shop_code', 'created_date', 'loan_code'],ascending=[True, True, True] ) # Sắp xếp tăng dần (Ascending)
    
        # EXTRACT DIMMENTION DATA TO RETRIVE EACH ID IN DATABASE
        data_reference_data = {}
        for key, query in queries.items():
            df = get_df_from_postgres_db(engine, query)
            data_reference_data[key] = df
        # Bắt đầu tạo df 
        df_documents_merged_reference = df_documents_data.copy()
        df_documents_merged_reference['manager_code'] = df_documents_merged_reference['qlv_user_code']+df_documents_merged_reference['qlkv_user_code']
        # Chình lại trạng thái của các cột để merge được với nhau
        df_documents_merged_reference['shop_code'] = df_documents_merged_reference['shop_code'].astype(str)
        data_reference_data['shops']['shop_code'] = data_reference_data['shops']['shop_code'].astype(str)
        df_documents_merged_reference['folder_type_code'] = df_documents_merged_reference['folder_type_code'].astype('int64')
        data_reference_data['folder_types']['folder_type_code'] = data_reference_data['folder_types']['folder_type_code'].astype('int64')
        data_reference_data['shops']['shop_id'] = data_reference_data['shops']['shop_id'].astype('int64')
        data_reference_data['business_types']['business_type_id'] = data_reference_data['business_types']['business_type_id'].astype('int64')
    
        # Tiến hành merge để lấy các ID 
        df_documents_merged_reference = df_documents_merged_reference.merge(data_reference_data['regions'], left_on='region', right_on='region_name', how='left')
        df_documents_merged_reference = df_documents_merged_reference.merge(data_reference_data['managers'], left_on='manager_code', right_on='manager_code', how='left')
        df_documents_merged_reference = df_documents_merged_reference.merge(data_reference_data['shops'], left_on='shop_code', right_on='shop_code', how='left')
        df_documents_merged_reference = df_documents_merged_reference.merge(data_reference_data['folder_types'], left_on='folder_type_code', right_on='folder_type_code', how='left')
        # -- Khi merge business_type thì có điều kiện nếu cột need_actio_code = false thì merge bình thường còn lại n
        # ếu true sẽ phải merge 2 cột action_code và business_type_name
        df_documents_merged_reference['action_code'] = df_documents_merged_reference['action_code'].str.strip()
        # Chuẩn hóa cột action_code
        df_documents_merged_reference['action_code'] = df_documents_merged_reference['action_code'].astype(str).str.strip().str.upper()
        df_documents_merged_reference['business_type'] = df_documents_merged_reference['business_type'].astype(str).str.strip()
        business_types = data_reference_data['business_types']
        # Chuẩn hóa cột action_code và business_type_name
        df_documents_merged_reference['action_code'] = df_documents_merged_reference['action_code'].astype(str).str.strip().str.upper()
        df_documents_merged_reference['business_type'] = df_documents_merged_reference['business_type'].astype(str).str.strip()
        business_types['action_code'] = business_types['action_code'].astype(str).str.strip().str.upper()
        business_types['business_type_name'] = business_types['business_type_name'].astype(str).str.strip()
        # Chuẩn hóa business_type theo yêu cầu 
        df = df_documents_merged_reference.copy()
        bt = data_reference_data['business_types'].copy()
        df['business_type'] = df['business_type'].str.strip()
        df['action_code'] = df['action_code'].astype(str).str.strip().str.upper()
        bt['business_type_name'] = bt['business_type_name'].str.strip()
        bt['action_code'] = bt['action_code'].astype(str).str.strip().str.upper()
        # Tách bảng ref
        bt_true = bt[bt['need_action_code'] == True].copy()
        bt_false = bt[bt['need_action_code'] == False].copy()
        # ===== Step 1: merge theo business_type + action_code (ưu tiên) =====
        df_true_merged = df.merge(
            bt_true,
            left_on=['business_type', 'action_code'],
            right_on=['business_type_name', 'action_code'],
            how='inner',
            suffixes=('', '_bt_true')
        )
        # ===== Step 2: loại bỏ các dòng đã match =====
        # Cần xác định dòng duy nhất → dùng index
        df_true_matched_keys = df_true_merged[['business_type', 'action_code']].drop_duplicates()
        df_remaining = df.merge(df_true_matched_keys, on=['business_type', 'action_code'], how='left', indicator=True)
        df_remaining = df_remaining[df_remaining['_merge'] == 'left_only'].drop(columns=['_merge'])
        # ===== Step 3: merge phần còn lại theo business_type =====
        df_false_merged = df_remaining.merge(
            bt_false,
            left_on='business_type',
            right_on='business_type_name',
            how='left',
            suffixes=('', '_bt_false')
        )
        # ===== Step 4: gộp kết quả =====
        df_merged_final = pd.concat([df_true_merged, df_false_merged], ignore_index=True)
        # Data để đi tiếp
        df_documents_merged_reference  = df_merged_final
        # --- Maintain employee ---
        df_employee = df_documents_merged_reference[['employee_code', 'employee_name']].copy()
        df_employee['employee_code'] = df_employee['employee_code'].str.strip()
        df_employee = df_employee.drop_duplicates(subset=['employee_code'], keep='first').dropna(subset=['employee_code'])
        # Tạo nhân viên
        df_employee_id = insert_and_get_employee(engine, df_employee)
        #--- Chuyển đổi employee_id về kiểu Int64 --- 
        df_employee_id['employee_id'] = df_employee_id['employee_id'].astype('Int64')
        # --- Sau khi đã insert employee và merge employee vào ----
        df_documents_merged_reference = df_documents_merged_reference.merge(df_employee_id, on='employee_code', how='left') 
    
        # --- Maintain customer ---
        df_customer = df_documents_merged_reference[['customer_code', 'customer_name']].copy()
        df_customer['customer_code'] = df_customer['customer_code'].str.strip()
        df_customer = df_customer.drop_duplicates(subset=['customer_code'], keep='first').dropna(subset=['customer_code'])
        # Tạo khách hàng
        df_customer_id = insert_and_get_customer(engine, df_customer)
        #--- Chuyển đổi customer_id về kiểu Int64 ---
        df_customer_id['customer_id'] = df_customer_id['customer_id'].astype('Int64')
        # --- Sau khi đã insert customer và merge customer vào  ----
        df_documents_merged_reference = df_documents_merged_reference.merge(df_customer_id, on='customer_code', how='left')
    
        # --- Maintain contract ---
        df_contract = df_documents_merged_reference[['contract_code', 'customer_id', 'employee_id']].copy()
        df_contract = df_contract.drop_duplicates(subset=['contract_code'], keep='first').dropna(subset=['contract_code'])
        # Cho phép customer_id và employee_id là null do model cho phép
        insert_query_contract = text("""
            INSERT INTO "d_ContractDetail" (contract_code, customer_id, employee_id)
            VALUES (:contract_code, :customer_id, :employee_id)
            ON CONFLICT (contract_code) DO NOTHING;
        """)
        with engine.begin() as conn:
            for _, row in df_contract.iterrows():
                conn.execute(insert_query_contract, {
                    "contract_code": row['contract_code'],
                    "customer_id": None if pd.isna(row['customer_id']) else int(row['customer_id']),
                    "employee_id": None if pd.isna(row['employee_id']) else int(row['employee_id'])
                })
        # --- Lấy contract_id từ contract_code sau khi insert ---
        contract_codes = df_documents_merged_reference['contract_code'].dropna().unique().tolist()
        df_contract_id = pd.DataFrame(columns=['contract_id', 'contract_code'])
        if contract_codes:
            for i in range(0, len(contract_codes), 1000):
                chunk = contract_codes[i:i+1000]
                placeholders = ','.join([f"'{x}'" for x in chunk])
                select_query = f'SELECT contract_id, contract_code FROM "d_ContractDetail" WHERE contract_code IN ({placeholders})'
                df_chunk = get_df_from_postgres_db(engine, select_query)
                df_contract_id = pd.concat([df_contract_id, df_chunk], ignore_index=True)
        # Nếu không có dữ liệu thì vẫn merge vào để tránh lỗi
    
        df_contract_id['contract_id'] = df_contract_id['contract_id'].astype('Int64')
        # --- Sau khi đã Merged contract ----
        df_documents_merged_reference = df_documents_merged_reference.merge(df_contract_id, on='contract_code', how='left')
        
        # --- Maintain loan ---
        df_loan = df_documents_merged_reference[[
            'loan_code', 'customer_id', 'employee_id',
            'customer_code', 'customer_name', 'employee_code', 'employee_name'
        ]].copy()
        df_loan = df_loan.drop_duplicates(subset=['loan_code'], keep='first').dropna(subset=['loan_code'])
        insert_query_loan = text("""
            INSERT INTO "d_LoanDetail" (
                loan_code, customer_id, employee_id,
                customer_code, customer_name, employee_code, employee_name
            )
            VALUES (
                :loan_code, :customer_id, :employee_id,
                :customer_code, :customer_name, :employee_code, :employee_name
            )
            ON CONFLICT (loan_code) DO NOTHING;
        """)
        with engine.begin() as conn:
            for _, row in df_loan.iterrows():
                conn.execute(insert_query_loan, {
                    "loan_code": row['loan_code'],
                    "customer_id": None if pd.isna(row['customer_id']) else int(row['customer_id']),
                    "employee_id": None if pd.isna(row['employee_id']) else int(row['employee_id']),
                    "customer_code": row['customer_code'],
                    "customer_name": row['customer_name'],
                    "employee_code": row['employee_code'],
                    "employee_name": row['employee_name']
                })
        # --- Lấy loan_id từ loan_code sau khi insert ---
        loan_codes = df_documents_merged_reference['loan_code'].dropna().unique().tolist()
        df_loan_id = pd.DataFrame()
        if loan_codes:
            for i in range(0, len(loan_codes), 1000):
                chunk = loan_codes[i:i+1000]
                placeholders = ','.join([f"'{x}'" for x in chunk])
                select_query = f'SELECT loan_id, loan_code FROM "d_LoanDetail" WHERE loan_code IN ({placeholders})'
                df_chunk = get_df_from_postgres_db(engine, select_query)
                df_loan_id = pd.concat([df_loan_id, df_chunk], ignore_index=True)
    
        # --- Chuyển đổi loan_id về kiểu Int64 ---
        # Hadle case df_loan_id is empty
        if not df_loan_id.empty:
            df_loan_id['loan_id'] = df_loan_id['loan_id'].astype('Int64')
            # --- Sau khi đã Merged loan ----
            df_documents_merged_reference = df_documents_merged_reference.merge(df_loan_id, on='loan_code', how='left')
            # Lưu các dòng shop_id, folder_type_id, manager_id, region_id ra excel 
            # Nếu có dữ liệu null thì xuất ra file để kiểm tra
        save_null_records(df_documents_merged_reference, single_date.strftime('%Y-%m-%d'), null_output_dir)
        
        # Chỗ này drop đi các giá trị null để tránh bị lỗi khi insert vào database
        df_documents_merged_reference = df_documents_merged_reference.dropna(subset=['shop_id'])
        df_documents_merged_reference = df_documents_merged_reference.dropna(subset=['folder_type_id'])
        # df_documents_merged_reference = df_documents_merged_reference.dropna(subset=['business_type_id'])
        df_documents_merged_reference = df_documents_merged_reference.dropna(subset=['manager_id'])
        df_documents_merged_reference = df_documents_merged_reference.dropna(subset=['region_id'])
    
        # Nếu phát hiện có null ở shop_id thì báo ngay cho team.
        if len(df_documents_merged_reference[df_documents_merged_reference['shop_id'].isnull()]) > 0:
            logger.error(
                "[ERROR] Có %s giá trị null trong cột shop_id. Vui lòng kiểm tra lại dữ liệu.",
                len(df_documents_merged_reference[df_documents_merged_reference['shop_id'].isnull()])
            )
        # # Nếu phát hiện có null ở nghiệp vụ business_type thì báo ngay cho team.
        # if  len(df_documents_merged_reference [df_documents_merged_reference['business_type_id'].isnull()] ) >0: 
        #     print(f"[ERROR] Có {len(df_documents_merged_reference [df_documents_merged_reference['business_type_id'].isnull()] )} giá trị null trong cột business_type_id. Vui lòng kiểm tra lại dữ liệu.")
        # Nếu phát hiện có null ở managers thì báo ngay cho team.
        if len(df_documents_merged_reference[df_documents_merged_reference['manager_id'].isnull()]) > 0:
            logger.error(
                "[ERROR] Có %s giá trị null trong cột manager_id. Vui lòng kiểm tra lại dữ liệu.",
                len(df_documents_merged_reference[df_documents_merged_reference['manager_id'].isnull()])
            )
        # Nêu phát hiện có null ở folder_type_id thì báo ngay cho team.
        if len(df_documents_merged_reference[df_documents_merged_reference['folder_type_id'].isnull()]) > 0:
            logger.error(
                "[ERROR] Có %s giá trị null trong cột folder_type_id. Vui lòng kiểm tra lại dữ liệu.",
                len(df_documents_merged_reference[df_documents_merged_reference['folder_type_id'].isnull()])
            )
        # Nếu phát hiện có null ở region_id thì báo ngay cho team.
        if len(df_documents_merged_reference[df_documents_merged_reference['region_id'].isnull()]) > 0:
            logger.error(
                "[ERROR] Có %s giá trị null trong cột region_id. Vui lòng kiểm tra lại dữ liệu.",
                len(df_documents_merged_reference[df_documents_merged_reference['region_id'].isnull()])
            )
        else:
            # Biến đổi dữ liệu về Int64 
            df_documents_merged_reference['shop_id'] = df_documents_merged_reference['shop_id'].astype('Int64')
            df_documents_merged_reference['folder_type_id'] = df_documents_merged_reference['folder_type_id'].astype('Int64')
            df_documents_merged_reference['business_type_id'] = df_documents_merged_reference['business_type_id'].astype('Int64')
            df_documents_merged_reference['manager_id'] = df_documents_merged_reference['manager_id'].astype('Int64')
            df_documents_merged_reference['region_id'] = df_documents_merged_reference['region_id'].astype('Int64')
    
        #--- Tách các giá trị trong cột 'doc_grp' thành danh sách ---
        df_documents_merged_reference['doc_grp'] = df_documents_merged_reference['doc_grp'].str.split(', ')
        # --- Sau đó mở rộng các giá trị trong danh sách thành nhiều dòng ---
        df_documents_merged_reference = df_documents_merged_reference.explode('doc_grp')
        # --- Sau đó merge với bảng d_DocumentType để lấy document_type_id ---
        df_documents_merged_reference = df_documents_merged_reference.merge(data_reference_data['document_types'], left_on='doc_grp', right_on='document_type_name', how='left') 
        #--- Chuyển đổi document_type_id về kiểu Int64 ---
        df_documents_merged_reference['document_type_id'] = df_documents_merged_reference['document_type_id'].astype('Int64')
        # --- Sau khi đã Merged document_type_id ---- 
        df_documents_merged_reference = df_documents_merged_reference.dropna(subset=['document_type_id'])
        # --- Nếu phát hiện có null ở document_type_id thì báo ngay cho team.
        if len(df_documents_merged_reference[df_documents_merged_reference['document_type_id'].isnull()]) > 0:
            logger.error(
                "[ERROR] Có %s giá trị null trong cột document_type_id. Vui lòng kiểm tra lại dữ liệu.",
                len(df_documents_merged_reference[df_documents_merged_reference['document_type_id'].isnull()])
            )
        # --- Công thức điều chỉnh document_parent_code : Mã quyển cha + mã chứng từ cha + business_type_id ---
        df_documents_merged_reference['parent_document_code'] = (
            df_documents_merged_reference['parent_folder_code'] + 
            df_documents_merged_reference['parent_document_code']+ 
            df_documents_merged_reference['business_type_id'].astype('str')+ 
            df_documents_merged_reference['document_type_id'].astype('str') 
            )
        
        # FOLDER
        # Mục đích của đoạn này là để lấy được các thông tin cần thiết cho việc tạo folder
        df_folder_data = df_documents_merged_reference 
    
        df_folder_data = df_folder_data.groupby([
            'created_year', 'created_month', 'created_day', 'parent_folder_code',
            'shop_code', 'folder_type_code', 'folder_code', 'created_date',
            'shop_id', 'folder_type_id', 'region_id', 'manager_id'
        ]).size().reset_index(name='is_issue')
    
        df_folder_data['is_issue'] = True
        df_folder_data['is_original'] = True
    
        # Tính khoảng thời gian cần sinh quyển ảo
        # Neu df_folder_data['created_date'].min() hoac max() la NaT thi se bi loi khi sinh date_range 
        # Giai phap la lay min cua date range input
        
        min_date = df_folder_data['created_date'].min()  
        max_date = df_folder_data['created_date'].max()
        # Nếu df_folder_data rỗng thì không cần sinh dates, tránh lỗi NaT
        if pd.isna(min_date) or pd.isna(max_date):
            # min_date  = start_date start_date
            # max_date = input_
            dates = pd.date_range(start=start_date, end=end_date)
        else:
            dates = pd.date_range(start=min_date, end=max_date)
    
        # Danh sách để chứa các dòng cần sinh
        new_rows_list = []
        folder_type_code_list = [1, 2]
    
        # Duyệt qua từng shop_id duy nhất
        for shop_id in df_folder_data['shop_id'].unique():
            for folder_type_code in folder_type_code_list:
                # Lấy dữ liệu mẫu cho shop_id, folder_type_id nếu có
                filtered = df_folder_data[ 
                        (df_folder_data['shop_id'] == shop_id) &
                        (df_folder_data['folder_type_code'] == folder_type_code)] 
                
                if not filtered.empty:
                    shop_data = filtered.iloc[0]
                else:
                    # Fallback từ shop_id bất kỳ và gán folder_type_id tương ứng
                    fallback = df_folder_data[df_folder_data['shop_id'] == shop_id].iloc[0]
                    shop_data = fallback.copy()
                    
                    shop_data['folder_type_code'] = folder_type_code
                for date in dates:
                    
                    exists = (
                        (df_folder_data['shop_id'] == shop_id) &
                        (df_folder_data['folder_type_code'] == folder_type_code) &
                        (df_folder_data['created_date'] == date.strftime('%Y-%m-%d'))
                    ).any()
    
                    if not exists:
                        new_row = {
                            'created_date': date.strftime('%Y-%m-%d'),
                            'created_year': date.year,
                            'created_month': str(date.month).zfill(2),
                            'created_day': str(date.day).zfill(2),
                            'is_issue': False,
                            'is_original': True,
                            'region_id': shop_data['region_id'],
                            'folder_type_code': folder_type_code,
                            'manager_id': shop_data['manager_id'],
                            'shop_id': shop_id,
                            'folder_code': str(date.year) + str(date.month).zfill(2) + str(date.day).zfill(2) + str(shop_data['shop_code']) + str(shop_data['folder_type_code'])
                        }
                        new_rows_list.append(new_row)
    
        # Tạo DataFrame mới và gộp lại
        df_new_rows = pd.DataFrame(new_rows_list)
        
        if len(new_rows_list) == 0:
            df_folder_combined = df_folder_data
        else:
            df_new_rows = df_new_rows.merge(data_reference_data['folder_types'], left_on='folder_type_code', right_on='folder_type_code', how='left') 
            df_folder_combined = pd.concat([df_folder_data, df_new_rows], ignore_index=True)
    
        # Sắp xếp dữ liệu sau khi gộp
        df_folder_combined = df_folder_combined.sort_values(by=['created_date', 'shop_id', 'folder_type_id']).reset_index(drop=True)
        # df_folder_data = df_documents_merged_reference 
    
        def find_group_id(created_day):
            matching_group = data_reference_data['folder_group'][
                ( data_reference_data['folder_group']['day_from'] <= int(created_day)) &
                ( data_reference_data['folder_group']['day_to'] >= int(created_day))
            ]
            if not matching_group.empty:
                return matching_group.iloc[0]['group_id'], False
            return None,True
        # Áp dụng hàm find_group_id và unpack kết quả trả về thành hai cột riêng biệt
        df_folder_combined[['group_id', 'is_out_of_group']] = df_folder_combined['created_day'].apply(lambda x: pd.Series(find_group_id(x)))
        df_folder_final = df_folder_combined[['folder_code','created_date','shop_id','folder_type_id', 'manager_id', 'is_original', 'is_issue','group_id','is_out_of_group']]  
        df_folder_final_inserted = df_folder_final
        folder_inserted_data = insert_folders_with_return(engine, df_folder_final_inserted)
        df_folder_id = pd.DataFrame(folder_inserted_data, columns=['folder_id', 'folder_code'])
        df_documents_merged_reference = df_documents_merged_reference.merge(df_folder_id, on='folder_code', how='left')
        # --- Chuẩn bị dữ liệu documents và insert ---
        df_document_detail_final = df_documents_merged_reference[[  
            'parent_document_code', 'document_type_id', 'shop_id', 'loan_id', 'contract_id', 'created_date', 'folder_id', 'business_type_id', 'manager_id',
            'business_type_name', 'document_type_name', 'action_code'
        ]].copy()
        # Chuyển định dạng của parent_document_code về kiểu text
        df_document_detail_final['parent_document_code'] = df_document_detail_final['parent_document_code'].astype(str)
    
        # --- Insert documents vào database ---
        insert_documents(engine, df_document_detail_final) 
        logger.info("[✅] Đã xử lý xong ngày %s", single_date.strftime('%Y-%m-%d'))
        
        folder_inserted_count = len(df_folder_id)
        document_inserted_count = len(df_document_detail_final)
        # Ghi log theo ngày xử lý
        log_insert_summary(single_date.strftime('%Y-%m-%d'), folder_inserted_count, document_inserted_count)
        # Gọi lưu log cuối cùng sau vòng lặp theo ngay
        summary_path = summary_output_dir / f"insert_log_summary_{single_date.strftime('%Y%m%d')}.xlsx"
        save_insert_log(summary_path)


def parse_args():
    parser = argparse.ArgumentParser(description="Maintain document and folder data.")
    parser.add_argument("--credentials", required=True, help="Path to credential YAML file.")
    parser.add_argument("--pg-conn", default="connectionDocumentationProd", help="Postgres connection key in credential file.")
    parser.add_argument("--oracle-conn", default="connectionf88dwh", help="Oracle connection key in credential file.")
    parser.add_argument("--start-date", required=True, help="Start date (YYYY-MM-DD).")
    parser.add_argument("--end-date", required=True, help="End date (YYYY-MM-DD).")
    parser.add_argument("--null-output-dir", default="tmp/null_records", help="Directory to store null record reports.")
    parser.add_argument("--summary-output-dir", default="tmp/insert_logs", help="Directory to store insert summaries.")
    parser.add_argument("--log-level", default="INFO", help="Logging level (INFO, DEBUG, ...).")
    return parser.parse_args()


def main():
    args = parse_args()
    logging.basicConfig(level=getattr(logging, args.log_level.upper(), logging.INFO), format="%(asctime)s %(levelname)s %(message)s")

    credentials = open_yaml_file(args.credentials)
    pg_engine = postgres_create_connection(credentials, args.pg_conn)
    oracle_cfg = credentials[args.oracle_conn]
    oracle_dsn = oracle_cfg.get('dns')
    if not oracle_dsn:
        oracle_dsn = f"{oracle_cfg['host']}:{oracle_cfg['port']}/{oracle_cfg['sid']}"

    start_date = datetime.strptime(args.start_date, "%Y-%m-%d")
    end_date = datetime.strptime(args.end_date, "%Y-%m-%d")

    run_job(
        start_date=start_date,
        end_date=end_date,
        engine=pg_engine,
        oracle_user=oracle_cfg['user'],
        oracle_password=oracle_cfg['pass'],
        oracle_dsn=oracle_dsn,
        null_output_dir=Path(args.null_output_dir),
        summary_output_dir=Path(args.summary_output_dir),
    )


if __name__ == "__main__":
    main()
