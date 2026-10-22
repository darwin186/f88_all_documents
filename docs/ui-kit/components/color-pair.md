# Color pair (chọn màu chữ + màu nền, xem trước trực tiếp)

Trạng thái: 🟡 **Đã áp dụng cho**: cấu hình màu "Trạng thái văn bản" ở `master_data.html`.

Giao diện: một **huy hiệu xem trước** hiển thị đúng tên mục với màu chữ + màu nền đang chọn, bên cạnh hai ô nhỏ — ô **A** (gạch chân theo màu chữ, nhãn "Chữ") và ô **vuông tô màu nền** (nhãn "Nền"). Bấm ô để mở bảng chọn màu; huy hiệu đổi màu ngay khi kéo chọn. Nút **Lưu màu** chỉ bật khi có thay đổi. Nếu chữ và nền gần nhau (tương phản dưới 3:1), hiện dòng cảnh báo.

## Cách dùng

```html
<form method="post" class="ui-color-pair" data-ui-color-pair>
  {% csrf_token %}
  <span class="ui-color-preview" data-color-preview style="color:{{ text }};background-color:{{ bg }}">{{ name }}</span>
  <label class="ui-color ui-color-text" title="Màu chữ"><span class="ui-color-tile" style="--ui-color-value:{{ text }}">A</span>Chữ
    <input type="color" name="badge_text_color" value="{{ text }}" data-color-text aria-label="Màu chữ"></label>
  <label class="ui-color ui-color-bg" title="Màu nền"><span class="ui-color-tile" style="--ui-color-value:{{ bg }}"></span>Nền
    <input type="color" name="badge_bg_color" value="{{ bg }}" data-color-bg aria-label="Màu nền"></label>
  <button type="submit" class="ui-btn ui-btn-primary ui-btn-sm" data-color-save disabled>Lưu màu</button>
  <p class="ui-color-warn" data-color-warn hidden>Chữ và nền khó phân biệt, nên chọn màu tương phản hơn.</p>
</form>
```

- Hai `<input type="color">` gốc **vẫn là field được submit**; server vẫn kiểm tra giá trị hợp lệ như trước.
- `data-min-contrast="3"` trên form đổi ngưỡng cảnh báo tương phản.
- Nạp sẵn trong `base_app_documents_v2.html` (`ui-kit.css`, `ui-color.js`).

## Cấm

- Không tách hai ô màu rời nhau khỏi huy hiệu xem trước (người dùng không biết màu sẽ ra sao).
- Không hiển thị cùng lúc một huy hiệu "đang lưu" và một huy hiệu "đang sửa" cho cùng một mục.

## Ghi chú kỹ thuật

- Tệp: `static/js/ui-color.js`; CSS trong `ui-kit.css` (mục "Color pair"). Tăng `?v=` ở `base_app_documents_v2.html` khi sửa.
- Kiểm thử: `app_admindocuments/test_status_colors.py` (server), `test_parcel_intake_select.py` (cấu trúc). Hành vi (huy hiệu đổi màu, nút Lưu bật/tắt, cảnh báo tương phản) kiểm tra trên Chrome headless.
