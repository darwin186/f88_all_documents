# Kế hoạch cấp số văn bản bổ sung theo ngày cũ

## Trạng thái

- Trạng thái: Chờ triển khai.
- Phạm vi: `app_admindocuments` – văn bản hành chính.
- Mục tiêu: Cho phép tạo văn bản độc lập có ngày ban hành trong quá khứ mà vẫn nằm đúng vị trí trong chuỗi số hiệu, không tạo hai số hiệu hiển thị hoàn toàn giống nhau và không làm thay đổi bộ đếm hiện tại.

## Quyết định nghiệp vụ

Áp dụng đồng thời hai cơ chế:

1. Số chèn bằng hậu tố chữ cái `A`, `B`, `C`.
2. Đánh dấu văn bản là “Cấp số bổ sung/hồi tố” để phục vụ nhận diện và kiểm toán.

Ví dụ:

- Văn bản gốc: `123/2026/QĐ-F88/TGĐ`.
- Văn bản chèn thứ nhất: `123A/2026/QĐ-F88/TGĐ`.
- Văn bản chèn tiếp theo: `123B/2026/QĐ-F88/TGĐ`.

Không cho phép hai văn bản độc lập có cùng toàn bộ số hiệu hiển thị. Badge “Cấp bổ sung” chỉ là thông tin hỗ trợ, không thay thế hậu tố phân biệt số hiệu.

Quy ước cuối cùng giữa `123A` và `123-A` cần được nghiệp vụ/pháp chế xác nhận trước khi mở tính năng trên production.

## Phân biệt trường hợp sử dụng

### Văn bản độc lập cần chèn về ngày cũ

- Tạo bản ghi văn bản mới.
- Dùng cùng số chạy với văn bản làm mốc.
- Hệ thống tự cấp hậu tố kế tiếp `A`, `B`, `C`.
- Bắt buộc lưu ngày ban hành, lý do, người thực hiện và văn bản làm mốc.

### Bản sửa đổi hoặc thay thế của cùng một văn bản

- Không cấp số chèn.
- Giữ nguyên số hiệu nghiệp vụ.
- Quản lý bằng phiên bản hoặc quan hệ thay thế.
- Chỉ một phiên bản được đánh dấu đang có hiệu lực.

## Thay đổi mô hình dữ liệu

Bổ sung vào `AdmAdministrativeDocument`:

- `number_suffix`: hậu tố số chèn, để trống với số cấp bình thường.
- `numbering_year`: năm thuộc chuỗi cấp số, tách khỏi `created_at`.
- `allocation_mode`: `normal` hoặc `backdated`.
- `anchor_document`: văn bản/số hiệu được chọn làm mốc.
- `backdated_reason`: lý do cấp số hồi tố, bắt buộc với chế độ `backdated`.
- `backdated_by`: người thực hiện hoặc phê duyệt cấp hồi tố.
- `backdated_at`: thời điểm thao tác thực tế.

Ràng buộc duy nhất đề xuất:

```text
doc_type + issuing_company + numbering_year + running_number + number_suffix
```

`document_number_full` vẫn giữ unique và được sinh từ các thành phần trên.

## Quy tắc cấp số

### Cấp số bình thường

- Khóa counter bằng `select_for_update` như hiện tại.
- Lấy `next_number` và tăng counter sau khi cấp thành công.
- `number_suffix` để trống.
- `numbering_year` lấy từ năm nghiệp vụ được xác định cho văn bản.

### Cấp số bổ sung

- Chỉ Admin Documents hoặc quyền chuyên biệt mới được thao tác.
- Người dùng phải chọn văn bản làm mốc, không nhập trực tiếp toàn bộ số hiệu.
- Hệ thống khóa các bản ghi cùng bộ loại văn bản, công ty, năm và số chạy.
- Hệ thống tự tìm hậu tố còn trống tiếp theo: `A`, `B`, `C`.
- Không cập nhật `AdmDocumentCounter.next_number`.
- Bắt buộc có `issue_date`, lý do hồi tố và người thao tác.
- Không cho đổi số chạy, hậu tố, năm cấp số hoặc văn bản làm mốc sau khi đã tạo.

### Sắp xếp

Thứ tự hiển thị theo:

```text
numbering_year, running_number, number_suffix
```

Trong cùng số chạy: số gốc trước, sau đó `A`, `B`, `C`.

## Điều chỉnh logic hiện tại

Hiện tại một số đoạn đang dùng `timezone.now().year` hoặc `created_at__year` để cấp và kiểm tra số. Cần chuyển sang `numbering_year`; nếu không, văn bản được nhập ở năm sau nhưng ban hành trong năm cũ sẽ đi vào sai chuỗi counter.

Các khu vực cần rà soát:

- `allocate_running_number`.
- `AdmAdministrativeDocument.save`.
- Form tạo và cập nhật văn bản.
- Màn hình quản lý counter.
- Biểu đồ trực quan số đã dùng/số trống.
- Import, export và báo cáo.
- Luồng vô hiệu văn bản và hoàn counter.
- Tìm kiếm, sắp xếp và lịch sử thay đổi.

## Giao diện dự kiến

Trong form tạo văn bản:

- Mặc định: “Cấp số bình thường”.
- Tùy chọn dành cho người có quyền: “Cấp số bổ sung theo ngày cũ”.
- Khi chọn cấp bổ sung, hiển thị:
  - Ngày ban hành.
  - Loại văn bản và công ty.
  - Văn bản/số hiệu làm mốc.
  - Số hiệu dự kiến, ví dụ `123A/2026/QĐ-F88/TGĐ`.
  - Lý do cấp hồi tố.
- Yêu cầu hộp thoại xác nhận trước khi lưu.

Trong danh sách và chi tiết:

- Hiển thị badge trung tính “Cấp bổ sung”.
- Hiển thị số hiệu đầy đủ có hậu tố.
- Cho xem văn bản làm mốc, lý do, người thực hiện và thời điểm thực tế.
- Lịch sử phải phân biệt ngày ban hành nghiệp vụ và ngày ghi nhận trên hệ thống.

## Migration và dữ liệu cũ

1. Thêm các trường mới ở trạng thái nullable/default an toàn.
2. Backfill `numbering_year` từ năm đang nằm trong `document_number_full`; chỉ fallback sang `issue_date` hoặc `created_at` khi không tách được.
3. Backfill `number_suffix` thành chuỗi rỗng cho dữ liệu hiện tại.
4. Kiểm tra và xuất báo cáo các số hiệu không parse được để xử lý thủ công.
5. Thêm unique constraint mới sau khi backfill và đối soát hoàn tất.
6. Giữ nguyên `document_number_full` của toàn bộ dữ liệu cũ.

Không tự động đổi số hiệu hoặc ngày ban hành của dữ liệu production hiện có.

## Phân quyền và kiểm toán

- Chỉ nhóm được cấp quyền cấp số hồi tố mới thấy thao tác.
- Không cho sửa trực tiếp hậu tố hoặc số hiệu đầy đủ.
- Ghi lịch sử trước/sau cho toàn bộ thao tác.
- Lưu người tạo, người phê duyệt, thời điểm thao tác và lý do.
- Có thể bổ sung quy trình phê duyệt hai bước nếu nghiệp vụ yêu cầu.

## Kiểm thử bắt buộc

- Cấp số bình thường vẫn liên tục và không thay đổi hành vi hiện tại.
- Cấp `123A`, tiếp theo tự cấp `123B`.
- Cấp số chèn không làm tăng counter chính.
- Hai request đồng thời không nhận cùng hậu tố.
- Không tạo được hai số hiệu đầy đủ giống nhau.
- Văn bản năm cũ dùng đúng `numbering_year` dù tạo ở năm hiện tại.
- User không đủ quyền không thể gọi trực tiếp endpoint cấp hồi tố.
- Số hiệu và trường định danh không sửa được sau khi tạo.
- Danh sách, tìm kiếm, export và lịch sử hiển thị đúng hậu tố.
- Migration giữ nguyên số hiệu của dữ liệu cũ.

## Trình tự triển khai

1. Nghiệp vụ xác nhận định dạng hậu tố `123A` hoặc `123-A` và quyền phê duyệt.
2. Tạo migration trường mới và script kiểm tra/backfill.
3. Tách logic sinh số hiệu thành service dùng chung.
4. Cập nhật cấp số bình thường sang `numbering_year`.
5. Xây service cấp số bổ sung có khóa giao dịch.
6. Bổ sung form, preview, xác nhận và badge.
7. Cập nhật counter, báo cáo, import/export và lịch sử.
8. Chạy test concurrency và migration trên bản sao dữ liệu production.
9. Triển khai theo feature flag; đối soát trước khi mở quyền cho người dùng.

## Ngoài phạm vi giai đoạn đầu

- Tự động xác định hiệu lực pháp lý của văn bản.
- Tự động thay thế hoặc hủy hiệu lực văn bản làm mốc.
- Cho phép người dùng nhập tự do số hiệu đầy đủ.
- Dùng cùng một số hiệu hiển thị cho hai văn bản độc lập mà không có hậu tố.
