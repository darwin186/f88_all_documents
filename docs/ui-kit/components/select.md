# Select (droplist có tìm kiếm)

Trạng thái: 🟡 **Đã áp dụng cho**: modal "Tạo giấy hành chính", modal "Tạo văn bản hành chính" và form "Cập nhật văn bản hành chính" (`app_admindocuments`). Các màn hình khác vẫn dùng bản cũ (xem "Legacy map").

Mẫu giao diện: droplist trong form "Chỉnh sửa giấy hành chính" — nút bo tròn, menu nổi có "Bỏ chọn" (xanh, góc phải), ô tìm kiếm, danh sách cuộn, mục đang chọn tô xanh nhạt kèm ✓.

Xem trực quan: mở `docs/ui-kit/demo/select.html` bằng trình duyệt (thêm `?open=demo-multi-max` để mở sẵn một biến thể).

## Khi nào dùng

| Cần | Dùng |
|---|---|
| Chọn **một** giá trị trong danh sách (nhất là danh sách dài: PGD, đơn vị...) | Select mặc định |
| Chọn **nhiều** giá trị (nhiều PGD, nhiều vùng) | Select với `<select multiple>` |
| Danh sách rất ngắn (2–3 lựa chọn, ví dụ Có/Không) | Radio hoặc segmented control, không dùng Select |
| Cần gõ giá trị tự do ngoài danh sách | Không thuộc component này (Combobox, chưa có) |

## Cách dùng

Component bọc một `<select>` gốc. Select gốc **vẫn là field được submit và validate**; component chỉ dựng giao diện phía trên.

```django
{# Django form field #}
{% include 'components/ui_select.html' with field=form.requested_department %}

{# Chọn nhiều, tối đa 3 #}
{% include 'components/ui_select.html' with field=form.shops max=3 %}
```

```html
<!-- HTML thuần -->
<label for="shop">Phòng giao dịch</label>
<div class="ui-select" data-ui-select>
  <select id="shop" name="shop"><option value="">Chọn phòng giao dịch</option>…</select>
</div>
```

Nạp sẵn: `static/css/ui-kit.css` và `static/js/ui-select.js` đều được nạp trong `base_app_documents_v2.html`. Trang không extend base này phải tự thêm hai file đó. JS tự khởi tạo mọi `[data-ui-select]`, kể cả phần tử thêm vào trang sau đó.

Với field Django `ModelMultipleChoiceField` / `SelectMultiple`, dùng đúng include trên; component nhận ra `multiple` từ select.

## Biến thể

| Biến thể | Cách bật | Ghi chú |
|---|---|---|
| Chọn một | mặc định | Chọn xong tự đóng |
| Chọn nhiều | `<select multiple>` | Menu giữ mở; mỗi mục có ô tích; có "Chọn tất cả" |
| Giới hạn số lượng | `max=3` / `data-max="3"` | Đủ số thì khóa các mục còn lại; hiện "Đã chọn 3/3"; ẩn "Chọn tất cả" |
| Tóm tắt dạng số | `summary=count` / `data-summary="count"` | Hiện "Đã chọn N" thay cho chip (mặc định: tối đa 2 chip + "+N"; trên 3 mục tự chuyển sang "Đã chọn N") |
| Ô tìm kiếm | `search=auto` (mặc định) / `on` / `off` | `auto`: chỉ hiện khi có hơn 7 lựa chọn |
| Nút "Bỏ chọn" | `clear=auto` (mặc định) / `on` / `off` | `auto`: ẩn nếu select `required` ở chế độ chọn một |
| Cỡ nhỏ | `size=sm` / class `ui-select-sm` | 28px, dùng trong thanh công cụ |
| Nhóm lựa chọn | `<optgroup label="…">` | Tiêu đề nhóm không chọn được |
| Màu chữ theo mục | `<option data-color="#dc2626">` | Tuỳ chọn |
| Placeholder | `placeholder="…"` hoặc `<option value="">Chọn …</option>` | Mặc định lấy từ option rỗng; nếu không có thì "Chọn <nhãn>" |
| Giới hạn hiển thị | `limit=300` / `data-limit` | Danh sách dài chỉ vẽ N mục đầu, hiện ghi chú "gõ thêm để lọc" |
| Lọc phụ thuộc | `<option hidden>` | Option có `hidden` bị bỏ qua (không hiện, không đếm). Ví dụ Phòng ban lọc theo Công ty: xem "Lọc phụ thuộc" bên dưới |
| Màu trạng thái | `<option data-color="#047857">` | Với chọn một, chữ trên nút lấy màu của mục đang chọn (dùng cho Trạng thái văn bản) |

## Trạng thái

| Trạng thái | Quy tắc |
|---|---|
| mở | viền xanh + vòng sáng; mũi tên quay lên; menu tự lật lên trên nếu thiếu chỗ phía dưới |
| focus | `outline: 2px solid #A7F3D0` |
| disabled | đặt `disabled` trên `<select>` gốc; nút xám, không mở được |
| lỗi | viền đỏ. Server: truyền field có `errors` (include tự thêm `data-invalid`). Client: khi `required` còn trống lúc submit, component tự đánh dấu lỗi và mở menu |
| đang chọn | nền xanh nhạt, chữ xanh đậm; chọn một có thêm ✓ |

## Bàn phím

| Phím | Tác dụng |
|---|---|
| ↓ / ↑ trên nút | Mở menu |
| ↓ trong ô tìm kiếm | Xuống mục đầu tiên |
| ↑ / ↓ / Home / End trong danh sách | Di chuyển |
| Enter / Space | Chọn mục đang focus (Enter trong ô tìm: chọn mục đầu tiên đang hiện) |
| Esc | Đóng, trả focus về nút |
| Tab | Đóng |

Tìm kiếm không phân biệt hoa/thường và dấu thanh theo locale `vi` (gõ "tân" khớp "Tân Châu").

## Lọc phụ thuộc (ví dụ Phòng ban theo Công ty)

Không cần tính năng riêng: bật/tắt `hidden` trên các `<option>` của select phụ thuộc mỗi khi select chính đổi, rồi xóa giá trị nếu mục đang chọn bị ẩn. Component tự cập nhật (nó theo dõi thuộc tính `hidden`).

```js
company.addEventListener('change', () => {
  [...department.options].forEach(o => { if (o.value) o.hidden = company.value && o.dataset.company !== company.value; });
  if (department.selectedOptions[0]?.hidden) { department.value = ''; department.dispatchEvent(new Event('change', {bubbles: true})); }
});
```

Mẫu thực tế: `static/admindocuments/js/document_create_controls.js` (form tạo văn bản hành chính).

## Dùng trong hộp thoại chỉnh sửa trực tiếp

Khi ẩn một vùng chứa droplist bằng code (ví dụ thoát chế độ sửa), gọi `window.uiSelect.closeAll(vungChua)` để đóng menu đang mở, nếu không lần mở lại sẽ thấy menu còn mở. `document_edit_modal.js` đã làm việc này.

## Hành vi với form

- Giá trị lấy từ select gốc nên `FormData`, validate `required`, `form.reset()` đều hoạt động như thường.
- Mã khác đổi lựa chọn bằng code: gán `select.value` (hoặc `option.selected`) rồi `select.dispatchEvent(new Event('change', {bubbles: true}))` — giao diện tự cập nhật.
- Thêm / xóa `<option>` hoặc đổi `disabled` trên select gốc: giao diện tự cập nhật (MutationObserver).
- Component phát sự kiện `change` bình thường trên select gốc, nên code lắng nghe `change` sẵn có không phải sửa.
- Nhãn `<label for="id">` bấm vào sẽ focus nút của component; cần select gốc có `id`.

## Cấm

- Không tự dựng droplist bằng `<div>`/`<ul>` riêng cho từng trang. Dùng component này.
- Không đặt `data-ui-select` lên phần tử không chứa `<select>`.
- Không gắn thêm script bọc `<select>` khác lên cùng phần tử (xem Legacy map về `admin_ui.js`).
- Không dùng chip để thay `<select multiple>` khi cần submit nhiều giá trị: giữ select gốc làm nguồn giá trị.

## Legacy map

| Cũ | Nơi dùng | → Kit | Ghi chú |
|---|---|---|---|
| `includes/document_select.html` + `document_form_controls.js` (`[data-document-select]`) | form chỉnh sửa **giấy** hành chính, form tách thửa | `components/ui_select.html` | **Chưa migrate** — giao diện gần như giống nhau. (Form cập nhật **văn bản** hành chính đã migrate.) |
| Droplist Alpine tự viết (`admReferenceDropdown`, `admSignerDropdown`, `admDepartmentDropdown`) | modal tạo văn bản hành chính | `ui-select` | ✅ Đã migrate và xóa khỏi `document_list.html` |
| `adm-ui-select` (do `admin_ui.js` tự bọc mọi `<select>` đơn) | nhiều form admindocuments | `ui-select` | Chưa migrate. `admin_ui.js` đã được dặn bỏ qua `[data-ui-select]` |
| `[data-filter-select]` (`document_filters.js`) | thanh bộ lọc danh sách | giữ nguyên | Bộ lọc có chip và cơ chế riêng; xét lại khi làm component Filter |
| Droplist React/Tailwind riêng | `app_package_list_v2.html`, các trang GDĐB | `ui-select` | Chưa migrate |

Đã áp dụng:
- Modal "Tạo giấy hành chính" (`paper_document_create_modal.html`): 5 droplist.
- Modal "Tạo văn bản hành chính" (`document_create_modal_v2.html`): Công ty, Loại văn bản, Loại nội dung, Tham chiếu tới văn bản, Người ký, Phòng ban (lọc theo công ty), Trạng thái.
- Form "Cập nhật văn bản hành chính" (`document_edit_form.html`): mọi field dạng select, tự lưu khi chọn.

## Ghi chú kỹ thuật

- Tên class: `ui-select`, `ui-select-toggle`, `ui-select-menu`, `ui-select-option`...; biến CSS `--ui-*` trong `ui-kit.css`.
- Tăng `?v=` ở `base_app_documents_v2.html` khi sửa `ui-kit.css` hoặc `ui-select.js`.
- Kiểm thử: `app_admindocuments/test_paper_select_component.py`, `test_document_select_component.py` (cấu trúc, biến thể, lọc phụ thuộc). Hành vi tương tác (mở/đóng, tìm kiếm, chọn nhiều, giới hạn, bàn phím, reset form, `required`) đã được kiểm tra bằng 35 phép thử chạy trên Chrome headless với trang demo.

## Checklist khi thêm Select

- [ ] Select gốc có `id`, `name`, và `<label for>`
- [ ] Có option rỗng với chữ gợi ý nếu cho phép bỏ trống
- [ ] Chọn nhiều thì dùng `multiple` và đặt `max` nếu có giới hạn nghiệp vụ
- [ ] Danh sách không quá dài; nếu hàng nghìn mục, đặt `limit` và cân nhắc tải theo tìm kiếm
