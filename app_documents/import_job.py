# Cấu hình kết nối đến PostgreSQL
dbname='documentation'
user='vhadmin'
password='Pvh12345678@F88vn'
host='192.168.10.89'#'139-162-63-52.ip.linodeusercontent.com'
port='5432'

import pandas as pd
import psycopg2
from psycopg2 import sql
class ImportJobFolder():
    def reset_tempfolder_table (cursor):
        try:
            # Xóa dữ liệu trong bảng TempFolder
            cursor.execute("DELETE FROM app_documents_tempfolder")
            # Reset lại sequence của bảng TempFolder
            cursor.execute("ALTER SEQUENCE app_documents_tempfolder_id_seq RESTART WITH 1")
            print("Dữ liệu trong bảng TempFolder đã được xóa và sequence đã được reset.")
        except Exception as e:
            print(f"Có lỗi xảy ra khi xóa dữ liệu và reset sequence: {e}")
    def load_reference_data_for_folders(cursor):
        # Fetch data từ database và trả về dưới dạng DataFrame
        queries = {
            "regions": "SELECT region_name, region_id, region_code FROM \"d_Region\"",
            "managers": "SELECT manager_code, manager_id FROM \"d_Manager\"",
            "shops": "SELECT shop_code, shop_id FROM \"d_Shops\"",
            "folder_types": "SELECT folder_type_code, folder_type_id FROM \"d_FolderType\""
        }
        data = {}
        for key, query in queries.items():
            cursor.execute(query)
            data[key] = pd.DataFrame(cursor.fetchall(), columns=[col.name for col in cursor.description])
        return data
    # Hàm chuyển dữ liệu từ DataFrame vào bảng TempFolder
    def folder_temp(folder_df, dbname, user, password, host, port): 
        # Cấu hình kết nối đến PostgreSQL
        conn = psycopg2.connect(
            dbname=dbname,
            user=user,
            password=password,
            host=host,
            port=port
        )
        try:
            with conn.cursor() as cursor:
                # Tải dữ liệu tham chiếu
                reference_data = ImportJobFolder.load_reference_data_for_folders(cursor)

                # Tạo cột manager_code từ QLV_USER_CODE và QLKV_USER_CODE
                folder_df['manager_code'] = folder_df['QLV_USER_CODE'].astype(str) + folder_df['QLKV_USER_CODE'].astype(str)
                reference_data['folder_types']['folder_type_code'] = reference_data['folder_types']['folder_type_code'].astype(str)
                folder_df['FOLDER_TYPE_CODE'] = folder_df['FOLDER_TYPE_CODE'].astype(str)
                # Merge dữ liệu từ DataFrame với các DataFrame tham chiếu để lấy các id cần thiết
                folder_df = folder_df.merge(reference_data['regions'], left_on='REGION', right_on='region_name', how='left')
                folder_df = folder_df.merge(reference_data['managers'], left_on='manager_code', right_on='manager_code', how='left')
                folder_df = folder_df.merge(reference_data['shops'], left_on='SHOP_CODE', right_on='shop_code', how='left')
                folder_df = folder_df.merge(reference_data['folder_types'], left_on='FOLDER_TYPE_CODE', right_on='folder_type_code', how='left')

                 # Kiểm tra và đánh dấu lỗi
                folder_df['is_error'] = folder_df[['region_id', 'manager_id', 'shop_id', 'folder_type_id']].isnull().any(axis=1)
                folder_df['error_list'] = folder_df.apply(lambda row: ', '.join(
                    [col for col in ['region_id', 'manager_id', 'shop_id', 'folder_type_id'] if pd.isnull(row[col])]
                ), axis=1)

                # Chuẩn bị dữ liệu để chèn
                data_to_insert = [
                    (row['shop_id'], row['SHOP_CODE'], row['SHOP_NAME'], row['REGION'], row['region_code'], row['region_id'], 
                    row['QLKV_USER_CODE'], row['QLKV'], row['QLV_USER_CODE'], row['QLV'], row['manager_id'], row['folder_type_id'], row['FOLDER_TYPE_CODE'], 
                    pd.Timestamp(year=int(row['YEAR_NUM']), month=int(row['MONTH_NUM']), day=int(row['DATE_NUM'])), row['FOLDER_CODE'], 
                    True, pd.notnull(row['ISREAL']), 1, row['is_error'], row['error_list'])
                    for index, row in folder_df.iterrows()
                ]
                # # Reset temp tables and sequences
                ImportJobFolder.reset_tempfolder_table(cursor)
                # Thực thi truy vấn SQL để chèn dữ liệu vào bảng TempFolder
                insert_query = sql.SQL("""
                    INSERT INTO "app_documents_tempfolder" 
                    (shop_id, shop_code, shop_name, region_name, region_code, region_id, qlkv_user_code, qlkv_name, qlv_user_code, qlv_name, 
                    manager_id, folder_type_id, folder_type_code, folder_create_date, folder_code, is_original, is_issue, user_id, is_error, error_list)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """)
                cursor.executemany(insert_query, data_to_insert)
                conn.commit()
                print("Dữ liệu đã được chèn thành công vào cơ sở dữ liệu.")
        except Exception as e:
            conn.rollback()
            print(f"Có lỗi xảy ra: {e}")
        finally:
            conn.close()
   
    @staticmethod
    def transfer_data_to_main_table(dbname, user, password, host, port):
        # Cấu hình kết nối đến PostgreSQL
        conn = psycopg2.connect(
            dbname=dbname,
            user=user,
            password=password,
            host=host,
            port=port
        )
        try:
            with conn.cursor() as cursor:
                # Lấy dữ liệu từ bảng tạm
                cursor.execute("SELECT * FROM app_documents_tempfolder WHERE is_error = FALSE")
                temp_data = cursor.fetchall()
                col_names = [desc[0] for desc in cursor.description]

                # Chuyển đổi dữ liệu thành DataFrame để dễ dàng thao tác
                temp_df = pd.DataFrame(temp_data, columns=col_names)

                # Chuẩn bị câu lệnh SQL để chèn dữ liệu vào bảng chính
                insert_query = sql.SQL("""
                    INSERT INTO "f_FolderDetail" 
                    (folder_code, shop_id, folder_type_id, folder_status_id, manager_id, folder_created_date, 
                    note, package_id, lastest_received_date, lastest_received_by, is_original, is_issue, row_created_date)
                    VALUES (%s, %s, %s, 1, %s, %s, NULL, NULL, NULL, NULL, %s, %s, NOW())
                """)

                # Chèn dữ liệu từ bảng tạm vào bảng chính
                data_to_insert = [
                    (row['folder_code'], row['shop_id'], row['folder_type_id'], row['manager_id'], 
                        row['folder_create_date'], row['is_original'], row['is_issue'])
                    for index, row in temp_df.iterrows()
                ]

                cursor.executemany(insert_query, data_to_insert)
                conn.commit()
                print("Dữ liệu đã được chuyển thành công từ bảng tạm vào bảng chính.")
        except Exception as e:
            conn.rollback()
            print(f"Có lỗi xảy ra: {e}")
        finally:
            conn.close()
# Đọc file Excel cho folder
excel_file_mba = r"C:\Users\DAT NGUYEN\OneDrive - CONG TY CO PHAN KINH DOANH F88\Documents - phongvanhanh\1.Data PVH\3.Báo cáo\2.Báo cáo PVH\9.Kiểm duyệt chứng từ\2.Chứng từ bản cứng\3.Setup\2.PVH-CTV\Receiving\Miền Bắc\2024-08\CTV_Miền Bắc_Receive 2024-08_01.xlsx"
excel_file_mna = r"C:\Users\DAT NGUYEN\OneDrive - CONG TY CO PHAN KINH DOANH F88\Documents - phongvanhanh\1.Data PVH\3.Báo cáo\2.Báo cáo PVH\9.Kiểm duyệt chứng từ\2.Chứng từ bản cứng\3.Setup\2.PVH-CTV\Receiving\Miền Nam\2024-08\CTV_Miền Nam_Receive 2024-08_01.xlsx"
folder_mba_df = pd.read_excel(excel_file_mba, sheet_name='MainData-Receive', skiprows=1)
folder_mna_df = pd.read_excel(excel_file_mna, sheet_name='MainData-Receive', skiprows=1)
folder_df = pd.concat([folder_mba_df, folder_mna_df], ignore_index=True)

# # # Gọi hàm với dữ liệu đã đọc cho folder_temp
ImportJobFolder.folder_temp(folder_df,dbname, user, password, host, port)
# #ImportJobFolder.transfer_data_to_main_table(dbname, user, password, host, port)

class ImportJobDocument:

    @staticmethod
    def load_reference_data_for_documents(cursor):
        # Fetch data từ database và trả về dưới dạng DataFrame
        queries = {
            "regions": "SELECT region_name, region_id FROM \"d_Region\"",
            "managers": "SELECT manager_code, manager_id FROM \"d_Manager\"",
            "shops": "SELECT shop_code, shop_id, shop_name FROM \"d_Shops\"",
            "business_types": "SELECT business_type_name, business_type_id FROM \"d_BusinessType\"",
            "document_types": "SELECT document_type_name, document_type_id FROM \"d_DocumentType\"",
            "folders": "SELECT folder_code, folder_id FROM \"f_FolderDetail\"",
            "loans": "SELECT loan_code, loan_id FROM \"d_LoanDetail\""
        }
        data = {}
        for key, query in queries.items():
            cursor.execute(query)
            data[key] = pd.DataFrame(cursor.fetchall(), columns=[col.name for col in cursor.description])
        print( 'Load data success')
        return data

    @staticmethod
    def reset_temp_tables(cursor):
        try:
            # Xóa dữ liệu trong bảng TempDocument
            cursor.execute("DELETE FROM app_documents_tempdocument")
            # Reset lại sequence của bảng TempDocument
            cursor.execute("ALTER SEQUENCE app_documents_tempdocument_id_seq RESTART WITH 1")
            print("Dữ liệu trong bảng TempDocument đã được xóa và sequence đã được reset.")
        except Exception as e:
            print(f"Có lỗi xảy ra khi xóa dữ liệu và reset sequence: {e}")

    @staticmethod
    def documents_temp(document_df, dbname, user, password, host, port):
        # Cấu hình kết nối đến PostgreSQL
        conn = psycopg2.connect(
            dbname=dbname,
            user=user,
            password=password,
            host=host,
            port=port
        )
        try:
            with conn.cursor() as cursor:
                # Tải dữ liệu tham chiếu
                reference_data = ImportJobDocument.load_reference_data_for_documents(cursor)
                
                # Tạo cột manager_code từ QLV_USER_CODE và QLKV_USER_CODE
                document_df['manager_code'] = document_df['QLV_USER_CODE'].astype(str) + document_df['QLKV_USER_CODE'].astype(str)
                document_df['FOLDER_CODE'] = document_df['FOLDER_CODE'].astype(str)
                document_df['LOAN_CODE'] = document_df['LOAN_CODE'].astype(str)
                
                # Merge dữ liệu từ DataFrame với các DataFrame tham chiếu để lấy các id cần thiết
                document_df = document_df.merge(reference_data['regions'], left_on='REGION', right_on='region_name', how='left')
                document_df = document_df.merge(reference_data['managers'], left_on='manager_code', right_on='manager_code', how='left')
                document_df = document_df.merge(reference_data['shops'], left_on='SHOP_CODE', right_on='shop_code', how='left')
                document_df = document_df.merge(reference_data['business_types'], left_on='BUSINESS_TYPE', right_on='business_type_name', how='left')
                document_df = document_df.merge(reference_data['document_types'], left_on='DOCUMENT_TYPE', right_on='document_type_name', how='left')
                document_df = document_df.merge(reference_data['folders'], left_on='FOLDER_CODE', right_on='folder_code', how='left')
                print('Merge success')
                # Kiểm tra sự tồn tại của loan_code và tạo mới nếu cần
                new_loans = []
                for index, row in document_df.iterrows():
                    if row['LOAN_CODE'] not in reference_data['loans']['loan_code'].values:
                        new_loans.append((row['LOAN_CODE'], row['EMPLOYEE_CODE'], row['EMPLOYEE_NAME'], row['CUSTOMER_CODE'], row['CUSTOMER_NAME']))
                        new_loan_entry = pd.DataFrame({'loan_code': [row['LOAN_CODE']], 'loan_id': [None]})
                        reference_data['loans'] = pd.concat([reference_data['loans'], new_loan_entry], ignore_index=True)
                print('find loan success')
                
                if new_loans:
                    for loan in new_loans:
                        loan_insert_query = sql.SQL("""
                            INSERT INTO "d_LoanDetail" (loan_code, employee_code, employee_name, customer_code, customer_name)
                            VALUES (%s, %s, %s, %s, %s)
                            ON CONFLICT (loan_code) DO NOTHING
                            RETURNING loan_code, loan_id
                        """)
                        cursor.execute(loan_insert_query, loan)
                        loan_code, loan_id = cursor.fetchone()
                        reference_data['loans'].loc[reference_data['loans']['loan_code'] == loan_code, 'loan_id'] = loan_id
                        
                print('create new loan success')
                # Merge để lấy loan_id
                document_df = document_df.merge(reference_data['loans'], left_on='LOAN_CODE', right_on='loan_code', how='left')
                
                # Kiểm tra và đánh dấu lỗi
                document_df['is_error'] = document_df[['region_id', 'manager_id', 'shop_id', 'business_type_id', 'document_type_id', 'folder_id', 'loan_id']].isnull().any(axis=1)
                document_df['error_list'] = document_df.apply(lambda row: ', '.join(
                    [col for col in ['region_id', 'manager_id', 'shop_id', 'business_type_id', 'document_type_id', 'folder_id', 'loan_id'] if pd.isnull(row[col])]
                ), axis=1)

                # Chuẩn bị dữ liệu để chèn
                data_to_insert = [
                    (str(row['DOCUMENTS_CODE']), row['DOCUMENTS_CREATED_DATE'], row['document_type_id'], row['manager_id'], row['business_type_id'], 
                    row['QLKV'], row['QLV'], row['QLKV_USER_CODE'], row['QLV_USER_CODE'], row['loan_id'], row['LOAN_CODE'], row['EMPLOYEE_CODE'], 
                    row['EMPLOYEE_NAME'], row['CUSTOMER_CODE'], row['CUSTOMER_NAME'], row['shop_id'], row['shop_name'], 
                    row['region_id'], row['folder_id'], True, True, 1,  # Giả sử user_id là 1 cho ví dụ này
                    row['is_error'], row['error_list'])
                    for index, row in document_df.iterrows()
                ]

                # Reset temp tables and sequences
                # ImportJobDocument.reset_temp_tables(cursor)

                # Thực thi truy vấn SQL để chèn dữ liệu vào bảng TempDocument
                insert_query = sql.SQL("""
                    INSERT INTO "app_documents_tempdocument" 
                    (document_code, document_create_date, document_type_id, manager_id, business_type_id, qlkv_name, qlv_name, qlkv_user_code, qlv_user_code, 
                    loan_id, loan_code, employee_code, employee_name, customer_code, customer_name, shop_id, shop_name, region_id, 
                    folder_id, is_original, is_issue, user_id, is_error, error_list)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """)
                cursor.executemany(insert_query, data_to_insert)
                conn.commit()
                print("Dữ liệu đã được chèn thành công vào cơ sở dữ liệu.")
        except Exception as e:
            conn.rollback()
            print(f"Có lỗi xảy ra: {e}{row}")
        finally:
            conn.close()
            
    @staticmethod
    def transfer_data_to_main_table(dbname, user, password, host, port):
        # Cấu hình kết nối đến PostgreSQL
        conn = psycopg2.connect(
            dbname=dbname,
            user=user,
            password=password,
            host=host,
            port=port
        )
        try:
            with conn.cursor() as cursor:
                # Lấy dữ liệu từ bảng tạm
                cursor.execute("SELECT * FROM app_documents_tempdocument WHERE is_error = FALSE")
                temp_data = cursor.fetchall()
                col_names = [desc[0] for desc in cursor.description]

                # Chuyển đổi dữ liệu thành DataFrame để dễ dàng thao tác
                temp_df = pd.DataFrame(temp_data, columns=col_names)

                # Chuẩn bị câu lệnh SQL để chèn dữ liệu vào bảng chính
                insert_query = sql.SQL("""
                    INSERT INTO "f_DocumentsDetail" 
                    (documents_code, document_type_id, shop_id, loan_id, documents_created_date, folder_id, business_type_id, manager_id,
                    check_status_id, lastest_checked_date, lastest_checked_by, document_status_id, note, package_id)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, NULL, NULL, NULL, NULL, NULL, NULL)
                """)

                # Chèn dữ liệu từ bảng tạm vào bảng chính theo từng batch 1000 hàng
                batch_size = 1000
                total_batches = (len(temp_df) // batch_size) + (1 if len(temp_df) % batch_size != 0 else 0)
                for i in range(total_batches):
                    start = i * batch_size
                    batch = temp_df[start:start + batch_size]
                    data_to_insert = [
                        (row['document_code'], row['document_type_id'], row['shop_id'], row['loan_id'], row['document_create_date'], 
                         row['folder_id'], row['business_type_id'], row['manager_id'])
                        for index, row in batch.iterrows()
                    ]
                    cursor.executemany(insert_query, data_to_insert)
                    conn.commit()
                    print(f"Batch {i + 1}/{total_batches}: Đã chèn {len(batch)} hàng vào bảng chính.")

                    # Xóa các hàng đã xử lý từ bảng tạm
                    doc_codes = tuple(batch['document_code'].values)
                    delete_query = sql.SQL("DELETE FROM app_documents_tempdocument WHERE document_code IN %s")
                    cursor.execute(delete_query, (doc_codes,))
                    conn.commit()
                    print(f"Batch {i + 1}/{total_batches}: Đã xóa {len(batch)} hàng khỏi bảng tạm.")
                print("Dữ liệu đã được chuyển thành công từ bảng tạm vào bảng chính.")
        except Exception as e:
            conn.rollback()
            print(f"Có lỗi xảy ra: {e}{batch}")
        finally:
            conn.close()


# # Đọc file Excel
# excel_file_d_mna = r"C:\Users\DAT NGUYEN\OneDrive - CONG TY CO PHAN KINH DOANH F88\Documents - phongvanhanh\1.Data PVH\3.Báo cáo\2.Báo cáo PVH\9.Kiểm duyệt chứng từ\2.Chứng từ bản cứng\3.Setup\2.PVH-CTV\Checking\Miền Bắc\2024-07\CTV_Miền Bắc_Check 2024-07_02.xlsx"
# excel_file_d_mba =  r"C:\Users\DAT NGUYEN\OneDrive - CONG TY CO PHAN KINH DOANH F88\Documents - phongvanhanh\1.Data PVH\3.Báo cáo\2.Báo cáo PVH\9.Kiểm duyệt chứng từ\2.Chứng từ bản cứng\3.Setup\2.PVH-CTV\Checking\Miền Nam\2024-07\CTV_Miền Nam_Check 2024-07_02.xlsx"
# document_df_mna = pd.read_excel(excel_file_d_mna, sheet_name='MainData', skiprows=1)
# document_df_mba = pd.read_excel(excel_file_d_mba, sheet_name='MainData', skiprows=1)

# document_df = pd.concat([document_df_mna, document_df_mba], ignore_index=True)

# #document_df.to_csv( r"C:\Users\DAT NGUYEN\OneDrive - CONG TY CO PHAN KINH DOANH F88", sep="|" ,encoding='utf-8')
# # Gọi hàm với dữ liệu đã đọc
# ImportJobDocument.documents_temp(document_df, dbname, user, password, host, port)
# # ImportJobDocument.transfer_data_to_main_table(dbname, user, password, host, port)