# documents
# The system of management document

## App Documents (app_documents) - Tổng quan A-Z

### 1) Mục tiêu hệ thống
Hệ thống quản lý chứng từ bản cứng gồm các luồng chính: **nhận chứng từ**, **duyệt chứng từ**, **quản lý thùng**, **chỉ tiêu/KPI**, và **mượn chứng từ**. Toàn bộ màn hình v2 dùng base/layout chung để đồng bộ UI.

## App Documents v2 - Yêu cầu nghiệp vụ

Tài liệu này mô tả các yêu cầu nghiệp vụ cho nhóm màn hình v2 của `app_documents`. Phần này tập trung vào cách người dùng nghiệp vụ vận hành hệ thống, các điều kiện kiểm soát, trạng thái dữ liệu và kết quả mong đợi sau mỗi thao tác.

### 1) Phạm vi nghiệp vụ v2

Nhóm màn hình `app_documents` v2 phục vụ quản lý vòng đời chứng từ bản cứng từ lúc phát sinh, tiếp nhận về kho xử lý, duyệt, đóng thùng, theo dõi KPI và cho mượn.

Các màn hình chính:

- **Nhận chứng từ v2**: `/nhan-chung-tu-v2`
- **Duyệt chứng từ v2**: `/duyet-chung-tu-v2`
- **Quản lý thùng**: `/package-list-management`
- **Chỉ tiêu chứng từ**: `/chi-tieu-chung-tu-v2`
- **Yêu cầu mượn chứng từ**: `/yeu-cau-muon-chung-tu-v2`
- **Quản lý mượn chứng từ**: `/quan-ly-muon-chung-tu-v2`
- **Quản lý tài khoản CTV**: `/quan-ly-tai-khoan-ctv`

### 2) Vai trò sử dụng

- **Admin**: quản trị nghiệp vụ, xem/chỉnh dữ liệu toàn hệ thống, xem KPI, quản lý CTV.
- **Checker/CTV**: xử lý nhận chứng từ, duyệt chứng từ, tạo và xử lý yêu cầu mượn nếu được cấp quyền.
- **Shop/PGD**: là đơn vị phát sinh chứng từ, dữ liệu được lọc theo phạm vi được phân quyền.
- **Supervisor/Manager/Risk**: xem hoặc thao tác theo phạm vi vùng/khu vực được cấu hình.

Nguyên tắc phân quyền chung: người dùng chỉ được xem và thao tác dữ liệu thuộc phạm vi được cấp quyền. Các màn xử lý nghiệp vụ trọng yếu như nhận, duyệt, mượn và KPI chỉ mở cho nhóm có quyền phù hợp.

### 3) Yêu cầu nghiệp vụ - Nhận chứng từ v2

**Mục tiêu**

Ghi nhận việc chứng từ/quyển chứng từ đã được tiếp nhận từ PGD về bộ phận xử lý, đồng thời đưa chứng từ vào đúng thùng lưu trữ.

**Luồng nghiệp vụ**

1. Người xử lý mở màn hình nhận chứng từ.
2. Lọc danh sách quyển theo PGD, vùng, loại quyển, trạng thái, ngày phát sinh hoặc mã thùng.
3. Chọn quyển cần nhận.
4. Nhập hoặc chọn mã thùng F88 phù hợp.
5. Xác nhận nhận chứng từ.
6. Hệ thống cập nhật trạng thái quyển sang đã nhận.
7. Hệ thống ghi nhận người nhận, ngày nhận, thùng nhận và lịch sử nhận.
8. Hệ thống đồng bộ chứng từ trong quyển vào cùng thùng.

**Điều kiện kiểm soát**

- Chỉ nhận các quyển thuộc phạm vi người dùng được quyền xử lý.
- Thùng nhận phải hợp lệ theo loại quyển và vùng/khu vực.
- Một quyển đã nhận phải có lịch sử nhận để truy vết.
- Nếu quyển/chứng từ nhận trễ so với quy định, hệ thống phải ghi nhận phục vụ KPI.

**Kết quả sau xử lý**

- Quyển có trạng thái đã nhận.
- Quyển được gắn với thùng.
- Chứng từ trong quyển được đồng bộ thùng.
- Có log nhận chứng từ và log đưa quyển/chứng từ vào thùng.

### 4) Yêu cầu nghiệp vụ - Duyệt chứng từ v2

**Mục tiêu**

Kiểm tra tính đầy đủ/hợp lệ của từng chứng từ và ghi nhận kết quả duyệt.

**Luồng nghiệp vụ**

1. Người xử lý mở màn hình duyệt chứng từ.
2. Lọc chứng từ theo PGD, mã hợp đồng, mã GNN, mã thùng, trạng thái nhận, trạng thái duyệt hoặc ngày.
3. Chọn một hoặc nhiều chứng từ cần duyệt.
4. Chọn kết quả duyệt.
5. Nếu cần bổ sung, nhập thông tin yêu cầu bổ sung.
6. Xác nhận duyệt.
7. Hệ thống cập nhật trạng thái duyệt và trạng thái nghiệp vụ của chứng từ.
8. Hệ thống ghi lịch sử duyệt.

**Điều kiện kiểm soát**

- Chỉ duyệt chứng từ thuộc phạm vi quyền của người dùng.
- Chứng từ cần có dữ liệu hợp lệ để xác định PGD, loại chứng từ, mã hợp đồng hoặc mã GNN.
- Duyệt nhiều chỉ áp dụng cho nhóm chứng từ cùng mã hợp đồng/GNN và chưa duyệt.
- Trạng thái duyệt không được hardcode theo mã cố định mà phải dựa trên cấu hình trạng thái.
- Nếu kết quả là yêu cầu bổ sung, hệ thống phải tạo bản ghi bổ sung để theo dõi.

**Kết quả sau xử lý**

- Chứng từ được cập nhật trạng thái duyệt.
- Chứng từ đủ điều kiện được chuyển sang trạng thái đã duyệt.
- Chứng từ cần bổ sung có bản ghi yêu cầu bổ sung.
- Có lịch sử duyệt chứng từ để truy vết người xử lý và thời điểm xử lý.

### 5) Yêu cầu nghiệp vụ - Quản lý thùng

**Mục tiêu**

Quản lý thùng lưu trữ chứng từ, đảm bảo quyển/chứng từ được đóng gói đúng loại, đúng vùng và có lịch sử luân chuyển.

**Luồng nghiệp vụ**

1. Người xử lý tạo hoặc chọn thùng.
2. Hệ thống sinh mã thùng theo quy chuẩn.
3. Người xử lý đưa quyển/chứng từ vào thùng qua nghiệp vụ nhận chứng từ.
4. Khi cần điều chỉnh, người xử lý có thể gỡ thùng theo điều kiện cho phép.
5. Hệ thống ghi nhận lịch sử thùng với quyển và chứng từ.

**Điều kiện kiểm soát**

- Mã thùng phải theo format quản trị quy định.
- Thùng phải phù hợp với loại quyển/chứng từ.
- Thùng phải phù hợp với vùng/khu vực.
- Chỉ cho gỡ thùng khi còn trong ngày và chưa có chứng từ đã duyệt.
- Không làm mất lịch sử luân chuyển khi thay đổi thùng.

**Kết quả sau xử lý**

- Thùng được tạo đúng chuẩn.
- Quyển/chứng từ có thông tin thùng hiện tại.
- Lịch sử đóng thùng và luân chuyển được lưu đầy đủ.

### 6) Yêu cầu nghiệp vụ - Mượn chứng từ v2

**Mục tiêu**

Quản lý việc phòng ban/bộ phận mượn chứng từ bản cứng đã được duyệt, theo dõi từ lúc yêu cầu, gán chứng từ, bàn giao, hoàn trả hoặc báo mất.

**Đối tượng nghiệp vụ**

- **Phiếu yêu cầu mượn**: ghi nhận nhu cầu mượn của một phòng ban.
- **Chứng từ trong phiếu**: từng chứng từ được gán và theo dõi trạng thái riêng.
- **Giao dịch mượn thực tế**: phát sinh khi chứng từ được bàn giao.
- **Log xử lý**: ghi lại toàn bộ thao tác trên phiếu và từng chứng từ.

**Luồng nghiệp vụ**

1. Người xử lý tạo phiếu yêu cầu mượn với phòng ban, ngày mượn, ngày hẹn trả, mã ticket, mã hợp đồng/GNN, email/SĐT liên hệ và ghi chú.
2. Phiếu mới tạo có trạng thái **Chờ xử lý**.
3. Người xử lý vào chi tiết phiếu và tìm chứng từ theo `contract_code` hoặc `loan_code`.
4. Hệ thống hiển thị danh sách chứng từ liên quan và lý do không đủ điều kiện nếu có.
5. Người xử lý chọn chứng từ hợp lệ để gán vào phiếu.
6. Chứng từ được gán chuyển sang trạng thái **Đã gán**.
7. Khi chứng từ sẵn sàng rời kho, người xử lý thực hiện **Bàn giao**.
8. Hệ thống tạo giao dịch mượn thực tế, chuyển chứng từ sang trạng thái **Đang mượn** và gỡ chứng từ khỏi thùng hiện tại.
9. Khi phòng ban trả chứng từ, người xử lý thực hiện **Hoàn trả** trên từng chứng từ.
10. Nếu chứng từ bị mất, người xử lý thực hiện **Báo mất**.
11. Hệ thống cập nhật trạng thái từng chứng từ và trạng thái tổng của phiếu.

**Điều kiện chứng từ được mượn**

- Chứng từ phải đã duyệt.
- Chứng từ không được đang mượn.
- Chứng từ không có giao dịch mượn chưa đóng.
- Chứng từ chưa được gán trong phiếu hiện tại.
- Người thao tác phải thuộc nhóm có quyền xử lý nghiệp vụ mượn.

**Quy tắc bàn giao**

- Chỉ bàn giao các chứng từ đã gán và có mã chứng từ hợp lệ.
- Khi bàn giao, hệ thống tạo bản ghi giao dịch mượn thực tế.
- Người cho mượn là user đang thao tác.
- Phòng ban mượn lấy từ phiếu yêu cầu.
- Ngày mượn là ngày bàn giao thực tế.
- Ngày hẹn trả lấy từ chứng từ trong phiếu, nếu không có thì lấy từ phiếu.
- Chứng từ được chuyển sang trạng thái đang mượn.
- Chứng từ được gỡ khỏi thùng hiện tại.

**Quy tắc hoàn trả**

- Chỉ hoàn trả chứng từ đã bàn giao.
- Khi hoàn trả, giao dịch mượn được chuyển sang trạng thái đã trả.
- Hệ thống ghi nhận ngày trả.
- Chứng từ được chuyển lại trạng thái đã duyệt.
- Phiếu được cập nhật lại trạng thái tổng.

**Quy tắc báo mất**

- Chỉ báo mất chứng từ đã bàn giao.
- Giao dịch mượn được chuyển sang trạng thái báo mất.
- Chứng từ được chuyển sang trạng thái đã mất.
- Phiếu được cập nhật lại trạng thái tổng.

**Trạng thái phiếu mượn**

- **Chờ xử lý**: phiếu mới tạo, chưa gán chứng từ.
- **Đã gán chứng từ**: phiếu đã có chứng từ nhưng chưa bàn giao.
- **Đã bàn giao**: chứng từ đã được bàn giao cho phòng ban mượn.
- **Trả một phần**: một phần chứng từ đã trả/báo mất, phần còn lại chưa hoàn tất.
- **Đã trả**: toàn bộ chứng từ trong phiếu đã kết thúc.
- **Hủy**: phiếu bị hủy trước khi có chứng từ.
- **Từ chối**: trạng thái dự phòng cho trường hợp không chấp nhận yêu cầu.

**Trạng thái chứng từ trong phiếu**

- **Chờ gán**
- **Đã gán**
- **Đã bàn giao**
- **Đã trả**
- **Báo mất**
- **Hủy**

**Quy tắc hủy phiếu**

- Chỉ được hủy phiếu khi chưa có chứng từ được gán.
- Nếu phiếu đã có chứng từ, không cho hủy để tránh mất lịch sử xử lý.

**Kết quả sau xử lý**

- Phiếu mượn thể hiện đầy đủ phòng ban, thời gian, liên hệ, ticket và danh sách chứng từ.
- Mỗi chứng từ có trạng thái riêng.
- Giao dịch mượn thực tế được ghi nhận sau bàn giao.
- Có log cho các thao tác tạo phiếu, gán chứng từ, bàn giao, hoàn trả, báo mất và cập nhật ngày hẹn trả.

### 7) Yêu cầu nghiệp vụ - KPI/Chỉ tiêu chứng từ

**Mục tiêu**

Theo dõi năng suất xử lý chứng từ, tình trạng nhận/duyệt, SLA và tình hình mượn chứng từ.

**Nhóm chỉ tiêu chính**

- Tổng số quyển/chứng từ phát sinh.
- Số lượng đã nhận.
- Số lượng chưa nhận.
- Số lượng nhận đúng hạn/trễ hạn.
- Số lượng đã duyệt.
- Số lượng cần bổ sung.
- Năng suất theo người xử lý.
- Báo cáo theo PGD, vùng/khu vực và tháng.
- Tổng lượt mượn chứng từ.
- Số chứng từ đang mượn.
- Số chứng từ đã trả.
- Số chứng từ báo mất.
- Số lượt mượn quá hạn.
- Tỷ lệ trả đúng hạn.

**Điều kiện kiểm soát**

- Chỉ admin hoặc người được cấp quyền mới xem được KPI tổng hợp.
- Dữ liệu KPI phải dựa trên trạng thái nghiệp vụ và log xử lý thực tế.
- Các chỉ tiêu bật/tắt theo cấu hình `DocumentKpiSetting`.
- Báo cáo phải hỗ trợ lọc theo thời gian và đơn vị.

### 8) Yêu cầu nghiệp vụ - Quản lý tài khoản CTV

**Mục tiêu**

Theo dõi tình trạng hoạt động của cộng tác viên/người xử lý nghiệp vụ trên màn hình v2.

**Luồng nghiệp vụ**

1. Khi người dùng sử dụng hệ thống v2, trình duyệt gửi heartbeat định kỳ.
2. Hệ thống ghi nhận thời điểm online gần nhất.
3. Hệ thống cộng dồn thời gian hoạt động trong ngày.
4. Admin xem danh sách người dùng online/offline và tổng thời gian hoạt động.

**Điều kiện kiểm soát**

- Chỉ admin được xem màn quản lý tài khoản CTV.
- Online/offline được xác định theo khoảng thời gian không hoạt động được cấu hình.
- Thời gian hoạt động chỉ cộng khi heartbeat liên tục trong ngưỡng hợp lệ.

### 9) Nguyên tắc truy vết và an toàn dữ liệu

- Mọi thao tác nghiệp vụ quan trọng phải có log.
- Không xóa lịch sử nhận, duyệt, đóng thùng hoặc mượn chứng từ.
- Không hardcode trạng thái theo tên/mã cụ thể nếu hệ thống đã có flag cấu hình.
- Khi chuyển trạng thái chứng từ, phải cập nhật theo đúng trạng thái nghiệp vụ hiện hành.
- Không cho phép thao tác làm mất dấu chứng từ đang nằm trong thùng, đang duyệt hoặc đang mượn.
- Dữ liệu hiển thị phải tuân thủ phân quyền vùng/PGD/người dùng.

### 10) Kết luận nghiệp vụ

Luồng chuẩn của `app_documents` v2 được hiểu là:

**PGD phát sinh chứng từ -> bộ phận xử lý nhận chứng từ -> duyệt chứng từ -> đóng thùng/quản lý lưu trữ -> theo dõi KPI -> cho mượn khi có yêu cầu -> hoàn trả hoặc báo mất.**

Mỗi màn v2 phải phục vụ đúng một bước trong vòng đời này, đồng thời đảm bảo chứng từ luôn có trạng thái hiện tại rõ ràng, lịch sử xử lý đầy đủ và dữ liệu đủ tin cậy để báo cáo/KPI.

### 2) Ứng dụng chính
- `app_documents`: nghiệp vụ chứng từ, nhận/duyệt, thùng, KPI, mượn.
- `app_admindocuments`: cấp số văn bản hành chính/giấy tờ (khác mảng chứng từ).
- `app_notification`: thông báo hệ thống (gửi, template).
- `documents/`: project settings, urls, celery.

### 3) Vai trò & phân quyền
Lấy từ `app_documents/utils.py::get_user_context`:
- **super_admin**: quyền cao nhất.
- **admin**: quản trị hệ thống nghiệp vụ.
- **checker**: cộng tác viên xử lý nhận/duyệt.
- **shop**: người dùng cửa hàng.
- **supervisor/manager/risk**: theo nhóm.

Filter dữ liệu theo role dùng `app_documents/access_controls.py` (lọc region/shop).

### 4) Điều hướng v2 (routes chính)
- Nhận chứng từ v2: `/nhan-chung-tu-v2`
- Duyệt chứng từ v2: `/duyet-chung-tu-v2`
- Quản lý thùng: `/package-list-management`
- Chỉ tiêu chứng từ: `/chi-tieu-chung-tu-v2` (admin)
- Mượn chứng từ (tab): `/yeu-cau-muon-chung-tu-v2`, `/quan-ly-muon-chung-tu-v2`
- Quản lý tài khoản CTV (online): `/quan-ly-tai-khoan-ctv` (admin)

### 5) Dữ liệu & thực thể chính
- **Folder (quyển)**: `Folder` (f_FolderDetail)
- **Document (chứng từ)**: `DocumentsDetail` (f_DocumentsDetail)
- **Package (thùng)**: `Package` (d_Package)
- **FolderType/DocumentType/BusinessType**: danh mục loại
- **FolderStatus/DocumentStatus**: trạng thái quyển/chứng từ
- **BorrowingDocument/BorrowRequest**: mượn chứng từ
- **Logs**: `FoldersTransactionReceiving`, `DocumentsTransactionChecking`, `PackageFolderHistory`, `PackageDocumentHistory`, `BorrowRequestLog`

#### Trạng thái quyển (FolderStatus)
Flag chính: `is_received`, `is_not_received_yet`, `is_borrow`, `is_lost`, `is_transfer`.

#### Trạng thái chứng từ (DocumentStatus)
Flag chính: `is_selectable` (đã nhận), `is_checked` (đã duyệt), `is_borrow` (đang mượn), `is_lost`.

### 6) Luồng nghiệp vụ chính

#### 6.1 Nhận chứng từ (v2)
Trang: `/nhan-chung-tu-v2`.
Luồng:
1) Lọc quyển theo shop, loại, trạng thái, ngày.
2) Nhập mã thùng F88 để nhận (validate package type).
3) Cập nhật: `Folder.folder_status_id`, `lastest_received_date`, `lastest_received_by`, `package_id`.
4) Ghi log:
   - `FoldersTransactionReceiving` (trạng thái quyển)
   - `PackageFolderHistory` (quyển ↔ thùng)
   - `PackageDocumentHistory` (chứng từ ↔ thùng)
5) Đồng bộ `DocumentsDetail.package_id` theo thùng.
6) Check đúng hạn bằng `check_on_time()` (set `is_on_time`, `is_late`).

#### 6.2 Duyệt chứng từ (v2)
Trang: `/duyet-chung-tu-v2`.
Luồng:
1) Chọn trạng thái duyệt (CheckingTransactionStatus).
2) Cập nhật `DocumentsDetail.status_id`, `lastest_checked_date`, `lastest_checked_by`.
3) Chuyển `document_status_id` theo cờ `is_checked` (không hardcode code).
4) Tạo log `DocumentsTransactionChecking`.
5) Nếu trạng thái yêu cầu bổ sung (`is_request_additional`) thì tạo `CheckingAdditional`.
6) Duyệt nhiều: chỉ cho phép chọn chứng từ cùng HDCC/GNN và chưa duyệt.

#### 6.3 Quản lý thùng
Trang: `/package-list-management`.
- Tạo thùng theo chuẩn `{FolderType}-{yymmdd}-{region}{bb}`.
- Validate thùng theo loại quyển, region.
- Gỡ thùng v1: chỉ cho gỡ trong ngày, không có chứng từ đã duyệt.

#### 6.4 KPI/Chỉ tiêu chứng từ
Trang: `/chi-tieu-chung-tu-v2` (admin).
- Dataset: các quyển gốc phát sinh (`is_issue=True` & `is_original=True`).
- KPI dùng `DocumentKpiSetting` với các metric được bật.
- Báo cáo theo: PGD, vùng/khu vực, theo tháng.
- Hỗ trợ export dữ liệu chi tiết.

#### 6.5 Mượn chứng từ (Borrow Request v2)
Trang: `/yeu-cau-muon-chung-tu-v2`.
Luồng:
1) Tạo **Phiếu yêu cầu mượn** (BorrowRequest) với phòng ban, ngày mượn, hẹn trả, ticket/email...
2) Gán chứng từ theo **contract_code/loan_code** (chỉ chứng từ đã duyệt, chưa mượn).
3) **Bàn giao**: tạo `BorrowingDocument`, cập nhật `document_status_id` sang `is_borrow`.
   - Khi bàn giao, chứng từ được gỡ khỏi thùng: `DocumentsDetail.package_id = None`.
4) **Hoàn trả** (theo item hoặc theo phiếu): cập nhật legacy `BorrowingDocument` và trả lại `document_status_id` sang `is_checked`.
5) Log đầy đủ `BorrowRequestLog`.

### 7) Giao diện v2 (theme)
Base: `app_documents/templates/app_documents/base_app_documents_v2.html`.
Đặc trưng v2:
- Font nhỏ (9–10px), input bo tròn, viền mỏng.
- Filter và droplist đồng nhất với nhận/duyệt.
- Drawer cho thao tác chi tiết (nhận/duyệt).
- Toast thông báo (duyệt/nhận).

### 8) API chính
- `POST /api/folder/receive-v2/` nhận quyển v2
- `POST /api/document/<id>/note/` cập nhật ghi chú
- `POST /api/package/create-v2/` tạo thùng v2
- `POST /api/borrow-requests/` tạo BorrowRequest từ hệ thống khác (API key)
- `POST /api/heartbeat/` ping online user

### 9) Online user / đo thời gian làm việc
- Model: `UserPresenceDaily` (f_UserPresenceDaily)
- Heartbeat chạy từ base v2 mỗi 60s.
- Online window mặc định 5 phút.
- Trang admin: `/quan-ly-tai-khoan-ctv`

### 10) Cấu hình env liên quan
Trong `documents/settings.py`:
- `BORROW_REQUEST_API_KEY`
- `USER_PRESENCE_ACTIVE_GAP`, `USER_PRESENCE_ONLINE_WINDOW`, `USER_PRESENCE_HEARTBEAT_SECONDS`
- Celery/GAPO (xem phần Celery bên dưới)

### 11) Quy ước versioning
Các màn hình v2 có hậu tố `_v2` để tách khỏi v1 (route/template/JS).

## Celery (background tasks)
This project now includes a basic Celery setup.

### Dependencies
- Redis as broker/result backend (default `redis://localhost:6379/0`). Install and run Redis locally, or update `CELERY_BROKER_URL`/`CELERY_RESULT_BACKEND` in `.env`.
- Python packages: `celery==5.3.6`, `redis==5.0.4` (already listed in `requirements.txt`).

### Configuration
- `documents/celery.py` bootstraps Celery and autodiscovers tasks.
- Sample task: `app_documents/tasks.py::ping`.
- Settings in `documents/settings.py`:
  - `CELERY_BROKER_URL` (default Redis)
  - `CELERY_RESULT_BACKEND` (defaults to broker)
  - JSON serializers, timezone inherits Django `TIME_ZONE`.

### Running locally
1) Start Redis (choose one):
   - Local: `redis-server`
   - Docker: `docker compose up -d redis`
2) Run Celery worker:
   ```bash
   # Linux/mac: default pool
   celery -A documents worker -l info
   # Windows: dùng --pool=solo để tránh lỗi handle invalid
   celery -A documents worker -l info --pool=solo
   ```
3) (Optional) Run Celery beat for periodic tasks:
   ```bash
   celery -A documents beat -l info
   ```

### Docker compose (Redis)
- `docker-compose.yml` now includes a `redis` service. Web is pre-set with `CELERY_BROKER_URL`/`CELERY_RESULT_BACKEND` pointing to that service. On prod, keep this or point the env vars to your managed Redis.

### Using tasks
- Example call from Django shell:
  ```python
  from app_documents.tasks import ping
  ping.delay()
  ```
- Add your own tasks in `app_documents/tasks.py` (or any app’s `tasks.py`); Celery will autodiscover.

### GAPO scheduled messaging (demo)
- Model: `GapoScheduledMessage` stores receiver_id, message, schedule_at, status.
- Task: `app_documents.tasks.send_gapo_scheduled_message` enqueues via Celery; it will send at `schedule_at` and update status/log errors.
- UI: Admin menu → “Thông tin khác” → “Gửi tin GAPO hẹn giờ” to create schedule (receiver_id, message, time) and view recent tasks.
- Broker required: Celery + Redis must be running; GAPO env vars (`GAPO_API_URL`, `GAPO_BOT_API_KEY`, `GAPO_BOT_ID`) must be set.

## Cấp số văn bản hành chính (allocate number)
- Bảng `adm_document_counter` lưu `next_number` theo bộ `(doc_type, company, year)` và được khóa `select_for_update` khi cấp số.
- Hàm `app_admindocuments.services.allocate_running_number(doc_type_id, company_id, year=None)`:
  - Nếu `year` trống thì dùng năm hiện tại theo timezone.
  - Lấy/tạo dòng counter, chọn số ứng viên (`next_number`), kiểm tra `AdmAdministrativeDocument` cùng loại/công ty/năm để bỏ qua số đã dùng (kể cả khi có bản ghi nhập tay).
  - Ghi lại `next_number = candidate + 1` sau khi tìm được số trống và trả về `candidate`.
- View `document_create` gọi hàm trên trong transaction, thử tối đa 3 lần; nếu gặp `IntegrityError` sẽ tự tăng counter thêm 1 rồi thử lại để tránh đụng độ khi nhiều người tạo cùng lúc.
- `AdmAdministrativeDocument.save()` dùng `running_number` để tạo số hiệu chính thức dạng `NNN/YYYY/TYPE-COMPANY/SIGNER` (mặc định padding 3 chữ số). Nếu vì lý do nào đó `running_number` chưa có, model sẽ tự tính từ số lớn nhất của năm đó để không bị trùng.

## Cấp số giấy hành chính (paper)
- `AdmPaperDocument` cấp số riêng theo `paper_type` và năm (padding 5 chữ số).
- Khi tạo mới qua view `paper_document_list`:
  - Transaction + `select_for_update` lấy bản ghi cuối cùng của `paper_type` trong năm hiện tại, tính `running_number = last + 1`.
  - Sinh số hiệu dạng `NNNNN/YYYY/{paper_type.code}-F88`, kiểm tra trùng `document_number_full`; nếu trùng thì tăng tiếp đến khi trống.
  - Thử tối đa 3 lần nếu gặp `IntegrityError` (đụng độ đồng thời) trước khi báo lỗi.
- Tải Excel import: với mỗi dòng, hệ thống tìm `paper_type`, lấy `running_number` kế tiếp theo năm, sinh số hiệu cùng format; chạy trong transaction, tránh trùng bằng cách tăng `running_number` khi cần.
- Trang danh sách cho phép lọc/sắp xếp theo loại giấy, mã vận đơn; số thứ tự (`running_number`) dùng cho mục sắp xếp và hiển thị.

## Change log (manual)
- 2025-02-03: Administrative docs numbering theo công ty + định dạng mới `NNN/YYYY/TYPE-COMPANY/SIGNER`; bắt buộc các trường chính khi tạo; thông báo và highlight record mới tạo.
- 2025-02-03: GAPO scheduler: thêm AI hỗ trợ soạn tin (Gemini), layout rộng hơn, bảng lịch sử có cuộn; thêm endpoint `gapo/schedule/ai-draft/`.
- 2025-02-03: Administrative docs list: thêm cột STT lên đầu, “Số hiệu” đứng thứ 2.
- 2025-02-03: Paper documents list: thêm ô tìm kiếm theo số hiệu/mã vận đơn, thêm cột STT.

