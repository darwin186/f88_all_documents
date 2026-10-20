# File (ô chọn tệp gọn)

Trạng thái: 🟡 **Đã áp dụng** cho các ô tải **một tệp** (xem "Đã áp dụng"). Ô tải nhiều ảnh/vùng kéo thả chưa thuộc component này.

Giao diện: một ô bo tròn hiện tên tệp + dung lượng, nút ✕ để bỏ tệp, và **nút mũi tên (↑) ở cuối ô** để mở hộp chọn tệp (không dùng chữ "Chọn tệp"). Kéo thả tệp vào ô cũng được.

Xem trực quan: mở `docs/ui-kit/demo/file.html` bằng trình duyệt. (Các phương án đã cân nhắc: `docs/ui-kit/demo/file-upload-options.html`.)

## Khi nào dùng

| Cần | Dùng |
|---|---|
| Chọn **một** tệp (đính kèm, import Excel, ảnh đại diện) | File mặc định |
| Chọn vài tệp, không cần xem tiến độ từng tệp | File với `multiple` (hiện "Đã chọn N tệp") |
| Tải nhiều ảnh, cần danh sách/ tiến độ/ xem trước | Chưa có component (vùng kéo thả riêng) |
| Chọn giữa tệp hoặc link | Radio "Tải tệp / Nhập link" + File (xem `document_attachment_modal.html`) |

## Cách dùng

Bọc `<input type="file">` gốc trong `.ui-file[data-ui-file]`. Input gốc **vẫn là field được submit** và vẫn có `files`, `change`, `required`, `accept`.

```html
<label for="doc-file">Tệp đính kèm <span class="text-red-500">*</span></label>
<div class="ui-file" data-ui-file data-max-mb="25">
  <input id="doc-file" type="file" name="attachment" required accept=".pdf,.docx">
</div>
```

```django
{# Django form field #}
{% include 'components/ui_file.html' with field=form.attachment max_mb=25 %}
```

Nạp sẵn: `static/css/ui-kit.css` và `static/js/ui-file.js` đã được nạp trong `base_app_documents_v2.html`. Trang không extend base này phải tự thêm hai file. JS tự khởi tạo mọi `[data-ui-file]`, kể cả phần tử thêm sau.

## Tuỳ chọn

| Tuỳ chọn | Cách bật | Ghi chú |
|---|---|---|
| Giới hạn dung lượng | `data-max-mb="10"` | Vượt giới hạn thì tự bỏ tệp và hiện lỗi dưới ô |
| Định dạng | `accept=".xlsx"` trên input | Khi kéo thả, tệp sai định dạng bị từ chối và báo lỗi |
| Nhiều tệp | `multiple` trên input | Hiện "Đã chọn N tệp"; nút có nhãn "Chọn các tệp" |
| Cỡ nhỏ | `data-size="sm"` | 28px |
| Chữ khi chưa chọn | `data-placeholder="..."` | Mặc định "Chưa chọn tệp" |
| Thông báo bắt buộc | `data-required-text="..."` | Mặc định "Vui lòng chọn tệp." |
| Vô hiệu hóa | `disabled` trên input | Ô và nút xám, không bấm được |

## Hành vi

- Chọn tệp: hiện tên (cắt bớt nếu dài, rê chuột xem đủ) và dung lượng (KB/MB).
- ✕: bỏ tệp và phát sự kiện `change`.
- `required` mà chưa chọn lúc submit: ô viền đỏ, hiện thông báo, focus vào nút mũi tên.
- `form.reset()` đưa ô về trạng thái ban đầu.
- Nhãn `<label for="id">` bấm vào sẽ focus nút mũi tên; cần input có `id`.
- Nút mũi tên có `aria-label` "Chọn tệp — <nhãn>" nên đọc được bằng trình đọc màn hình.

## Mã khác thao tác với ô tệp

- Đọc `input.files` và nghe `change` như bình thường; không phải sửa.
- Nếu mã gán `input.value = ''` hoặc đổi `input.files` bằng code, gọi `window.uiFile.refresh(input)` để giao diện cập nhật.

## Cấm

- Không dùng `file:...` (Tailwind) hay `::file-selector-button` để tô nút "Choose file" nữa.
- Không đặt `data-ui-file` lên phần tử không chứa `<input type="file">`.
- Không dùng `hidden` hay `display:none` cho input gốc (trình duyệt bỏ qua kiểm tra `required` của input ẩn). Component tự ẩn input bằng class.

## Đã áp dụng

| Form | File |
|---|---|
| Đính kèm tệp / link (văn bản hành chính) | `document_attachment_modal.html` |
| Tạo văn bản hành chính — Tải lên văn bản | `document_create_modal_v2.html` |
| Tạo giấy hành chính — Tạo theo file Excel | `paper_document_create_modal.html` |
| Giao dịch đảm bảo — mapping PGD | `app_gddb_registration_v2.html` |
| Quản lý thùng — import / tạo hàng loạt (2 ô) | `app_package_list_v2.html` |
| Nhận chứng từ — import | `app_receiving_import_v2.html` |

## Legacy map — chưa áp dụng

| Cũ | Nơi dùng | Ghi chú |
|---|---|---|
| `label.file-choice` (ô kéo thả riêng) | `master_data.html` (Cập nhật từ Excel) | Có JS riêng đổi chữ tên tệp; cần chuyển cùng lúc |
| Ô chọn nhiều ảnh (`images`, có `capture`) | bưu kiện (`parcel_receipt_*`), công văn đến (`incoming_dispatch_list`) | Dạng nhiều tệp + camera; chưa có component |
| Vùng kéo thả `dec-upload-zone` | campaign `dataset_panel.html` | Có luồng tải riêng |
| Input ẩn kích hoạt bằng nút | `document_detail.html`, `user_profile_v2.html` (ảnh đại diện), `campaign_qtrr_booking.html` | Không có ô hiển thị; không cần component |

## Ghi chú kỹ thuật

- Class: `ui-file`, `ui-file-name`, `ui-file-size`, `ui-file-clear`, `ui-file-pick`, `ui-file-error`; dùng biến `--ui-*` trong `ui-kit.css`.
- Tăng `?v=` ở `base_app_documents_v2.html` khi sửa `ui-kit.css` hoặc `ui-file.js` (và `admin_ui.js` ở `base_v2.html` nếu sửa).
- `admin_ui.js` tự gán class `ui-btn` cho mọi nút; nó đã được dặn bỏ qua `[data-ui-file]`.
- Kiểm thử: `app_admindocuments/test_file_component.py` (cấu trúc). Hành vi tương tác (chọn, ✕, giới hạn dung lượng, kéo thả, định dạng, reset, `required`, vô hiệu, FormData) kiểm tra bằng 22 phép thử chạy trên Chrome headless với trang demo.
