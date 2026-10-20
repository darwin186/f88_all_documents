# Toast (thông báo)

Trạng thái: 🟢 **Đã áp dụng toàn hệ thống** — văn bản hành chính, giấy hành chính, công văn đến, bưu kiện, chứng từ bản cứng v2, giao dịch đảm bảo, mượn chứng từ, master data, ca làm việc, profile, campaign (book lỗi), trang PGD trả lời, trang đăng nhập (v1). Mọi hệ thống thông báo cũ đã bị thay thế.

Giao diện: thẻ trắng bo tròn lớn, ô icon vuông bo góc có màu theo loại ở bên trái, **tiêu đề đậm + thời gian** ở hàng đầu, mô tả bên dưới, và (tuỳ chọn) nút hành động, thanh tiến độ, dòng thông tin, vòng phần trăm.

Xem trực quan và bắn thử: mở `docs/ui-kit/demo/toast.html` bằng trình duyệt.

## Cách dùng

```js
// Ngắn gọn
uiToast.success('Đã lưu thay đổi.');
uiToast.error('Số 15 đã được sử dụng.');
uiToast.warning('Còn 3 phòng giao dịch chưa có email nhận.');
uiToast.info('Có 5 bưu kiện mới.', {icon: 'package'});

// Đầy đủ
uiToast({
  type: 'success',                // success | error | warning | info | neutral | accent
  icon: 'file',                   // tuỳ chọn, xem bảng icon
  title: 'Báo cáo đã sẵn sàng',   // mặc định theo loại
  message: 'Báo cáo tháng 10 đã được tạo.',
  time: '21 phút',                // mặc định "Vừa xong"; time:false để ẩn
  action: {label: 'Tải file Excel', icon: 'download', href: url},   // hoặc onClick
  meta: [{icon: 'user', text: 'PGD Cầu Giấy'}, {icon: 'clock', text: 'còn 3 giờ'}],
});
```

Mọi giá trị chữ được gán dạng **văn bản** (không HTML), nên an toàn với dữ liệu người dùng nhập.

### Thông báo có tiến độ (cập nhật được)

```js
const toast = uiToast({type: 'info', icon: 'upload', title: 'Đang xuất Excel', message: 'Đang chuẩn bị…', progress: 0});
toast.update({progress: 40, message: 'Đã xử lý 40%'});
toast.update({type: 'success', progress: 100, title: 'Xuất xong', action: {label: 'Tải xuống', icon: 'download', href: url}});
```

Thông báo có `progress`/`ring` dưới 100 **không tự đóng**; đạt 100 thì tự đóng sau thời gian mặc định. `toast.dismiss()` đóng thủ công.

### Trong Django

- Tin nhắn Django (`messages.success(...)`, `messages.error(...)`) **tự hiện thành toast** trên mọi trang kế thừa `base_app_documents_v2.html` và trang đăng nhập. Không cần viết gì thêm trong template; không render `{% for message in messages %}` thành khung inline nữa.
- Trang HTML độc lập (không kế thừa base v2), thêm vào `<body>`:

```django
{% include 'components/ui_toast.html' %}        {# CSS + JS, an toàn khi nạp nhiều lần #}
{% include 'components/ui_toast_seeds.html' %}   {# đẩy messages vào toast #}
```

Muốn một trang không hiện toast từ messages: override `{% block toast_messages %}{% endblock %}` rỗng.

## Loại và màu

| `type` | Màu ô icon | Dùng cho |
|---|---|---|
| `success` | xanh F88 `#00844A` | Hoàn tất, đã lưu |
| `error` | đỏ `#EF4444` | Thất bại, không hợp lệ (đọc ngay bằng `role="alert"`) |
| `warning` | cam `#F59E0B` | Cần kiểm tra |
| `info` | xanh dương `#0EA5E9` | Thông tin, tiến độ |
| `neutral` | xám đậm `#475569` | Tác vụ nền, nhắc việc trung tính |
| `accent` | tím `#8B5CF6` | Lịch hẹn, sự kiện sắp tới |

## Biến thể nội dung

| Muốn | Dùng |
|---|---|
| Nút hành động (tải file, mở…) | `action: {label, icon?, href \| onClick, download?, target?, dismiss?}` |
| Thanh tiến độ ngang | `progress: 0–100` |
| Vòng phần trăm bên phải | `ring: 0–100` |
| Dòng thông tin (người, giờ, nơi…) | `meta: [{icon, text}, 'text']` |
| Hiển thị tại chỗ (demo/tài liệu) | `container: element` (không tự đóng, không dùng hộp nổi) |

Icon có sẵn: `success`, `error`, `warning`, `info`, `file`, `download`, `upload`, `calendar`, `clock`, `user`, `mail`, `package`, `bell`, `link`, `copy`, `edit`, `check`. Mặc định theo `type`.

## Hành vi

- Xuất hiện ở góc phải trên (dưới thanh menu), thẻ mới nằm trên cùng, tối đa **4** thẻ cùng lúc (thẻ cũ nhất bị bỏ).
- Nằm ở top layer (popover) nên **hiện trên cả hộp thoại/modal** đang mở và không cướp focus.
- Tự đóng: 6 giây (cảnh báo 8, lỗi 9). Rê chuột hoặc focus vào thẻ thì tạm dừng.
- Nút ✕ hiện khi rê chuột/focus (thay cho chỗ hiển thị thời gian); trên thiết bị cảm ứng luôn hiện.
- Hiệu ứng trượt vào/ra; tắt khi hệ điều hành bật "giảm chuyển động".
- Màn hình hẹp (≤480px): thẻ trải gần hết chiều ngang.

## API tương thích cũ

Mã cũ không phải sửa; hai hàm sau là lớp bọc quanh `uiToast`:

| Hàm cũ | Nơi dùng | Tương đương |
|---|---|---|
| `adminDocumentNotify({type, title, message})` | admindocuments (`notifications.js`) | `uiToast({...})` |
| `campaignToast(message, level)` | campaign (`campaign_toasts.js`) | `uiToast({type: level, message})` |

Mã mới nên gọi thẳng `uiToast`. `notifications.js` của admin vẫn giữ riêng phần gom lỗi bắt buộc của form (`invalid`) thành một thông báo.

## Cấm

- Không tự viết toast riêng cho từng trang (`.toast`, `.toast-container`, `showToast` tự định nghĩa…).
- Không render `messages` thành khung inline cho kết quả thao tác; để toast hiển thị.
- Không đưa HTML vào `title`/`message`.
- Không dùng toast cho thông tin người dùng cần xem lại lâu (ví dụ token hiện một lần): dùng khối nội dung trong trang.

## Ghi chú kỹ thuật

- Tệp: `static/css/ui-toast.css`, `static/js/ui-toast.js`, include `templates/components/ui_toast.html` (tài nguyên) và `ui_toast_seeds.html` (messages).
- Gọi `uiToast(...)` trước khi thư viện tải xong vẫn được: lời gọi xếp hàng rồi chạy khi tải xong.
- Tăng `?v=` trong `ui_toast.html` khi sửa CSS/JS của toast.
- Kiểm thử: `app_documents/tests/access/test_toast_component.py` (cấu trúc, không trùng lặp, không còn mã cũ). Hành vi tương tác (xếp hàng, tối đa 4, tiến độ cập nhật, nút hành động, vòng %, đóng/tự đóng, chống HTML, seeds) đã kiểm tra bằng 33 phép thử trên Chrome headless.
