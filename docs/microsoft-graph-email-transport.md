# Microsoft Graph email transport

## Biến môi trường

```env
# Entra application (client credentials)
MS_TENANT_ID=<Directory tenant ID>
MS_APPLICATION_ID=<Application client ID>
MS_VALUE=<Client secret VALUE>

# Địa chỉ hiển thị ở trường From.
MS_GRAPH_SENDER_EMAIL=vanhanh_chungtu@f88.vn

# Mailbox thật dùng để gọi /users/{mailbox}/sendMail. Có thể bỏ khi trùng From.
MS_GRAPH_MAILBOX_EMAIL=vanhanh_chungtu@f88.vn

# Tuỳ chọn
MS_GRAPH_CONNECT_TIMEOUT=10
MS_GRAPH_READ_TIMEOUT=30
MS_GRAPH_EMAIL_CHUNK_SIZE=25
```

`MS_SECRET_ID` và `MS_OBJECT_ID` không tham gia OAuth. Hệ thống cần **secret value** trong `MS_VALUE`, không phải secret ID.

Web và Celery worker phải nhận cùng cấu hình, sau đó restart/redeploy cả hai.

## Cấu hình Entra/Exchange cần IT xác nhận

- Microsoft Graph **Application permission**: `Mail.Send`.
- Đã cấp **admin consent** cho tenant.
- `MS_GRAPH_MAILBOX_EMAIL` là user/shared mailbox thực tế và nằm trong scope RBAC.
- Nếu `MS_GRAPH_SENDER_EMAIL` khác mailbox thực tế, Exchange phải cấp **Send As** cho mailbox thực tế trên địa chỉ From.
- Nếu tổ chức dùng Application Access Policy hoặc Exchange RBAC for Applications, app phải được phép truy cập đúng mailbox gửi.
- Không đưa secret/token vào log hoặc giao diện.

## Hành vi trong hệ thống

- Microsoft Graph là kênh gửi duy nhất của email chiến dịch; UI không hiển thị lựa chọn kênh.
- Graph nhận HTML, To, CC và BCC từ template đã render.
- Worker lấy app-only token bằng client credentials rồi gọi
  `POST /v1.0/users/{mailbox}/sendMail`; trường `message.from` lấy từ `MS_GRAPH_SENDER_EMAIL`.
- HTTP `202` nghĩa là Graph đã nhận yêu cầu; không phải xác nhận người nhận đã đọc hay thư đã tới inbox.
- Mỗi lần gửi được ghi vào `dec_campaign_email_batch`, `dec_campaign_email_delivery` và
  `dec_campaign_email_attempt`.

## Kiểm thử UAT

1. Chạy `python manage.py migrate`.
2. Restart web và worker.
3. Mở cấu hình email của một kỳ, nhập hộp thư kiểm thử.
4. Bấm gửi thử.
5. Xác nhận UI báo đã xếp hàng, worker không có lỗi `MICROSOFT_GRAPH_*`, delivery chuyển thành `sent`, và email tới hộp thư kiểm thử.
6. Sau khi gửi thử đạt, thử một batch nhỏ trước khi gửi toàn bộ.
