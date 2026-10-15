# Đề xuất tách thửa số hiệu văn bản hành chính

Ngày nghiên cứu và triển khai mã nguồn: 13/10/2026. Phạm vi: `app_admindocuments`, tab Văn bản hành chính. Các quy tắc bên dưới đã được đưa vào mã nguồn; migration chưa áp dụng vào database ứng dụng vì PostgreSQL local chưa chạy.

## 1. Hành vi nghiệp vụ

Tách thửa phục vụ việc cấp số cho văn bản cần backdate khi dãy số chính đã đi xa hơn. Đây là một văn bản mới độc lập về nội dung, phòng ban, người ký, ngày ban hành, trạng thái, ticket và tệp đính kèm; chỉ dùng chung số nền và nhóm đánh số với số được chọn. Văn bản gốc giữ nguyên số hiệu, nội dung, trạng thái và tệp đính kèm.

Ví dụ đã cấp đến 200 nhưng cần bổ sung văn bản có ngày ban hành phù hợp vị trí số 100: chọn ô 100 để tạo 100A, nhập ngày ban hành lùi về ngày cần thiết. Ngày tạo và người tạo vẫn được ghi theo thao tác thực tế, không sửa `created_at` để backdate.

Điều chỉnh theo xác nhận nghiệp vụ: số gốc đã VOID vẫn được sinh 100A, 100B. VOID là trạng thái riêng, được xếp sau Z trong hiển thị, không phải hậu tố chữ cái tham gia cấp số.

Ví dụ số mới nhất đã cấp là 200:

| Thao tác | Số được cấp | Số tiếp theo của bộ đếm chính |
| --- | --- | --- |
| Trước khi tách | Đã có văn bản 100 và 200 | 201 |
| Tách lần đầu tại ô 100 | 100A | 201 |
| Tách lần hai tại ô 100 | 100B | 201 |
| Tạo văn bản thông thường | 201 | 202 |

Nếu 200 là giá trị “Số tiếp theo” trên màn hình, sau khi tách thì giá trị đó vẫn là 200; tạo thông thường sẽ cấp 200 rồi tăng thành 201. Cần phân biệt số mới nhất đã cấp với số tiếp theo.

Ví dụ số đầy đủ: `100/2026/QD-F88/GD` → `100A/2026/QD-F88/GD`, `100B/2026/QD-F88/GD`. Giữ quy tắc đệm số hiện có: số 5 thành `005A/...`.

## 2. Thao tác trên màn hình

1. Vào Quản lý số hiệu, chọn dòng loại văn bản/công ty/năm để mở sơ đồ.
2. Click ô đã dùng, ví dụ **100**, để mở bảng bên cạnh hoặc hộp thoại.
3. Hiển thị văn bản gốc, các nhánh đã tạo, trạng thái từng nhánh và nút **Tạo văn bản tách thửa**.
4. Mở biểu mẫu tạo văn bản mới, hiển thị số dự kiến **100A**. Khóa số nền, loại văn bản, công ty và năm số hiệu theo ô đã chọn để giữ đúng nhóm đánh số. Người dùng chọn phòng ban và người ký phù hợp, nhập tiêu đề, nội dung, ngày ban hành cần backdate, ticket, ghi chú và tệp mới. Không bắt buộc phòng ban/người ký giống văn bản gốc. Trạng thái ban đầu là nháp.
5. Khi lưu, máy chủ cấp hậu tố chính thức, tạo văn bản và cập nhật sơ đồ. Click chỉ mở giao diện; chỉ thao tác lưu mới tạo dữ liệu.

Ô 100 hiển thị dấu nhận biết có nhánh, ví dụ `100 · 2 nhánh`. Mở ô sẽ thấy `100`, `100A`, `100B`, mỗi mục có đường dẫn đến chi tiết. Có thể tạo tiếp `100C` từ bảng này. Các văn bản VOID hiển thị cuối nhóm, sau các mục A–Z, giữ nhãn VOID rõ ràng. Ô chỉ có văn bản VOID vẫn click và tạo nhánh được.

Thông báo tại biểu mẫu: “Số gốc 100 được giữ nguyên. Tách thửa không thay đổi số tiếp theo 201.”

Số dự kiến chưa phải số giữ chỗ. Nếu người khác vừa tạo 100A, trả thông báo số dự kiến đã thay đổi, giữ nguyên dữ liệu nhập và cho người dùng lưu lại với 100B.

## 3. Quy tắc đề xuất cho phiên bản đầu

- Cho tách từ số nền đã có văn bản, kể cả văn bản gốc đã VOID. Ô chưa từng dùng chưa có văn bản làm căn cứ thì chưa hỗ trợ tách trong phiên bản đầu.
- Một lần lưu tạo một văn bản nhánh. Muốn có 100A và 100B thì tạo hai lần, mỗi văn bản có nội dung riêng.
- Hậu tố tự cấp A → B → … → Z. Chưa hỗ trợ vượt Z trong phiên bản đầu; khi hết phải báo rõ, không tự đổi quy tắc.
- Không tách lồng thành 100AA từ 100A. Mở nhánh có thể dẫn về gốc để tạo nhánh tiếp theo.
- Quan hệ tách thửa không đồng nghĩa với sửa đổi/thay thế. Không tự điền `reference_document` hoặc `reference_number`.
- Biểu mẫu là tạo văn bản mới; phòng ban và người ký được chọn độc lập, phòng ban phải thuộc công ty đang chọn theo quy tắc dữ liệu. Không tự sao chép nội dung, phòng ban, tệp, trạng thái đã ban hành hoặc lịch sử gốc.
- VOID 100A không ảnh hưởng 100/100B và không trả số về bộ đếm chính. Hậu tố A đã dùng không được cấp lại; nhánh tiếp theo là C nếu đã có A và B.
- VOID gốc không chặn việc sinh A/B và không VOID các văn bản nhánh. Bỏ đề xuất chặn thu hồi gốc vì có nhánh. Không bổ sung thay đổi cơ chế tái sử dụng số gốc vào tính năng này; nhóm hậu tố phải nhận diện bằng loại/công ty/năm/số nền, kể cả có nhiều bản ghi gốc do tái sử dụng số VOID.
- Khi xác định hậu tố tiếp theo, chỉ đọc `number_suffix` A–Z, không đưa chuỗi `VOID` vào phép so sánh hậu tố. Với 100-VOID chưa có nhánh, hậu tố tiếp theo vẫn là A; nếu đã có 100A-VOID thì A vẫn đã từng cấp, tiếp theo là B.
- Nhánh dùng năm số hiệu của gốc, kể cả tạo ở năm khác. `created_at` vẫn ghi ngày tạo thực tế.
- Dùng quyền truy cập hiện có của module cho thao tác tách; kiểm tra tại máy chủ và yêu cầu POST + CSRF khi tạo.

Giới hạn Z, chỉ tách một cấp và chưa tách ô chưa từng dùng là đề xuất để làm rõ phạm vi. Văn bản mới độc lập và cho phép tách từ số VOID là yêu cầu đã được xác nhận.

## 4. Kết quả khảo sát mã nguồn

| Vị trí | Hiện trạng / tác động |
| --- | --- |
| `app_admindocuments/models.py`: `AdmAdministrativeDocument` | `running_number` là số nguyên; `document_number_full` tự sinh và bất biến sau tạo. Cần thêm hậu tố và quan hệ gốc, không chuyển số nền thành chuỗi. |
| `app_admindocuments/services.py`: `allocate_running_number` | Khóa bộ đếm theo loại/công ty/năm, tăng `next_number`; kiểm tra xung đột bằng `.first()`. Cần xét toàn bộ bản ghi phù hợp và phân biệt gốc/nhánh khi có nhiều bản ghi cùng số nền. |
| `app_admindocuments/views.py`: `document_create` | Luồng thường luôn gọi cấp số chính; tách thửa cần nhánh xử lý riêng, không gọi allocator này. |
| `document_counter_visual`, `document_counter_manage` | Dùng năm `created_at`, tập số nguyên, tổng số bản ghi. Cần chuyển sang năm số hiệu và trả nhóm gốc/nhánh. |
| `document_counter_visual_partial.html`, `document_counter_visual.html` | Ô số là `div` hiển thị trạng thái; cần nút và hành vi mở bảng. Cả trang độc lập và sơ đồ nhúng đều phải hỗ trợ. |
| `document_counters.html` | Sơ đồ nhúng tải bằng fetch rồi gán `innerHTML`; ô dùng liên kết gốc của trình duyệt nên hoạt động cả sau khi tải động. Chặn click input/nút Lưu lan lên dòng mở sơ đồ. |
| `document_delete` | Có thể lùi bộ đếm nếu `running_number == next_number - 1`. Phải bỏ hành vi này cho nhánh; thu hồi gốc không chặn tạo nhánh và không thu hồi dây chuyền. |
| `forms.py` | Có kiểm tra trùng tiêu đề và số tham chiếu; vẫn áp dụng cho nhánh, không mặc định nhân bản tiêu đề gây lỗi. |
| `tests.py`: `AdmAdministrativeDocumentNumberInvariantTests` | Đã có kiểm tra số bất biến và VOID. Cần giữ các hành vi này khi thêm hậu tố. |

## 5. Thiết kế dữ liệu và cấp số

Thêm vào `AdmAdministrativeDocument`:

- `number_year`: năm của số hiệu, độc lập ngày tạo.
- `number_suffix`: chuỗi, mặc định rỗng cho gốc; A–Z cho nhánh.
- `split_parent`: khóa ngoại đến văn bản gốc, nullable, `PROTECT`, không dùng trường tham chiếu hiện có.
- `split_reason`: lý do tách tùy chọn để ghi lịch sử nếu nghiệp vụ cần.

Giữ `running_number=100` cho cả 100/100A/100B; số đầy đủ được sinh từ số nền + hậu tố + năm + mã loại/công ty/người ký của văn bản mới. Ví dụ gốc `100/2026/QD-F88/GD`, văn bản mới chọn người ký mã `PGD` thì nhận `100A/2026/QD-F88/PGD`. Số nền, hậu tố, năm số hiệu và quan hệ gốc bất biến sau tạo. Không sao chép toàn bộ số đầy đủ của gốc và không mang `-VOID` của gốc sang số mới.

Giữ unique của `document_number_full`; thêm ràng buộc unique có điều kiện cho nhánh `(doc_type, issuing_company, number_year, running_number, number_suffix)`, gồm cả nhánh VOID. Phạm vi hậu tố không bao gồm phòng ban hoặc người ký: khác phòng ban/người ký vẫn phải nhận A rồi B, không cấp hai số 100A trong cùng nhóm. Không chỉ unique theo `split_parent` vì cùng số nền có thể có nhiều bản ghi gốc sau tái sử dụng số VOID. Kiểm tra gốc không có hậu tố, nhánh có hậu tố hợp lệ và cha luôn là gốc cùng phạm vi số hiệu. Không đặt unique số nền cho mọi bản ghi vì nhánh cố ý trùng số nền, và hiện hệ thống có tái sử dụng số VOID.

Service tạo nhánh chạy trong transaction: khóa chung theo nhóm đánh số, kiểm tra phạm vi và căn cứ số gốc (chấp nhận gốc VOID), tìm hậu tố chữ cái lớn nhất đã dùng trong nhóm kể cả nhánh đã VOID, kiểm tra số dự kiến, cấp hậu tố kế tiếp, lưu văn bản và lịch sử. Có thể dùng hàng `AdmDocumentCounter` của loại/công ty/năm để đồng bộ khóa với luồng cấp số hiện có, không tăng hay đặt lại `next_number`; cần xử lý nhất quán trường hợp chưa có hàng counter. Khóa riêng bản ghi gốc chưa đủ nếu số gốc từng được tái sử dụng. Mọi luồng tạo nhánh phải dùng cùng service. Hai người tách cùng nhóm không được nhận cùng hậu tố, kể cả chọn hai bản ghi gốc khác nhau.

Service tách không sửa `AdmDocumentCounter.next_number` của bộ đếm hiện có. Luồng thường phải phân biệt văn bản gốc và nhánh: sự tồn tại của 100A không tự thay đổi chính sách tái sử dụng số gốc 100 đã VOID. Nhánh luôn lấy hậu tố trong cùng nhóm số nền, độc lập trạng thái của gốc.

Thống nhất thứ tự khóa cho cấp số/thu hồi/tách trước khi triển khai; tránh luồng thu hồi khóa văn bản rồi bộ đếm nhưng luồng khác làm ngược lại. Unique tại database vẫn cần làm lớp bảo vệ cuối cùng. Chống gửi lặp bằng khóa yêu cầu tạo dùng một lần, kiểm tra trong transaction; khóa nút Lưu ở trình duyệt chỉ hỗ trợ trải nghiệm.

Migration: thêm trường nullable, backfill năm từ phần năm trong số đầy đủ đã cấp, đối chiếu với ngày tạo và báo các bản ghi không phân tích được để xử lý trước khi bắt buộc trường. Gốc hiện có nhận hậu tố rỗng và cha null; không đổi số đầy đủ. Các truy vấn cấp số, sơ đồ, báo cáo theo năm phải dùng `number_year` thống nhất. Thống kê tách riêng số gốc và tổng văn bản để 100A không làm tăng “đã dùng đến”.

## 6. Tiêu chí nghiệm thu

1. Đã cấp đến 200, tách 100 hai lần được 100A/100B; gốc giữ nguyên; tạo thường được 201.
2. Bộ đếm đang chờ 200, tách 100 xong vẫn chờ 200.
3. Tách số sát bộ đếm, rồi VOID nhánh, bộ đếm không lùi.
4. VOID 100A rồi tạo tiếp không tái sử dụng A.
5. Hai yêu cầu đồng thời cùng dự kiến A: một thành công, một nhận thông báo đổi số; lưu lại được B, không mất nội dung nhập.
6. Gửi lại cùng yêu cầu tạo không sinh thêm văn bản.
7. Tạo văn bản mới khác phòng ban/người ký, nhập ngày ban hành backdate; thông tin lưu độc lập, ngày tạo đúng hiện tại. Tạo nhánh năm trước vẫn hiện trong nhóm số hiệu năm trước.
8. Từ ô 100 chỉ có gốc VOID vẫn tạo được 100A rồi 100B; VOID hiển thị sau A–Z, không ảnh hưởng việc cấp hậu tố. Không tách ô chưa từng dùng hoặc tách lồng nhánh; không đổi số qua cập nhật thông thường; người không có quyền không tạo được qua endpoint trực tiếp.
9. Sơ đồ nhúng và trang độc lập đều mở được ô; tìm kiếm/xuất danh sách thể hiện đầy đủ 100A; lịch sử thể hiện gốc, hậu tố và người tạo.
10. Migration giữ nguyên toàn bộ số cũ; các kiểm tra bất biến/VOID hiện có vẫn đạt. Kiểm tra đồng thời trên database hỗ trợ khóa hàng thực tế.
11. Gốc 100 đã VOID rồi có bản ghi tái sử dụng 100: chọn bất kỳ bản ghi gốc nào vẫn dùng cùng chuỗi hậu tố A/B, không trùng A dù phòng ban/người ký khác nhau.

## 7. Phạm vi triển khai

Triển khai cùng một đợt: migration và quy tắc bất biến → service tách/cấp số/thu hồi → biểu mẫu và endpoint → ô tương tác ở cả hai sơ đồ → thống kê/tìm kiếm/xuất/lịch sử → kiểm tra nghiệm thu. Không chỉ thêm chữ A/B vào giao diện vì cấp số và thu hồi hiện đang dựa trên số nguyên.

Chưa mở rộng sang tab Giấy tờ hành chính: phần này có allocator và cơ chế điền khoảng trống riêng, cần khảo sát/thiết kế tiếp nếu nghiệp vụ yêu cầu.

## 8. Mã nguồn đã triển khai và vận hành

- Ô số đã dùng hoặc VOID mở popup tạo văn bản tách thửa ngay trên sơ đồ (kể cả sơ đồ nhúng tải động). Form chia hai cột, mỗi cột xếp từ trên xuống: thông tin văn bản/đơn vị bên trái, ngày/tham chiếu/tệp bên phải. Màn hình nhỏ chuyển một cột. Trang riêng vẫn hỗ trợ truy cập trực tiếp và có nút mở popup; form lỗi mở lại popup giữ nội dung. AJAX GET trả fragment, POST thành công trả URL chi tiết; POST lỗi giữ form trong popup.
- Migration `0037_admadministrativedocument_number_suffix_and_more` bổ sung năm số hiệu, hậu tố, văn bản gốc, khóa chống gửi lặp và ràng buộc database. Năm cũ được đọc từ số đầy đủ, kể cả số VOID. Số không phân tích được sẽ dừng migration và báo ID để đối soát; không đoán năm hay đổi số cũ.
- Hậu tố A–Z dùng chung theo loại/công ty/năm/số nền, độc lập phòng ban/người ký và trạng thái VOID. Khóa bộ đếm trước khi khóa văn bản để đồng bộ với luồng tạo và thu hồi.
- Không bổ sung `split_reason` riêng trong phiên bản này; người dùng có thể nhập lý do vào Ghi chú. Lịch sử tạo ghi năm số hiệu, hậu tố và ID văn bản gốc.
- Khi có xung đột số dự kiến, giữ nội dung biểu mẫu và cập nhật hậu tố để lưu lại. Tệp tải lên cần chọn lại theo cơ chế bảo mật của trình duyệt; giao diện nhắc rõ điều này.
- Các số thuộc nhóm đã tách giữ cố định loại văn bản/công ty; phòng ban và người ký vẫn chỉnh độc lập theo biểu mẫu.
- Trạng thái trong popup tách thửa được chọn như form tạo mới: mặc định Nháp, danh sách đầy đủ sắp theo tên. Trạng thái được chọn áp dụng cho văn bản mới, không đổi trạng thái văn bản gốc.

Sau khi PostgreSQL của ứng dụng chạy, áp dụng schema bằng:

```powershell
.venv/Scripts/python.exe manage.py migrate app_admindocuments
```

Kiểm tra tính năng trên database SQLite độc lập:

```powershell
.venv/Scripts/python.exe manage.py test app_admindocuments.test_number_splitting app_admindocuments.tests.AdmAdministrativeDocumentNumberInvariantTests --settings=documents.test_settings --noinput
```

Kiểm tra đồng thời cần chạy suite `app_admindocuments.test_number_splitting` trên PostgreSQL; test khóa hàng tự bỏ qua trên SQLite.
