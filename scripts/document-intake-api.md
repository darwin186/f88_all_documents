# API nhận dữ liệu chứng từ từ Prefect

API này dành cho hệ thống làm sạch dữ liệu gọi vào production. Người dùng UI không dùng API này.

> Tài liệu chuẩn và đầy đủ nằm tại `docs/document-intake-api.md`. File này chỉ
> được giữ lại để tương thích với đường dẫn triển khai cũ.

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

## 1. Tạo batch

`POST /api/integrations/v1/batches/`

```json
{
  "batch_key": "documents-2026-07-22-run-01",
  "kind": "documents",
  "business_date": "2026-07-22",
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
      "source_record_id": "DOC-20260722-000001",
      "documents_created_date": "2026-07-22",
      "shop_code": 20008,
      "document_type_code": "HD",
      "folder_type_code": "1",
      "business_type_code": "VAY",
      "action_code": "GIAI_NGAN",
      "contract_code": "60769518780001",
      "loan_code": "60769518780001",
      "is_pending_metadata": false
    }
  ]
}
```

Trường bắt buộc: `source_record_id`, `shop_code`, `document_type_code`, `folder_type_code`.

- `source_record_id` là mã chứng từ nguồn, tối đa 50 ký tự và phải ổn định giữa các lần chạy.
- `documents_created_date` nếu có phải bằng `business_date`; điều này ngăn lẫn dữ liệu giữa batch ngày.
- `business_type_code`/`action_code` là tùy chọn; nếu gửi thì phải khớp đúng một nghiệp vụ đã cấu hình.
- `contract_code`/`loan_code` tùy chọn. Hệ thống chỉ tạo dimension tối thiểu nếu mã chưa tồn tại, không ghi đè thông tin người dùng đã có.
- Folder code do server tự tạo theo `YYYYMMDD + shop_code + folder_type_code`; server cũng chỉ cập nhật cờ `is_issue` của folder ảo, không đè ghi chú/nhận quyển/hẹn quyển.

## 3. Finalize và theo dõi

`POST /api/integrations/v1/batches/{batch_key}/finalize/` trả `202` và `task_id` Celery.

`GET /api/integrations/v1/batches/{batch_key}/` trả `status`, tổng record/chunk và `summary` (`created`, `skipped`, `rejected`).

`GET /api/integrations/v1/batches/{batch_key}/rejections/?limit=200&offset=0` trả lỗi từng dòng gồm `row_no`, `source_record_id`, `error_code`, `message`, `raw_record`.

Trạng thái: `created` → `uploading` → `processing` → `completed` hoặc `completed_with_rejections`. `failed` nghĩa là Celery đã retry hết; kiểm tra `error_message`, sửa nguyên nhân rồi finalize lại hoặc tạo batch mới.

## Master data (schema v1)

`kind: "master_data"` chỉ upsert PGD có trong payload và **không bao giờ tự deactivate/xóa** PGD không xuất hiện. Mỗi record:

```json
{"entity":"shop","shop_code":20008,"shop_name":"BDG20008 ...","manager_code":"QLV001","is_shop_active":true,"closed_date":null}
```

`manager_code` phải tồn tại trước. Đây là chốt an toàn để không tạo PGD mất người quản lý.

## Làm sạch trước khi gửi

1. Chuẩn hóa mã: `source_record_id`, `shop_code`, type code, contract/loan là string trim; không đổi mã gốc bằng float (đọc Excel với dtype string).
2. Parse ngày có timezone rõ ràng rồi xuất ISO `YYYY-MM-DD`; chặn dòng có ngày khác business date.
3. Kiểm tra null và mapping reference (PGD, loại chứng từ, loại quyển, nghiệp vụ) tại nguồn; gửi report lỗi sang nơi theo dõi thay vì silently drop dòng.
4. Không dedup dòng Oracle theo `parent_document_code`. Phải explode `doc_grp`,
   sinh mã chứng từ cuối cùng rồi mới dedup theo `source_record_id`
   (`documents_code`).
5. Không gửi PII không cần thiết trong `raw_record`; rejection lưu payload để đối soát.

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
