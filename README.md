# documents
# The system of management document

## App Documents (app_documents) - Tổng quan A-Z

### 1) Mục tiêu hệ thống
Hệ thống quản lý chứng từ bản cứng gồm các luồng chính: **nhận chứng từ**, **duyệt chứng từ**, **quản lý thùng**, **chỉ tiêu/KPI**, và **mượn chứng từ**. Toàn bộ màn hình v2 dùng base/layout chung để đồng bộ UI.

### 2) Ứng dụng chính
- `app_documents`: nghiệp vụ chứng từ, nhận/duyệt, thùng, KPI, mượn.
- `app_admindocuments`: cấp số văn bản hành chính/giấy tờ (khác mảng chứng từ).
- `app_notification`: thông báo hệ thống (gửi, template).
- `documents/`: project settings, urls, celery.

### 3) Vai trò & phân quyền
Lấy từ `app_documents/utils.py::get_user_context`:
- **super_admin**: quyền cao nhất.
- **admin**: quản trị hệ thống nghiệp vụ.
- **checker**: cộng tác viên xử lý nhận/duyệt.
- **shop**: người dùng cửa hàng.
- **supervisor/manager/risk**: theo nhóm.

Filter dữ liệu theo role dùng `app_documents/access_controls.py` (lọc region/shop).

### 4) Điều hướng v2 (routes chính)
- Nhận chứng từ v2: `/nhan-chung-tu-v2`
- Duyệt chứng từ v2: `/duyet-chung-tu-v2`
- Quản lý thùng: `/package-list-management`
- Chỉ tiêu chứng từ: `/chi-tieu-chung-tu-v2` (admin)
- Mượn chứng từ (tab): `/yeu-cau-muon-chung-tu-v2`, `/quan-ly-muon-chung-tu-v2`
- Quản lý tài khoản CTV (online): `/quan-ly-tai-khoan-ctv` (admin)

### 5) Dữ liệu & thực thể chính
- **Folder (quyển)**: `Folder` (f_FolderDetail)
- **Document (chứng từ)**: `DocumentsDetail` (f_DocumentsDetail)
- **Package (thùng)**: `Package` (d_Package)
- **FolderType/DocumentType/BusinessType**: danh mục loại
- **FolderStatus/DocumentStatus**: trạng thái quyển/chứng từ
- **BorrowingDocument/BorrowRequest**: mượn chứng từ
- **Logs**: `FoldersTransactionReceiving`, `DocumentsTransactionChecking`, `PackageFolderHistory`, `PackageDocumentHistory`, `BorrowRequestLog`

#### Trạng thái quyển (FolderStatus)
Flag chính: `is_received`, `is_not_received_yet`, `is_borrow`, `is_lost`, `is_transfer`.

#### Trạng thái chứng từ (DocumentStatus)
Flag chính: `is_selectable` (đã nhận), `is_checked` (đã duyệt), `is_borrow` (đang mượn), `is_lost`.

### 6) Luồng nghiệp vụ chính

#### 6.1 Nhận chứng từ (v2)
Trang: `/nhan-chung-tu-v2`.
Luồng:
1) Lọc quyển theo shop, loại, trạng thái, ngày.
2) Nhập mã thùng F88 để nhận (validate package type).
3) Cập nhật: `Folder.folder_status_id`, `lastest_received_date`, `lastest_received_by`, `package_id`.
4) Ghi log:
   - `FoldersTransactionReceiving` (trạng thái quyển)
   - `PackageFolderHistory` (quyển ↔ thùng)
   - `PackageDocumentHistory` (chứng từ ↔ thùng)
5) Đồng bộ `DocumentsDetail.package_id` theo thùng.
6) Check đúng hạn bằng `check_on_time()` (set `is_on_time`, `is_late`).

#### 6.2 Duyệt chứng từ (v2)
Trang: `/duyet-chung-tu-v2`.
Luồng:
1) Chọn trạng thái duyệt (CheckingTransactionStatus).
2) Cập nhật `DocumentsDetail.status_id`, `lastest_checked_date`, `lastest_checked_by`.
3) Chuyển `document_status_id` theo cờ `is_checked` (không hardcode code).
4) Tạo log `DocumentsTransactionChecking`.
5) Nếu trạng thái yêu cầu bổ sung (`is_request_additional`) thì tạo `CheckingAdditional`.
6) Duyệt nhiều: chỉ cho phép chọn chứng từ cùng HDCC/GNN và chưa duyệt.

#### 6.3 Quản lý thùng
Trang: `/package-list-management`.
- Tạo thùng theo chuẩn `{FolderType}-{yymmdd}-{region}{bb}`.
- Validate thùng theo loại quyển, region.
- Gỡ thùng v1: chỉ cho gỡ trong ngày, không có chứng từ đã duyệt.

#### 6.4 KPI/Chỉ tiêu chứng từ
Trang: `/chi-tieu-chung-tu-v2` (admin).
- Dataset: các quyển gốc phát sinh (`is_issue=True` & `is_original=True`).
- KPI dùng `DocumentKpiSetting` với các metric được bật.
- Báo cáo theo: PGD, vùng/khu vực, theo tháng.
- Hỗ trợ export dữ liệu chi tiết.

#### 6.5 Mượn chứng từ (Borrow Request v2)
Trang: `/yeu-cau-muon-chung-tu-v2`.
Luồng:
1) Tạo **Phiếu yêu cầu mượn** (BorrowRequest) với phòng ban, ngày mượn, hẹn trả, ticket/email...
2) Gán chứng từ theo **contract_code/loan_code** (chỉ chứng từ đã duyệt, chưa mượn).
3) **Bàn giao**: tạo `BorrowingDocument`, cập nhật `document_status_id` sang `is_borrow`.
   - Khi bàn giao, chứng từ được gỡ khỏi thùng: `DocumentsDetail.package_id = None`.
4) **Hoàn trả** (theo item hoặc theo phiếu): cập nhật legacy `BorrowingDocument` và trả lại `document_status_id` sang `is_checked`.
5) Log đầy đủ `BorrowRequestLog`.

### 7) Giao diện v2 (theme)
Base: `app_documents/templates/app_documents/base_app_documents_v2.html`.
Đặc trưng v2:
- Font nhỏ (9–10px), input bo tròn, viền mỏng.
- Filter và droplist đồng nhất với nhận/duyệt.
- Drawer cho thao tác chi tiết (nhận/duyệt).
- Toast thông báo (duyệt/nhận).

### 8) API chính
- `POST /api/folder/receive-v2/` nhận quyển v2
- `POST /api/document/<id>/note/` cập nhật ghi chú
- `POST /api/package/create-v2/` tạo thùng v2
- `POST /api/borrow-requests/` tạo BorrowRequest từ hệ thống khác (API key)
- `POST /api/heartbeat/` ping online user

### 9) Online user / đo thời gian làm việc
- Model: `UserPresenceDaily` (f_UserPresenceDaily)
- Heartbeat chạy từ base v2 mỗi 60s.
- Online window mặc định 5 phút.
- Trang admin: `/quan-ly-tai-khoan-ctv`

### 10) Cấu hình env liên quan
Trong `documents/settings.py`:
- `BORROW_REQUEST_API_KEY`
- `USER_PRESENCE_ACTIVE_GAP`, `USER_PRESENCE_ONLINE_WINDOW`, `USER_PRESENCE_HEARTBEAT_SECONDS`
- Celery/GAPO (xem phần Celery bên dưới)

### 11) Quy ước versioning
Các màn hình v2 có hậu tố `_v2` để tách khỏi v1 (route/template/JS).

## Celery (background tasks)
This project now includes a basic Celery setup.

### Dependencies
- Redis as broker/result backend (default `redis://localhost:6379/0`). Install and run Redis locally, or update `CELERY_BROKER_URL`/`CELERY_RESULT_BACKEND` in `.env`.
- Python packages: `celery==5.3.6`, `redis==5.0.4` (already listed in `requirements.txt`).

### Configuration
- `documents/celery.py` bootstraps Celery and autodiscovers tasks.
- Sample task: `app_documents/tasks.py::ping`.
- Settings in `documents/settings.py`:
  - `CELERY_BROKER_URL` (default Redis)
  - `CELERY_RESULT_BACKEND` (defaults to broker)
  - JSON serializers, timezone inherits Django `TIME_ZONE`.

### Running locally
1) Start Redis (choose one):
   - Local: `redis-server`
   - Docker: `docker compose up -d redis`
2) Run Celery worker:
   ```bash
   # Linux/mac: default pool
   celery -A documents worker -l info
   # Windows: dùng --pool=solo để tránh lỗi handle invalid
   celery -A documents worker -l info --pool=solo
   ```
3) (Optional) Run Celery beat for periodic tasks:
   ```bash
   celery -A documents beat -l info
   ```

### Docker compose (Redis)
- `docker-compose.yml` now includes a `redis` service. Web is pre-set with `CELERY_BROKER_URL`/`CELERY_RESULT_BACKEND` pointing to that service. On prod, keep this or point the env vars to your managed Redis.

### Using tasks
- Example call from Django shell:
  ```python
  from app_documents.tasks import ping
  ping.delay()
  ```
- Add your own tasks in `app_documents/tasks.py` (or any app’s `tasks.py`); Celery will autodiscover.

### GAPO scheduled messaging (demo)
- Model: `GapoScheduledMessage` stores receiver_id, message, schedule_at, status.
- Task: `app_documents.tasks.send_gapo_scheduled_message` enqueues via Celery; it will send at `schedule_at` and update status/log errors.
- UI: Admin menu → “Thông tin khác” → “Gửi tin GAPO hẹn giờ” to create schedule (receiver_id, message, time) and view recent tasks.
- Broker required: Celery + Redis must be running; GAPO env vars (`GAPO_API_URL`, `GAPO_BOT_API_KEY`, `GAPO_BOT_ID`) must be set.

## Cấp số văn bản hành chính (allocate number)
- Bảng `adm_document_counter` lưu `next_number` theo bộ `(doc_type, company, year)` và được khóa `select_for_update` khi cấp số.
- Hàm `app_admindocuments.services.allocate_running_number(doc_type_id, company_id, year=None)`:
  - Nếu `year` trống thì dùng năm hiện tại theo timezone.
  - Lấy/tạo dòng counter, chọn số ứng viên (`next_number`), kiểm tra `AdmAdministrativeDocument` cùng loại/công ty/năm để bỏ qua số đã dùng (kể cả khi có bản ghi nhập tay).
  - Ghi lại `next_number = candidate + 1` sau khi tìm được số trống và trả về `candidate`.
- View `document_create` gọi hàm trên trong transaction, thử tối đa 3 lần; nếu gặp `IntegrityError` sẽ tự tăng counter thêm 1 rồi thử lại để tránh đụng độ khi nhiều người tạo cùng lúc.
- `AdmAdministrativeDocument.save()` dùng `running_number` để tạo số hiệu chính thức dạng `NNN/YYYY/TYPE-COMPANY/SIGNER` (mặc định padding 3 chữ số). Nếu vì lý do nào đó `running_number` chưa có, model sẽ tự tính từ số lớn nhất của năm đó để không bị trùng.

## Cấp số giấy hành chính (paper)
- `AdmPaperDocument` cấp số riêng theo `paper_type` và năm (padding 5 chữ số).
- Khi tạo mới qua view `paper_document_list`:
  - Transaction + `select_for_update` lấy bản ghi cuối cùng của `paper_type` trong năm hiện tại, tính `running_number = last + 1`.
  - Sinh số hiệu dạng `NNNNN/YYYY/{paper_type.code}-F88`, kiểm tra trùng `document_number_full`; nếu trùng thì tăng tiếp đến khi trống.
  - Thử tối đa 3 lần nếu gặp `IntegrityError` (đụng độ đồng thời) trước khi báo lỗi.
- Tải Excel import: với mỗi dòng, hệ thống tìm `paper_type`, lấy `running_number` kế tiếp theo năm, sinh số hiệu cùng format; chạy trong transaction, tránh trùng bằng cách tăng `running_number` khi cần.
- Trang danh sách cho phép lọc/sắp xếp theo loại giấy, mã vận đơn; số thứ tự (`running_number`) dùng cho mục sắp xếp và hiển thị.

## Change log (manual)
- 2025-02-03: Administrative docs numbering theo công ty + định dạng mới `NNN/YYYY/TYPE-COMPANY/SIGNER`; bắt buộc các trường chính khi tạo; thông báo và highlight record mới tạo.
- 2025-02-03: GAPO scheduler: thêm AI hỗ trợ soạn tin (Gemini), layout rộng hơn, bảng lịch sử có cuộn; thêm endpoint `gapo/schedule/ai-draft/`.
- 2025-02-03: Administrative docs list: thêm cột STT lên đầu, “Số hiệu” đứng thứ 2.
- 2025-02-03: Paper documents list: thêm ô tìm kiếm theo số hiệu/mã vận đơn, thêm cột STT.

