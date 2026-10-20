# Button

Trạng thái: 🟡 **Đang migrate** — CSS dùng chung `static/css/ui-kit.css` đã có và được nạp qua `app_documents/base_app_documents_v2.html`.

| App | Trạng thái |
|---|---|
| `app_admindocuments` | 🟢 Đã migrate (`adm-button*` đã xóa) |
| `app_document_campaigns` | 🟢 Đã migrate (`crm-btn`, `crm-mini-btn`, `dec-btn`, `dcf-btn`, `mm-button` đã xóa) |
| `app_documents` (v2) | 🟡 Đã migrate 95 nút Tailwind rõ kiểu (primary/secondary/danger); còn các nút ở mục "Chưa migrate" bên dưới. v1 (Bootstrap) đã gỡ bỏ |
| `app_workshift` | ⚪ Chưa quét |

Nguồn token: [DESIGN.md](../../../DESIGN.md) (`button-primary`, `button-secondary`, `button-danger`, `rounded.button = 8px`).

## Khi nào dùng

| Cần | Dùng |
|---|---|
| Hành động chính của màn hình / dialog (Lưu, Gửi, Xác nhận) | `ui-btn ui-btn-primary` |
| Hành động phụ (Hủy, Đóng, Xuất file, Lọc) | `ui-btn ui-btn-secondary` |
| Hành động phá huỷ (Xóa, Hủy tờ trình) | `ui-btn ui-btn-danger` |
| Hành động nhẹ trong dòng bảng / toolbar | `ui-btn ui-btn-ghost` + `ui-btn-sm` |
| Nút chỉ có icon (đóng, sửa, copy) | `ui-btn ui-btn-icon` (bắt buộc `aria-label`) |
| Điều hướng sang trang khác | `<a class="ui-btn ...">`, không dùng `<button onclick="location...">` |

**Mỗi vùng chỉ có tối đa 1 nút màu đậm (primary / info / warning)** (một dialog, một thanh toolbar, một card).

## Anatomy

`[icon 14px?] [nhãn] ` — cao `34px` (md), bo góc `8px`, chữ 10px / weight 600, khoảng cách icon–nhãn `7px`, không xuống dòng.

## Biến thể (variant)

| Class | Nền | Chữ | Viền | Hover |
|---|---|---|---|---|
| `ui-btn-primary` | `primary` #00844A | trắng | cùng màu nền | nền `primary-hover` #006837 |
| `ui-btn-secondary` | trắng | `text` #1F2937 | `border-strong` #D1D5DB | nền `surface-muted` #F9FAFB |
| `ui-btn-danger` | `danger-soft` #FEF2F2 | `danger-text` #DC2626 | `danger-border` #FECACA | nền #FEE2E2 |
| `ui-btn-info` | `info-strong` #1769AA | trắng | cùng màu nền | nền #125A92 |
| `ui-btn-warning` | `warning-strong` #D97706 | trắng | cùng màu nền | nền #B45309 |
| `ui-btn-ghost` | trong suốt | `text-muted` #6B7280 | không | nền `surface-subtle` #F3F4F6 |

> `info` dùng cho hành động trung tính-nổi bật (Sao chép link, Xem trước); `warning` cho hành động cần thận trọng nhưng không phá huỷ (Gửi lại, Ghi đè). Vẫn tuân thủ "tối đa 1 nút màu đậm mỗi vùng".

## Kích thước

| Class | Cao | Padding | Chữ |
|---|---|---|---|
| `ui-btn-sm` | 28px | 4px 10px | 10px |
| (mặc định, md) | 34px | 7px 12px | 10px |
| `ui-btn-lg` | 40px | 9px 18px | 12px — chỉ dùng cho CTA trang đơn như form tạo mới |

Modifier khác: `ui-btn-block` (rộng 100%).

## Trạng thái

| Trạng thái | Quy tắc |
|---|---|
| hover | theo bảng variant |
| focus-visible | `outline: 2px solid #A7F3D0; outline-offset: 2px` (không bỏ outline) |
| disabled | nền `disabled` #F3F4F6, chữ `disabled-text` #9CA3AF, `cursor: not-allowed`; dùng thuộc tính `disabled` (hoặc `aria-disabled="true"` cho thẻ `<a>`) |
| loading | thêm class `is-loading` + `disabled`; hiện spinner 13px bên trái nhãn, giữ nguyên độ rộng nút, không đổi nhãn thành "..." |

## HTML mẫu

```html
<!-- Primary + secondary trong dialog -->
<div class="ui-btn-group">
  <button type="button" class="ui-btn ui-btn-secondary" data-close>Hủy</button>
  <button type="submit" class="ui-btn ui-btn-primary">Lưu</button>
</div>

<!-- Có icon -->
<button type="button" class="ui-btn ui-btn-secondary">
  <svg aria-hidden="true">...</svg> Xuất Excel
</button>

<!-- Danger -->
<button type="submit" class="ui-btn ui-btn-danger">Xóa</button>

<!-- Icon-only -->
<button type="button" class="ui-btn ui-btn-ghost ui-btn-icon ui-btn-sm" aria-label="Sao chép">
  <svg aria-hidden="true">...</svg>
</button>

<!-- Link trông như nút -->
<a href="{% url 'admindocuments:document_list' %}" class="ui-btn ui-btn-secondary">Quay lại</a>

<!-- Loading -->
<button type="submit" class="ui-btn ui-btn-primary is-loading" disabled>Gửi email</button>
```

`ui-btn-group`: flex, `gap: 8px`, căn phải trong footer dialog; thứ tự **phụ trước, chính sau** (chính nằm bên phải).

## Cấm

- Không hard-code màu / `border-radius` / `font-size` trên nút bằng `style=""` hoặc CSS riêng của trang.
- Không dùng `<div>`/`<span>` làm nút.
- Không đặt 2 nút primary cạnh nhau.
- Không tự thêm họ class mới (`xxx-btn`).
- Không dùng Bootstrap `btn btn-*` cho trang mới (xem Legacy map về `app_documents`).

## Legacy map — class cũ → class kit

Dùng bảng này khi migrate. Thực trạng quét ngày 2026-10-19.

| Class cũ | Nơi dùng | → Kit | Ghi chú lệch chuẩn |
|---|---|---|---|
| `adm-button` | `app_admindocuments` | `ui-btn ui-btn-secondary` | ✅ Đã migrate (template + `admin_ui.js` tự gán class cho nút Tailwind) |
| `adm-button-primary` | như trên | `ui-btn-primary` | trùng màu chuẩn |
| `adm-button-gray` | như trên | `ui-btn-secondary` | nền xám #E5E7EB → trắng |
| `adm-button-danger` | như trên | `ui-btn-danger` | |
| `crm-btn` | `app_document_campaigns` monitor/dialog | `ui-btn-primary` (hoặc `lg` nếu cần giữ cỡ) | hiện 39px, 9px radius, 12px/750, không viền |
| `crm-btn-outline` | như trên | `ui-btn-secondary` | viền xanh → xám |
| `crm-btn-blue` | như trên | `ui-btn-info` | |
| `crm-mini-btn` | như trên (~28 lần) | `ui-btn-secondary ui-btn-sm` | hiện nền xanh nhạt, 31px, chữ 800 |
| `crm-mini-btn.is-copy` | như trên | `ui-btn-info ui-btn-sm` | nền xanh dương |
| `dec-btn-primary` | `campaign_detail`, `dataset_panel` | `ui-btn-primary` | hiện 42px, 10px radius, 13px |
| `dec-btn-secondary` | như trên | `ui-btn-secondary` | viền xanh → xám |
| `dec-btn-blue` / `dec-btn-warning` | như trên | `ui-btn-info` / `ui-btn-warning` | |
| `dcf-btn-primary` / `-secondary` | `campaign_form` | `ui-btn-primary` / `-secondary` (+ `lg`) | hiện 40px, 10px radius, 12px |
| `mm-button` / `mm-primary` / `mm-danger` / `mm-quiet` | `mail_merge_preview` | `ui-btn` / `-primary` / `-danger` / `-ghost` | |
| `mm-icon-button` | như trên | `ui-btn-ghost ui-btn-icon ui-btn-sm` | |
| `btn btn-*` (Bootstrap 5) | `app_documents` v1 | — | Đã xóa cùng giao diện v1 (2026-10-19); `base.html` Bootstrap chỉ còn cho trang đăng nhập / đặt lại mật khẩu |
| Tailwind trực tiếp: `px-* py-* rounded-lg bg-emerald-600 text-white hover:bg-emerald-700` | `app_documents` v2 | `ui-btn ui-btn-primary` | Đã migrate |
| Tailwind: `px-* py-* rounded-lg border border-gray-200 text-gray-700 hover:bg-gray-50` | `app_documents` v2 | `ui-btn ui-btn-secondary` | Đã migrate |
| Tailwind: `border-red-200 text-red-600 hover:bg-red-50` | `app_documents` v2 | `ui-btn ui-btn-danger` | Đã migrate |
| `btn-close` | modal Bootstrap | giữ nguyên (thuộc component Modal) | không động vào trong đợt Button |
| `tab-btn`, `parcel-mode-button`, `toggle-btn` | rải rác | **không phải Button** — thuộc component Tabs/Toggle | để sau |

## Chưa migrate trong app_documents v2

Đã xong: nút PosMini / đăng ký / nhận hàng loạt (`app_gddb_registration_v2.html`, dùng hàm `setPostminiButtonState`) và nút Lưu cập nhật (`app_borrow_request_detail_v2.html`).

Quy tắc cho nút đổi trạng thái bằng JS: không thao tác từng class Tailwind. Gán `button.className = 'ui-btn ui-btn-<variant>'` (hoặc dùng một hàm helper như `setPostminiButtonState`) và dùng thuộc tính `disabled` cho trạng thái khóa.

Còn lại (không thuộc Button, để các component sau): tab, link trên `top_nav_v2.html`, mục dropdown, nút tròn chỉ icon, chip lọc, nút chọn view (Card/Bảng), `input[type=file]::file-selector-button`. Cần soát tay các nút React/JSX có `=>` trong thuộc tính ở `app_package_list_v2.html` nếu phát sinh thêm.

## Quyết định đã chốt

1. Thêm variant `info` (#1769AA) và `warning` (#D97706) — token `info-strong`, `warning-strong` trong DESIGN.md.
2. `app_documents`: giao diện v1 (Bootstrap) đã gỡ; chỉ migrate nút Tailwind của v2.
3. CSS dùng chung: `static/css/ui-kit.css`, nạp ở `base_app_documents_v2.html`. Trang không extend base này (vd. `app_documents/base.html` Bootstrap, các trang standalone) phải tự `<link>`.

## Lưu ý kỹ thuật

- Nút có thuộc tính `hidden` vẫn ẩn đúng (kit có `.ui-btn[hidden]`).
- Loading: JS chỉ cần `disabled = true` + `classList.add('is-loading')`; nút giữ nguyên màu variant. Không đổi `disabled` sang style xám khi đang loading.
- Nhóm nút hành động trong `.crm-info-actions` (trang theo dõi phản hồi) dùng `ui-btn-secondary ui-btn-block` — trước đây là các nút xanh đặc, đổi để tuân thủ "tối đa 1 nút primary mỗi vùng".
- Nút trong dialog campaign cần chiều rộng tối thiểu: dùng selector theo ngữ cảnh (`.crm-dialog-actions .ui-btn { min-width: 108px }`), không tạo variant mới.
- `ui-btn` trần (không variant) trông như secondary, nhưng luôn ghi rõ `ui-btn-secondary` trong template mới.
- Khi sửa `ui-kit.css`, tăng `?v=` ở `base_app_documents_v2.html` để bust cache.

## Checklist khi thêm / sửa nút

- [ ] Dùng đúng variant theo bảng "Khi nào dùng"
- [ ] Tối đa 1 primary trong vùng
- [ ] Có `type="button"` hoặc `type="submit"` rõ ràng
- [ ] Icon-only có `aria-label`
- [ ] Có trạng thái disabled/loading nếu hành động gọi server
- [ ] Không còn class `btn-*`, `adm-button*`, `crm-*btn`, `dec-btn*`, `dcf-btn*`, `mm-button` trong code mới
