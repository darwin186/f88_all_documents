# Mail Merge — bản xem thử giao diện

Mở `/error-campaigns/mail-merge/preview/` bằng tài khoản admin. Có thể truy cập từ tab Mail Merge trên danh sách chiến dịch. Danh sách chung không còn hiển thị steps cố định của Book lỗi; các màn nghiệp vụ Book lỗi vẫn giữ workflow hiện tại.

Nút Tạo chiến dịch mở `/error-campaigns/campaigns/new/`, yêu cầu chọn loại Chứng từ bản cứng hoặc Mail Merge, không chọn sẵn. Chứng từ bản cứng chuyển tới form hiện tại với `workflow_type=hard_copy` (POST cũng bắt buộc gửi giá trị này). Mail Merge chuyển tới `?step=1&mode=create`, mở cấu hình với tên trống và bỏ qua bản nháp mẫu đã lưu trước đó. Việc tạo chiến dịch Mail Merge thật vẫn chưa triển khai; POST loại Mail Merge bị chặn để không tạo nhầm Book lỗi.

Mặc định mở bước 3 để review bộ thiết kế bảng. Có đủ sáu bước tương tác: Cấu hình, Tải dữ liệu, Thiết kế bảng, Mapping PGD/email, Phát hành/theo dõi, Chốt/báo cáo.

Thử chọn cột, đổi tên, ẩn/hiện với PGD, thay kiểu nhập, chỉnh droplist, thêm/xóa cột phản hồi; đổi nguồn danh sách để xem dữ liệu mẫu. “PGD nhìn thấy” và “Xem giao diện PGD” dùng các cột được hiện và chỉ các dòng của PGD được chọn. Dropdown bắt buộc được kiểm tra khi gửi phản hồi mẫu. Cấu hình ngày giờ dùng lại component Flatpickr của Campaign.

Bản này chỉ để duyệt UI:

- Không tạo chiến dịch hay ghi phản hồi vào database.
- File được chọn chỉ dùng tên tệp minh họa; chưa phân tích/upload file lên server.
- Email, phát hành/thu hồi link và chốt kết quả là mô phỏng trên dữ liệu mẫu.
- Nút Lưu bản nháp lưu thiết kế mẫu trong localStorage của trình duyệt. Có thể xóa key `f88-mail-merge-ui-preview-v1` để trở về mẫu ban đầu.
- Xuất CSV tải được từ dữ liệu mẫu hiện tại; xuất Excel và xử lý dữ liệu thực sẽ triển khai sau khi duyệt UI.

Ảnh: `docs/previews/mail-merge-design.png`.

Các kiểm thử Django riêng của `app_document_campaigns.tests.test_mail_merge_preview` đã pass, bao gồm chọn loại, phân nhánh form, kiểm tra quyền và chặn tạo nhầm Book lỗi từ loại Mail Merge. Luồng tạo Book lỗi hiện hữu cũng được kiểm tra với loại Chứng từ bản cứng. Kiểm thử workflow Book lỗi mở rộng chạy được các màn tạo kỳ, chuẩn bị dữ liệu và phản hồi; riêng `campaign_review` gặp lỗi SQLite hiện hữu `no such column: dec_campaign_error.folder_id`, chưa xử lý trong phạm vi UI này. Đã kiểm tra trên Chrome các bước, bộ thiết kế cột, droplist PGD, mapping, lịch ngày giờ, thu hồi/chốt mẫu. Không cần migration; khi deploy cần collectstatic cho hai asset `mail_merge_preview.css/js`.
