# Upload (kéo thả + danh sách tệp + chụp ảnh) — "Mẫu D"

Trạng thái: 🟡 **Đã áp dụng cho**: form tiếp nhận bưu phẩm ("Ảnh đính kèm / File", có chụp ảnh = mẫu D), mục "Tệp đính kèm" trong ngăn chi tiết bưu kiện (D), và công văn đến (modal tiếp nhận + ngăn chi tiết, không có chụp ảnh = mẫu C).

Giao diện: vùng kéo thả nét đứt xanh (mẫu C) + **nút "Chụp ảnh"** nằm trong vùng. Tệp đã chọn hiện thành danh sách bên dưới: ảnh có ảnh xem trước, tệp khác có nhãn đuôi (PDF, DOCX…), kèm tên, dung lượng và nút ✕.

Xem trực quan: `docs/ui-kit/demo/file-upload-options.html` (mục D, tương tác được).

## Khi nào dùng

| Cần | Dùng |
|---|---|
| Một tệp (Excel import, đính kèm đơn) | [File](file.md) |
| Nhiều tệp/ảnh, cần danh sách, xem trước, giới hạn số tệp | **Upload** |
| Nhiều ảnh chụp tại chỗ bằng điện thoại | **Upload** với `data-camera` |

## Cách dùng

Bọc `<input type="file" multiple>` gốc trong `.ui-upload[data-ui-upload]`. Input gốc **vẫn là field được submit** (cùng `name`, cùng `request.FILES.getlist(...)` ở server). Component giữ danh sách cuối cùng trong input này, nên chọn nhiều lần, chụp thêm, kéo thả đều gộp được vào một lần submit.

```html
<div class="ui-upload" data-ui-upload data-camera data-max-files="5" data-max-mb="30"
     data-hint="Ảnh, PDF, Word, Excel · tối đa 5 tệp, mỗi tệp không quá 30MB">
  <input type="file" id="images" name="images" multiple accept="image/*,.pdf,.doc,.docx,.xls,.xlsx">
</div>
```

Nạp sẵn: `ui-kit.css` và `ui-upload.js` đã có trong `base_app_documents_v2.html`. Trang độc lập tự thêm hai file. JS tự khởi tạo mọi `[data-ui-upload]`, kể cả phần tử thêm sau.

## Tuỳ chọn

| Tuỳ chọn | Cách bật | Ghi chú |
|---|---|---|
| Nút chụp ảnh | `data-camera` | Trên điện thoại mở camera sau (`capture="environment"`); trên máy tính mở hộp chọn ảnh |
| Giới hạn số tệp | `data-max-files="5"` | Đủ số thì vùng và nút chụp bị khóa; thêm quá số thì báo lỗi. `data-max-files="1"` = chọn một tệp, chọn lại thì thay |
| Giới hạn dung lượng | `data-max-mb="30"` | Tệp quá lớn bị bỏ qua, các tệp khác vẫn nhận, báo lỗi dưới vùng |
| Định dạng | `accept="…"` trên input | Tệp sai định dạng bị từ chối (cả khi kéo thả) |
| Gợi ý dưới tiêu đề | `data-hint="…"` | |
| Chữ | `data-drop-text`, `data-pick-text`, `data-camera-text`, `data-required-text` | Mặc định: "Kéo thả tệp vào đây hoặc" / "chọn từ máy" / "Chụp ảnh" / "Vui lòng chọn tệp." |
| Bắt buộc | `required` trên input | Thiếu lúc submit: vùng viền đỏ + thông báo, focus vào vùng |
| Vô hiệu hóa | `disabled` trên input | |

## Hành vi

- Tệp trùng (cùng tên, dung lượng, thời gian sửa) bị bỏ qua.
- ✕ bỏ một tệp và xóa thông báo lỗi; `form.reset()` hoặc `window.uiUpload.reset(input)` xóa hết.
- Danh sách cập nhật `input.files` và bắn `change` trên input gốc, nên code lắng nghe `change` vẫn chạy.
- Ảnh xem trước dùng `URL.createObjectURL` và được giải phóng khi bỏ tệp. Tên tệp luôn hiển thị dạng văn bản.
- Bàn phím: Enter/Space trên vùng mở hộp chọn tệp.

## Cấm

- Không dùng `<label>` + `<input class="hidden">` riêng cho từng trang (kiểu "Chụp ảnh" / "Tải tệp" hai ô cũ).
- Không để hai input cùng `name` để tách chụp/chọn; component gộp vào một input.
- Không dùng `hidden`/`display:none` cho input gốc (trình duyệt bỏ qua `required`). Component tự ẩn bằng class.

## Legacy map

| Cũ | Nơi dùng | Ghi chú |
|---|---|---|
| Hai ô "Chụp ảnh" + "Tải tệp" (`<label>` + input ẩn) | form tiếp nhận bưu phẩm, ngăn chi tiết bưu kiện | ✅ Đã migrate |
| `incomingDispatchFiles`, `incomingDrawerFiles` (có JS tóm tắt riêng) | `incoming_dispatch_list.html` | ✅ Đã migrate (mẫu C, không `data-camera`) |
| Vùng kéo thả `dec-upload-zone` | campaign `dataset_panel.html` | Có luồng tải/tiến độ riêng, chưa thuộc component |

## Ghi chú kỹ thuật

- Class: `ui-upload`, `ui-upload-drop`, `ui-upload-list`, `ui-upload-item`, `ui-upload-thumb`, `ui-upload-camera`, `ui-upload-error`.
- Component thêm hai input tạm (chọn tệp, chụp ảnh) **không có `name`** nên không bị gửi đi.
- `admin_ui.js` đã được dặn bỏ qua `[data-ui-upload]`.
- Tăng `?v=` ở `base_app_documents_v2.html` khi sửa `ui-kit.css`/`ui-upload.js` (và `admin_ui.js` ở `base_v2.html` nếu sửa).
- Giới hạn trên trình duyệt chỉ là tiện lợi; server vẫn kiểm tra (`_validate_parcel_images`: tối đa 5 tệp, 30MB).
- Kiểm thử: `app_admindocuments/test_parcel_intake_select.py` (cấu trúc). Hành vi (chọn, chụp, trùng, sai định dạng, quá lớn, quá số lượng, ✕, kéo thả, FormData, reset, an toàn HTML) kiểm tra bằng 18 phép thử trên Chrome headless.
