# API nhận dữ liệu chứng từ từ Prefect

API này dành cho hệ thống làm sạch dữ liệu gọi vào production. Người dùng UI không dùng API này.

## An toàn và quy tắc vận hành

- Tạo token ở production một lần: `python manage.py generate_document_intake_token --name prefect-production --scope documents:write`.
- Lưu giá trị token vào **Prefect Secret** `DOCUMENT_INTAKE_TOKEN`; token thô không được lưu vào database, Git, log hoặc file `.env` cục bộ.
- Gọi bằng `Authorization: Bearer <token>` và HTTPS. Production cần giới hạn IP/VPN của worker Prefect ở reverse proxy/firewall.
- Batch có tính idempotent theo `batch_key`; chunk idempotent theo `(batch_key, chunk_no, nội dung)`. Có thể retry HTTP mà không sinh trùng.
- Mỗi chunk tối đa 1.000 record. Khuyến nghị 500–1.000 record/chunk, timeout 60 giây, retry exponential backoff.
- Không gửi dữ liệu trực tiếp vào bảng `f_DocumentsDetail`. API lưu staging, chỉ Celery xử lý sau `finalize`.

## Luồng chuẩn

1. Làm sạch và kiểm tra dữ liệu tại Prefect.
2. `POST /api/integrations/v1/batches/` để tạo batch ngày.
3. Gửi lần lượt các chunk.
4. `POST .../finalize/`; nhận `202` nghĩa là đã xếp việc cho Celery, không có nghĩa dữ liệu đã hoàn tất.
5. Poll `GET .../{batch_key}/` đến `completed` hoặc `completed_with_rejections`.
6. Nếu có rejection, tải `GET .../rejections/`, sửa nguồn và dùng **batch_key mới** để gửi lại các record lỗi.

Không được finalize nếu Prefect chưa gửi đủ số chunk/record đã khai báo. API trả `409` để tránh mất case.

## 0. Lấy mapping thật từ production

`GET /api/integrations/v1/catalog/` trả danh mục PGD không dành riêng cho luồng
mượn, loại quyển, loại chứng từ và nghiệp vụ. Prefect phải gọi endpoint này ở
đầu mỗi flow thay vì hard-code mapping. Catalog cố ý trả cả reference
`is_valid=false`, giống truy vấn của `maintain document data 3.py`; ví dụ loại
quyển CIMB code `2` vẫn phải map được. Token `documents:write` hoặc
`master_data:write` đều dùng được.

Đây là bước chuyển đổi cần thiết với dữ liệu Oracle thực tế, vốn có các trường
`folder_type`, `doc_grp`, `business_type`, `action_code` theo **tên**; API intake
nhận `folder_type_code`, `document_type_code`, `business_type_code` đã chuẩn hóa.
Flow mẫu tại `scripts/prefect_document_intake.py` thực hiện chuyển đổi này và chỉ
ghi report lỗi không chứa thông tin khách hàng/nhân viên.

## 1. Tạo batch

`POST /api/integrations/v1/batches/`

```json
{
  "batch_key": "documents-2025-08-06-run-01",
  "kind": "documents",
  "business_date": "2025-08-06",
  "source": "prefect-document-cleaner",
  "schema_version": "v1",
  "expected_records": 2400,
  "expected_chunks": 3
}
```

`kind` là `documents` hoặc `master_data`. Token phải có scope tương ứng `documents:write` hoặc `master_data:write`.

## 2. Gửi chunk chứng từ

`POST /api/integrations/v1/batches/{batch_key}/chunks/`

```json
{
  "chunk_no": 1,
  "records": [
    {
      "source_record_id": "20250806930450453860200876369994992621",
      "documents_created_date": "2025-08-06",
      "shop_code": 9304,
      "document_type_code": "1021",
      "folder_type_code": "1",
      "business_type_code": "1035",
      "contract_code": "50453860200876",
      "loan_code": "50453860200876",
      "customer_code": "<mã khách hàng từ Oracle>",
      "customer_name": "<tên khách hàng từ Oracle>",
      "employee_code": "<mã nhân viên từ Oracle>",
      "employee_name": "<tên nhân viên từ Oracle>",
      "is_pending_metadata": false
    }
  ]
}
```

Payload trên được đối chiếu từ một dòng thật đang có trong `f_DocumentsDetail`:
PGD `9304`, ngày `2025-08-06`, loại chứng từ `1021`, loại quyển `1`, nghiệp vụ
`1035`, hợp đồng/khoản vay `50453860200876`. Không gửi lại chính dòng minh họa
này vào production vì `source_record_id` đó đã tồn tại; batch mới phải dùng mã
chứng từ thực tế của ngày chạy.

Trường bắt buộc: `source_record_id`, `shop_code`, `document_type_code`, `folder_type_code`.

- `source_record_id` là **mã chứng từ cuối cùng** (`documents_code`), tối đa 50 ký tự và phải ổn định giữa các lần chạy.
- `documents_created_date` nếu có phải bằng `business_date`; điều này ngăn lẫn dữ liệu giữa batch ngày.
- `business_type_code`/`action_code` là tùy chọn; nếu gửi thì phải khớp đúng một nghiệp vụ đã cấu hình. `action_code` chỉ gửi khi nghiệp vụ thực tế cần phân biệt theo action; ví dụ dữ liệu thật `1035` ở trên không có action code.
- `contract_code`/`loan_code` và thông tin khách hàng/nhân viên là tùy chọn. Khi có dữ liệu, hệ thống duy trì `d_LoanCustomer`, `d_Employee`, `d_ContractDetail`, `d_LoanDetail` tương đương script cũ; dữ liệu đã có chỉ được bổ sung trường còn trống, không ghi đè giá trị hiện hữu.
- Folder code do server tự tạo theo `YYYYMMDD + shop_code + folder_type_code`; server cũng chỉ cập nhật cờ `is_issue` của folder ảo, không đè ghi chú/nhận quyển/hẹn quyển.

## 3. Finalize và theo dõi

`POST /api/integrations/v1/batches/{batch_key}/finalize/` trả `202` và `task_id` Celery.

`GET /api/integrations/v1/batches/{batch_key}/` trả `status`, tổng record/chunk và `summary` (`created`, `skipped`, `rejected`).

`GET /api/integrations/v1/batches/{batch_key}/rejections/?limit=200&offset=0` trả lỗi từng dòng gồm `row_no`, `source_record_id`, `error_code`, `message`, `raw_record`.

Trạng thái: `created` → `uploading` → `processing` → `completed` hoặc `completed_with_rejections`. `failed` nghĩa là Celery đã retry hết; kiểm tra `error_message`, sửa nguyên nhân rồi finalize lại hoặc tạo batch mới.

## Master data

### Upsert đơn lẻ — schema v1

`kind: "master_data"` với `entity: "shop"` chỉ upsert PGD có trong payload và
**không bao giờ tự deactivate/xóa** PGD không xuất hiện:

```json
{"entity":"shop","shop_code":20008,"shop_name":"BDG20008 ...","manager_code":"QLV001","is_shop_active":true,"closed_date":null}
```

`manager_code` phải tồn tại trước. Đây là chốt an toàn để không tạo PGD mất người quản lý.

### Snapshot orgchart — schema v2

Luồng thay thế đầy đủ cho `scripts/maintain_documents_master_data.py` dùng
`scripts/prefect_document_master_data.py`. Mỗi batch tháng có:

```json
{
  "entity": "orgchart_shop",
  "shop_code": 20008,
  "shop_name": "BDG20008.516 Đại lộ Bình Dương",
  "manager_code": "QLV001QLKV001",
  "region_manager_code": "QLV001",
  "region_manager_name": "Nguyễn Văn A",
  "region_manager_email": "a@example.com",
  "region_manager_gender": "Nam",
  "area_manager_code": "QLKV001",
  "area_manager_name": "Nguyễn Văn B",
  "area_manager_email": "b@example.com",
  "area_manager_gender": "Nam",
  "region_code": "2",
  "status": "active",
  "shop_closed_date": null
}
```

Record cuối batch là manifest:

```json
{
  "entity": "orgchart_snapshot",
  "snapshot_complete": true,
  "deactivate_missing_shops": true,
  "source_rows": 1072,
  "shop_rows": 1072
}
```

Quy tắc an toàn:

- Toàn bộ snapshot được validate trước khi ghi. Chỉ một dòng sai cũng khiến
  `snapshot_applied=false`; không manager/PGD nào bị thay đổi.
- Chỉ manifest có `snapshot_complete=true` mới được áp dụng.
- Chỉ khi `deactivate_missing_shops=true` mới chuyển PGD vắng khỏi snapshot
  sang inactive. API không xóa PGD.
- Thứ tự maintain là Region Manager → Area Manager → Manager → Shop.
- Manager đã tồn tại không bị ghi đè, giống `ON CONFLICT DO NOTHING` của script
  cũ. PGD đã tồn tại được cập nhật tên, manager, region, trạng thái và ngày đóng.
- PGD active được xóa ngày đóng cũ. PGD closed không có ngày đóng mới sẽ giữ
  ngày đóng gần nhất, tránh làm mất dữ liệu đã có.
- Snapshot tháng dùng `schema_version: "v2"` và token scope
  `master_data:write`.

Prefect nên chạy flow master trước flow chứng từ. Nếu source xuất hiện PGD hoặc
manager mới mà master chưa hoàn tất, batch chứng từ sẽ đưa dòng đó vào rejection
thay vì tạo liên kết sai.

Chạy kiểm tra local, chỉ upload staging và chưa finalize:

```powershell
python scripts/run_oracle_master_data_intake.py `
  --credentials C:\duong-dan\credential.yml `
  --api-url https://documents.example.com `
  --target-month 2026-06 `
  --run-key verify-01 `
  --skip-finalize
```

Khi kiểm tra partial, thêm `--keep-missing-shops-active`. Khi production chạy
snapshot đầy đủ thì không dùng cờ này để đồng bộ inactive giống script cũ.

## Làm sạch trước khi gửi

1. Chuẩn hóa mã: `source_record_id`, `shop_code`, type code, contract/loan là string trim; không đổi mã gốc bằng float (đọc Excel với dtype string).
2. Parse ngày có timezone rõ ràng rồi xuất ISO `YYYY-MM-DD`; chặn dòng có ngày khác business date.
3. Kiểm tra null và mapping reference (PGD, loại chứng từ, loại quyển, nghiệp vụ) tại nguồn; gửi report lỗi sang nơi theo dõi thay vì silently drop dòng.
4. Không dedup dòng Oracle theo `parent_document_code`: cùng mã cha có thể chứa
   nhóm chứng từ khác nhau. Tách `doc_grp` trước, sinh `source_record_id` cuối
   cùng rồi mới dedup theo mã này; production cũng dedup bằng
   `f_DocumentsDetail.documents_code`.
5. Chỉ gửi PII cần cho model khách hàng/nhân viên qua HTTPS. API tự che các trường khách hàng/nhân viên trong `raw_record` của rejection.

## Quy tắc tương thích `maintain document data 3.py`

Flow mẫu `scripts/prefect_document_intake.py` bám các quy tắc sau:

1. Truy vấn đúng nguồn Oracle, gồm thay nhân viên hệ thống bằng trưởng PGD,
   region/QLV/QLKV theo tháng và các điều kiện loại trừ PGD/chứng từ của script cũ.
2. Map loại quyển theo tên sang code `1`, `2`, `3`; reference inactive vẫn được
   dùng vì script cũ không lọc `is_valid`.
3. Map nghiệp vụ cần action bằng `(business_type, action_code)` trước, sau đó
   map nghiệp vụ không cần action bằng `business_type`.
4. Duy trì employee, customer, contract và loan trước khi loại thành phần
   `doc_grp` không có trong danh mục.
5. Tách `doc_grp` bằng dấu `", "` thành nhiều chứng từ. Công thức mã cuối cùng:
   `YYYYMMDD + shop_code + parent_document_code + business_type_id + document_type_id`.
6. Chỉ dedup ở mã cuối cùng, tương đương
   `ON CONFLICT (documents_code) DO NOTHING`. Không dedup sớm theo mã cha.
7. Quyển thật được nhóm theo ngày + PGD + loại quyển và có `is_issue=true`.
   Quyển ảo chỉ sinh cho loại `1` và `3`, cho mọi PGD `for_borrow_only=false`,
   không sinh sau `shop_closed_date`.
8. Folder status dùng PK `1`; folder group lấy group active bao phủ ngày trong
   tháng. Retry không ghi đè ghi chú, nhận quyển, hẹn quyển, package hoặc lịch sử
   người dùng.

Các dòng không map được PGD/manager/region/loại quyển bị đưa vào report làm
sạch. Thành phần `doc_grp` không map được document type cũng vào report và
không tạo `DocumentsDetail`, giống bước `dropna(document_type_id)` của script cũ.

## Ví dụ Prefect tối thiểu

```python
import os, requests
from prefect import flow, task
from prefect.blocks.system import Secret

BASE_URL = os.environ["DOCUMENT_API_URL"].rstrip("/")

@task(retries=4, retry_delay_seconds=15)
def post(path, payload, token):
    response = requests.post(f"{BASE_URL}{path}", json=payload,
        headers={"Authorization": f"Bearer {token}"}, timeout=60)
    response.raise_for_status()
    return response.json()

@flow
def send_documents(business_date: str, cleaned_rows: list[dict]):
    token = Secret.load("DOCUMENT_INTAKE_TOKEN").get()
    key = f"documents-{business_date}-daily"  # giữ nguyên key khi retry cùng run
    chunks = [cleaned_rows[i:i + 1000] for i in range(0, len(cleaned_rows), 1000)]
    post.submit("/api/integrations/v1/batches/", {
        "batch_key": key, "kind": "documents", "business_date": business_date,
        "source": "prefect-document-cleaner", "schema_version": "v1",
        "expected_records": len(cleaned_rows), "expected_chunks": len(chunks),
    }, token).result()
    for number, rows in enumerate(chunks, 1):
        post.submit(f"/api/integrations/v1/batches/{key}/chunks/", {"chunk_no": number, "records": rows}, token).result()
    post.submit(f"/api/integrations/v1/batches/{key}/finalize/", {}, token).result()
```

Lịch chạy nằm ở Prefect (ví dụ hằng ngày sau khi pipeline làm sạch hoàn tất). Celery production chỉ thực hiện xử lý nền khi batch được finalize; không cấu hình Celery Beat để tự đọc dữ liệu từ máy cục bộ.
