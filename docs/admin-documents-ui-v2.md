# AdminDocuments — bản UI đầu tiên

Mở `/admindocuments/documents/` bằng tài khoản có quyền quản lý hành chính.

Bản này áp dụng cho màn chọn nghiệp vụ, danh sách Văn bản hành chính, khung xem nhanh, popup tạo mới và popup tách thửa mở từ danh sách. Giấy hành chính, Công văn đến, Bưu phẩm và Quản trị dùng chung thanh điều hướng và bộ thành phần UI hành chính. Xem [hướng dẫn thành phần dùng chung](admin-shared-ui.md).

- Dùng layout và thanh điều hướng chung của Documents v2. Các mục hành chính nằm ngay trên nav cạnh logo; không có thanh subnav riêng dưới header. Khoảng cách nội dung tự cập nhật theo chiều cao nav khi xuống dòng trên màn hình hẹp.
- Tìm kiếm, Công ty, Loại văn bản, Loại nội dung, Ngày tạo văn bản và Ngày ban hành luôn hiển thị trong một khối bộ lọc. Ngày tạo chọn từ ngày–đến ngày trên cùng một lịch; Ngày ban hành lọc riêng một ngày. Các dropdown dùng menu bo góc, có tìm kiếm, đánh dấu lựa chọn hiện tại và hỗ trợ bàn phím. Dải nút phía dưới bộ lọc nằm bên phải, theo thứ tự Tạo văn bản → Áp dụng bộ lọc → Xóa bộ lọc. Xuất Excel là icon tải xuống 12px tại header cột thao tác (phía trên các nút …), có tooltip và tên truy cập; vẫn đồng bộ đầy đủ bộ lọc hiện tại.
- Hiển thị khoảng ngày mặc định mà server đang dùng (năm hiện tại).
- Các lựa chọn hiện thành chip bên trái dải nút trong khối bộ lọc của Văn bản hành chính. Chip tự xuống hàng trong vùng còn lại, không lấn vào các nút; trên màn hình hẹp, dải nút nằm phía dưới chip. Bấm × bỏ riêng một điều kiện và áp dụng ngay. Bỏ khoảng Ngày tạo hoặc Xóa bộ lọc dùng `created_all=1` để xem mọi năm, không tự khôi phục điều kiện năm hiện tại. Danh sách, phân trang, sắp xếp và Excel dùng cùng điều kiện ngày.
- Tổng số kết quả và phân trang ở phía trên bảng. Phân trang luôn hiện ba ô ‹ [trang hiện tại] ›, kể cả khi chỉ có một trang hoặc chưa có dữ liệu. Mũi tên không có trang tương ứng được vô hiệu; giữ điều kiện lọc và STT liên tục qua các trang.
- Bấm vào dòng dữ liệu, số hiệu hoặc tên văn bản để mở khung xem nhanh; có thể dùng Enter/Space khi focus dòng. Menu cuối dòng có Chỉnh sửa, Tạo văn bản tách thửa, Tạo văn bản tham chiếu và Vô hiệu; thao tác menu không mở xem nhanh.
- Popup tạo mới sắp theo từng hàng hai cột như mẫu cũ: Công ty / Loại văn bản; Loại nội dung bên trái; Tên văn bản toàn chiều ngang; Số hiệu tham chiếu / Tham chiếu tới văn bản; Người ký / Phòng ban; Ngày ban hành / Ngày hiệu lực; checkbox tham chiếu bên trái; Trạng thái / Ngày hết hiệu lực. Link/tệp và Ghi chú chiếm toàn chiều ngang, cuối form là Hủy / Lưu văn bản. Không có ô Mã ticket yêu cầu trong form tạo mới. Màn hẹp xếp một cột theo cùng thứ tự. Các trường vẫn gửi tới endpoint hiện có. Popup tách thửa dùng dịch vụ cấp số hiện có.
- Chỉnh sửa mở popup ngay trên danh sách, cả từ menu dòng và từ Xem nhanh. Liên kết chi tiết cũ chuyển về `/admindocuments/documents/?edit=<id>` để tự mở popup. Các giá trị ở hai cột; bấm giá trị để sửa trực tiếp. Enter/Lưu cập nhật một trường, Ctrl+Enter lưu ghi chú; chọn ngày, danh sách hoặc checkbox tự lưu. Hủy/Escape khôi phục giá trị đã lưu gần nhất.
- Chỉnh sửa từng giá trị dùng AJAX tại endpoint `field/`, khóa bản ghi trong transaction và chỉ ghi trường được yêu cầu (kèm số hiệu/đánh dấu tham chiếu khi chọn văn bản tham chiếu). Lỗi hiện ngay dưới trường và giữ nội dung đã nhập. Thành công cập nhật dòng tương ứng ngay trên danh sách, không tải lại trang.
- Xem nhanh có ba tab Thông tin / Đính kèm / Lịch sử, hỗ trợ chuyển tab bằng bàn phím. Lịch sử hiển thị các lần tạo/cập nhật, người sửa, thời gian và giá trị trước/sau; không đặt lịch sử trong popup chỉnh sửa.
- Tab Đính kèm trong Xem nhanh hiển thị tệp/link theo phiên bản mới nhất trước, trạng thái, người thêm và thời gian. Phiên bản đã đánh dấu xóa vẫn lưu thông tin, không còn liên kết mở/tải. Đánh dấu xóa dùng AJAX, cập nhật danh sách và giữ nguyên tab. Đầu tab có nút Đính kèm mở popup riêng ngay trên drawer, chọn tải tệp hoặc nhập link/thư mục. Bên dưới là toàn bộ phiên bản. Popup chỉnh sửa cũng có nút mở cùng popup đính kèm. Thêm tệp/link dùng AJAX và dịch vụ tạo phiên bản cũ, cập nhật danh sách cùng số phiên bản trên tab mà không tải lại trang. Danh sách phiên bản không còn trong popup chỉnh sửa hoặc tab Thông tin. Thao tác tạo văn bản tham chiếu và vô hiệu nằm trong menu … cuối dòng, không còn nút riêng trong popup hoặc Xem nhanh. Vô hiệu vẫn gửi POST kèm CSRF và yêu cầu xác nhận như trước.
- Xuất Excel giữ các điều kiện hiện tại, kể cả dấu `&`, dấu `+` và tiếng Việt trong ô tìm kiếm.
- Hai bộ lọc ngày dùng Flatpickr 4.6.13 với ngôn ngữ Việt, lưu cục bộ trong `admindocuments/vendor/flatpickr/` kèm giấy phép MIT. Popup tạo/sửa/tách thửa tiếp tục dùng Flowbite Datepicker 1.3.0 từ đường dẫn npm cố định; `datepicker_assets` là block cho phép base của module chọn bộ lịch mà không đổi cấu hình các màn khác.
- Số ngày và giá trị ngày dùng màu primary `#00844A`, nền trắng. Bấm ra ngoài, chuyển focus sang trường khác, cuộn form hoặc thay đổi kích thước cửa sổ sẽ đóng lịch, cả trong popup tạo mới, chỉnh sửa và tách thửa. Chỉ một lịch được mở tại một thời điểm. CSS riêng của module buộc `.adm-datepicker.hidden` ẩn thực sự: Flowbite 1.3 vẫn giữ `.active` khi đóng, khiến `.datepicker.active` lấn át utility `.hidden` và làm lịch trông bị treo/chồng lên nhau.
- Màu trạng thái trong lưới và khung xem nhanh đọc `AdmDocumentStatus.badge_text_color` / `badge_bg_color`. Chỉnh hai màu tại Danh mục → Trạng thái văn bản → Lưu màu; yêu cầu quyền `change_admdocumentstatus`. Trạng thái mới cũng có hai ô chọn màu. Django Admin hỗ trợ cùng cấu hình.

Khi triển khai, chạy `python manage.py migrate app_admindocuments` để áp dụng migration `0038_admdocumentstatus_badge_colors` trước khi chạy ứng dụng. Migration bổ sung hai trường màu và màu ban đầu cho mã 100/101/102/103; không đổi tên, mã, liên kết văn bản hoặc quy tắc cấp số. Các trạng thái khác có màu trung tính và chỉnh được trong cấu hình.

Cần phục vụ các static assets `admindocuments/css/documents_v2.css`, `admindocuments/js/documents_v2.js`, `admindocuments/js/document_filters.js`, `admindocuments/js/document_edit_modal.js` và thư mục `admindocuments/vendor/flatpickr/` (collectstatic theo quy trình hiện tại). Phiên bản cache CSS chung, JS bộ lọc và form controls là `20261017-1`, JS danh sách là `20261016-6`, JS chỉnh sửa là `20261016-5`. Bổ sung `admin_ui.css/js?v=20261017-1` cho toàn module.

Ảnh trong `docs/previews/admin-documents-list.png` và `admin-documents-create.png` dùng dữ liệu mẫu trong SQLite tạm để duyệt bố cục.

Kiểm tra lỗi lịch bị treo trên Chrome: 15 kiểm tra đạt, gồm trạng thái hiển thị thực tế bằng computed style, chuyển giữa các trường ngày, chọn ngày khi AJAX còn chờ, chọn lại cùng ngày, bấm ra ngoài, cuộn, resize, hủy và đóng/mở lại popup.

Các ô ngày trong popup tạo mới khai báo `autocomplete="off"` như popup chỉnh sửa, tách thửa và bộ lọc, để trình duyệt không gợi ý các ngày đã nhập đè lên lịch. Vẫn cho phép nhập ngày trực tiếp.

Màn chọn nghiệp vụ: card Văn bản hành chính ở trang chủ mở `/admindocuments/workflows/`. Bốn thẻ Văn bản hành chính / Giấy tờ hành chính / Công văn đến / Bưu kiện đến dùng kiểu thẻ chọn flow của Campaign, lưới hai cột trên desktop và một cột trên màn hẹp. Mỗi thẻ có hai nút Tạo mới và Xem danh sách. Hai thẻ Văn bản hành chính/Giấy tờ hành chính có thêm nút Số hiệu tương ứng, mở đúng tab quản lý số hiệu và chỉ hiện khi có quyền quản lý hành chính.

Tạo mới dùng `?create=1` để tự mở popup hiện có của văn bản, giấy tờ và công văn; bưu kiện đi thẳng vào form tiếp nhận hiện có. Xem danh sách bưu kiện dùng `?pane=list`. Các URL danh sách cũ tiếp tục hoạt động. Màn chọn nghiệp vụ yêu cầu đăng nhập; chỉ nhóm có quyền quản lý hành chính mới dùng hai thẻ văn bản/giấy tờ, các tài khoản còn lại có thể vào công văn/bưu kiện theo quyền sẵn có. Không thay đổi quyền tạo hay cấp số của các endpoint.

Ảnh màn chọn nghiệp vụ: `docs/previews/admin-documents-workflows.png`.

Form Công văn đến cho phép chọn Công ty nhận ngay trong popup, để luồng Tạo mới từ thẻ hoạt động độc lập với menu chọn công ty ở danh sách. Kiểm tra: 4 test quyền truy cập/luồng công văn đạt; Chrome kiểm tra đủ bốn luồng tạo mới, danh sách bưu kiện và bố cục màn chọn trên desktop/màn hẹp đều đạt.

Thông báo của AdminDocuments dùng chung `includes/notifications.html` cùng `notifications.css/js` trên layout cũ, layout v2, màn chọn nghiệp vụ và trang xác nhận bưu kiện. Toast nằm góc trên bên phải, dùng manual popover để nổi trên dialog đang mở mà không lấy focus. Nội dung đầy đủ, xuống dòng và ngắt URL dài; mọi loại toast tự đóng sau 7 giây, hoặc đóng sớm bằng nút ×. Thông báo chỉnh sửa nêu số văn bản, trường và giá trị; thêm/xóa đính kèm nêu số văn bản, phiên bản và tên tệp/link. Các lỗi tại trường vẫn giữ cạnh ô nhập để sửa.

Bảng Văn bản hành chính tăng một cỡ chữ: nội dung và số hiệu 11px, tiêu đề cột/trạng thái 10px. Văn bản tách thửa hiển thị icon nhánh rẽ 14px cạnh số hiệu, tooltip “Văn bản tách thửa”, thay cho badge chữ. Các phần khác giữ cỡ chữ hiện có.

Static bổ sung: `admindocuments/js/document_attachments.js`, `admindocuments/js/notifications.js`, `admindocuments/css/notifications.css`, phiên bản cache `20261016-1`, riêng notifications JS là `20261016-2`. Popup đính kèm chống gửi trùng khi đang lưu; nếu đã lưu nhưng tải danh sách lỗi, đóng popup và báo cảnh báo, không yêu cầu gửi lại. Kiểm tra trước đó: 23 test Django và 21 kiểm tra Chrome đạt, bao gồm tệp, link, lỗi mạng, dữ liệu không hợp lệ, trạng thái chờ, cập nhật phiên bản/số lượng, toast dài và toast trên dialog.

Ảnh popup đính kèm và toast: `docs/previews/admin-documents-attachment-popup.png`.

Danh sách bỏ tiêu đề Văn bản hành chính phía trên bộ lọc; tiêu đề tab trình duyệt và mục điều hướng giữ nguyên. Số hiệu ở lưới, Xem nhanh và popup chỉnh sửa có icon sao chép 12px cạnh bên. Sao chép dùng Clipboard API, có phương án dự phòng khi API không khả dụng/từ chối. Thành công hiển thị toast với nguyên số hiệu; thất bại hiển thị hướng dẫn sao chép thủ công. Bấm icon không mở drawer hoặc gửi form.

Paginator Văn bản hành chính và Giấy hành chính dùng các ô vuông bo góc, viền 2px, cỡ tối thiểu 28px và số 11px. Trang hiện tại có nền/viền primary `#00844A`, số trắng; hai mũi tên nền trắng, hover xanh nhạt, màu xám khi vô hiệu. Hiện tối đa 5 số trang giữa hai mũi tên: đầu danh sách là [1] [2] [3] [n−1] [n], khi chuyển trang tự điều chỉnh để luôn có trang hiện tại; một trang vẫn hiện ‹ [1] ›. Nút Xóa bộ lọc dùng nền xám, cùng chiều cao với hai nút bên cạnh.

Bộ lọc mới: 27 test Django đạt (bộ lọc ngày, Excel, chỉnh sửa và chọn nghiệp vụ); 20 kiểm tra Chrome đạt ở mỗi kích thước 1500px và 504px, gồm dropdown, tìm kiếm, bàn phím, chọn khoảng ngày, chip, Excel, icon tách thửa, bố cục và bốn loại toast tự đóng sau 7 giây. Ảnh dữ liệu mẫu: `docs/previews/admin-documents-filters.png`.


## Giấy hành chính

`/admindocuments/paper-documents/` kế thừa `base_v2.html`, dùng chung thanh nav, kích thước chữ, bộ lọc/dropdown/chip, icon sao chép, toast 7 giây, popup chỉnh sửa từng giá trị và paginator tối đa 5 số trang, một trang dùng ‹ [1] ›. Mục Giấy hành chính được đánh dấu trên nav. Không có tiêu đề lớn hoặc thanh tab loại giấy riêng phía trên.

- Bộ lọc gồm tìm theo số hiệu/nội dung/mã vận đơn, Loại giấy, Miền, Tình trạng, Phòng giao dịch và một ô chọn khoảng Ngày tạo. Mặc định năm hiện tại; bỏ chip Ngày tạo hoặc Xóa bộ lọc xem mọi năm. Ba nút Tạo giấy hành chính / Áp dụng bộ lọc / Xóa bộ lọc nằm cùng dải; Xóa bộ lọc nền xám.
- Lưới giữ thông tin của giấy tờ, thêm tình trạng và STT liên tục qua các trang. Xuất Excel là icon trong header cột …; cột thao tác cố định bên phải khi cuộn ngang. Danh sách, phân trang, sắp xếp và Excel dùng chung hàm lọc. Chuỗi Excel được lưu dưới dạng văn bản, kể cả nội dung bắt đầu bằng dấu bằng.
- Bấm dòng hoặc số hiệu/nội dung mở Xem nhanh, có tab Thông tin / Vận chuyển và nút chỉnh sửa. Menu … có chỉnh sửa và ẩn/thu hồi số hiệu. Chỉnh sửa dùng cùng controller popup với Văn bản hành chính; tự lưu danh sách, Enter/Lưu cho văn bản, Hủy giữ giá trị đã lưu. Endpoint `paper-documents/<id>/field/` khóa bản ghi và chỉ lưu trường được yêu cầu. Không thay đổi số hiệu khi sửa, giữ yêu cầu có PGD hoặc phòng ban nội bộ; các danh mục cũ không còn hoạt động vẫn hiển thị và không ngăn cập nhật trường khác.
- Popup tạo đọc từ trên xuống theo hai cột và dùng dropdown có tìm kiếm. Tab tạo theo file Excel giữ quy trình tải mẫu → kiểm tra file → lưu, dùng các endpoint nhập và cấp số hiện có. Thay file hủy mã kiểm tra cũ, tránh lưu nhầm file. Thông báo lỗi gồm đủ chi tiết từng dòng; biểu mẫu không hợp lệ giữ giá trị đã nhập và tự mở lại popup.
- Không thêm schema hoặc migration. Tiếp tục yêu cầu đăng nhập và quyền quản lý hành chính cho danh sách, chi tiết, xuất và cập nhật. Luồng ẩn/thu hồi vẫn dùng POST, CSRF và xác nhận như trước.

Static mới `admindocuments/js/paper_documents.js?v=20261016-1`; triển khai cùng CSS/JS chung nêu trên qua collectstatic. Ảnh dữ liệu mẫu: `docs/previews/paper-documents-list.png`, `paper-documents-create.png` và `paper-documents-edit.png`.

Kiểm tra Giấy hành chính: 39 test Django đạt (12 test mới và 27 test liên quan Văn bản hành chính/chọn nghiệp vụ); 23 kiểm tra Chrome đạt ở mỗi kích thước 1500px và 504px. Bao gồm quyền/CSRF, bảo toàn số hiệu khi sửa, ngày tạo, bộ lọc kết hợp, xuất Excel, lỗi biểu mẫu giữ dữ liệu, danh mục cũ, xem nhanh, popup sửa, sao chép và quy trình kiểm tra/lưu file Excel.

Popup tạo văn bản theo mẫu cũ đã kiểm tra trên Chrome: đúng thứ tự/kích thước các hàng, trạng thái mặc định/màu cấu hình, dropdown người ký/phòng ban/tham chiếu, ba lịch ngày đóng khi ra ngoài, chuyển chế độ đính kèm và giá trị gửi form. Ảnh mới: `docs/previews/admin-documents-create.png`.

Danh sách Văn bản hành chính và Giấy hành chính giữ bộ lọc, chip và paginator phía trên vùng cuộn dữ liệu. Tiêu đề cột dùng sticky trong cùng vùng cuộn với các dòng, nên luôn khớp khi cuộn ngang. Bố cục chiếm chiều cao viewport còn lại dưới nav; chiều cao nav vẫn được đo bằng ResizeObserver. Dropdown/lịch và các popup tiếp tục nổi trên bảng. Kiểm tra Chrome: 12 kiểm tra đạt ở mỗi màn và mỗi kích thước 1500px/504px, gồm cuộn lên/xuống/ngang, chip xuống hàng, menu/lịch và header popup.


Lịch trong popup tách thửa: khi bấm trực tiếp vào ô ngày (span không nhận focus), Chrome có thể chuyển focus từ input về dialog. Sự kiện focusin đóng lịch trước sự kiện click chọn ngày, dẫn đến ô ngày vẫn trống. `document_form_controls.js` giữ focus của input khi mousedown trong lịch thuộc dialog; vẫn cho phép focus các input/select/textarea của lịch nếu có. Thao tác chọn ngày và chuyển tháng tiếp tục chạy qua click, không thay đổi giá trị hoặc định dạng gửi server. Script dùng cache `20261020-1`.


Kiểm tra hồi quy lỗi chọn ngày: Chrome với chuột ở 1500px và thao tác chạm ở 504px, 43 kiểm tra mỗi lượt đều đạt. Trang Số hiệu bắt đầu chưa có form, tải popup qua AJAX rồi bấm/chạm trực tiếp để chọn cả ba ngày, kiểm tra giá trị FormData, tự đóng sau chọn, mở lại, chuyển tháng, chuyển ra ngoài lịch và đóng/mở popup để tạo instance mới. Kiểm tra này dùng thao tác đầu vào trình duyệt thực tế, không dùng setDate để giả lập chọn ngày.
