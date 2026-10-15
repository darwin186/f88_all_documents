# Chỉ tiêu chứng từ — Xuất dữ liệu

Trang độc lập `/chi-tieu-chung-tu-v2/xuat-du-lieu/`, truy cập từ sub navbar **Xuất dữ liệu** trong **Chỉ tiêu chứng từ**. Không có nút xuất trên màn nhận/duyệt, không còn hai endpoint báo cáo dưới các màn đó.

Trang dùng chung `components/kpi_styles.html` và `components/kpi_subnav.html` với dashboard Chỉ tiêu: cùng chiều rộng layout, font 9–10px, thanh lọc cao 34px, card KPI và bảng `table-xs`.

## Bộ lọc và quyền

Chỉ tài khoản có nhóm `admin` được vào trang và tải file, đúng quy tắc dashboard Chỉ tiêu. Checker bị từ chối kể cả truy cập URL tải trực tiếp. Admin được lọc tất cả PGD, không bị giới hạn theo vùng.

Thiết lập bộ lọc, chọn tab Nhận chứng từ hoặc Duyệt chứng từ, bấm **Quét dữ liệu**, rồi **Xuất Excel**. Tab chứa toàn bộ thanh thao tác, số liệu và bảng xem trước. Chuyển tab giữ các bộ lọc đang nhập. PGD là danh sách checkbox nhiều lựa chọn, có tìm kiếm, đếm số đã chọn và bỏ chọn tất cả. Không chọn PGD nghĩa là tất cả PGD, nhưng vẫn phải có ít nhất một điều kiện lọc khác.

Giữ đúng 11 bộ lọc, theo thứ tự: Phòng giao dịch, Loại quyển chứng từ, Ngày phát sinh, Ngày nhận, Mã thùng, Mã thùng đối tác, Ngày duyệt, Người duyệt, Người nhận, Nghiệp vụ, Loại chứng từ.

Thu gọn hiển thị bốn mục đầu trên một hàng; mở rộng hiển thị 11 mục trong hai hàng (6 + 5). Màn hình hẹp cuộn ngang lưới thay vì tăng số hàng. Bộ lọc phụ đang có giá trị tự mở khi trang được tải lại; thu gọn không xóa giá trị.

Báo cáo nhận lọc Ngày duyệt/Người duyệt/Nghiệp vụ/Loại chứng từ thông qua chứng từ thuộc quyển. Tất cả điều kiện chứng từ phải khớp cùng một chứng từ; dùng EXISTS để không nhân bản dòng quyển. Báo cáo duyệt lọc Người nhận qua quyển gắn với chứng từ.

Bộ lọc ngày gồm từ/đến, không tự rút ngắn khoảng ngày. Khoảng ngày sai bị báo lỗi. Xem trước tối đa 25 dòng; file xuất mọi dòng phù hợp, không phụ thuộc phân trang. Quét và tải dùng cùng truy vấn.

## Mapping

Nhận: 10 cột, mỗi dòng là một `Folder`. Duyệt: 16 cột, mỗi dòng là một `DocumentsDetail`, thêm Mã thùng đối tác cuối file.

Ngày phát sinh là `Folder.folder_created_date`; ngày nhận là `Folder.lastest_received_date` trong cả hai báo cáo. Ngày duyệt là `DocumentsDetail.lastest_checked_date`, người duyệt là `lastest_checked_by.username`.

Báo cáo duyệt ưu tiên mã HĐCC, thiếu thì lấy GNN. Khách hàng giữ quy tắc màn duyệt: có `loan_id` lấy `loan_id.customer_name`, nếu không có lấy `contract_id.customer_id.customer_name` (viết hoa ký tự đầu như bảng hiện tại). PGD là `DocumentsDetail.shop_id.shop_name`, không nối thêm `shop_code` nội bộ. Thùng F88 và thùng đối tác lấy từ `DocumentsDetail.package_id`, mỗi loại một cột.

Báo cáo nhận lấy PGD, loại quyển, trạng thái, người nhận và thùng từ `Folder`. Phiên bản ghép Gốc/Bổ sung (`is_original`) và PSCT (`is_issue`). Trạng thái ghép tên trạng thái và Trễ hạn (`is_late`), hoặc Đúng hạn (`is_on_time`), theo thứ tự ưu tiên của màn nhận. Cột thùng ghép `F88: … | ĐT: …`; không có thì `—`. Không tự tính lại hạn khi xuất.

File có một dòng tiêu đề, bộ lọc Excel, cố định dòng 1, mã dạng text và ngày dạng ngày Excel. Dữ liệu phản ánh trạng thái mới nhất, không phải lịch sử giao dịch.

## Giới hạn và vận hành

Excel có tối đa 1.048.576 dòng mỗi sheet. Báo cáo giữ đúng một sheet theo mẫu, do đó cho phép tối đa **1.048.575 dòng dữ liệu**, trừ một dòng tiêu đề. Quét thấy vượt giới hạn thì hiện số dòng, báo lỗi và khóa nút xuất. Endpoint tải cũng đếm lại và từ chối; không cắt bớt dữ liệu hoặc tự chia sheet.

Có thể đặt Django setting `DOCUMENT_RAW_EXPORT_MAX_ROWS` thấp hơn để giới hạn vận hành; giá trị cao hơn không vượt được giới hạn Excel. Mặc định dùng giới hạn Excel.

Truy vấn chỉ đọc và tải trực tiếp, không tạo bản ghi lịch sử xuất hay tác vụ Celery. Dùng write-only workbook và đọc dữ liệu theo chunk. Không cần migration. Với file gần một triệu dòng, vẫn cần thời gian và tài nguyên cho truy vấn và tạo file; giới hạn dòng Excel không thay thế giới hạn tài nguyên/timeout của deployment.

Kiểm thử:

```bash
python manage.py test app_documents.tests.receiving.test_raw_reports --settings=documents.test_settings
```
