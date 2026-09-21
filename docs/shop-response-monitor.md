# Theo dõi phát hành và phản hồi PGD

- Tiến độ bước 3 = PGD đã gửi chính thức hoặc đã hết hạn riêng / tổng PGD có lỗi trong phạm vi tài khoản. Khi tất cả đã đóng phản hồi, tiến độ 100%. Không thay đổi câu trả lời PGD khi hết hạn.
- Zone thông tin đếm toàn bộ PGD trong dữ liệu chiến dịch thuộc phạm vi tài khoản, không chỉ trang hiện tại. “Đã nhận phát hành” đếm PGD có link được phát hành, không xác nhận email đã được nhận/đọc.
- “QLKV đã được gửi email” đếm số QLKV hiện tại khác nhau có địa chỉ email được đưa vào thư và tác vụ gửi đã báo thành công, trong phạm vi PGD tài khoản đang xem. Chỉ số này không có nghĩa người nhận đã mở/đọc thư; các tác vụ đang chờ hoặc thất bại không được tính.
- Bước 3 có hai tab đổi riêng phần lưới: “Theo Phòng giao dịch” và “Theo Quản lý khu vực”. Zone thống kê và bộ lọc liên kết QLV → QLKV → PGD dùng chung, giữ tham số khi chuyển tab. Tab QLKV gom số PGD, dòng lỗi và tiến độ phản hồi theo `Shop.manager.areaManager` hiện tại. Route xem lỗi theo hợp đồng cũ vẫn được giữ để tương thích nhưng không còn đặt trên màn hình monitor.
- Mỗi chiến dịch–QLKV có tối đa một link public hiện hành. Tạo/gửi lại sẽ đổi token và làm URL cũ mất hiệu lực. Link chỉ xem bộ dữ liệu của các PGD hiện thuộc QLKV đó, không có endpoint comment hoặc cập nhật phản hồi. Admin được tạo/copy, gửi email và gia hạn; tài khoản QLKV chỉ xem phạm vi xác định từ email/mã nhân viên trong Master Data.
- Màn hình tổng hợp QLKV (cả tài khoản đăng nhập và unique link) lọc được theo từ khóa, PGD, loại lỗi và lựa chọn phản hồi. Mọi cột trong lưới, gồm ngày phát sinh, đều sort tăng/giảm; filter được giữ khi sort và phân trang 100 dòng.
- Thông điệp trên link QLKV lấy từ `Campaign.area_manager_instructions`, cấu hình lúc tạo kỳ và sửa được trong popup cài đặt kỳ, độc lập với hướng dẫn PGD.
- Bộ lọc QLV dựa trên RegionManager của Shop.manager, không phải Region hay UserProfile.region. QLV → QLKV → PGD liên kết; trạng thái nhận nhiều giá trị GET `status`. Phân quyền vẫn áp dụng trước mọi bộ lọc.
- Mỗi trang 50 PGD. PGD còn mở phản hồi được xếp trước, sau đó tiến độ thấp nhất, mã PGD và ID. Deadline riêng được hiển thị tại từng dòng.
- Gia hạn chỉ admin, kỳ active, chưa submit và chưa có TeamReview của PGD. Không đổi deadline chiến dịch. Khi deadline mới vượt hạn link, hạn link riêng tăng đến deadline mới + 31 ngày. Đổi link và cập nhật deadline chung giữ các gia hạn riêng. Team review (web/bulk/Excel import) tôn trọng deadline riêng.
- Gửi email chỉ khi link còn nhận phản hồi. Vì DB chỉ lưu hash token, thao tác này yêu cầu xác nhận đổi link. Email Celery gửi tới shop_email, CC QLKV/QLV hiện tại của Master Data; link cũ bị vô hiệu. UI polling trạng thái tác vụ và chỉ tăng thống kê QLKV khi gửi thành công. Nếu broker lỗi sau khi đổi link, URL mới được trả lại để admin copy.
- Deadline chung được chỉnh trong popup. Các PGD đã có deadline riêng không bị ghi đè. QLKV chỉ được xem, lọc và mở chi tiết phản hồi ở bước 3; các thao tác link, email và deadline đều bị chặn cả ở UI lẫn backend.
- Link hết hạn không truy cập được (410); không xóa bản ghi phản hồi/historical audit.
- Header bảng được ghim phía dưới quy trình khi bảng cuộn tới vị trí đó, đồng bộ cuộn ngang và nhả khi cuộn ngược hoặc rời bảng. Chỉ bật trên trang monitor.

## Triển khai

Chạy `python manage.py migrate` (đến migration `0015_campaign_area_manager_instructions`), collectstatic, restart web và Celery worker. Cần cấu hình SMTP và media dùng chung. Local đã migrate; production chưa triển khai trong thay đổi này.
