# Kế hoạch triển khai chiến dịch lỗi chứng từ

Tài liệu này là checklist theo dõi triển khai cho `app_document_campaigns`.
Mỗi ticket chỉ được đánh dấu hoàn tất khi đạt đủ tiêu chí verify.

## Phạm vi bảo vệ hệ thống hiện hữu

- Không di chuyển hoặc đổi tên model trong `app_documents`.
- Không sửa notebook báo cáo lỗi chứng từ cũ.
- Không sửa base template, navigation hoặc static dùng chung trong giai đoạn đầu.
- Không sửa Dockerfile, entrypoint, WhiteNoise hoặc quy trình `collectstatic`.
- App mới chỉ phụ thuộc một chiều vào dữ liệu nguồn của `app_documents`.
- URL mới nằm dưới prefix `/error-campaigns/`.
- Static mới được namespace dưới `app_document_campaigns/`.

## Epic DEC — Document Error Campaign

### DEC-01 — Khởi tạo app độc lập

- [x] Tạo Django app `app_document_campaigns`.
- [x] Đăng ký app trong `INSTALLED_APPS`.
- [x] Gắn URL prefix riêng.
- [x] Tạo namespace template/static riêng.
- [x] `python manage.py check` không có lỗi.

Verify:

- Truy cập URL health của app nhận HTTP 200.
- Không thay đổi URL hiện hữu của `app_documents`.

### DEC-02 — Schema chiến dịch và version dữ liệu

- [x] Model chiến dịch theo tháng.
- [x] Model phiên bản dữ liệu SQL/Excel.
- [x] Model lỗi chiến dịch với `error_uid` ổn định.
- [x] Foreign key tới Shop/Folder/Document hiện hữu.
- [x] Index theo campaign + Shop/Area/Region + trạng thái.
- [x] Migration độc lập của app mới.

Verify:

- Không tạo được hai campaign trùng mã.
- Không tạo được hai version cùng số trong một campaign.
- Không tạo được hai lỗi trùng `source_key` trong một campaign.

#### Đánh giá lại domain trước khi mở rộng campaign

- [x] Thêm `CampaignType` để cấu hình loại chiến dịch; hai nguồn lỗi quyển/lỗi chứng từ hiện tại cùng thuộc `hardcopy-document-error`.
- [x] Đổi ràng buộc kỳ từ duy nhất toàn hệ thống sang duy nhất theo `(campaign_type, report_month)`.
- [x] Dùng một `Campaign` cho mỗi loại chiến dịch trong mỗi kỳ; các lần xử lý SQL/Excel tiếp tục được refactor thành revision nội bộ ở bước sau.
- [ ] Giữ revision nội bộ bất biến để audit: bản nháp ban đầu hoặc bản điều chỉnh; mỗi thời điểm chỉ có một revision chính thức.
- [ ] UI hiển thị trạng thái nghiệp vụ `Nháp`, `Đã phát hành`, `Đã điều chỉnh`; số revision chỉ xuất hiện trong lịch sử/audit.
- [ ] Sau phát hành, không sửa trực tiếp dữ liệu đã gửi; tạo revision điều chỉnh từ bản chính thức và lưu quan hệ thay thế.

### DEC-03 — Checklist phản hồi PGD

- [x] Model checklist template.
- [x] Model câu hỏi và lựa chọn.
- [x] Gắn checklist với loại lỗi.
- [x] Hỗ trợ câu hỏi bắt buộc, dropdown, nhiều lựa chọn và text.
- [x] Django Admin cấu hình mẫu phản hồi theo loại campaign; lựa chọn dropdown nhập mỗi giá trị trên một dòng, không cần sửa JSON.

Verify:

- Có thể thay đổi checklist giữa các chiến dịch mà không sửa code.
- Checklist đã phát hành không bị thay đổi âm thầm.

### DEC-04 — Link truy cập PGD

- [x] Token ngẫu nhiên, database chỉ lưu token hash.
- [x] Gắn token với campaign, Shop và email Shop.
- [x] Có ngày phát hành, hạn phản hồi, ngày hết hạn và thu hồi.
- [x] Hết hạn phản hồi chuyển sang chỉ đọc.
- [ ] Chuẩn bị điểm mở rộng xác thực email/OTP.

#### Luồng phát hành nhiều cấp đã chốt

1. Admin hoàn tất dữ liệu, phát hành link PGD và gửi email chính tới `shop_email`; Gapo là kênh bổ sung triển khai sau.
2. Deadline PGD được cấu hình khi tạo chiến dịch. Hết deadline, link chỉ đọc; link hết hạn sau thêm một kỳ 31 ngày.
3. Khi PGD đã gửi hoặc hết deadline, Admin tổng hợp, comment/loại từng dòng và phát hành vòng xác nhận cho QLKV/Area Manager.
4. Khi QLKV hoàn tất hoặc hết deadline QLKV, hệ thống phát hành báo cáo cho QLV/Region Manager.
5. Phạm vi Vùng được xác định bằng `RegionManager`/QLV trong cơ cấu `Manager`; không dùng `UserProfile.region` để cấp quyền dữ liệu chiến dịch.

- [x] Cấu hình deadline PGD tại màn hình tạo chiến dịch và tự tính hạn link sau 31 ngày.
- [x] UI Admin tích hợp phát hành vào bảng theo dõi PGD, tạo/đổi và copy unique link thủ công; URL gốc chỉ hiển thị ngay sau khi phát hành.
- [x] Nút phát hành thủ công tạo link cho toàn bộ PGD, chuyển chiến dịch sang `Đang phản hồi` và cho copy toàn bộ; chưa gửi email.
- [ ] UI Admin phát hành campaign, tạo link PGD hàng loạt và gửi email qua Celery.
- [ ] UI Admin comment/loại từng dòng sau vòng PGD.
- [ ] Link và deadline xác nhận riêng cho QLKV/Area Manager.
- [ ] Link và deadline xác nhận riêng cho QLV/Region Manager.
- [ ] Audit từng lần phát hành, email và hành động xác nhận theo cấp.

Verify:

- Token sai hoặc bị thu hồi không truy cập được.
- Link hết hạn không cho xem dữ liệu.
- Sau hạn phản hồi không autosave/submit được.

### DEC-05 — Autosave batch

- [x] API lưu tối đa 50 thay đổi/request.
- [x] Debounce và batch ở frontend.
- [x] Lưu trực tiếp PostgreSQL, không đi qua Celery.
- [x] Dùng `version_no` chống ghi đè giữa nhiều tab.
- [x] Báo trạng thái đang lưu/đã lưu/lỗi/xung đột.

Verify:

- Nhiều dropdown liên tiếp được gom thành một request.
- Version cũ nhận HTTP 409.
- Request lỗi không hiển thị “Đã lưu”.

### DEC-06 — Gửi phản hồi chính thức

- [x] Flush autosave trước khi submit.
- [x] Validate các câu bắt buộc.
- [x] Idempotency key chống submit trùng.
- [x] Khóa phản hồi sau khi submit.
- [x] Đẩy email xác nhận sang Celery sau commit; metric/snapshot triển khai tại DEC-10.

Verify:

- Bấm submit nhiều lần chỉ sinh một submission.
- Không submit được khi còn câu bắt buộc chưa trả lời.

### DEC-07 — Import và ưu tiên Excel

- [x] Chạy hai nguồn SQL vào staging.
  - [x] Có schema version/source/staging độc lập, lưu raw row và normalized row.
  - [x] Import lại cùng source thay thế staging cũ, không tạo dòng trùng.
  - [x] Gắn hai câu SQL nghiệp vụ thực tế vào source adapter và xác nhận bằng `EXPLAIN`.
  - [x] Chạy truy xuất bằng Celery job có polling tiến độ, timeout và trạng thái lỗi.
  - [x] Chạy staging trên campaign/version nghiệp vụ thực tế.
- [x] Xuất Excel để team làm sạch.
  - [x] Tạo file bằng Celery job, lưu file kết quả và chỉ mở tải xuống sau khi job thành công.
  - [x] Có polling tiến độ, timeout và trạng thái lỗi để job tạo file không làm treo request web.
- [x] Import preview: thêm/sửa/loại/lỗi.
  - [x] Upload và đối chiếu Excel bằng Celery job có polling tiến độ, timeout và trạng thái lỗi.
  - [x] Preview theo từng source đã có thêm/sửa/không đổi/lỗi.
  - [x] File Excel tính số dòng bị loại so với staging SQL.
- [x] Excel được ưu tiên sau khi team xác nhận.
- [x] Không xóa vật lý dòng bị loại khỏi chiến dịch.
- [ ] Sau phát hành chỉ cho tạo bản điều chỉnh.
- [x] UI nội bộ để tạo campaign/version, chạy SQL, export/import, xem preview và xác nhận.

Verify:

- Import lại cùng file không tạo lỗi trùng.
- Có thể đối chiếu hai version dữ liệu.
- Không import đè campaign đang active.

### DEC-08 — Team review

- [x] UI theo dõi danh sách PGD có lỗi phát sinh và tiến độ phản hồi theo campaign.
- [x] Phân quyền phạm vi dữ liệu theo cấp Admin → Vùng → Khu vực → Shop.
- [x] Bấm một PGD để xem toàn bộ lỗi và nội dung PGD đã phản hồi.
- [x] Bộ lọc theo Vùng, Khu vực, PGD và trạng thái chưa phản hồi/đang làm/đã gửi.
- [ ] Hàng đợi phản hồi PGD.
- [ ] Phân loại và phê duyệt.
- [ ] Trả lại đúng lỗi cần bổ sung.
- [ ] Audit người thao tác và thời điểm.

Verify:

- Chỉ lỗi được team duyệt mới chuyển Area.
- PGD chỉ sửa được lỗi được mở bổ sung.

### DEC-09 — Area xác nhận

- [ ] Phân quyền theo Area.
- [ ] Xác nhận hoặc trả lại team.
- [ ] Lưu version dữ liệu được xác nhận.

Verify:

- Area không xem được dữ liệu Area khác.
- Region không có quyền phê duyệt.

### DEC-10 — Chốt lỗi và snapshot

- [ ] Team chốt lỗi sau Area xác nhận.
- [ ] Snapshot tại các mốc nghiệp vụ.
- [ ] Metric tổng hợp theo Shop/Area/Region.
- [ ] Celery cập nhật snapshot/metric bất đồng bộ.

Verify:

- Snapshot không được tạo sau từng autosave.
- Dữ liệu đã chốt không chỉnh sửa âm thầm.

### DEC-11 — Dashboard Region

- [ ] Region chỉ xem dữ liệu thuộc Region.
- [ ] Đọc bảng metric/snapshot thay vì quét toàn bộ lỗi.
- [ ] Bộ lọc tháng, Area, PGD, loại lỗi, trạng thái.

Verify:

- Region không có endpoint cập nhật/phê duyệt.
- Truy vấn dashboard dùng index phù hợp.

### DEC-12 — UI và static

- [x] Giữ theme F88 của giao diện V2.
- [x] Layout nội bộ và layout PGD tách riêng.
- [x] CSS/JS namespace trong app mới.
- [x] Chưa thay đổi shared base/static/CDN.
- [x] Thêm menu navbar và card trang chủ theo yêu cầu kiểm thử nội bộ.

Verify:

- `collectstatic --noinput` thu được asset app mới.
- Không trùng tên static với app hiện hữu.
- Màn PGD hoạt động trên desktop và tablet.

### DEC-13 — Hiệu năng và vận hành

- [ ] Load test autosave batch ở tải mục tiêu.
- [ ] Theo dõi p95 latency và DB connection pool.
- [ ] Celery queue riêng cho email/import/snapshot nếu cần.
- [ ] Logging không ghi raw token hoặc dữ liệu nhạy cảm.

Verify mục tiêu:

- Autosave p95 dưới 500 ms ở tải mục tiêu.
- Submit p95 dưới 2 giây.
- Không mất hoặc ghi trùng phản hồi.

## Thứ tự phát hành

1. Foundation: DEC-01 → DEC-06.
2. Data preparation: DEC-07.
3. Internal workflow: DEC-08 → DEC-10.
4. Reporting: DEC-11.
5. UI hardening và production readiness: DEC-12 → DEC-13.
