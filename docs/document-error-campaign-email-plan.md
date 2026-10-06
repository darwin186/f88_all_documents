# Kế hoạch email chiến dịch lỗi chứng từ

## Mục tiêu

Sau khi version dữ liệu đã publish, Admin cấu hình, kiểm tra và phát hành email riêng cho từng PGD. Email gửi tới `shop_email`, tự động CC Quản lý khu vực hiện tại, chứa unique link phản hồi và có đầy đủ trạng thái/audit để gửi lại khi lỗi.

## Nguyên tắc

- Mỗi PGD nhận một email riêng; không gom nhiều PGD trong To/CC/BCC.
- Chỉ Admin được cấu hình, gửi thử và phát hành email.
- Publish dữ liệu không tự gửi email. Gửi email là một bước xác nhận riêng.
- Chỉ dùng placeholder trong whitelist; không thực thi Django/Jinja template do người dùng nhập.
- `{{response_url}}` bắt buộc có trong body.
- Retry không được âm thầm gửi trùng; trạng thái phải theo dõi theo từng PGD.
- Không ghi raw access token vào application log.
- Email đã gửi lưu snapshot người nhận, subject và phiên bản template để audit.

## Placeholder hỗ trợ

- `{{campaign_code}}`
- `{{campaign_name}}`
- `{{report_month}}`
- `{{shop_code}}`
- `{{shop_name}}`
- `{{area_manager_name}}`
- `{{response_deadline}}`
- `{{link_expires_at}}`
- `{{response_url}}`
- `{{support_email}}`

## Pha 1 — Cấu hình, preview và preflight

- [x] Thêm cấu hình email riêng theo campaign.
- [x] Subject/body dùng placeholder an toàn.
- [x] Cấu hình tự động CC QLKV, CC/BCC bổ sung và tên hiển thị người gửi. PGD trả lời trực tiếp về địa chỉ From.
- [x] Đặt cụm nút email ngay dưới vùng tổng hợp số liệu bước 3.
- [x] Preview theo một PGD mẫu.
- [x] Preflight thống kê PGD/email hợp lệ và các lỗi Master Data.
- [x] Gửi email thử chỉ tới địa chỉ kiểm thử, không gửi CC/BCC thật và không phát hành link thật.
- [x] Chuẩn hóa cấu hình Microsoft Graph dùng chung cho web và worker.

## Pha 2 — Phát hành email hàng loạt

- [ ] Nút `Phát hành & gửi email` có màn hình xác nhận số lượng.
- [ ] Sinh link và delivery trong cùng thao tác để không mất raw token giữa hai bước.
- [ ] Chia lô Celery, giới hạn tốc độ và theo dõi tiến độ tổng.
- [ ] Idempotency chống double-click/gửi trùng.
- [ ] PGD thiếu email không chặn toàn bộ lô; ghi lỗi theo từng PGD.
- [ ] Retry riêng email thất bại.
- [ ] Retry giữ nguyên link nếu vẫn còn hiệu lực; chỉ `Đổi link` mới thu hồi link cũ.

## Pha 3 — Theo dõi và audit

- [ ] Thống kê Chưa gửi/Chờ gửi/Đang gửi/Đã gửi/Thất bại.
- [ ] Hiện người nhận To/CC/BCC, thời gian gửi, số lần thử và lỗi gần nhất.
- [ ] Xem snapshot subject/body template đã dùng mà không lộ token trong log.
- [ ] Xuất danh sách email lỗi để sửa trong Master Data.
- [ ] Cảnh báo nếu cấu hình email thay đổi sau khi một phần chiến dịch đã gửi.

## Pha 4 — Kiểm thử và rollout

- [x] Unit test render placeholder, recipient và preflight.
- [x] Unit test email thử không gửi tới PGD/QLKV thật.
- [ ] Staging redirect toàn bộ email tới mailbox kiểm thử.
- [ ] Production canary một shop test trước khi gửi toàn bộ.
- [ ] Kiểm tra quyền Graph `Mail.Send`, Exchange Application RBAC và giới hạn gửi của mailbox.

## Điều kiện phát hành

- Version hiện tại đã publish.
- Campaign chưa đóng/hủy và deadline còn hiệu lực.
- Template hợp lệ, có `{{response_url}}`.
- Có ít nhất một PGD với email hợp lệ.
- Microsoft Graph đã qua bước gửi thử.
