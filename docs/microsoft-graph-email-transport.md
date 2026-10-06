# Microsoft Graph email transport

## Biến môi trường

```env
# Kênh mặc định cho các nút gửi đơn lẻ. Gửi thử/gửi hàng loạt vẫn cho chọn trên UI.
EMAIL_TRANSPORT=microsoft_graph

# Entra application (client credentials)
MS_TENANT_ID=<Directory tenant ID>
MS_APPLICATION_ID=<Application client ID>
MS_VALUE=<Client secret VALUE>

# Mailbox thật dùng để gửi. Có thể bỏ nếu DEFAULT_FROM_EMAIL đã đúng mailbox này.
MS_GRAPH_SENDER_EMAIL=phongvanhanh@f88.vn

# Tuỳ chọn
MS_GRAPH_CONNECT_TIMEOUT=10
MS_GRAPH_READ_TIMEOUT=30
```

`MS_SECRET_ID` và `MS_OBJECT_ID` không tham gia OAuth. Hệ thống cần **secret value** trong `MS_VALUE`, không phải secret ID.

Web và Celery worker phải nhận cùng cấu hình, sau đó restart/redeploy cả hai.

## Cấu hình Entra/Exchange cần IT xác nhận

- Microsoft Graph **Application permission**: `Mail.Send`.
- Đã cấp **admin consent** cho tenant.
- `MS_GRAPH_SENDER_EMAIL` là mailbox có thể gửi thư (user/shared mailbox), không chỉ là distribution list.
- Nếu tổ chức dùng Application Access Policy hoặc Exchange RBAC for Applications, app phải được phép truy cập đúng mailbox gửi.
- Không đưa secret/token vào log hoặc giao diện.

## Hành vi trong hệ thống

- Khi đủ cấu hình, UI gửi thử và gửi hàng loạt hiện thêm lựa chọn **Microsoft Graph**.
- Graph nhận HTML, To, CC và BCC từ template đã render.
- Worker lấy app-only token bằng client credentials rồi gọi
  `POST /v1.0/users/{sender}/sendMail`.
- HTTP `202` nghĩa là Graph đã nhận yêu cầu; không phải xác nhận người nhận đã đọc hay thư đã tới inbox.
- Mỗi lần gửi được ghi vào `dec_campaign_email_batch`, `dec_campaign_email_delivery` và
  `dec_campaign_email_attempt`.

## Kiểm thử UAT

1. Chạy `python manage.py migrate`.
2. Restart web và worker.
3. Mở cấu hình email của một kỳ, nhập hộp thư kiểm thử.
4. Chọn **Microsoft Graph** trong mục kênh gửi và bấm gửi thử.
5. Xác nhận UI báo đã xếp hàng, worker không có lỗi `MICROSOFT_GRAPH_*`, delivery chuyển thành `sent`, và email tới hộp thư kiểm thử.
6. Sau khi gửi thử đạt, thử một batch nhỏ trước khi gửi toàn bộ.
