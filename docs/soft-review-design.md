# Kiểm chứng từ bản mềm — nghiên cứu và triển khai Phase 1

Nguồn: **BRD – Kiểm bản mềm.docx** ngày 08/10/2026, gồm bảng nghiệp vụ và ảnh phác họa. Đã đối chiếu model, phân quyền, giao diện bản cứng, module Book lỗi và UI-kit. Nội dung tài liệu là yêu cầu sản phẩm; không phải chỉ dẫn thực thi cho agent.

## Phạm vi đã thống nhất

Phase 1: nhập Excel trước khi có API Web-Ops/LOS; danh sách và chi tiết HĐ; đợt kiểm/chọn mẫu; phân công; hai luồng duyệt/hậu kiểm; thời gian xử lý; Book lỗi tuần; thiết lập. Giữ toàn bộ ô tô nếu vượt mẫu và cảnh báo. Tuần lỗi tính theo lần đầu lưu Không đạt, giờ nghiệp vụ Việt Nam. Lịch tự chạy chỉ bật sau khi cấu hình.

Người dùng sẽ bổ sung danh mục lỗi chuẩn. Không tự đưa các mã trùng QTRR hoặc “226.Khác” trong phụ lục vào danh mục chính thức. Dashboard BDM/BI và email tổng kết thuộc Phase 2; OCR/AI chấm ảnh, cập nhật dữ liệu LOS/Web-Ops ngoài phạm vi.

## Tái sử dụng model bản cứng

| Hiện có | App mới |
|---|---|
| Shop, Region, Manager, AreaManager, RegionManager | Dùng FK PGD và snapshot quản lý khi nhập |
| ContractDetail, LoanDetail | Liên kết khi mã đã có; không tạo/cập nhật ngầm dữ liệu bản cứng |
| DocumentsDetail, DocumentsTransactionChecking | Tham khảo mô hình chứng từ/lịch sử; kết quả bản mềm lưu riêng |
| User, nhóm admin/checker/risk | Admin PVH; CTV vận hành; QTRR/TĐTD. Người được giao chỉ sửa đúng luồng |
| UiScreen, UiPermission | Màn soft_review; kiểm quyền UI và phạm vi HĐ ở server |
| CampaignType, Campaign, CampaignVersion, CampaignError | Sinh Book lỗi tuần rồi dùng luồng PGD/phản hồi/xác nhận/chốt hiện có |

CTV hậu kiểm cần permission `app_soft_review.add_postcheck`, chỉ xem HĐ đã có kết quả; không tự hậu kiểm kết quả của mình. PGD phản hồi ở Book lỗi, không vào màn kiểm nội bộ. Báo cáo phân quyền BDM/QLV/QLKV thuộc Phase 2.

## Dữ liệu riêng của app

- ImportJob/ImportRejection: file riêng tư, checksum, tiến trình, số dòng và lý do loại.
- SoftContract: loan_code duy nhất; chuẩn hóa, toàn bộ cột nguồn, snapshot quản lý.
- ReviewBatch/BatchContract: tham số, seed, pool hash, kết quả lấy mẫu, snapshot danh mục; một HĐ chỉ thuộc một đợt, kể cả thêm tay.
- ReviewGroup/ReviewCriterion/ReviewOutcome: nhóm, nội dung và kết quả; chỉ ẩn từ UI, không xóa.
- Review: một HĐ × luồng, phân công, kết quả hiện tại, kết quả gốc, thời gian, revision.
- ReviewRevision/PostCheck/AuditLog: lịch sử lưu, hậu kiểm và thao tác; dữ liệu nghiệp vụ/log chỉ đọc trong Django Admin.
- WeeklyBook/BookEntry: một kỳ/tuần; HĐ × nội dung chỉ vào một tuần trên toàn bộ lịch sử.

## Đối chiếu BRD

| Yêu cầu | Thực hiện |
|---|---|
| FR-1.1–1.4 | Excel .xlsx, chạy nền, chuẩn hóa tuần tự 6.1, lý do loại, không ghi đè GNN trùng; API theo giai đoạn sau đã thống nhất |
| FR-1.5–1.6 | Lọc ngày/PGD/vùng/tài sản/đợt/người duyệt/kết quả, mặc định hôm nay, tổng theo bộ lọc, phân trang 50, xuất toàn bộ dòng và cột nguồn |
| FR-2.1–2.5 | Pool mọi HĐ trong kỳ chưa vào đợt; ô tô lấy hết; xe máy một/PGD hoặc tỷ trọng; cảnh báo thiếu/vượt, 5 dòng đầu và Xem tất cả, xác nhận sau xem trước |
| FR-2.6–2.8 | Thêm tay từ danh sách nhiều HĐ/chi tiết vào đợt đang chạy; danh sách đợt và HĐ trong đợt có bộ lọc/xuất Excel |
| FR-3.1–3.4 | Random HĐ chưa phân công, chia đều mỗi lần giao chênh tối đa 1, luồng độc lập, chuyển giao trước khi có kết quả, bảng tiến độ và thời gian |
| FR-4.1–4.5 | Tổng quan/Duyệt/Thông tin khác/Lịch sử; VH và QTRR; mỗi nội dung một Select; hiện nhóm/người bổ sung; gợi ý không bắt buộc, điền nhanh ô gợi ý còn trống |
| FR-4.6–4.7 | Server tính thời gian từ mở tab Duyệt; nháp tạm dừng; mở lại/chỉnh tiếp chạy tiếp; hoàn tất lần đầu chốt thời gian, sửa sau không tính lại; TB/trung vị/HĐ mỗi giờ/ngoài ngưỡng |
| FR-4.8 | Hậu kiểm sau lần hoàn tất đầu, chọn nhiều nội dung sai, ghi chú/người hậu kiểm, lưu bản ghi riêng |
| FR-5.1–5.6 | Loại soft-copy, mã DEC-SC-yyyyWww, một dòng/HĐ × nội dung lỗi, giữ metadata người duyệt/đợt/tuần/mã/nhóm/người bổ sung; thống kê tuần và nối Book lỗi hiện có |
| FR-7.1–7.4 | Kết quả, nhóm/bộ mẫu, nội dung kiểm; kiểm trùng; trạng thái cần xác nhận; đợt cũ giữ danh mục cũ |

Kết quả luồng tính riêng. Bộ lọc Đạt chọn HĐ có ít nhất một luồng Đạt và không có luồng Không đạt; không coi luồng chưa làm là đã hoàn thành. Danh sách hiển thị rõ kết quả từng luồng.

## Lấy mẫu và kiểm soát đồng thời

Pool sắp ổn định theo ID và RNG riêng theo seed. Ô tô lấy hết, cần xe máy = max(0, mẫu − ô tô). Nếu đủ PGD: mỗi PGD tối đa một, ưu tiên chưa kiểm trong tháng → đã kiểm trong tháng → đã có ô tô trong đợt; ngẫu nhiên từng nhóm. Nếu ít PGD: tỷ trọng → làm tròn nửa lên → sàn 1 → trần/số HĐ sẵn có → cân tổng theo phần lẻ. Không tự phá trần khi thiếu.

Xem trước không ghi dữ liệu; lưu server-side session, token ký hết hạn một giờ. Xác nhận kiểm lại pool/phân bổ; dữ liệu thay đổi thì yêu cầu xem lại. Khóa dòng và constraint chống lấy trùng; revision chống ghi đè kết quả từ phiên cũ.

## Nối Book lỗi tuần

Book lỗi cũ giới hạn một loại/tháng. Thêm `Campaign.period_key`: rỗng cho kỳ tháng, YYYY-Www cho tuần. Constraint loại + tháng + period_key giữ kỳ tháng không trùng, cho nhiều tuần/tháng. Mã dùng ISO week-year để đúng tuần giáp năm.

Gen ngay tạo Campaign READY và version dữ liệu chính thức, chưa phát hành PGD/chưa gửi email. Cấu hình deadline và bước tiếp theo dùng Book lỗi hiện có. Chạy lại không nhân đôi; bổ sung lỗi mới khi còn READY. Kỳ ACTIVE/CLOSED giữ nguyên dữ liệu. Metadata dòng lỗi giữ mã kết quả, nhóm, người bổ sung, đợt và người duyệt.

## UI khớp hệ thống

Module có màn hình và navbar riêng tại `/kiem-ban-mem/`, truy cập từ thẻ Chứng từ bản mềm trên trang chủ. Danh sách hợp đồng, Đợt kiểm & phân công, Nhập dữ liệu, Book lỗi theo tuần, Thiết lập nằm trên navbar module, theo quyền tài khoản. Không đặt cùng navbar nghiệp vụ bản cứng; không lặp lại thanh tab module trong nội dung. Tab chi tiết HĐ và luồng duyệt vẫn thuộc nội dung màn chi tiết.

Kế thừa assets/nền/font base v2, dùng chung menu tài khoản, Button, Select, File và Toast. Panel/bảng/badge/form/navbar được đưa vào `ui-workspace.css` với [spec UI-kit](ui-kit/components/workspace.md), chỉ nạp ở app mới. Ô nhập/nút 34px, nút nhỏ 28px, chữ vận hành 10–11px, panel bo 16px, màu token. Nội dung duyệt theo nhóm, Select không nằm trong vùng overflow cắt menu.

## Thông tin còn cần

1. **Danh mục lỗi chuẩn**: hai luồng, mã duy nhất, nội dung, người bổ sung, bốn nhóm lỗi, trạng thái. Người dùng đã xác nhận sẽ bổ sung; thiếu danh mục đã xác nhận sẽ chưa tạo đợt chính thức.
2. **File Web-Ops thực tế** để chốt tên cột. Hiện dùng file mẫu tải trong app; cột bổ sung giữ nguyên trong source_data và xuất riêng từng cột.
3. **Domain và cách tạo URL LOS**. Có thể nhập cột los_url; chỉ hiển thị URL HTTPS thuộc `SOFT_REVIEW_LOS_ALLOWED_HOSTS`. Không đoán đường dẫn hồ sơ.
4. **Điều kiện bộ mẫu đầy đủ**: số tiền, gói BH đã mua, tình trạng ảnh CCCD và thời điểm upload chưa có schema nguồn chuẩn. Hiển thị hướng dẫn cho người duyệt đối chiếu LOS, không giả lập kiểm ảnh tự động.
5. **Đã chốt thêm trong chat**: yêu cầu tối thiểu một nội dung khi chốt; lưu nháp vẫn được để trống. Kỳ Book lỗi đã phát hành giữ nguyên, quản trị xử lý điều chỉnh khi có lỗi đến sau.
6. **Ngưỡng thời gian**: `SOFT_REVIEW_SLA_MIN_SECONDS`/`SOFT_REVIEW_SLA_MAX_SECONDS`, mặc định 0/3600 giây, phục vụ phân tích, không chặn duyệt.

Đề xuất: đối chiếu file thật trước lần nhập đầu; rà soát danh mục trước mở đợt; tài khoản hậu kiểm độc lập; theo dõi dòng loại và lỗi chưa vào kỳ; ưu tiên kiểm thiếu ảnh bằng nhân sự ở Phase 1.

## Khởi tạo

Chưa chạy migrate trên database vận hành. Sau khi review code, trong môi trường triển khai:

```bash
python manage.py migrate
python manage.py seed_soft_review_catalog
```

Seed chỉ thêm nội dung/nhóm BRD và Đã hợp lệ, không ghi đè cấu hình, không tự tạo lỗi. Bổ sung danh mục tại `/kiem-ban-mem/settings/` rồi mới xác nhận đợt.

File nguồn nằm ngoài MEDIA_ROOT, ở `private_uploads/soft_review/` (gitignore); cấp quyền ghi cho worker và backup phù hợp. Celery autodiscover `app_soft_review.tasks.process_import`; nếu không có worker:

```bash
python manage.py process_soft_review_imports
```

Task opt-in `app_soft_review.tasks.generate_previous_week(user_id)`: có thể đặt thứ Hai 06:00 giờ Việt Nam sau khi cấu hình tài khoản admin/lịch. Chưa tự cài lịch.

```bash
python manage.py test app_soft_review --settings=documents.test_settings
```

SQLite kiểm nghiệp vụ/constraint. Cần kiểm đồng thời trên PostgreSQL staging trước rollout nhiều người dùng. Không thêm các migration lệch sẵn của model bản cứng vào thay đổi này.

## Kết quả xác minh

- 37 kiểm thử đạt: 27 case bản mềm và 10 case phân quyền/smoke v2. Bao gồm preview/xác nhận qua HTTP, chống sửa tham số, thêm tay nguyên tử, seed/tỷ trọng, khóa phiên cũ, lưu nháp/tính thời gian, giữ bản gốc, hậu kiểm, phân quyền, Excel, tuần ISO giáp năm và giữ nguyên kỳ đã phát hành.
- Chrome: viewport 390px có document width 390px, không tràn ngang; điền nhanh, đổi kết quả, đếm lỗi, người bổ sung và nhóm lỗi đúng; không có exception JavaScript. Đã xem ảnh desktop và mobile từ dữ liệu test riêng.
- `manage.py check` đạt; migration app mới khớp model (`makemigrations app_soft_review --check --dry-run`).
- Bộ hồi quy mở rộng 154 case còn 6 thất bại và 8 lỗi ở phần cũ. Đã tái hiện các trường hợp tương ứng trên bản đối chiếu tách riêng: truy vấn Book lỗi trên SQLite (`dec_campaign_error.folder_id`), chế độ job chạy nền, test Toast cũ và cấu trúc trang chủ. Không sửa các phần không thuộc phạm vi để tránh ghi đè công việc có sẵn.
- Chưa chạy migration, seed hay nhập dữ liệu trên database vận hành; chưa phát hành Book lỗi/đặt lịch/gửi email.

Ảnh và HTML xem thử từ dữ liệu test nằm trong `tmp/soft-review-preview/` (không commit). Báo cáo lượt kiểm cuối: `tmp/soft-review-final-tests.log`; lượt hồi quy mở rộng: `tmp/soft-review-regression.log`.
