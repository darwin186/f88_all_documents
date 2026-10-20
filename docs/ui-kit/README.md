# F88 Documents UI Kit

Bộ quy chuẩn UI dùng chung cho **toàn dự án** (`app_admindocuments`, `app_document_campaigns`, `app_documents`, `app_workshift`).

> **Đọc file này đầu tiên** khi làm bất kỳ thay đổi UI nào. Sau đó đọc file component tương ứng. Không tự viết CSS mới nếu kit đã có component.

## Nguồn sự thật (thứ tự ưu tiên)

1. `docs/ui-kit/components/*.md` — spec từng component (file này thắng nếu mâu thuẫn).
2. [`DESIGN.md`](../../DESIGN.md) — tokens màu / chữ / bo góc / tinh thần thiết kế.
3. Code hiện có — chỉ để tra cứu, có thể đang lệch chuẩn (xem mục "Legacy map" trong từng component).

## Danh sách component

| Component | Trạng thái | File |
|---|---|---|
| Button | 🟡 Đang migrate (admindocuments xong) | [components/button.md](components/button.md) |
| Select (droplist, chọn 1 hoặc nhiều) | 🟡 Mới — đã áp dụng cho modal Tạo giấy hành chính | [components/select.md](components/select.md) · [demo](demo/select.html) |
| File (ô chọn tệp gọn, nút mũi tên) | 🟡 Đã áp dụng cho các ô tải một tệp | [components/file.md](components/file.md) · [demo](demo/file.html) |
| Toast (thông báo) | 🟢 Đã áp dụng toàn hệ thống | [components/toast.md](components/toast.md) · [demo](demo/toast.html) |
| Badge status | ⚪ Chưa làm | — |
| Table | ⚪ Chưa làm | — |
| Form field | ⚪ Chưa làm | — |
| Modal / Drawer | ⚪ Chưa làm | — |

Trạng thái: ⚪ chưa làm → 🟡 draft (spec xong, code chưa migrate) → 🟢 stable (CSS dùng chung đã có, template đã migrate).

## Quy tắc chung

- Một component = một họ class duy nhất, tiền tố `ui-`. Không tạo họ class mới theo từng app (`crm-`, `dec-`, `dcf-`, `mm-`, `adm-`...).
- Màu / bo góc / cỡ chữ lấy từ biến CSS (xem DESIGN.md), không hard-code hex trong template.
- Không inline `style=""` cho thứ kit đã định nghĩa.
- Đổi spec thì **sửa .md cùng commit** với code. .md lệch code là lỗi.

## Cách thêm một component mới vào kit

1. Quét các template để xem component đang được dùng ra sao (grep class, liệt kê file).
2. Viết `components/<tên>.md` theo mẫu trong [button.md](components/button.md): Khi dùng / Anatomy / Biến thể / Trạng thái / HTML mẫu / Legacy map / Checklist.
3. Thêm vào bảng ở trên.
4. Tạo CSS dùng chung, migrate template từng app, đổi trạng thái sang 🟢.
