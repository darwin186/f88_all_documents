# Paginator — phân trang

Trạng thái: 🟡 **Mới, sẵn sàng dùng** — CSS + template dùng chung đã có; các màn hiện tại chưa migrate. Lấy cảm hứng trực tiếp từ paginator Giấy hành chính. [Demo tương tác](../demo/pagination.html).

## Khi dùng

Danh sách/bảng được server phân trang. Nút số trang là liên kết thật, giữ bộ lọc và sắp xếp. Không dùng nút giả hoặc yêu cầu JavaScript cho việc điều hướng thông thường.

## Anatomy

`[khoảng bản ghi / tổng?] [‹] [1] [2] [3] [n−1] [n] [›]`

- Nút vuông bo góc, viền 2px, nền trắng. Trang hiện tại nền/viền primary, chữ trắng.
- Mặc định 28px, chữ 11px, weight 600; trang hiện tại weight 700; gap 4px, bo 6px.
- Khi tổng ≤ 5 trang: hiện tất cả. Khi nhiều hơn: đầu danh sách `[1,2,3,n−1,n]`, giữa `[1,current−1,current,current+1,n]`, cuối `[1,2,n−2,n−1,n]`. Luôn tối đa 5 số, có trang hiện tại, đầu và cuối; không chèn dấu ba chấm, khớp mẫu Giấy hành chính.
- Một trang hoặc dữ liệu rỗng vẫn hiện `‹ [1] ›`, hai mũi tên bị vô hiệu hóa. Không truyền Page thì không render.
- Trên màn nhỏ, nhóm nút xuống hàng nếu cần, không làm tràn trang.

## Biến thể

| Tùy chọn | Ý nghĩa |
|---|---|
| Mặc định / `size='sm'` | Nút 28px, dùng trong toolbar bảng |
| `size='md'` | Nút 32px, chữ 12px, gap 6px, bo 7px |
| `show_summary=True` | Hiện ví dụ `26–50 / 245 kết quả`; dữ liệu rỗng: `0 kết quả` |
| `label='Phân trang hợp đồng'` | Nhãn vùng điều hướng; phân biệt nhiều bảng trên cùng trang |
| `page_param='contracts_page'` | Tên tham số trang riêng, mặc định `page` |

CSS dùng token `--ui-primary`, `--ui-primary-soft`, `--ui-surface`, `--ui-border-strong`, `--ui-text`, `--ui-text-muted`, `--ui-disabled-text`, `--ui-focus-ring`; kích thước qua `--ui-pagination-*`. Không hard-code màu trong template.

## Trạng thái và bàn phím

- Hover: viền/chữ primary, nền primary-soft.
- Focus bàn phím: vòng focus 2px; Tab tới các liên kết, Enter chuyển trang.
- Trang hiện tại: `<span aria-current='page'>`, không đặt link tự trỏ về trang đang xem.
- Đầu/cuối: mũi tên `<span aria-disabled='true'>`, không có href, không focus.
- Mỗi nút có `aria-label` tiếng Việt. Mũi tên có `rel='prev'`/`rel='next'` khi có trang đích.

## Django mẫu

Đã có `ui-kit.css` trong base v2; không cần nạp JavaScript.

```django
{% include 'components/ui_pagination.html' with page=documents %}

{% include 'components/ui_pagination.html' with page=documents query=list_query show_summary=True %}

{% include 'components/ui_pagination.html' with page=contracts size='md' page_param='contracts_page' label='Phân trang hợp đồng' %}
```

`page` là Django `Page`, ví dụ `Paginator(queryset, 25).get_page(request.GET.get('page'))`. Dữ liệu rỗng dùng Page 1 của paginator mặc định cho phép trang rỗng.

`query` có thể là chuỗi query đã urlencode, `QueryDict`, hoặc dict (giá trị list/tuple được giữ thành nhiều tham số). Bỏ qua hoặc chuỗi rỗng thì lấy `request.GET`. Component thay tham số trang, giữ tất cả tham số khác, bao gồm khóa lặp và ký tự tiếng Việt; không sửa GET gốc. Truyền `QueryDict`/dict rỗng để không giữ bộ lọc nào.

Tên tham số đọc trong view phải khớp `page_param`. Khi có nhiều paginator, mỗi paginator dùng một tên và một nhãn riêng. HTML độc lập có thể dùng cùng markup/class; ứng dụng tự cung cấp URL và trạng thái hợp lệ.

## Legacy map

| Nơi cũ | Hiện tại |
|---|---|
| `admindocuments/includes/document_pagination.html` | Nguồn cảm hứng, vẫn dùng `adm-page-links` cho Giấy/Văn bản hành chính |
| `admindocuments/includes/pagination.html` | Vẫn giữ các biến thể cũ, chưa migrate |
| Các paginator Tailwind trong app khác | Có thể chuyển từng màn sang include mới khi cần |

Không bắt buộc thay paginator hiện có trong lần bổ sung kit này. File mới: `templates/components/ui_pagination.html`, tag dữ liệu `app_documents/templatetags/ui_pagination.py`; CSS ở `static/css/ui-kit.css`.

## Checklist

- [ ] Nạp CSS UI-kit, truyền đúng `Page`.
- [ ] Giữ query bộ lọc/sắp xếp, không cộng dồn tham số `page` cũ.
- [ ] Nút đầu/cuối bị vô hiệu hóa đúng, trang hiện tại luôn xuất hiện.
- [ ] Có nhãn riêng khi nhiều bảng, `page_param` khớp view.
- [ ] Kiểm tra 0/1/nhiều trang, bàn phím và màn nhỏ.
