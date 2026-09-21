# Phản hồi PGD theo chiến dịch

- Master Data → Phản hồi PGD (`/master-data/response-options/`): admin quản lý
  danh mục chung, mã ổn định, tên, mô tả, thứ tự và trạng thái hoạt động.
- Form tạo kỳ và popup cài đặt có checkbox chọn bộ phản hồi. Cần ít nhất một mục.
- Khi chọn, chiến dịch lưu riêng mã và tên. Sửa/ngừng dùng trong Master Data
  không thay đổi các kỳ đã áp dụng hoặc câu trả lời cũ.
- Chiến dịch đang phản hồi chỉ được thêm lựa chọn, không bỏ bất kỳ lựa chọn cũ nào.
  Quy tắc được kiểm tra ở backend, kể cả khi đã hết deadline nhưng chưa chốt kỳ.
- Trước khi phản hồi, có thể bỏ mục chưa được PGD sử dụng. Kỳ đã chốt/hủy không
  đổi bộ phản hồi. Sửa hướng dẫn không thay đổi deadline.
- PGD refresh màn hình để thấy các mục vừa thêm. Autosave kiểm tra câu trả lời
  thuộc bộ lựa chọn của kỳ. Team review/monitor hiển thị tên từ dữ liệu theo kỳ.
- ChecklistTemplate/ChecklistQuestion vẫn là nền legacy cho kỳ chưa cấu hình.
  Migration giữ nguyên value/label cũ của các kỳ hiện hữu, không viết lại phản hồi.

Deploy: chạy migrations, collectstatic và restart web/worker như quy trình hiện tại.
