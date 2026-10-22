# Combobox (tìm kiếm + chọn trong cùng một ô)

Trạng thái: 🟡 **Đã áp dụng cho**: ô "Người nhận" ở form tiếp nhận bưu phẩm (`parcel_receipt_list.html`) và ô "Tìm theo mã thùng F88" ở Nhận chứng từ v2 (chế độ gõ tự do). Các ô tìm người nhận trong ngăn chi tiết (nhận hộ, gán người nhận) vẫn dùng bản cũ.

Một ô duy nhất: người dùng gõ để tìm, menu nổi hiện kết quả tải từ server, chọn xong thì ô hiển thị giá trị đã chọn kèm nút ✕.

Xem trực quan: mở `docs/ui-kit/demo/combobox.html` bằng trình duyệt (dữ liệu giả lập).

Bản thiết kế **danh sách gợi ý khi nhập liệu**: [demo/suggestions.html](../demo/suggestions.html). Có thể thử tìm kiếm, chọn, bỏ chọn, bàn phím, không có kết quả và lỗi tải. Dùng nguyên CSS/JS Combobox hiện có; dữ liệu minh họa chỉ nằm trong demo.

## Anatomy — danh sách gợi ý khi nhập liệu

`[icon tìm kiếm] [từ khóa / nhãn đã chọn] [bỏ chọn ×]`

- Ô nhập cao 34px (cỡ nhỏ 28px), viền và vòng focus theo token chung.
- Menu nổi cách ô nhập 5px, rộng bằng ô nhập; vùng kết quả cao tối đa 260px, cuộn khi dài, tự lật lên trên khi thiếu chỗ.
- Mỗi dòng: **tên** ở trên, mã định danh và thông tin phân biệt ở dưới; thông tin bổ sung ngắn ở bên phải. Không dùng màu làm dấu hiệu phân biệt duy nhất.
- Kết quả đang trỏ dùng nền `surface-subtle`. Chọn bằng chuột hoặc Enter thì đóng menu, lưu ID và hiển thị nhãn; nút × bỏ lựa chọn.
- Chờ nhập: chỉ dẫn số ký tự tối thiểu. Đang tìm: “Đang tìm…”. Rỗng hoặc lỗi: giải thích ngắn và hướng dẫn nhập lại.
- Đây là trường **chọn giá trị có sẵn**: từ khóa chưa chọn không được xem là giá trị hợp lệ. Trường cho phép lưu văn bản tự do cần đặc tả riêng.

## Khi nào dùng

| Cần | Dùng |
|---|---|
| Chọn một giá trị trong danh sách **ngắn/vừa**, đã nạp sẵn trong trang | [Select](select.md) (có ô tìm kiếm trong menu) |
| Chọn một giá trị trong danh sách **lớn** (danh bạ nhân viên, hàng nghìn dòng), phải tìm phía server | **Combobox** |
| Chọn nhiều giá trị | Select `multiple` (Combobox chỉ chọn một) |
| Nhập giá trị tự do không có trong danh sách | Không thuộc component này |

## Cách dùng

Component dựng giao diện trong một khối rỗng. **Giá trị thật nằm ở `<input type="hidden">` của form**, nên submit/validate không đổi.

```html
<input type="hidden" id="id_recipient_directory" name="recipient_directory">
<input type="hidden" id="id_recipient_unknown" name="recipient_unknown">

<div class="ui-combobox" data-ui-combobox
     data-source="/admindocuments/parcel-receipts/recipient-search/"
     data-value-input="#id_recipient_directory"
     data-special-input="#id_recipient_unknown"
     data-filter="department:#id_recipient_department" data-filter-ignore="__unknown__"
     data-title-key="full_name" data-meta-keys="employee_code,department_name"
     data-meta-empty="Không có mã NV|Chưa có phòng ban"
     data-aside-keys="phone_number,email" data-label-key="label"
     data-placeholder="Tìm theo tên, mã nhân viên, email…"
     data-hint="Nhập tên, mã nhân viên hoặc email."
     data-special-label="Người nhận chưa xác định"></div>
```

Nạp sẵn: `ui-kit.css` và `ui-combobox.js` đều có trong `base_app_documents_v2.html`. Trang độc lập phải tự thêm hai file. JS tự khởi tạo mọi `[data-ui-combobox]`, kể cả phần tử thêm sau.

## Chế độ gõ tự do (gợi ý)

Thêm `data-free` khi ô tìm kiếm là **văn bản tự do** (ví dụ "Tìm theo mã thùng") và danh sách chỉ để **gợi ý**: người dùng có thể bỏ qua gợi ý và gõ/nhấn Enter để lọc theo đúng chữ đã gõ.

```html
<div class="ui-combobox" data-ui-combobox data-free data-name="filter_package" data-value="{{ request.GET.filter_package|default:'' }}"
     data-source="{% url 'package_code_suggest' %}" data-title-key="label" data-label-key="label" data-meta-keys="meta"
     data-placeholder="Tìm theo mã thùng F88"></div>
```

- Ô nhập **chính là field gửi đi**: đặt tên bằng `data-name`, giá trị ban đầu bằng `data-value`. Không cần `data-value-input`.
- Chọn một gợi ý thì điền chữ đó vào ô (bắn `change`); không có gợi ý nào được tô sáng sẵn nên Enter gửi form với chữ đang gõ. ↓ rồi Enter mới chọn gợi ý.
- Không có kết quả thì menu tự ẩn (đặt `data-empty-text` nếu muốn hiện dòng "Không có gợi ý").
- API trả `{"results": [{"label": "...", "meta": "..."}]}` như bình thường; `selected_id` không dùng.

## API server

`GET data-source?q=<từ khóa>[&<tên lọc>=<giá trị>]` → `{"results": [ {...}, ... ]}`.
Khi form dựng lại với giá trị có sẵn, component gọi `GET data-source?selected_id=<giá trị>` (đổi tên bằng `data-select-param`) để lấy nhãn hiển thị.

## Thuộc tính

| Thuộc tính | Ý nghĩa | Mặc định |
|---|---|---|
| `data-source` | URL tìm kiếm (bắt buộc) | — |
| `data-value-input` | Selector ô ẩn nhận `id` của mục đã chọn | — |
| `data-special-input` | Selector ô ẩn nhận `1` khi chọn mục đặc biệt | — |
| `data-special-label` | Chữ của mục đặc biệt cố định ở cuối menu (ví dụ "Chưa xác định"); không đặt thì không có mục này | — |
| `data-filter` | `tênThamSố:selector` — thêm giá trị của một ô khác vào truy vấn; đổi giá trị ô đó thì tìm lại | — |
| `data-filter-ignore` | Giá trị của ô lọc không gửi lên (phân tách bằng dấu phẩy) | — |
| `data-query-param` / `data-select-param` | Tên tham số từ khóa / khôi phục | `q` / `selected_id` |
| `data-id-key` / `data-label-key` | Khóa `id` và khóa nhãn hiển thị sau khi chọn | `id` / `label` |
| `data-title-key` | Khóa của dòng tiêu đề đậm trong mỗi kết quả | = `label-key` |
| `data-meta-keys`, `data-meta-empty` | Các khóa ghép thành dòng phụ (nối bằng " · "); `meta-empty` là chữ thay khi thiếu (phân tách `|`) | — |
| `data-aside-keys` | Các khóa xếp dọc ở bên phải mỗi kết quả | — |
| `data-min` / `data-delay` | Số ký tự tối thiểu / debounce (ms) | `1` / `220` |
| `data-placeholder`, `data-hint`, `data-empty-text`, `data-error-text`, `data-clear-label` | Chữ gợi ý | tiếng Việt mặc định |
| Class `ui-combobox-sm` | Cỡ nhỏ 28px | — |

Mọi chữ lấy từ server được gán dạng văn bản (không HTML).

## Sự kiện (nổi lên từ khối `.ui-combobox`)

| Sự kiện | `detail` | Khi nào |
|---|---|---|
| `ui-combobox:select` | `{item}` — object kết quả | Chọn một mục |
| `ui-combobox:special` | `{label}` | Chọn mục đặc biệt |
| `ui-combobox:clear` | — | Bỏ chọn (nút ✕, Backspace, hoặc gõ lại sau khi đã chọn) |
| `ui-combobox:restore` | `{item}` | Khôi phục lựa chọn có sẵn từ server |

Ô ẩn cũng bắn `change`, nên code lắng nghe `change` trên ô ẩn vẫn chạy.

Ví dụ: điền phòng ban theo người nhận đã chọn.

```js
box.addEventListener('ui-combobox:select', e => {
  department.value = e.detail.item.department_name;
  window.uiSelect.refresh(department);
});
```

## API JS

| Hàm | Tác dụng |
|---|---|
| `window.uiCombobox.clear(box)` | Bỏ chọn (không focus) |
| `window.uiCombobox.setSpecial(box)` | Chọn mục đặc biệt |
| `window.uiCombobox.reset(box)` | Về trạng thái rỗng, không bắn sự kiện |

## Trạng thái và bàn phím

| Trạng thái | Quy tắc |
|---|---|
| mở | viền xanh + vòng sáng; menu tự lật lên nếu thiếu chỗ phía dưới |
| đang chọn | chữ đậm; mục đặc biệt: chữ nghiêng xám |
| chưa gõ | menu hiện gợi ý (`data-hint`) |
| đang tải / không có kết quả / lỗi | dòng trạng thái trong menu |
| lỗi nhập | thêm class `is-invalid` lên `.ui-combobox` (viền đỏ) |

| Phím | Tác dụng |
|---|---|
| ↓ / ↑ | Mở menu, di chuyển giữa kết quả và mục đặc biệt |
| Enter | Chọn mục đang sáng |
| Esc | Đóng menu |
| Backspace khi ô rỗng và đã chọn | Bỏ chọn |
| Tab / bấm ra ngoài | Đóng; ô trả về nhãn đã chọn |

## Cấm

- Không tự dựng ô tìm kiếm + danh sách kết quả riêng cho từng trang. Dùng component này.
- Không đưa HTML vào dữ liệu trả về để hiển thị.
- Không dùng cho danh sách nhỏ đã nạp sẵn: dùng Select.

## Legacy map

| Cũ | Nơi dùng | → Kit | Ghi chú |
|---|---|---|---|
| Ô gõ + khung "Chưa chọn người nhận" + danh sách thẻ + nút "Người nhận chưa xác định" | form tiếp nhận bưu phẩm | `ui-combobox` | ✅ Đã migrate |
| `renderProxyRecipientResults`, `renderAssignRecipientResults` | ngăn chi tiết bưu kiện (nhận hộ, gán người nhận) | `ui-combobox` | Chưa migrate |

## Ghi chú kỹ thuật

- Tệp: `static/js/ui-combobox.js`; CSS trong `static/css/ui-kit.css` (mục "Combobox"). Tăng `?v=` ở `base_app_documents_v2.html` khi sửa.
- Mỗi lần gõ hủy yêu cầu trước (`AbortController`) nên kết quả cũ không ghi đè kết quả mới.
- Kiểm thử: `app_admindocuments/test_parcel_intake_select.py` (cấu trúc, bỏ mã cũ). Hành vi tương tác (tìm, chọn, lọc phụ thuộc, mục đặc biệt, bàn phím, khôi phục) đã kiểm tra bằng 21 phép thử trên Chrome headless với trang demo.

## Checklist khi thêm Combobox

- [ ] Có ô ẩn `data-value-input` nằm trong `<form>` và có `name`
- [ ] API trả `{"results": [...]}` có khóa `id` và `label`, giới hạn số dòng
- [ ] API hỗ trợ `selected_id` nếu form có thể dựng lại với giá trị có sẵn
- [ ] Có `<label>` hoặc `data-placeholder` rõ nghĩa
