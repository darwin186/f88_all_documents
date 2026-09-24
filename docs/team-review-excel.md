# Excel team review

Tại bước 4, Admin xuất toàn bộ dữ liệu review của kỳ (không chỉ trang/bộ lọc đang xem), sửa hai cột **Kết luận review** và **Nhận xét team**, rồi import lại. Kết luận có droplist `Giữ lỗi / Loại lỗi`; nhận xét không bắt buộc. Dữ liệu PGD và dữ liệu gốc chỉ đọc.

Xuất/import chạy Celery, UI có spinner và polling tiến độ. Mỗi kỳ chỉ có một job đang xử lý cho mỗi loại thao tác. Nút tải nằm dưới nút xuất; không có danh sách lịch sử job.

Khu số liệu và thao tác Excel được gom thành một toolbar gọn. Tiến độ nằm ở cạnh dưới card quy trình bước 4, đổi màu đỏ → xanh theo phần trăm. Bộ lọc PGD phản hồi dùng các giá trị của kỳ (và phản hồi cũ còn tồn tại). Nhận xét hàng loạt chỉ áp dụng dòng tick trên trang hiện tại; có chế độ thêm/thay nhận xét và chọn kết luận chung. Tất cả cập nhật được kiểm tra phiên review, quyền admin, điều kiện PGD gửi/hết hạn và lưu lịch sử trong một transaction.

Với lỗi quyển, trạng thái nhận được tra trực tiếp từ Folder, `FolderStatus.is_received` và `lastest_received_date`, hỗ trợ cả dữ liệu nguồn chỉ có ID/code chưa gắn FK. Không tìm thấy quyển được hiển thị rõ, không suy đoán đã/chưa nhận. Cột trạng thái/ngày nhận có trên web và Excel; focus vào droplist kết luận và bấm lưu sẽ truy lại trạng thái. Không tự động giữ/loại lỗi. Template cũ 15 cột vẫn import được; template mới 17 cột có droplist ở O và snapshot ở Q.

Giới hạn file 50 MB, giải nén 512 MB, 100.000 dòng; ingress trên IDA cũng phải cho phép upload dung lượng tương ứng. Vòng xuất không dùng `sheet.max_row`/truy cập nguyên hàng trong mỗi lượt, tránh quét lại toàn bộ ô theo O(n²). Job quá 12 phút không cập nhật tiến độ được chuyển failed khi polling để có thể tạo lại (task hard limit 10 phút).

Mỗi dòng có ID lỗi và snapshot ký số. Import từ chối sai kỳ, trùng ID, sửa cột gốc, lựa chọn ngoài droplist, nhận xét quá dài, thay đổi đồng thời hoặc PGD chưa gửi/chưa hết hạn. Toàn bộ validation hoàn tất trước khi áp dụng trong transaction; chỉ thêm lịch sử `TeamReview`, không cập nhật phản hồi PGD hay xóa lỗi. Dòng bị bỏ khỏi file, hoặc dòng không thay đổi, được giữ nguyên. Dữ liệu thay đổi trên web cần xuất lại file.

Deploy: chạy migration `0011`, collectstatic và restart web. Với `APP_ROLE=web` (hoặc `FILE_JOBS_RUN_ON_WEB=true`), các job Excel chạy ngay trong web service và dùng `/app/media` của web; worker không cần chia sẻ media cho các job này. Gunicorn mặc định chờ tối đa 1.200 giây, nhưng timeout của Ingress/Nginx cũng phải được cấu hình tương ứng. Missing file trả thông báo 404 thay vì traceback 500.
