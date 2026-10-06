# Kế hoạch gửi email lỗi chứng từ qua Power Automate

## 1. Kết quả nghiệp vụ cần đạt

- Admin cấu hình và preview email HTML trong campaign.
- Hệ thống gửi được email riêng cho từng PGD, CC QLKV hiện tại.
- Hệ thống gửi được email QLKV cho hai giai đoạn: theo dõi PGD và xác nhận lỗi.
- Django render hoàn chỉnh To/CC/BCC, subject, HTML body và unique link trước khi gửi.
- Power Automate chỉ đảm nhiệm vận chuyển email, không tự xử lý placeholder nghiệp vụ.
- Theo dõi được từng email: chờ gửi, Power Automate đã nhận, đã gửi, thất bại hoặc bỏ qua.
- Có batch progress, lịch sử attempt, retry riêng email lỗi và idempotency chống gửi trùng.
- Không đánh dấu `sent` chỉ vì webhook trả HTTP 200/202; chỉ đánh dấu `sent` từ kết quả gửi hoặc callback cuối.

## 2. Phạm vi loại email

| `email_type` | Người nhận chính | Mục đích |
| --- | --- | --- |
| `pgd_response` | Email PGD | Gửi unique link phản hồi lỗi chứng từ |
| `area_monitoring` | QLKV | Theo dõi tình hình phản hồi của các PGD quản lý |
| `area_confirmation` | QLKV | Xác nhận kết quả Phòng Vận Hành review |
| `shop_submission_receipt` | Email PGD | Xác nhận hệ thống đã nhận phản hồi chính thức |

Pha đầu triển khai `pgd_response`, sau đó dùng cùng hạ tầng cho hai email QLKV.

## 3. Kiến trúc tổng thể

```text
Admin bấm gửi
  → Django preflight email và dữ liệu Master Data
  → Tạo CampaignEmailBatch
  → Tạo một CampaignEmailDelivery cho mỗi PGD/QLKV
  → transaction.on_commit đưa batch vào Celery
  → Celery chia chunk 20–50 email
  → POST HTTPS tới Power Automate
  → Power Automate trả accepted
  → Power Automate gửi email
  → Power Automate callback kết quả từng message
  → Django cập nhật progress và UI polling
```

Không gọi Power Automate trực tiếp từ trình duyệt. Webhook URL và secret chỉ tồn tại ở backend/worker.

## 4. Mô hình dữ liệu Django

### 4.1. `CampaignEmailBatch`

Một dòng cho mỗi lần Admin bấm gửi hoặc gửi lại một nhóm email.

```text
id                         UUID primary key
campaign_id                FK Campaign
email_type                 pgd_response / area_monitoring / area_confirmation / shop_submission_receipt
status                     queued / dispatching / accepted / processing / completed / partially_failed / failed / cancelled
idempotency_key            unique
total_count
accepted_count
sent_count
failed_count
skipped_count
provider_batch_id          Power Automate run/batch id
requested_by_id
queued_at
submitted_at
completed_at
last_error_code
last_error_message
created_at
updated_at
```

### 4.2. `CampaignEmailDelivery`

Một dòng cho mỗi email PGD hoặc QLKV.

```text
id                         UUID; đồng thời là message_id gửi sang Power Automate
batch_id                   FK CampaignEmailBatch
target_type                shop / area_manager
target_id                  ID của PGD hoặc QLKV tại thời điểm gửi
shop_access_link_id        nullable
area_access_link_id        nullable
to_emails                  JSON list
cc_emails                  JSON list
bcc_emails                 JSON list
from_email
from_name
rendered_subject
rendered_body_redacted     HTML audit đã che token
encrypted_payload          payload gửi thật được mã hóa
template_version
idempotency_key            unique
status                     queued / submitting / accepted / sent / failed / skipped / cancelled
attempt_count
provider_batch_id
provider_message_id
accepted_at
sent_at
failed_at
error_code
error_message
created_at
updated_at
```

`encrypted_payload` cần thiết vì unique link hiện chỉ lưu digest; muốn retry đúng email/link thì phải giữ payload gửi thật ở dạng mã hóa. Dùng khóa riêng `EMAIL_PAYLOAD_ENCRYPTION_KEY`, không dùng plaintext và không ghi payload vào application log.

### 4.3. `CampaignEmailAttempt`

Lưu lịch sử từng lần Django gọi webhook.

```text
id
delivery_id
attempt_number
request_id
http_status
provider_batch_id
outcome                    accepted / rejected / timeout / transport_error
duration_ms
error_code
error_message
created_at
```

### 4.4. `CampaignEmailWebhookEvent`

Chống callback trùng và phục vụ audit.

```text
event_id                   unique
batch_id
received_at
payload_digest
processed_at
status                     processed / rejected
message
```

### 4.5. Chuyển đổi dữ liệu hiện tại

- Giữ `ShopEmailDelivery` trong một migration chuyển tiếp, backfill dữ liệu sang delivery chung rồi ngừng ghi mới.
- Không dùng `AreaManagerAccessLink.email_status` làm nguồn sự thật nữa; có thể giữ làm cache hiển thị trong một release rồi xóa sau.
- Access link vẫn quản lý quyền truy cập; EmailDelivery chỉ quản lý việc gửi.

## 5. HTML email và editor

- Thêm trường template HTML cho PGD và QLKV.
- Rich-text editor chỉ cho phép paragraph, heading nhỏ, bold, italic, underline, list, alignment, safe link, màu giới hạn và CTA button.
- Sanitize HTML server-side theo whitelist; loại `script`, `iframe`, form, event handler và URL nguy hiểm.
- Inline CSS trước khi gửi; email layout tối đa khoảng 600 px.
- Django thay placeholder và HTML-escape dữ liệu nghiệp vụ.
- `{{response_url}}` hoặc `{{manager_url}}` vẫn là placeholder bắt buộc.
- Lưu `template_version` và HTML audit đã che token cho từng delivery.
- Power Automate nhận HTML cuối cùng và map thẳng vào Body của Outlook action.

## 6. Contract Django → Power Automate

### 6.0. Quy ước truyền và xử lý batch

- Mỗi lần Django gọi webhook, trường `messages` chứa **25–50 email độc lập**. JSON Schema giới hạn cứng tối đa 50 phần tử.
- Power Automate tách mảng bằng `Apply to each` trên `triggerBody()?['messages']`.
- Flow phải trả `202 Accepted` trong thời gian chờ HTTP của Django (mặc định 30 giây), trước khi hoàn tất việc gửi cả batch.
- Việc gửi chạy tuần tự với concurrency `1`; khuyến nghị Delay `3` giây/email để không vượt ngưỡng gửi của Exchange Online.
- Sau khi xử lý, Flow không dùng lại action Response của request intake để báo kết quả cuối. Flow phải `HTTP POST` kết quả `sent`/`failed` tới `callback.url`, theo contract mục 7.
- Có thể callback từng message để UI cập nhật liên tục, hoặc gom nhiều kết quả trong một callback; mọi `message_id` phải xuất hiện đúng một lần ở trạng thái kết thúc và callback phải idempotent.
- `POWER_AUTOMATE_EMAIL_CHUNK_SIZE=25` là mặc định an toàn; có thể đổi thành `50` sau khi UAT batch 50 thành công.

### 6.0.1. UX chuẩn bị và chọn batch để gửi

```text
Gửi email hàng loạt
  → Preflight người nhận
  → Tạo danh sách batch nháp (25–50 email/batch)
  → Admin tick batch
  → Xác nhận gửi
  → Celery xếp hàng tuần tự
  → Power Automate nhận từng batch
  → Callback cập nhật tiến độ từng email/batch
```

- Nút **Gửi email hàng loạt** không gửi ngay; chỉ tạo batch nháp để Admin kiểm tra.
- Mỗi dòng batch có checkbox, số lượng email, số người nhận, template version, trạng thái và tiến độ `sent/failed/total`.
- Khi Admin tick nhiều batch, hệ thống vẫn xử lý tuần tự, tối đa một batch đang submit webhook tại một thời điểm cho cùng chiến dịch/giai đoạn.
- Chỉ tạo hoặc thay thế unique link tại thời điểm batch thực sự được gửi. Việc chuẩn bị batch không được vô hiệu link đang dùng.
- Trước khi gửi phải kiểm tra lại email, deadline, trạng thái PGD/QLKV và template version; batch không còn hợp lệ phải quay về `Cần chuẩn bị lại`.
- Không cho gửi lại toàn bộ batch đã hoàn tất. Nút retry chỉ tạo delivery mới cho các message `failed`; message `sent` luôn được bỏ qua.

### 6.1. Endpoint

```http
POST ${POWER_AUTOMATE_EMAIL_WEBHOOK_URL}
```

### 6.2. Headers

```http
Content-Type: application/json
Accept: application/json
User-Agent: ida-chungtu/1.0
X-Schema-Version: 1
X-Request-ID: <UUID của request/chunk>
Idempotency-Key: <khóa duy nhất của chunk>
X-Timestamp: <Unix timestamp>
X-Webhook-Secret: <shared secret cho MVP>
X-Signature: sha256=<HMAC nếu đi qua APIM/Azure Function>
```

- MVP trực tiếp Power Automate: signed trigger URL kết hợp `X-Webhook-Secret`, Flow kiểm tra secret ngay bước đầu.
- Production khuyến nghị: Entra ID hoặc APIM/Azure Function xác minh HMAC và replay window 5 phút.
- Tuyệt đối không log webhook URL, secret, Authorization hoặc raw request body.

### 6.3. Request body

```json
{
  "schema_version": "1.0",
  "batch_id": "8cb83dc8-63ca-4e4a-b89c-89ef632de22f",
  "request_id": "f9ea25c4-289e-443a-a837-74303644df41",
  "requested_at": "2026-10-02T10:30:00+07:00",
  "source": "ida-chungtu",
  "email_type": "pgd_response",
  "campaign": {
    "id": 2,
    "code": "DEC_001_202606",
    "name": "Lỗi chứng từ tháng 6",
    "report_month": "2026-06"
  },
  "callback": {
    "url": "https://ida-chungtu.f88.co/api/integrations/power-automate/email/callback/"
  },
  "messages": [
    {
      "message_id": "61a633f5-37d9-41e3-90fe-c59d77e08319",
      "idempotency_key": "campaign:2:pgd:4309:link:1256:template:3",
      "target": {
        "type": "shop",
        "id": 4309,
        "code": "PTO21010.340",
        "name": "Đường Đào Giã"
      },
      "from": {
        "address": "phongvanhanh@f88.vn",
        "name": "Phòng Vận Hành"
      },
      "to": ["shop@f88.co"],
      "cc": ["area.manager@f88.vn"],
      "bcc": [],
      "subject": "Lỗi chứng từ bản cứng 06/2026",
      "body": {
        "content_type": "html",
        "content": "<html>...</html>"
      },
      "metadata": {
        "shop_link_id": 1256,
        "template_version": 3,
        "response_deadline": "2026-10-10T17:30:00+07:00",
        "link_expires_at": "2026-11-10T17:30:00+07:00"
      }
    }
  ]
}
```

### 6.4. Response nhận batch

Power Automate trả HTTP `202`:

```json
{
  "ok": true,
  "batch_id": "8cb83dc8-63ca-4e4a-b89c-89ef632de22f",
  "request_id": "f9ea25c4-289e-443a-a837-74303644df41",
  "provider_batch_id": "power-automate-run-id",
  "status": "accepted",
  "accepted_at": "2026-10-02T03:30:02Z",
  "results": [
    {
      "message_id": "61a633f5-37d9-41e3-90fe-c59d77e08319",
      "status": "accepted"
    }
  ]
}
```

HTTP 202 chỉ chuyển delivery sang `accepted`, không phải `sent`.

Response này phải được trả ngay sau bước xác thực, kiểm tra schema/idempotency và tạo danh sách accepted. Không chờ vòng `Apply to each` gửi xong 25–50 email; kết quả gửi thật được trả qua callback mục 7.

## 7. Contract Power Automate → Django callback

### 7.1. Endpoint Django

```http
POST /api/integrations/power-automate/email/callback/
```

Endpoint không dùng session/CSRF, nhưng bắt buộc xác thực secret/HMAC, timestamp và HTTPS.

### 7.2. Callback body

```json
{
  "schema_version": "1.0",
  "event_id": "9e169a42-ea48-4696-b74d-a95312742dd8",
  "batch_id": "8cb83dc8-63ca-4e4a-b89c-89ef632de22f",
  "provider_batch_id": "power-automate-run-id",
  "completed_at": "2026-10-02T03:31:20Z",
  "results": [
    {
      "message_id": "61a633f5-37d9-41e3-90fe-c59d77e08319",
      "status": "sent",
      "provider_message_id": "AAMkAD...",
      "sent_at": "2026-10-02T03:31:12Z"
    },
    {
      "message_id": "0472cc68-4d2b-4cb5-82fb-1868de115efd",
      "status": "failed",
      "error_code": "MAILBOX_NOT_FOUND",
      "error_message": "Recipient mailbox was not found"
    }
  ]
}
```

Callback response:

```json
{
  "ok": true,
  "event_id": "9e169a42-ea48-4696-b74d-a95312742dd8",
  "processed": 2,
  "duplicates": 0,
  "unknown_messages": []
}
```

Callback xử lý idempotent theo `event_id` và `message_id`.

## 8. State machine

### Delivery

```text
queued → submitting → accepted → sent
                   ↘ failed
queued/submitting → skipped
queued/accepted   → cancelled
```

Không cho callback cũ đổi `sent` ngược về `accepted`. Callback `failed` sau `sent` phải được ghi audit nhưng không hạ trạng thái nếu không có event loại delivery/bounce rõ ràng.

### Batch

- `completed`: mọi delivery kết thúc và không có lỗi.
- `partially_failed`: có cả `sent` và `failed/skipped`.
- `failed`: không email nào gửi thành công hoặc không submit được webhook.
- Progress UI = `(sent + failed + skipped) / total`.

## 9. Retry và idempotency

- Retry chỉ áp dụng cho timeout, HTTP 429 và HTTP 5xx.
- Không retry tự động HTTP 400/401/403 hoặc lỗi recipient/template.
- Backoff đề xuất: 30 giây, 2 phút, 5 phút; tối đa 3 attempt tự động.
- Retry dùng lại `message_id` và `idempotency_key`.
- Power Automate phải có kho idempotency hoặc kiểm tra message đã xử lý trước khi gửi, nếu không timeout có thể tạo email trùng.
- Nút “Gửi lại email lỗi” tạo batch retry mới nhưng liên kết delivery gốc và không gửi lại các dòng `sent`.

## 10. Các pha triển khai Django

### Pha A — Foundation và contract

- [x] Thêm environment settings webhook, timeout, secret và chunk size.
- [x] Tạo JSON Schema request/response/callback.
- [x] Viết client Power Automate với timeout, redacted logging và error mapping.
- [x] Thêm shared-secret verification cho callback (HMAC chiều callback để dành cho gateway ở pha hardening).
- [ ] Tạo sample payload và lệnh test contract độc lập.

### Pha B — Database và state machine

- [x] Tạo bốn bảng Batch, Delivery, Attempt, WebhookEvent.
- [x] Constraints cho idempotency và trạng thái.
- [x] Service chuyển trạng thái có khóa transaction, chống callback out-of-order.
- [ ] Backfill lịch sử `ShopEmailDelivery` phù hợp.
- [ ] Chuyển trạng thái email QLKV khỏi AccessLink sang Delivery chung.

### Pha C — Render HTML an toàn

- [ ] Thêm HTML template/editor cho PGD và QLKV.
- [ ] Sanitize HTML server-side.
- [ ] Render preview và placeholder bằng cùng service dùng khi gửi thật.
- [ ] Inline CSS/chuẩn hóa CTA link.
- [ ] Mã hóa payload có unique link; audit body phải che token.

### Pha D — Gửi batch bằng Celery

- [ ] Preflight toàn bộ người nhận trước khi tạo batch.
- [ ] Tạo access link và delivery transactionally.
- [ ] Chia chunk cấu hình được, mặc định 25 email và tối đa 50 email mỗi webhook.
- [ ] POST webhook, ghi Attempt và chuyển `accepted`.
- [ ] Retry theo policy; không tạo lại link khi retry transport.
- [ ] Hỗ trợ gửi thử một địa chỉ, không CC/BCC thật.

### Pha E — Callback và UI

- [x] Endpoint callback idempotent.
- [x] Recalculate batch counters sau callback.
- [ ] UI polling batch: tổng, accepted, sent, failed, progress.
- [ ] Xem lỗi theo PGD/QLKV và gửi lại riêng dòng lỗi.
- [ ] Toast khi batch hoàn tất hoặc có lỗi.
- [ ] Audit người gửi, template version và thời gian.

### Pha F — Tests và rollout

- [ ] Unit test render/sanitize HTML và placeholder.
- [ ] Unit test request headers, schema, timeout, 429/5xx retry.
- [ ] Unit test idempotency/callback trùng/out-of-order.
- [ ] Integration test bằng mock webhook.
- [ ] Contract test với Flow thật trên UAT.
- [ ] Canary gửi `datnm@f88.vn`.
- [ ] Canary một PGD test và một QLKV test.
- [ ] Sau đó mới gửi batch nhỏ 5–10, rồi 25, rồi toàn campaign.

## 11. Environment variables Django

```dotenv
EMAIL_TRANSPORT=power_automate
POWER_AUTOMATE_EMAIL_WEBHOOK_URL=https://...
POWER_AUTOMATE_EMAIL_WEBHOOK_SECRET=...
POWER_AUTOMATE_EMAIL_CALLBACK_SECRET=...
POWER_AUTOMATE_EMAIL_CALLBACK_URL=https://ida-chungtu.f88.co/api/integrations/power-automate/email/callback/
POWER_AUTOMATE_EMAIL_CONNECT_TIMEOUT=3.05
POWER_AUTOMATE_EMAIL_READ_TIMEOUT=30
POWER_AUTOMATE_EMAIL_CHUNK_SIZE=25
POWER_AUTOMATE_EMAIL_MAX_RETRIES=3
EMAIL_PAYLOAD_ENCRYPTION_KEY=...
EMAIL_FROM_ADDRESS=phongvanhanh@f88.vn
EMAIL_FROM_NAME=Phòng Vận Hành
```

Các secret triển khai bằng Kubernetes Secret, không ghi trực tiếp vào Deployment YAML hoặc repository.

> **Production go-live gate:** các biến webhook/secret/transport là cấu hình hạ tầng, không đưa lên UI. Web và worker phải được inject cùng cấu hình từ Kubernetes Secret. Chỉ bật `EMAIL_TRANSPORT=power_automate` sau khi callback HTTPS, quyền Send As và canary UAT đạt. Checklist chi tiết nằm tại `docs/power-automate-email-flow-build-checklist.md`.

## 12. Output bắt buộc sau khi hoàn tất Django

Codex/Django phải bàn giao đủ:

1. Migration và model Batch/Delivery/Attempt/WebhookEvent.
2. Power Automate client và Celery tasks gửi chunk.
3. Callback endpoint hoàn chỉnh, URL cụ thể trên local/UAT/prod.
4. JSON Schema machine-readable:
   - `power-automate-email-request.schema.json`
   - `power-automate-email-response.schema.json`
   - `power-automate-email-callback.schema.json`
5. Payload mẫu thực tế đã che token:
   - PGD request.
   - QLKV monitoring request.
   - QLKV confirmation request.
   - Accepted response.
   - Sent/failed callback.
6. Một `curl` hoặc Postman collection để test intake và callback.
7. Management command gửi canary tới `datnm@f88.vn`.
8. Danh sách environment variables và cách sinh encryption key/secret.
9. Kết quả unit/integration/contract tests.
10. Screenshot/UI hoặc đường dẫn màn hình theo dõi batch và retry email lỗi.

## 13. Checklist build Power Automate

### 13.1. Connection và quyền

- [ ] Tạo Outlook/Exchange connection bằng service account ổn định.
- [ ] Cấp quyền `Send As` cho `phongvanhanh@f88.vn`.
- [ ] Xác nhận gửi được tới domain ngoài `f88.co`.
- [ ] Không dùng tài khoản cá nhân làm connection production.
- [ ] Bật Secure Inputs/Outputs cho trigger, gửi email và callback.

### 13.2. Trigger và validation

- [ ] Tạo trigger `When an HTTP request is received`.
- [ ] Import JSON Schema request do Django bàn giao.
- [ ] Chỉ chấp nhận method POST và content type JSON.
- [ ] Kiểm tra `X-Schema-Version`.
- [ ] Kiểm tra `X-Webhook-Secret` hoặc Entra/HMAC ở gateway.
- [ ] Kiểm tra `batch_id`, `request_id`, `message_id` là UUID.
- [ ] Từ chối batch rỗng hoặc vượt kích thước thống nhất.
- [ ] Không ghi raw body chứa unique link vào log tùy chỉnh.

### 13.3. Xử lý từng message

- [ ] Dùng `Apply to each` trên `messages`.
- [ ] Giới hạn concurrency ban đầu 5; tăng sau khi kiểm thử throttling.
- [ ] Kiểm tra idempotency theo `message_id` trước khi gửi.
- [ ] Dùng action `Send an email from a shared mailbox (V2)`.
- [ ] Original mailbox address cố định `phongvanhanh@f88.vn`.
- [ ] Map To bằng join danh sách `to` với dấu `;`.
- [ ] Map CC/BCC tương tự.
- [ ] Map Subject từ `subject`.
- [ ] Map Body trực tiếp từ `body.content`; bật HTML.
- [ ] Không dùng expression thay placeholder nghiệp vụ trong Power Automate.
- [ ] Scope Try ghi kết quả `sent` và provider message id nếu connector trả về.
- [ ] Scope Catch ghi `failed`, error code và error message đã rút gọn.

### 13.4. Accepted response và callback

- [ ] Trả HTTP 202 với đúng `batch_id`, `request_id`, `provider_batch_id`.
- [ ] Callback Django bằng HTTPS sau khi xử lý.
- [ ] Callback có `event_id` duy nhất.
- [ ] Callback dùng shared secret/HMAC riêng, không dùng webhook intake secret.
- [ ] Retry callback khi timeout/5xx; giữ nguyên `event_id`.
- [ ] Không retry callback khi Django trả 400/401/403.
- [ ] Nếu Flow không cho tiếp tục sau action Response, tách Intake Flow và Worker Flow qua Dataverse/SharePoint/Azure Queue.

### 13.5. Vận hành và kiểm thử

- [ ] Test một email tới `datnm@f88.vn`.
- [ ] Kiểm tra From hiển thị `Phòng Vận Hành <phongvanhanh@f88.vn>`.
- [ ] Kiểm tra HTML, font, CTA link, tiếng Việt và link hết hạn.
- [ ] Test To/CC/BCC không trùng nhau.
- [ ] Test mailbox sai và callback `failed`.
- [ ] Test gửi lại cùng `message_id` không phát sinh email thứ hai.
- [ ] Test callback trùng không thay đổi counter lần hai.
- [ ] Test batch có cả thành công và thất bại.
- [ ] Kiểm tra Power Automate run history không lộ body/token do Secure Inputs/Outputs.
- [ ] Ghi nhận giới hạn connector/tenant và cấu hình concurrency phù hợp.

## 14. Điều kiện nghiệm thu cuối

- Email canary được nhận đúng From, To, CC/BCC, subject và HTML body.
- CTA mở đúng unique link PGD/QLKV.
- HTTP 202 chỉ hiện trạng thái `accepted`; callback mới chuyển `sent`.
- Email lỗi hiện đúng recipient và lý do, có thể retry riêng.
- Retry hoặc callback lặp không gửi trùng và không tăng counter sai.
- Batch UI khớp tổng delivery trong database.
- Secret, webhook URL và unique token không xuất hiện trong application log.
- Luồng SMTP cũ có feature flag/fallback trong giai đoạn rollout, sau khi Power Automate ổn định mới tắt.
