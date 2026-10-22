# Date (ngày / khoảng ngày / ngày giờ / giờ)

Trạng thái: 🟡 **Đã áp dụng cho**: hai ô khoảng ngày ("Ngày phát sinh", "Ngày nhận") ở thanh lọc Nhận chứng từ v2. Các ô ngày còn lại (ngăn chi tiết, Nhận nhiều, Tạo thùng, các màn khác) vẫn dùng Flatpickr / Flowbite / `<input type="date">` riêng — xem "Legacy map".

Giao diện: ô cùng họ với Select / Combobox (viền, bo góc, vòng focus, nút ✕) + lịch tiếng Việt, tuần bắt đầu thứ Hai, ngày chọn tô xanh F88, khoảng ngày tô xanh nhạt.

Xem trực quan, tương tác được: `docs/ui-kit/demo/date.html` (cần mạng để tải Flatpickr).

## Khi nào dùng

| Cần | `data-mode` | Giá trị gửi server |
|---|---|---|
| Một ngày | `single` (mặc định) | `YYYY-MM-DD` |
| Khoảng ngày (bộ lọc) | `range` | `YYYY-MM-DD to YYYY-MM-DD` |
| Ngày + giờ | `datetime` | `YYYY-MM-DD HH:mm` |
| Chỉ giờ | `time` | `HH:mm` |

Chữ hiển thị cho người dùng: `dd/mm/yyyy`, `dd/mm/yyyy HH:mm`, `HH:mm`; khoảng ngày hiển thị `dd/mm/yyyy → dd/mm/yyyy`. Giá trị gửi vẫn dùng ` to ` để khớp mã server hiện có.

## Cách dùng

Bọc `<input>` gốc trong `.ui-date[data-ui-date]`. **Ô gốc vẫn giữ `id`, `name`, giá trị và phát `change`**; component chỉ dựng ô hiển thị phía trên (ô này có id `<id>-display`). Nhãn `<label for="id">` bấm vào sẽ mở lịch.

```html
<label for="receive-date">Ngày nhận</label>
<div class="ui-date" data-ui-date data-mode="range" data-max-days="30" data-shortcuts="today,7,30,month">
  <input id="receive-date" name="receive_date" value="{{ request.GET.receive_date }}" placeholder="Chọn ngày nhận">
</div>
```

```django
{# Django form field #}
{% include 'components/ui_date.html' with field=form.appointment_at mode='datetime' step=5 min='now' %}
```

Nạp sẵn trong `base_app_documents_v2.html`: `ui-kit.css`, Flatpickr 4.6.13 (`components/ui_date_assets.html`) và `static/js/ui-date.js`. Trang không extend base này phải tự thêm đủ ba thứ. JS tự khởi tạo mọi `[data-ui-date]`, kể cả phần tử thêm sau. Đặt khối `.ui-date` trong một thẻ bao riêng (ví dụ `<div class="relative">`) vì component thêm dòng lỗi ngay sau nó.

## Tuỳ chọn

| Thuộc tính | Ý nghĩa |
|---|---|
| `data-mode` | `single` · `range` · `datetime` · `time` |
| `data-min` / `data-max` | Ngày nhỏ/lớn nhất chọn được: `today`, `now` hoặc `YYYY-MM-DD` |
| `data-max-days="30"` | (range) Tối đa N ngày; quá thì xóa lựa chọn và báo lỗi (`data-max-days-text` đổi câu báo) |
| `data-step="5"` | Bước phút của bộ chọn giờ |
| `data-min-time` / `data-max-time` | Giới hạn giờ trong ngày, ví dụ `08:00` / `17:30` |
| `data-shortcuts` | Lối tắt, phân tách bằng dấu phẩy. Range: `today`, `7`, `30`, `month`. Ngày/giờ: `today`, `now`, `tomorrow8`, `t:HH:MM` (ví dụ `t:17:30`) |
| `data-link-min="id"` | Ô này không được sớm hơn giá trị của ô có `id` đó (cặp "Từ — Đến"); "Đến" đang sớm hơn thì tự xóa |
| `data-default="today"` | Điền sẵn hôm nay |
| `data-required` hoặc `required` trên input | Bắt buộc (xem "Lỗi") |
| `data-invalid` + `data-error="…"` | Hiện lỗi từ server ngay khi tải trang |
| Class `ui-date-sm` | Cỡ nhỏ 28px |
| `disabled` trên input | Ô xám, không mở được |

## Lỗi

- **Bắt buộc:** chỉ báo lúc **submit form** (viền đỏ + dòng chữ dưới ô, focus vào ô lỗi đầu tiên); không báo ngay khi người dùng xóa ngày.
- Chọn được ngày thì **lỗi tự biến mất** (cả viền đỏ lẫn dòng chữ).
- Lỗi do server trả: `data-invalid` giữ đến khi người dùng chọn lại.

## API JS và sự kiện

| | |
|---|---|
| `change` | Bắn trên ô gốc mỗi khi giá trị đổi (code lắng nghe `change` sẵn có không phải sửa) |
| `window.uiDate.set(input, value)` | Gán giá trị (chuỗi ISO hoặc `Date`) |
| `window.uiDate.clear(input)` | Xóa |
| `window.uiDate.picker(input)` | Lấy đối tượng Flatpickr gốc (cũng là `input._flatpickr`) |

Bàn phím: ↓ / Enter / Space mở lịch; Backspace / Delete xóa; Esc đóng. `form.reset()` xóa giá trị.

## Cấm

- Không tự gọi `flatpickr(...)` rồi tô giao diện riêng cho từng trang; dùng component này.
- Không đọc giá trị từ ô hiển thị (`<id>-display`); luôn đọc ô gốc.
- Không dùng `<input type="date">` trần trong form v2.

## Legacy map

| Cũ | Nơi dùng | Ghi chú |
|---|---|---|
| `flatpickr(...)` trực tiếp trong trang | ngăn chi tiết quyển (`drawer-receive-date`, `drawer-additional-receive-date`), Nhận nhiều, Tạo thùng, Kiểm tra giao dịch, GĐĐB, Mượn chứng từ, Quản lý thùng, KPI | Có mã riêng gọi `picker.setDate/clear`; cần chuyển cùng lúc |
| Flowbite datepicker | `base_v2.html` (admin), `document_detail.html`… | Chưa migrate |
| `<input type="date">` | bưu kiện, ngăn chi tiết, ca làm việc, bộ lọc văn bản hành chính | Chưa migrate |

## Ghi chú kỹ thuật

- Tệp: `static/js/ui-date.js`; CSS trong `ui-kit.css` (mục "Date"); lịch được phủ giao diện qua class `ui-date-cal` nên không ảnh hưởng các lịch Flatpickr chưa migrate. Tăng `?v=` ở `base_app_documents_v2.html` khi sửa.
- Ô gốc được Flatpickr chuyển thành `type="hidden"`, nên lỗi "bắt buộc" do component tự kiểm tra lúc submit (trình duyệt không kiểm tra input ẩn).
- Kiểm thử: `app_documents/tests/access/test_receiving_selects.py` (cấu trúc trang Nhận chứng từ). Hành vi (ngày, khoảng ngày + giới hạn, lối tắt, bắt buộc, lỗi server, reset, ngày giờ, giờ + giới hạn, cặp liên kết, API) kiểm tra bằng 35 phép thử trên Chrome headless với trang demo.
