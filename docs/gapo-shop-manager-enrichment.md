# Bổ sung Trưởng PGD từ danh bạ Gapo

Tại **Master Data → Danh bạ Gapo**, super admin upload file Excel như hiện tại, sau đó mở **Đối chiếu Trưởng phòng giao dịch**. Bảng hiển thị thông tin đang lưu trong Shop và thông tin đề xuất từ file hiện hành. Upload, reimport và kích hoạt file cũ không tự ghi thông tin Trưởng PGD vào Shop.

**Áp dụng N dòng khớp duy nhất** cập nhật tất cả dòng sẵn sàng của file nguồn, kể cả trang khác và dòng ngoài kết quả tìm kiếm. Những dòng cần rà soát giữ nguyên dữ liệu. Có thể sửa danh bạ nguồn rồi nhập lại, hoặc chỉnh Shop qua Master Data rồi tải lại bản đối chiếu.

## Quy tắc ghép

- Lấy mã gồm 3 chữ cái và 5 chữ số ở đầu `department_name` và `Shop.shop_name`, ví dụ `AGG24019.Tân Châu`. Sau mã phải là dấu phân cách hoặc hết chuỗi. Chuẩn hóa chữ hoa và khoảng trắng đầu/cuối; không dùng `shop_code` dạng số để ghép.
- Chỉ lấy thành viên đang hoạt động, chức vụ đúng **Trưởng phòng giao dịch** (chuẩn hóa dấu, hoa/thường, khoảng trắng). Không ghép Phó trưởng phòng hoặc chuyên viên.
- Chỉ cập nhật khi có duy nhất một Shop, một ứng viên hợp lệ, Shop đang hoạt động và không phải Shop chỉ phục vụ mượn chứng từ.
- Phải đủ tên, mã nhân viên bắt đầu bằng F và email đúng định dạng. Áp dụng cùng bộ kiểm tra dữ liệu với chức năng sửa Shop hiện có.
- Ghép `full_name → shop_manager_name`, `employee_code → shop_manager_employee_code`, `email → shop_manager_email`. Mã nhân viên được chuẩn hóa thành chữ hoa.
- Không tìm thấy, thiếu dữ liệu, trùng người hoặc trùng Shop: báo lý do, không xóa thông tin đang có. Người có mã phòng ban không tìm thấy Shop cũng được liệt kê để rà soát.
- File cũ được kích hoạt lại có cảnh báo nếu tồn tại file mới hơn. Phải xem lại và chủ động áp dụng.

## Kiểm soát ghi dữ liệu

Bản đối chiếu có chữ ký, gắn người dùng và hết hạn sau 30 phút. Khi áp dụng, hệ thống kiểm tra lại file đang hiện hành, trạng thái import và dấu vân tay của dữ liệu nguồn/Shop. Nếu có thay đổi, yêu cầu tải lại bản đối chiếu. Các thay đổi cùng đợt ghi và lịch sử được xử lý trong một transaction; lỗi ghi lịch sử sẽ rollback cập nhật Shop. Import và kích hoạt danh bạ cũng thực hiện trong transaction để tránh đọc một phần dữ liệu đang nhập lại.

Mỗi Shop thay đổi tạo một `django.contrib.admin.models.LogEntry`, gồm người thực hiện, thời gian, nguồn `gapo_shop_manager_enrichment`, batch/file/checksum, dòng Excel, mã PGD, dữ liệu trước và sau. Dùng bảng lịch sử sẵn có; không cần migration mới. File thiếu/lỗi bị chặn áp dụng. Các dòng đã khớp không ghi lại lịch sử thừa.

## Kiểm tra

```console
.venv/Scripts/python.exe manage.py test app_documents.tests.test_gapo_shop_managers app_documents.tests.test_gapo_directory --settings=documents.test_settings --noinput
```

Lệnh kiểm thử dùng SQLite trong bộ nhớ và không cập nhật dữ liệu thật.
