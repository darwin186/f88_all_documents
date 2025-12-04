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

## Change log (manual)
- 2025-02-03: Administrative docs numbering theo công ty + định dạng mới `NNN/YYYY/TYPE-COMPANY/SIGNER`; bắt buộc các trường chính khi tạo; thông báo và highlight record mới tạo.
- 2025-02-03: GAPO scheduler: thêm AI hỗ trợ soạn tin (Gemini), layout rộng hơn, bảng lịch sử có cuộn; thêm endpoint `gapo/schedule/ai-draft/`.
- 2025-02-03: Administrative docs list: thêm cột STT lên đầu, “Số hiệu” đứng thứ 2.
- 2025-02-03: Paper documents list: thêm ô tìm kiếm theo số hiệu/mã vận đơn, thêm cột STT.

