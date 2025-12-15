# documents
# The system of management document

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

