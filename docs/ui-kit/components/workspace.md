# Operations workspace — panel, bảng, form field, badge

Trạng thái: 🟡 **Mới** — dùng trong `app_soft_review`, chưa migrate màn cũ. Nguồn token: [DESIGN.md](../../../DESIGN.md).

Nạp `static/css/ui-workspace.css` sau `ui-kit.css`. Button, Select, File và Toast dùng nguyên spec/JS hiện có. App kế thừa assets và nền/font của `base_app_documents_v2.html`, dùng navbar module riêng thay cho navbar nghiệp vụ bản cứng.

## Typography (token)

Cỡ chữ của kit nằm ở `:root` trong `ui-kit.css`: `--ui-fs-xs` 9px, `--ui-fs-sm` 10px, `--ui-fs-md` 11px, `--ui-fs-lg` 12px; bảng dùng `--ui-fs-table` (nội dung) và `--ui-fs-table-head` (header). Đổi giá trị ở đó là đổi toàn bộ component kit. Font: bảng/header bảng `--ui-font-table` (Be Vietnam Pro), số hiệu `.ui-code` với `--ui-font-code` (JetBrains Mono). Navbar và template mail giữ nguyên. Màn cũ dùng `text-[10px]` của Tailwind chưa đọc token này.

## Khi dùng

Màn vận hành có bộ lọc, tổng số, bảng/phân trang, form cấu hình hoặc duyệt theo nhóm.

## Anatomy

Navbar module `ui-module-nav` → `ui-workspace` → bộ lọc `ui-panel` + `ui-grid` → `ui-stats` → `ui-table` trong `ui-table-scroll` → phân trang. `ui-tabs` dùng cho các tab nội dung chi tiết.

Navbar gồm logo về trang chủ, tên module, các chức năng chính và menu tài khoản dùng chung `components/ui_user_menu.html`. Mục hiện tại có `aria-current="page"`. Dưới 1100px, các chức năng xuống hàng thứ hai và cuộn ngang trong navbar; `ui-module-main` chừa đúng khoảng trống bên dưới. Các mục quản trị vẫn theo quyền của server.

Màn chi tiết dùng `ui-description`. Nội dung duyệt dùng `ui-review-row`: tên/hướng dẫn ở trái, Select ở phải, về một cột trên màn nhỏ. Không bọc Select trong vùng cuộn bảng để tránh cắt menu.

## Biến thể

| Thành phần | Class | Quy tắc |
|---|---|---|
| Panel | `ui-panel` | Surface, border, bo 16px, padding 16px |
| Field | `ui-field` | Nhãn 10px, ô nhập 34px, focus theo token |
| Bảng | `ui-table` | Chữ 10px, header 9px nền surface-muted, padding 8px × 12px |
| Badge | `ui-badge` | Nhãn chữ, 9px, bo tròn |
| Đạt | `ui-badge-success` | primary-soft + primary-text |
| Không đạt | `ui-badge-danger` | danger-soft + danger-text |
| Chỉ dẫn thường trực | `ui-note` | Không thay Toast thông báo kết quả thao tác |
| Cảnh báo dữ liệu | `ui-note-warning` | Nhãn giải thích, màu danger |
| Hai cột | `ui-split` | Tỷ lệ 2:1, về một cột dưới 760px |
| Footer duyệt | `ui-review-actions` | Sticky dưới, nền surface, có khoảng trống cuối layout |

## Trạng thái

- Tab hiện tại: `aria-current="page"`, gạch chân xanh.
- Rỗng: `ui-table-empty`, giải thích theo bộ lọc/phạm vi.
- Field lỗi: `errorlist` dưới ô; lỗi chung có `role="alert"`.
- Chỉ đọc: `disabled`; server vẫn kiểm quyền.
- Không dùng màu làm dấu hiệu duy nhất.

## HTML mẫu

```html
<section class="ui-panel ui-stack">
  <h2>Thông tin hợp đồng</h2>
  <div class="ui-field">
    <label for="contract-code">Mã hợp đồng *</label>
    <input id="contract-code" name="contract_code" required>
  </div>
  <div class="ui-btn-group">
    <button type="submit" class="ui-btn ui-btn-primary">Lưu</button>
  </div>
</section>
```

## Legacy map

Màn cũ ở `app_documents`/`app_document_campaigns` dùng Tailwind/CSS riêng. Chưa migrate trong đợt này; CSS mới chỉ nạp ở app bản mềm.

## Checklist

- [ ] Dùng token; không hex/inline style trong template mới.
- [ ] Một nút màu đậm mỗi vùng.
- [ ] Bảng có tiêu đề, trạng thái rỗng và cuộn ngang.
- [ ] Select không bị overflow cắt menu.
- [ ] Kiểm tra desktop và màn nhỏ.
