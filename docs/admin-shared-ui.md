# Thành phần UI dùng chung cho Hành chính

Giấy hành chính và các màn Văn bản hành chính, Công văn đến, Bưu phẩm/Bưu kiện, Danh mục, Quản lý số hiệu và Cấu hình nhắc nhận dùng cùng giao diện hành chính.

- Thanh điều hướng trên cùng, đánh dấu màn đang mở và giữ điều kiện hiển thị theo quyền hiện tại.
- Dropdown bo góc, tìm kiếm, lựa chọn đang chọn và đóng khi ra ngoài/Escape. Giá trị vẫn gửi bằng trường select gốc; danh mục thay đổi được cập nhật vào menu.
- Bộ lọc có chip bỏ nhanh nằm bên trái dải nút, tự xuống hàng. Nút xóa nền xám, giữ màn/tab đang xem.
- Một slicer khoảng ngày thay cặp từ/đến ngày trong các bộ lọc cũ; giá trị gửi về server vẫn là `start_date`/`end_date` định dạng `Y-m-d`. Các biểu mẫu nghiệp vụ giữ nguyên tên trường và định dạng ngày của endpoint tương ứng.
- Bảng dùng chữ nội dung 11px, tiêu đề 10px, header cố định trong vùng cuộn; paginator màu primary luôn hiện trên các danh sách có phân trang. Riêng Văn bản hành chính/Giấy hành chính dùng ô 28px và tối đa 5 số trang (đầu danh sách: ‹ [1] [2] [3] [n−1] [n] ›), tự điều chỉnh để luôn hiển thị trang đang xem; một trang dùng ‹ [1] ›. Các danh sách khác giữ paginator ba ô hiện tại.
- Nút, ô nhập, panel, popup và drawer dùng chung màu primary `#00844A`, nền trắng, viền và góc bo. Toast ở góc phải trên cùng, nội dung đầy đủ và tự đóng sau 7 giây.

Trang xác nhận bưu kiện công khai dùng cùng màu, chữ và panel; không thêm thanh điều hướng nội bộ vào các trang này.

## Cấu trúc dùng lại

`templates/admindocuments/base_v2.html` tải toàn bộ thành phần chung một lần. `base.html` là lớp tương thích cho các trang cũ; nội dung trang dùng block `admin_content`. Các màn dùng block `admin_page_class=adm-shared-page` được chuẩn hóa bảng, form và panel; danh sách Văn bản/Giấy hành chính giữ bố cục workspace riêng.

- `static/admindocuments/css/admin_ui.css`: giao diện chung, bổ sung cho `documents_v2.css`.
- `static/admindocuments/js/admin_ui.js`: dropdown, bộ lọc/chip, lịch và khởi tạo nội dung được thêm động.
- `static/admindocuments/js/document_form_controls.js`: controller dropdown và biểu mẫu dùng lại cho popup.
- `includes/filter_chips.html`: vùng chip; controller riêng có thể gọi `window.adminUi.mountChips(form, container, {values, remove})`.
- `includes/pagination.html`: nhận `page` là Django Page; giữ đầy đủ query và các tham số lặp qua template tag `admin_query`.
- `templatetags/admin_ui.py`: trạng thái nav và query phân trang.

Các form GET hiện có được bổ sung UI tự động. Form có controller bộ lọc riêng dùng `data-adm-filters`; trường cần giữ điều khiển trình duyệt có thể khai báo `data-ui-native`. Không khai báo hai trường cùng tên cho cùng một điều kiện lọc.

Không thay đổi quyền truy cập, quy tắc cấp số, trạng thái nghiệp vụ hoặc endpoint gửi thông báo. Những tab/chức năng riêng như phiên bản đính kèm, lịch sử và vận chuyển vẫn theo dữ liệu hỗ trợ của từng nghiệp vụ. Triển khai static mới bằng quy trình collectstatic hiện tại.

## Kiểm tra

7 test Django cho các thành phần chung đạt. Chrome kiểm tra 10 màn trên hai chiều rộng 1500px/504px: 20 lượt đạt, gồm dropdown/tìm kiếm, danh mục cập nhật động, chip/bỏ lọc, khoảng ngày và giá trị gửi server, phân trang, chữ bảng và cuộn ngang. Form tạo Văn bản hành chính cũng được kiểm tra trên hai kích thước, gồm danh mục phụ thuộc, màu trạng thái, ngày, tham chiếu và giá trị gửi form.

Lần chạy toàn module 136 test còn một ca thất bại: `test_manual_change_to_pkg_processing_cancels_pending_reminder` nhận 403 thay vì 302 ở thao tác đổi trạng thái bưu phẩm. Điều kiện phân quyền endpoint này không được sửa trong thay đổi UI.

Ảnh dữ liệu mẫu: `previews/admin-shared-paper.png`, `admin-shared-incoming.png`, `admin-shared-parcels.png` và `admin-shared-master.png`.


## Tổ chức lại module

- Gỡ trang Tổng quan, bộ lọc, biểu đồ và CSV của Tổng quan. `/admindocuments/` chuyển về `/admindocuments/workflows/`; `/admindocuments/dashboard/export/` không còn phục vụ báo cáo.
- Danh bạ Gapo nằm tại `/master-data/gapo-directory/` (`master_data_gapo_directory`) và menu Master Data. Chỉ `is_superuser` được mở, tải file, kích hoạt hoặc nhập lại dữ liệu; nhóm admin/nhân viên hành chính không được cấp quyền này. View và template thuộc Master Data, tái sử dụng dịch vụ nhập dữ liệu bưu phẩm hiện có. Các bảng dữ liệu và chức năng tìm người nhận bưu phẩm giữ nguyên.
- Đường dẫn danh bạ cũ chỉ dành cho super admin: GET chuyển sang Master Data và giữ truy vấn; POST cũ vẫn được xử lý để tránh mất file gửi từ trang đang mở. Các thao tác thành công quay về trang Master Data mới.
- Hai thẻ Văn bản hành chính và Giấy tờ hành chính ở màn chọn nghiệp vụ có thêm nút số hiệu. Các nút mở `/admindocuments/counters/?tab=admin` và `?tab=paper`, vẫn yêu cầu quyền quản lý hành chính. Nút Số hiệu dùng nhãn gọn, nền trắng và chữ xanh primary, cùng hàng với Tạo mới. Phần header phía trên các thẻ đã bỏ; bấm vùng trống trên thẻ có quyền xem sẽ mở danh sách, các nút giữ đích riêng. Xem danh sách và vùng trống của thẻ Bưu kiện mở màn bưu kiện đã nhận, chỉ hiển thị khi có quyền xem màn này; Tạo mới vẫn mở tiếp nhận bưu kiện.
- Bố cục 6 màn liên quan được kiểm tra trên Chrome 1500px/504px: 12 lượt đạt, không có lỗi JavaScript hoặc tràn ngang. 25 test quyền, CSRF, điều hướng, bộ thành phần chung, upload danh bạ, tìm người nhận và tạo Công văn đến đạt.

Ảnh sau khi tổ chức lại: `previews/admin-reorganized-workflows.png` và `previews/admin-reorganized-gapo.png`.
