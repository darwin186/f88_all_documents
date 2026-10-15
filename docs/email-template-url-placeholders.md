# Link biến trong email QLKV

Triệu chứng: link QLKV dẫn tới `/master-data/email-templates/%7B%7Bmanager_url%7D%7D` thay vì unique link của chiến dịch. Đây là biến URL đã bị URL-encode và có thể được trình duyệt ghép với đường dẫn trang soạn mẫu; renderer trước đây chỉ thay thế token dạng `{{manager_url}}`.

Bản sửa:

- Trình soạn thảo tạo anchor với thuộc tính href nguyên bản, giữ token thay vì dùng `execCommand(createLink)`; click link trong ô soạn thảo không điều hướng.
- Client và server chuẩn hóa token URL bị mã hóa; phục hồi cả trường hợp token đứng cuối đường dẫn `/master-data/email-templates/`. Không bỏ tiền tố của URL bên ngoài hoặc thay đổi URL có query/fragment.
- Khi dựng email/preview, chuẩn hóa link trước khi thay token. Cả snapshot chiến dịch cũ và template master cũ được xử lý khi render, không cần migration hay cập nhật hàng loạt database.
- Áp dụng cho manager_url (Step 3/5), response_url và các biến link báo cáo/hướng dẫn.

Vận hành: deploy mã Python và template/JavaScript, chạy collectstatic theo quy trình hiện tại, restart web và worker xử lý email để cả hai dùng renderer mới. Cache version của email_rich_editor.js đã tăng. Không cần migration. Email đã gửi có nội dung cố định; sau deploy cần gửi lại từ chiến dịch để có unique link đúng. Không tự suy đoán token/campaign từ URL lỗi vì URL đó không có thông tin xác định người nhận hay kỳ.

Kiểm thử hồi quy: `test_email_template_links`, `test_email_template_master`, `test_microsoft_graph_email` và các luồng cấu hình/gửi email QLKV của `test_response_flow`. Các test gửi thư mock transport, không gửi thư thật.
