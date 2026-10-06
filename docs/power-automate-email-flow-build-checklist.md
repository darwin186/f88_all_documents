# Checklist dựng Flow gửi email cho IDA Chứng từ

## Đầu vào đã có từ Django

- Intake URL: Flow cung cấp sau khi lưu trigger `When an HTTP request is received`.
- Request schema: `docs/contracts/power-automate-email-request.schema.json`.
- Accepted-response schema: `docs/contracts/power-automate-email-accepted.schema.json`.
- Callback schema: `docs/contracts/power-automate-email-callback.schema.json`.
- Payload mẫu PGD: `docs/contracts/examples/power-automate-pgd-request.json`.
- Payload callback: `docs/contracts/examples/power-automate-callback.json`.
- Callback UAT: `https://ida-chungtu.f88.co/api/integrations/power-automate/email/callback/`.

## Flow 1 — Intake và gửi email

### Quy ước batch bắt buộc

- Django gửi một HTTP request chứa mảng `messages` gồm **25–50 email**; mỗi phần tử là một email độc lập, có `message_id`, To, CC, BCC, Subject và Body HTML riêng.
- Flow dùng `Apply to each` trên `triggerBody()?['messages']` để tách mảng và gửi từng email.
- Không gửi đồng thời toàn bộ phần tử. Đặt concurrency của `Apply to each` bằng **1** và thêm Delay **3 giây** sau mỗi lần gửi để giữ tốc độ khoảng 20 email/phút.
- Một batch 25 email mất khoảng 75 giây; batch 50 email mất khoảng 150 giây. Vì Django chỉ chờ intake tối đa 30 giây, **không chờ gửi xong mới trả HTTP Response cho request ban đầu**.
- Có hai phản hồi khác nhau:
  1. Action `Response` trả ngay HTTP `202 Accepted` cho Django sau khi kiểm tra và nhận đủ mảng.
  2. Sau khi gửi từng email, Flow dùng action `HTTP POST` tới `triggerBody()?['callback']?['url']` để báo `sent` hoặc `failed`. Đây là callback kết quả, không phải Response của request ban đầu.
- `202 Accepted` chỉ có nghĩa Flow đã nhận batch; trạng thái chỉ được coi là gửi thành công khi Django nhận callback `sent`.

### Luồng thao tác gửi hàng loạt trên Django

1. Admin bấm **Gửi email hàng loạt**, sau đó chọn một kênh đã được IT cấu hình: **Power Automate** hoặc **SMTP**. `EMAIL_TRANSPORT` chỉ xác định lựa chọn mặc định; credential không hiển thị trên UI.
2. Thao tác mở popup chỉ chạy preflight và chia người nhận thành các batch 25–50 email, chưa gửi email và chưa làm mất hiệu lực link hiện tại.
3. UI hiển thị danh sách batch với checkbox, số thứ tự, loại email, số người nhận hợp lệ/lỗi, template version và trạng thái.
4. Admin tick một hoặc nhiều batch rồi bấm **Gửi các batch đã chọn**.
5. Backend kiểm tra lại deadline, email, template, kênh gửi và trạng thái người nhận ngay tại thời điểm gửi; sau đó mới tạo/đổi link cần thiết, render HTML và đưa batch vào hàng đợi.
6. Nếu chọn nhiều batch, backend xử lý tuần tự từng batch. Power Automate nhận một mảng; SMTP gửi tuần tự từng email qua Celery worker.
7. Mỗi batch lưu snapshot `transport_provider` để truy vết kênh thực tế đã dùng.
8. Trạng thái batch: `Nháp → Chờ gửi → Đang xử lý → Hoàn tất / Hoàn tất một phần / Thất bại`.

1. Tạo Automated cloud flow với trigger `When an HTTP request is received`, method `POST`.
2. Dán request schema của Django vào trigger.
3. Bật Secure Inputs/Outputs cho trigger và mọi action chứa `body.content`.
4. Thêm Condition kiểm tra header `X-Webhook-Secret` bằng secret lưu trong Environment Variable của Solution.
5. Nếu secret sai, trả `401` và không xử lý messages.
6. Tạo `provider_batch_id` bằng Workflow Run ID: `workflow()?['run']?['name']`.
7. Dùng Select trên `triggerBody()?['messages']` để tạo danh sách `{message_id, status: accepted}`.
8. Trả HTTP `202` với nguyên `batch_id`, `request_id`, `provider_batch_id`, `status=accepted` và danh sách trên. Không trả `sent` ở bước này.
9. Apply to each trên `triggerBody()?['messages']`; bật Concurrency Control và đặt Degree of Parallelism bằng `1`.
10. Trước khi gửi, kiểm tra kho idempotency theo `message_id`. Khuyến nghị Dataverse; SharePoint List cũng dùng được nếu cột `message_id` được đặt unique.
11. Nếu `message_id` đã có trạng thái `sent`, bỏ qua action gửi và callback lại trạng thái `sent`.
12. Dùng `Send an email from a shared mailbox (V2)`:
    - Shared mailbox: `phongvanhanh@f88.vn` (cố định trong Flow, không tin giá trị From từ request).
    - To: `join(items('Apply_to_each')?['to'], ';')`.
    - CC/BCC: join tương tự.
    - Subject: `items('Apply_to_each')?['subject']`.
    - Body: `items('Apply_to_each')?['body']?['content']` và bật HTML.
13. Sau action gửi email, thêm Delay `3` giây. Scope Success cập nhật kho idempotency thành `sent`, sau đó POST callback một message với `event_id=guid()`.
14. Scope Failure chạy sau khi Scope gửi failed/timed out, lấy error đã rút gọn, cập nhật kho và POST callback `failed`.
15. Callback phải gửi header `X-Webhook-Secret` bằng callback secret riêng.

## Body callback cho từng message

```json
{
  "schema_version": "1.0",
  "event_id": "@{guid()}",
  "batch_id": "@{triggerBody()?['batch_id']}",
  "provider_batch_id": "@{workflow()?['run']?['name']}",
  "completed_at": "@{utcNow()}",
  "results": [
    {
      "message_id": "@{items('Apply_to_each')?['message_id']}",
      "status": "sent",
      "provider_message_id": ""
    }
  ]
}
```

Ở nhánh Failure đổi `status` thành `failed`, thêm `error_code` và `error_message`. Giữ error message dưới 500 ký tự.

## Cấu hình Django/Kubernetes

```dotenv
EMAIL_TRANSPORT=power_automate
POWER_AUTOMATE_EMAIL_WEBHOOK_URL=<HTTP POST URL của Flow>
POWER_AUTOMATE_EMAIL_WEBHOOK_SECRET=<secret intake>
POWER_AUTOMATE_EMAIL_CALLBACK_SECRET=<secret callback khác intake>
POWER_AUTOMATE_EMAIL_CALLBACK_URL=https://ida-chungtu.f88.co/api/integrations/power-automate/email/callback/
POWER_AUTOMATE_EMAIL_CONNECT_TIMEOUT=3.05
POWER_AUTOMATE_EMAIL_READ_TIMEOUT=30
POWER_AUTOMATE_EMAIL_CHUNK_SIZE=25  # được phép nâng lên 50 sau khi UAT batch 50 đạt
POWER_AUTOMATE_EMAIL_MAX_RETRIES=3
DEFAULT_FROM_EMAIL=phongvanhanh@f88.vn
```

Đặt các giá trị secret và URL trong Kubernetes Secret, inject giống nhau cho web và worker. Không ghi secret thẳng vào Deployment YAML hoặc repository.

## Lưu ý bắt buộc khi bàn giao Production Go-live

- [ ] Không cấu hình webhook URL hoặc secret trên UI/database. Đây là cấu hình hạ tầng, bắt buộc lấy từ Kubernetes Secret/environment.
- [ ] Inject cùng một bộ biến vào cả `chungtu-service` và `chungtu-worker`; kiểm tra giá trị đã tồn tại trong cả hai pod mà không in giá trị secret ra log.
- [ ] Chỉ đặt `EMAIL_TRANSPORT=power_automate` sau khi Flow UAT, callback và quyền Send As đã kiểm thử đạt.
- [ ] `POWER_AUTOMATE_EMAIL_WEBHOOK_SECRET` và `POWER_AUTOMATE_EMAIL_CALLBACK_SECRET` phải là hai secret khác nhau.
- [ ] `POWER_AUTOMATE_EMAIL_CALLBACK_URL` phải là URL HTTPS public của Production và Nginx/Ingress phải forward được đường dẫn `/api/integrations/power-automate/email/callback/` tới web service.
- [ ] Địa chỉ gửi `phongvanhanh@f88.vn` được khóa tại backend/Flow; UI chỉ hiển thị readonly. Service account của Flow phải có quyền `Send As` mailbox này.
- [ ] Không đưa webhook URL, secret, raw request body hoặc unique link vào application log, manifest Git hay ảnh chụp bàn giao.
- [ ] Chạy `python manage.py migrate` trước khi bật transport mới và xác nhận migration `0030_power_automate_email_transport` đã áp dụng.
- [ ] Giữ `EMAIL_TRANSPORT=smtp` làm rollback flag trong thời gian canary; việc đổi transport cần restart/redeploy cả web và worker.
- [ ] Canary theo thứ tự: `datnm@f88.vn` → 1 PGD test → 1 QLKV test → batch 5–10 → batch 25 → batch 50 → toàn chiến dịch.

## Kiểm thử UAT theo thứ tự

- [ ] IT chạy `python manage.py migrate` và route callback trả JSON 401 khi gọi không có secret.
- [ ] Gửi payload mẫu với địa chỉ đã thay thành `datnm@f88.vn`; Flow trả đúng HTTP 202.
- [ ] Xác nhận Django ghi delivery là `accepted`, chưa phải `sent`.
- [ ] Xác nhận mail đến từ `Phòng Vận Hành <phongvanhanh@f88.vn>` và HTML/tiếng Việt đúng.
- [ ] Xác nhận callback đổi delivery thành `sent`.
- [ ] Gửi lại cùng `message_id`; không phát sinh email thứ hai.
- [ ] Callback lại cùng `event_id`; Django trả `duplicate=true`, counter không tăng.
- [ ] Test mailbox sai; Flow callback `failed` và UI không hiển thị đã gửi.
- [ ] Test PGD có CC QLKV, sau đó test QLKV monitoring và QLKV confirmation.
- [ ] Canary 1 email, rồi 5–10 email, 25 email và 50 email; theo dõi HTTP 429, callback thiếu và email trùng trước khi mở toàn kỳ.

## Điều kiện quyền Exchange

- Connection của Flow dùng service account ổn định.
- Service account được cấp `Send As` cho `phongvanhanh@f88.vn`.
- Tenant cho phép gửi ra `f88.co`.
- Không dùng tài khoản cá nhân làm connection production.
