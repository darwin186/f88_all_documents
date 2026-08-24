# Kế hoạch triển khai luồng book lỗi chứng từ trên `app_documents`

> Trạng thái tài liệu: Draft để review nghiệp vụ và kỹ thuật  
> Ngày lập: 2026-08-13  
> Phạm vi ứng dụng: `app_documents`  
> Nguồn tham chiếu nghiệp vụ: notebook `báo cáo lỗi chứng từ.ipynb` và dữ liệu hiện có trong hệ thống chứng từ

## 1. Mục tiêu

Xây dựng trên `app_documents` một luồng quản lý book lỗi chứng từ có khả năng thay thế dần quy trình notebook, Excel thủ công, Power Automate và Power Query hiện tại.

Hệ thống phải hỗ trợ đầy đủ chu trình:

```text
Lấy dữ liệu lỗi
→ chốt snapshot theo kỳ
→ chia dữ liệu theo PGD
→ phát hành file/link SharePoint và gửi thông báo
→ PGD phản hồi
→ PVH kiểm tra và đưa ra hướng xử lý
→ QLKV xác nhận
→ PVH chốt book/gỡ lỗi
→ dashboard và xuất báo cáo cuối kỳ
```

Các mục tiêu chính:

- Database của `app_documents` là nguồn sự thật duy nhất về trạng thái và kết quả book lỗi.
- Mỗi lỗi có mã định danh ổn định, không bị tạo lại khi retry hoặc chạy lại job.
- Lưu đúng cơ cấu quản lý tại thời điểm phát sinh và cơ cấu nhận xử lý hiện tại.
- Theo dõi được PGD/QLKV đã phản hồi, chưa phản hồi, phản hồi một phần hoặc quá hạn.
- Cho phép phản hồi trực tiếp trên web; Excel là kênh bổ sung cho người dùng cần làm việc offline.
- Đồng bộ Excel từ SharePoint bằng Microsoft Graph, không phụ thuộc Excel COM hoặc Power Query.
- Có audit log đầy đủ từ lúc phát hành đến quyết định cuối cùng.
- Không dùng link chỉnh sửa anonymous và không để lộ dữ liệu giữa các PGD.

## 2. Phạm vi

### 2.1. Trong phạm vi

- Hai nguồn lỗi chính:
  - Quyển chứng từ chưa gửi/HO chưa nhận đúng điều kiện nghiệp vụ.
  - Chứng từ được kiểm duyệt với kết quả lỗi hoặc cần xử lý.
- Chốt dữ liệu theo kỳ báo cáo.
- Phát hành lỗi tới từng PGD.
- Phản hồi vòng PGD.
- Review vòng PVH.
- Xác nhận vòng QLKV.
- Quyết định cuối cùng: ghi nhận lỗi, gỡ lỗi, chuyển kỳ hoặc hủy.
- Sinh và nhập Excel phản hồi.
- Lưu file và phân quyền trên SharePoint/OneDrive for Business bằng Microsoft Graph.
- Email/GAPO thông báo và nhắc hạn.
- Dashboard vận hành và báo cáo tổng hợp.
- Phân quyền, log, retry, monitoring và test tự động.

### 2.2. Ngoài phạm vi phiên bản đầu

- Tự động đẩy kết quả book lỗi sang hệ thống QTRR nếu chưa có API được phê duyệt.
- OCR hoặc đọc chứng từ scan.
- Thay đổi logic nhận/duyệt/đóng thùng hiện tại của `app_documents`.
- Thay đổi master data tổ chức ngoài những trường cần snapshot.
- Đồng bộ hai chiều với các file Excel cũ không có `case_uuid`.
- Dùng AI để tự quyết định book/gỡ lỗi.

## 3. Nguyên tắc thiết kế bắt buộc

1. **Database-first**: trạng thái chính thức nằm trong PostgreSQL; Excel và SharePoint là artifact trao đổi.
2. **Snapshot bất biến**: nội dung đã phát hành phải được giữ nguyên để kiểm toán, kể cả khi dữ liệu nguồn đổi.
3. **Idempotent**: chạy lại bất kỳ job nào cũng không tạo case, phản hồi, email hoặc file trùng ngoài chủ đích.
4. **Least privilege**: PGD chỉ xem/sửa case của mình; QLKV chỉ xem/sửa phạm vi phụ trách; app Graph chỉ có quyền tối thiểu.
5. **Explicit submission**: file thay đổi không đồng nghĩa đã phản hồi; chỉ hoàn tất khi dữ liệu hợp lệ và có hành động submit.
6. **Append-only audit**: không ghi đè làm mất phản hồi hoặc quyết định cũ.
7. **Retry-safe**: lỗi mạng/Graph/email phải retry an toàn và quan sát được.
8. **Không phụ thuộc desktop**: production không dùng `win32com`, Excel desktop hoặc OneDrive sync của cá nhân.
9. **Mã nghiệp vụ thay cho ID cứng**: không dùng điều kiện kiểu `check_status_id != 1`.
10. **Tách module**: không tiếp tục dồn toàn bộ chức năng mới vào `app_documents/views.py` hoặc `models.py` nếu có thể tránh.

## 4. Quyết định nghiệp vụ cần xác nhận trước khi code

Các mục dưới đây phải được Product Owner/PVH xác nhận. Task kỹ thuật phụ thuộc vào quyết định này không được coi là hoàn thành nếu câu trả lời chưa được ghi lại.

| Mã | Câu hỏi cần chốt | Giá trị đề xuất |
|---|---|---|
| BR-01 | `Shop` trong hệ thống có chính là PGD không? | Có; nếu tồn tại cấp shop cha thì bổ sung master model riêng |
| BR-02 | Kỳ book lỗi theo tháng phát sinh hay tháng phát hành? | Lưu cả hai; khóa theo `report_period` |
| BR-03 | Điều kiện chính xác của “quyển chưa gửi” | Chốt bằng rule có version, không hard-code trong view |
| BR-04 | Trạng thái kiểm duyệt nào được coi là lỗi | Chọn bằng mã/flag danh mục, không dùng PK |
| BR-05 | Danh sách nghiệp vụ được book lỗi | Cấu hình theo campaign hoặc rule set |
| BR-06 | Một folder lỗi được tính theo folder hay gom theo hợp đồng | Hỗ trợ `case_group_key`; mặc định theo hợp đồng như notebook |
| BR-07 | Người chịu lỗi là quản lý lúc phát sinh hay hiện tại | Người chịu lỗi lúc phát sinh; người hiện tại nhận xử lý |
| BR-08 | Deadline PGD, PVH và QLKV | Cấu hình riêng cho từng vòng |
| BR-09 | Không phản hồi quá hạn có tự động ghi nhận lỗi không | Đề xuất tạo quyết định chờ PVH duyệt, không tự chốt âm thầm |
| BR-10 | PGD được sửa phản hồi sau submit không | Không; PVH phải mở lại và hệ thống ghi log |
| BR-11 | QLKV không đồng thuận thì quay lại bước nào | Quay về `ops_reviewing` với lý do bắt buộc |
| BR-12 | Case “hẹn bổ sung” được chuyển kỳ như thế nào | Đóng case cũ với kết quả `deferred`, tạo liên kết tới case kỳ mới |
| BR-13 | Khi chứng từ về sau thời điểm snapshot thì xử lý ra sao | Hiển thị dữ liệu hiện tại để tham khảo nhưng không sửa snapshot |
| BR-14 | Có bắt buộc Excel hay web là kênh chính | Web là chính, Excel là tùy chọn |
| BR-15 | Kênh thông báo chính | Email; GAPO là nhắc bổ sung nếu có mapping người nhận |
| BR-16 | File và link phải giữ bao lâu sau khi đóng kỳ | Đề xuất read-only tối thiểu theo chính sách lưu trữ nội bộ |
| BR-17 | Kết quả cuối cần format nào để gửi QTRR | Chốt schema CSV/XLSX/API |
| BR-18 | Ai có quyền hủy campaign/case | Chỉ admin nghiệp vụ được phân quyền riêng |

## 5. Kiến trúc mục tiêu

```text
┌──────────────────────────────────────────────────────────────────────┐
│                          app_documents UI                            │
│ Campaign │ PGD response │ PVH review │ QLKV confirm │ Dashboard     │
└──────────────────────────────┬───────────────────────────────────────┘
                               │
┌──────────────────────────────▼───────────────────────────────────────┐
│                         Application services                         │
│ candidate query │ snapshot │ workflow │ Excel │ notification │ sync │
└──────────────┬──────────────────────┬───────────────────────┬─────────┘
               │                      │                       │
┌──────────────▼──────────┐ ┌─────────▼──────────┐ ┌──────────▼────────┐
│ PostgreSQL              │ │ Celery/Redis       │ │ Microsoft Graph   │
│ campaigns/cases/logs    │ │ generate/sync/mail│ │ SharePoint/Email   │
└──────────────┬──────────┘ └────────────────────┘ └───────────────────┘
               │
┌──────────────▼───────────────────────────────────────────────────────┐
│ Nguồn hiện có: Folder, DocumentsDetail, CheckingAdditional, Shop,   │
│ Manager, Region, status catalogs và lịch sử nhận/kiểm duyệt         │
└──────────────────────────────────────────────────────────────────────┘
```

### 5.1. Cấu trúc code đề xuất

```text
app_documents/
├── error_booking/
│   ├── __init__.py
│   ├── admin.py
│   ├── choices.py
│   ├── forms.py
│   ├── models.py
│   ├── permissions.py
│   ├── selectors.py
│   ├── services/
│   │   ├── campaigns.py
│   │   ├── candidates.py
│   │   ├── excel.py
│   │   ├── graph.py
│   │   ├── notifications.py
│   │   ├── responses.py
│   │   ├── reviews.py
│   │   └── sync.py
│   ├── tasks.py
│   ├── urls.py
│   ├── views.py
│   └── templates/app_documents/error_booking/
│       ├── campaign_list.html
│       ├── campaign_detail.html
│       ├── assignment_detail.html
│       ├── shop_response.html
│       ├── ops_review.html
│       ├── manager_confirmation.html
│       └── dashboard.html
└── tests/error_booking/
    ├── factories.py
    ├── test_candidates.py
    ├── test_campaigns.py
    ├── test_excel_export.py
    ├── test_excel_import.py
    ├── test_graph.py
    ├── test_notifications.py
    ├── test_permissions.py
    ├── test_tasks.py
    └── test_workflow.py
```

Ghi chú: nếu giữ model trong `app_documents/models.py` để tránh đổi Django app label thì các service/view/test vẫn nên tách theo cấu trúc trên. Không tạo Django app mới nếu việc đó làm phức tạp migration hoặc phân quyền hiện tại mà chưa có lợi ích rõ ràng.

## 6. Thiết kế dữ liệu đề xuất

Tên model có thể thay đổi khi implementation, nhưng ý nghĩa và constraint phải được giữ.

### 6.1. `DocumentErrorRuleSet`

Lưu phiên bản rule chọn candidate.

| Trường | Kiểu | Ý nghĩa |
|---|---|---|
| `id` | BigAutoField | PK |
| `code` | CharField unique | Mã ổn định, ví dụ `BOOK_ERROR_V1` |
| `name` | CharField | Tên hiển thị |
| `version` | PositiveInteger | Phiên bản rule |
| `configuration` | JSONField | Loại lỗi, business type, status code, ngoại lệ |
| `is_active` | Boolean | Có được chọn khi tạo campaign không |
| `valid_from`, `valid_to` | DateTime | Hiệu lực |
| `created_by`, `created_at` | FK/DateTime | Audit |

Constraint:

- Unique `(code, version)`.
- Rule đã dùng trong campaign không được sửa nội dung; muốn đổi phải tạo version mới.

### 6.2. `DocumentErrorCampaign`

Đại diện một đợt book lỗi.

| Trường | Kiểu | Ý nghĩa |
|---|---|---|
| `id` | BigAutoField | PK |
| `campaign_code` | CharField unique | Ví dụ `DOCERR-2026-07-R1` |
| `name` | CharField | Tên đợt |
| `report_period` | DateField | Chuẩn hóa ngày đầu tháng |
| `rule_set` | FK | Rule version đã dùng |
| `scope` | JSONField | Vùng/PGD/loại lỗi được chọn |
| `shop_due_at` | DateTime | Hạn PGD |
| `ops_due_at` | DateTime | Hạn PVH |
| `manager_due_at` | DateTime | Hạn QLKV |
| `status` | CharField | State campaign |
| `snapshot_started_at` | DateTime nullable | Bắt đầu chốt |
| `snapshot_completed_at` | DateTime nullable | Chốt xong |
| `published_at` | DateTime nullable | Phát hành |
| `closed_at` | DateTime nullable | Đóng kỳ |
| `created_by`, `closed_by` | FK | Audit |
| `metadata` | JSONField | Tham số bổ sung có version |

Campaign states:

```text
draft
→ snapshotting
→ ready
→ publishing
→ open
→ ops_review
→ manager_confirmation
→ finalizing
→ closed
```

Nhánh lỗi/quản trị:

```text
snapshotting/publishing/finalizing → failed
draft/ready/open → cancelled
closed → reopened (chỉ qua action đặc quyền và log)
```

### 6.3. `DocumentErrorCase`

Một dòng lỗi ổn định trong campaign.

| Trường | Kiểu | Ý nghĩa |
|---|---|---|
| `id` | BigAutoField | PK nội bộ |
| `case_uuid` | UUIDField unique | ID trao đổi với Excel |
| `campaign` | FK | Đợt lỗi |
| `error_type` | CharField | `missing_folder`, `invalid_document`, ... |
| `source_folder` | FK nullable | Folder nguồn |
| `source_document` | FK nullable | Document nguồn |
| `case_group_key` | CharField | Khóa gom theo HĐ/folder/document |
| `dedupe_key` | CharField | Khóa idempotency |
| `shop` | FK | PGD nhận phản hồi |
| `responsible_manager_snapshot` | JSONField | Cơ cấu chịu lỗi lúc phát sinh |
| `current_manager_snapshot` | JSONField | Cơ cấu nhận xử lý lúc phát hành |
| `source_snapshot` | JSONField | Toàn bộ dữ liệu đã phát hành |
| `current_source_state` | JSONField | Cache trạng thái mới nhất nếu cần |
| `workflow_status` | CharField | Trạng thái case |
| `final_decision` | CharField nullable | Kết quả cuối |
| `final_reason` | TextField | Lý do cuối |
| `finalized_by`, `finalized_at` | FK/DateTime | Audit |
| `created_at`, `updated_at` | DateTime | Audit |

Constraints:

- Unique `(campaign, dedupe_key)`.
- Check constraint: có ít nhất một trong `source_folder`, `source_document`.
- `case_uuid` không đổi trong toàn bộ vòng đời.
- Không cascade xóa case khi dữ liệu nguồn bị xóa; dùng `SET_NULL` nếu chính sách dữ liệu cho phép.

Case states:

```text
draft
→ published_to_shop
→ shop_in_progress
→ shop_submitted
→ ops_reviewing
→ waiting_manager_confirmation
→ manager_confirmed / manager_rejected
→ finalized
```

Các trạng thái phụ:

```text
cancelled
deferred
reopened_to_shop
invalid_source
```

Final decisions:

- `book_error`
- `remove_error`
- `defer_to_next_period`
- `cancelled`
- `needs_manual_resolution`

### 6.4. `DocumentErrorAssignment`

Đại diện gói dữ liệu giao cho một PGD hoặc một QLKV trong một vòng.

| Trường | Kiểu | Ý nghĩa |
|---|---|---|
| `id` | BigAutoField | PK |
| `assignment_uuid` | UUIDField unique | ID ngoài hệ thống |
| `campaign` | FK | Campaign |
| `round_type` | CharField | `shop_response`, `manager_confirmation` |
| `shop` | FK nullable | Có ở vòng PGD |
| `manager_code` | CharField nullable | Có ở vòng QLKV |
| `recipient_snapshot` | JSONField | TO/CC/tên/gender tại lúc phát hành |
| `status` | CharField | Trạng thái assignment |
| `due_at` | DateTime | Hạn phản hồi |
| `published_at` | DateTime nullable | Thời điểm phát hành |
| `first_response_at` | DateTime nullable | Phản hồi đầu tiên |
| `submitted_at` | DateTime nullable | Hoàn tất |
| `submitted_by` | FK nullable | Người submit |
| `reopened_at`, `reopened_by` | DateTime/FK | Audit mở lại |
| `version` | PositiveInteger | Phiên bản gói/file |

Assignment states:

- `draft`
- `generating`
- `ready`
- `publishing`
- `sent`
- `in_progress`
- `submitted`
- `overdue`
- `reopened`
- `failed`
- `cancelled`

### 6.5. `DocumentErrorAssignmentCase`

Bảng liên kết assignment và case, giúp một case xuất hiện ở vòng PGD và vòng QLKV mà không nhân bản case.

Constraints:

- Unique `(assignment, case)`.
- Case phải thuộc cùng campaign với assignment.

### 6.6. `DocumentErrorResponse`

Lưu phiên bản phản hồi PGD, không ghi đè lịch sử.

| Trường | Kiểu | Ý nghĩa |
|---|---|---|
| `id` | BigAutoField | PK |
| `case` | FK | Case |
| `assignment` | FK | Assignment vòng PGD |
| `response_code` | CharField | Mã lựa chọn chuẩn hóa |
| `response_note` | TextField | Ghi chú PGD |
| `promised_date` | DateField nullable | Ngày hẹn bổ sung |
| `evidence` | File/JSON nullable | Tài liệu chứng minh |
| `source` | CharField | `web`, `excel`, `admin` |
| `source_version` | CharField | eTag/version file nếu từ Excel |
| `revision` | PositiveInteger | Lần sửa |
| `is_current` | Boolean | Phiên bản hiện hành |
| `responded_by`, `responded_at` | FK/DateTime | Audit |
| `raw_payload` | JSONField | Dữ liệu nhập gốc đã lọc |

Constraints:

- Chỉ một response `is_current=True` cho mỗi `(case, round)`.
- Tạo revision mới khi sửa; response cũ chuyển `is_current=False` trong transaction.

### 6.7. `DocumentErrorOpsReview`

Lưu quyết định sơ bộ của PVH.

Trường chính:

- `case`, `decision_code`, `detail_code`, `note`.
- `reviewed_by`, `reviewed_at`, `revision`, `is_current`.
- `based_on_response_id` để biết PVH review phản hồi nào.
- `needs_manager_confirmation`.

Decision đề xuất:

- `remove_error`
- `checking`
- `propose_book_error`
- `propose_defer`
- `request_shop_clarification`

### 6.8. `DocumentErrorManagerConfirmation`

Lưu xác nhận QLKV.

Trường chính:

- `case`, `assignment`, `confirmation_code`, `note`.
- `confirmed_by`, `confirmed_at`, `revision`, `is_current`.
- `based_on_review_id`.

Confirmation:

- `agree`
- `disagree`
- `request_more_information`

### 6.9. `DocumentErrorArtifact`

Lưu artifact SharePoint/Excel.

| Trường | Kiểu | Ý nghĩa |
|---|---|---|
| `id` | BigAutoField | PK |
| `assignment` | FK | Assignment sở hữu file |
| `artifact_type` | CharField | `shop_excel`, `manager_excel`, `final_export` |
| `version` | PositiveInteger | Phiên bản file |
| `filename` | CharField | Tên file |
| `site_id`, `drive_id`, `item_id` | CharField | Graph identifiers |
| `parent_item_id` | CharField | Thư mục cha |
| `web_url` | URLField | URL mở file |
| `e_tag`, `c_tag` | CharField | Theo dõi thay đổi |
| `content_hash` | CharField | SHA-256 nội dung đã xử lý |
| `permission_ids` | JSONField | Quyền đã cấp để thu hồi |
| `share_scope`, `share_role` | CharField | Kiểm toán quyền |
| `expires_at` | DateTime nullable | Hết hạn |
| `last_seen_modified_at` | DateTime | Lần đổi trên SharePoint |
| `last_synced_at` | DateTime | Lần import thành công |
| `sync_status` | CharField | Trạng thái sync |
| `created_at`, `updated_at` | DateTime | Audit |

Constraints:

- Unique `(assignment, artifact_type, version)`.
- Unique `(drive_id, item_id)` khi `item_id` không rỗng.

### 6.10. `DocumentErrorSyncJob`

Theo dõi một lần generate/upload/download/import.

Trường chính:

- `job_uuid`, `job_type`, `campaign`, `assignment`, `artifact`.
- `idempotency_key` unique.
- `status`: queued/running/succeeded/partially_succeeded/failed/cancelled.
- `attempt_count`, `started_at`, `finished_at`, `next_retry_at`.
- `summary` JSON, `error_code`, `error_message` đã lọc secret.
- `celery_task_id`.

### 6.11. `DocumentErrorImportRejection`

Lưu lỗi từng dòng khi import Excel:

- Job/artifact/row number.
- `case_uuid` nếu đọc được.
- Error code và message.
- Raw row đã loại dữ liệu không cần thiết.
- Mức độ: warning/error.
- Có thể retry hay không.

### 6.12. `DocumentErrorNotification`

Log email/GAPO:

- Campaign/assignment.
- Type: publish/reminder/overdue/reopened/completed.
- Channel: email/gapo.
- TO/CC snapshot.
- Template version.
- Idempotency key.
- Provider message ID nếu có.
- Status, attempts, sent_at, last_error.

### 6.13. `DocumentErrorAuditLog`

Log mọi chuyển trạng thái và thao tác quản trị:

- Actor/user hoặc system.
- Entity type/id.
- Action.
- From/to state.
- Metadata/diff đã lọc dữ liệu nhạy cảm.
- IP/user-agent khi phát sinh từ web.
- Timestamp.

## 7. Quy tắc chọn dữ liệu lỗi

### 7.1. Quyển chưa gửi

Candidate selector phải dùng Django ORM hoặc SQL tham số hóa và tái hiện rule đã được nghiệp vụ duyệt.

Các điều kiện khởi đầu tham khảo từ notebook:

- `Folder.is_issue=True`.
- `Folder.is_original=True`.
- Tháng `folder_created_date` bằng kỳ báo cáo.
- Chưa có `lastest_received_date` hoặc trạng thái nhận tương ứng.
- Loại bỏ document thuộc view/danh sách ngoại lệ đã phê duyệt.
- Gom document trong folder theo hợp đồng nếu nghiệp vụ yêu cầu.

Không dùng raw string interpolation cho SQL chứa dữ liệu người dùng.

### 7.2. Chứng từ kiểm duyệt lỗi

- Dựa vào mã/flag của `CheckingTransactionStatus` và `CheckingStatusType`.
- Loại bỏ chứng từ descend/duplicate theo rule hiện hành.
- Không dùng `status_id != 1`.
- Lưu cả trạng thái kiểm duyệt, note và lịch sử gần nhất trong snapshot.

### 7.3. Business type

Notebook hiện chỉ giữ một số nghiệp vụ. Danh sách này phải chuyển vào `DocumentErrorRuleSet.configuration`, ví dụ:

```json
{
  "included_business_type_codes": ["..."],
  "included_error_types": ["missing_folder", "invalid_document"],
  "group_missing_folder_by": "contract_code"
}
```

### 7.4. Dedupe key

Đề xuất:

```text
missing_folder:
  sha256(report_period|error_type|shop_id|folder_id|contract_code)

invalid_document:
  sha256(report_period|error_type|shop_id|documents_id|checking_status_code)
```

Nếu nghiệp vụ thay đổi cách gom, phải tăng rule version.

## 8. Thiết kế phản hồi và state machine

### 8.1. Vòng PGD

Các response code nên là danh mục có mã ổn định, không lưu trực tiếp câu tiếng Việt làm khóa:

| Mã | Nhãn | Trường bắt buộc |
|---|---|---|
| `PROMISE_SUPPLEMENT` | PGD hẹn bổ sung chứng từ | Ngày hẹn, ghi chú |
| `ACCEPT_ERROR` | PGD xác nhận lỗi, không thể bổ sung | Ghi chú tùy chọn |
| `OLD_MANAGER_HANDOVER` | Thất lạc/thiếu chữ ký từ TPGD cũ | Giải trình/bằng chứng |
| `ALREADY_SENT` | PGD đã gửi đầy đủ | Mã vận đơn và ngày gửi |
| `APPROVED_EXCEPTION_TICKET` | Có ticket ngoại lệ | Mã ticket, QLKV phê duyệt |
| `HELD_BY_AUTHORITY` | Công quyền/phòng ban khác giữ | Ticket/xác nhận liên quan |

Danh mục phải cấu hình được nhưng mã đã dùng không được xóa; chỉ được deactivate.

### 8.2. Vòng PVH

PVH xem đồng thời:

- Snapshot đã phát hành.
- Phản hồi PGD.
- Dữ liệu nguồn hiện tại.
- Lịch sử nhận/kiểm duyệt.
- Bằng chứng/ticket.
- Cảnh báo dữ liệu nguồn đã thay đổi sau snapshot.

PVH phải chọn quyết định có cấu trúc và note bắt buộc theo rule.

### 8.3. Vòng QLKV

- QLKV chỉ xác nhận các case thuộc phạm vi hiện tại được snapshot tại ngày phát hành.
- `disagree` bắt buộc ghi chú.
- Không cho QLKV sửa phản hồi PGD hoặc quyết định PVH.
- QLKV submit theo từng case hoặc bulk, nhưng assignment chỉ hoàn tất khi mọi case có giá trị hợp lệ.

### 8.4. Chốt cuối

- PVH xem các case QLKV không đồng thuận và xử lý lại.
- Finalize chạy trong transaction.
- Case đã finalized chỉ được sửa qua workflow reopen có quyền riêng.
- Đóng campaign chỉ khi không còn case ở trạng thái chưa giải quyết, trừ khi admin chọn đóng có ngoại lệ và ghi lý do.

## 9. Thiết kế Excel

### 9.1. Workbook vòng PGD

Sheets:

1. `PhanHoi`: dữ liệu và cột PGD nhập.
2. `HuongDan`: hướng dẫn nghiệp vụ/version/template.
3. `_Metadata`: very hidden, chứa campaign/assignment/schema/version/checksum.
4. `_Dropdowns`: very hidden, chứa danh mục phản hồi.

Các cột tối thiểu trong `PhanHoi`:

| Cột | Hiển thị | Sửa được |
|---|---|---|
| `case_uuid` | Có thể ẩn | Không |
| `campaign_code` | Có thể ẩn | Không |
| `assignment_uuid` | Có thể ẩn | Không |
| `error_type` | Có | Không |
| `shop_code` | Có | Không |
| `contract_code` | Có | Không |
| `document_date` | Có | Không |
| `document_type` | Có | Không |
| `checking_issue` | Có | Không |
| `shop_response_code` | Có | Có, dropdown |
| `shop_note` | Có | Có |
| `promised_date` | Có | Có theo response |
| `tracking_code` | Có | Có theo response |
| `exception_ticket` | Có | Có theo response |
| `ops_guidance` | Có | Không |

Yêu cầu:

- Table name không trùng trong workbook.
- Freeze header, filter, wrap text, width phù hợp.
- Chỉ unlock cột người dùng được nhập.
- Sheet protection chỉ để chống sửa nhầm, không được coi là security boundary.
- Không đưa email/token/ID quản trị không cần thiết vào workbook.
- File có schema version rõ ràng.
- Công thức không được dùng để quyết định kết quả chính thức; server tính lại khi import.

### 9.2. Workbook vòng QLKV

Ngoài dữ liệu PGD/PVH, chỉ mở:

- `manager_confirmation_code`.
- `manager_note`.

Có sheet `Summary` do server sinh, không cần Pivot Table/Power Query để dashboard hoạt động.

### 9.3. Validation khi import

Kiểm tra cấp file:

- Đúng extension `.xlsx`.
- Kích thước trong giới hạn.
- Không có macro.
- Có đủ sheet và metadata.
- Đúng schema version.
- Campaign/assignment tồn tại và đang mở.
- Artifact version đúng hoặc chính sách merge cho phép.
- Hash/metadata không bị sửa trái phép.

Kiểm tra cấp dòng:

- `case_uuid` hợp lệ, không trùng trong file.
- Case thuộc đúng assignment và PGD.
- Không thiếu dòng; không có dòng lạ.
- Cột nguồn không bị thay đổi so với snapshot.
- Response code thuộc danh mục đang cho phép.
- Trường điều kiện được nhập đủ.
- Ngày hợp lệ, mã vận đơn/ticket đúng format.
- Case chưa bị finalize hoặc khóa.

Kết quả import:

- Preview trước khi commit khi người dùng upload thủ công.
- Job SharePoint có thể import các dòng hợp lệ và ghi rejection cho dòng lỗi, nhưng không tự submit assignment nếu còn lỗi.
- Import lại cùng `artifact + eTag/content_hash` phải no-op.

## 10. Microsoft Graph và SharePoint

### 10.1. Authentication

Production ưu tiên app-only client credentials với certificate hoặc managed identity nếu hạ tầng hỗ trợ.

Không được:

- Nhập authorization code thủ công trên server.
- In access token ra log.
- Lưu client secret trong code hoặc notebook.
- Dùng tài khoản OneDrive cá nhân làm chủ sở hữu duy nhất của dữ liệu nghiệp vụ.

Biến môi trường dự kiến:

```text
MS_GRAPH_TENANT_ID
MS_GRAPH_CLIENT_ID
MS_GRAPH_CLIENT_SECRET hoặc certificate configuration
MS_GRAPH_SITE_ID
MS_GRAPH_DRIVE_ID
MS_GRAPH_ROOT_FOLDER_ID
MS_GRAPH_SENDER_USER
MS_GRAPH_CONNECT_TIMEOUT
MS_GRAPH_READ_TIMEOUT
```

### 10.2. Quyền

- POC `Sites.Selected` hoặc selected permission tương ứng trên đúng site/library.
- Xác minh API upload, invite, permissions, download, delta bằng app-only trên tenant thật.
- Nếu API chia sẻ yêu cầu quyền rộng hơn, trình Security/IT phê duyệt hoặc dùng thư mục/SharePoint group đã cấp quyền sẵn.
- PGD: write vào đúng file vòng PGD.
- QLV/QLKV vòng PGD: read nếu cần.
- QLKV vòng xác nhận: write vào đúng file vòng QLKV.
- Khi đóng kỳ: chuyển read-only hoặc thu hồi quyền write.
- Không tạo anonymous edit link.

### 10.3. Cấu trúc thư mục

```text
/DocumentErrorBooking/
  /2026-07/
    /shop-response/
      /<region-code>/<manager-code>/<shop-code>/response-v1.xlsx
    /manager-confirmation/
      /<region-code>/<manager-code>/confirmation-v1.xlsx
    /final/
      /final-booking.xlsx
```

Không dùng tên người làm khóa duy nhất vì tên có thể trùng/đổi. Path dùng code đã sanitize.

### 10.4. Graph client

Client phải có:

- Token caching có thời hạn.
- Timeout connect/read.
- Retry exponential backoff có jitter cho 429, 502, 503, 504.
- Tôn trọng `Retry-After`.
- Không retry 400/401/403 vô hạn.
- Correlation/request ID trong log.
- Response schema validation.
- Redact authorization header và dữ liệu nhạy cảm.

### 10.5. Theo dõi thay đổi

MVP có thể poll metadata từng artifact đang mở bằng `item_id` và eTag.

Khi quy mô lớn:

- Dùng drive delta token để lấy item thay đổi.
- Lưu delta link/token trong DB.
- Webhook chỉ làm tín hiệu đánh thức; vẫn dùng delta/GET để xác minh trạng thái.
- Chờ file ổn định trước khi tải, ví dụ kiểm tra eTag không đổi qua hai lần cách nhau một khoảng cấu hình.
- Không suy ra “đã phản hồi” chỉ từ `lastModifiedDateTime`.

## 11. Celery và scheduler

### 11.1. Các task dự kiến

| Task | Mục đích |
|---|---|
| `snapshot_campaign_candidates` | Chốt candidate và tạo case |
| `build_campaign_assignments` | Gom case theo PGD/QLKV |
| `generate_assignment_workbook` | Sinh file Excel |
| `upload_assignment_artifact` | Upload SharePoint |
| `grant_assignment_permissions` | Cấp quyền người nhận |
| `send_assignment_notification` | Gửi email/GAPO |
| `poll_open_artifacts` | Tìm file thay đổi |
| `sync_artifact_response` | Download, validate, import |
| `mark_overdue_assignments` | Đánh dấu quá hạn |
| `send_due_reminders` | Nhắc hạn idempotent |
| `build_manager_assignments` | Tạo vòng QLKV |
| `finalize_campaign` | Chốt kết quả cuối |
| `revoke_closed_campaign_write_access` | Thu hồi quyền sửa |

### 11.2. Idempotency

Mỗi task tạo `idempotency_key`, ví dụ:

```text
snapshot:<campaign_id>:<rule_version>
generate:<assignment_id>:<version>
upload:<artifact_id>:<content_hash>
notify:<assignment_id>:publish:<version>
sync:<artifact_id>:<etag_or_hash>
reminder:<assignment_id>:<reminder_stage>
```

Task phải khóa bản ghi phù hợp bằng `select_for_update()` hoặc lease để tránh hai worker xử lý cùng đối tượng.

### 11.3. Retry

- Graph/email/network: retry có backoff.
- Validation file: không retry tự động trừ khi file còn đang được Excel ghi.
- Lỗi permission/configuration: fail rõ ràng và cảnh báo admin.
- DB deadlock/transient: retry ngắn, giới hạn.
- Sau lần cuối, trạng thái phải là `failed`; không để `running` vĩnh viễn.

### 11.4. Scheduler

Quyết định một trong hai:

- Celery Beat với lịch cấu hình trong code/settings.
- `django-celery-beat` nếu admin cần sửa lịch trên UI.

Lịch tham khảo:

- Poll artifact đang mở: 5–15 phút.
- Reminder: mỗi giờ, nhưng mỗi assignment chỉ gửi đúng stage.
- Overdue: 15–60 phút.
- Reconcile job treo: mỗi 15 phút.
- Permission cleanup: hàng ngày.

## 12. Email và thông báo

### 12.1. Recipient resolution

Tại lúc phát hành phải snapshot:

- TO: `Shop.shop_email` hoặc danh sách email PGD được duyệt.
- CC: QLV, QLKV và role bổ sung theo cấu hình.
- Không tính lại recipient khi resend lịch sử; resend mới phải ghi rõ dùng snapshot hay cơ cấu hiện tại.

### 12.2. Template

Template có version và hỗ trợ:

- Campaign/kỳ.
- Tên PGD/QLKV.
- Tổng case.
- Deadline.
- Link web.
- Link SharePoint.
- Hướng dẫn và kênh hỗ trợ.
- Cảnh báo không chuyển tiếp link.

### 12.3. Trạng thái gửi

- `queued`
- `sending`
- `sent`
- `failed`
- `cancelled`

`sent` chỉ nghĩa provider chấp nhận gửi, không nghĩa người nhận đã đọc hoặc phản hồi.

## 13. UI và API

### 13.1. Màn hình admin campaign

Chức năng:

- Danh sách campaign và bộ lọc.
- Tạo draft.
- Preview số candidate theo loại lỗi/vùng/PGD.
- Hiển thị cảnh báo thiếu email/master data.
- Chốt snapshot.
- Kiểm tra assignment trước phát hành.
- Phát hành/resend có quyền.
- Theo dõi tiến độ.
- Chuyển vòng PVH/QLKV.
- Finalize/close/reopen/cancel.

### 13.2. Màn hình PGD

- Chỉ hiển thị assignment thuộc shop của user.
- Filter chưa trả lời/lỗi loại nào.
- Edit inline hoặc drawer.
- Bulk apply có kiểm soát.
- Upload bằng chứng.
- Save draft và Submit.
- Tải Excel/import Excel.
- Xem deadline và trạng thái khóa.

### 13.3. Màn hình PVH

- Queue case chờ review.
- So sánh snapshot với trạng thái nguồn hiện tại.
- Xem phản hồi PGD và lịch sử.
- Bulk decision chỉ cho nhóm tương thích.
- Gửi trả PGD bổ sung.
- Chuyển QLKV xác nhận.

### 13.4. Màn hình QLKV

- Chỉ hiển thị assignment được giao.
- Đồng thuận/không đồng thuận.
- Note bắt buộc khi không đồng thuận.
- Submit từng phần hoặc toàn bộ theo rule đã chốt.
- Tải/import Excel nếu được bật.

### 13.5. Dashboard

Cards:

- Tổng case.
- Tổng PGD/QLKV cần phản hồi.
- Chưa phản hồi/phản hồi một phần/đã hoàn tất/quá hạn.
- PVH đang review.
- QLKV không đồng thuận.
- Kết quả dự kiến và cuối: book/gỡ/defer.
- File sync lỗi/email lỗi/master data lỗi.

Breakdowns:

- Theo vùng, QLV, QLKV, PGD.
- Theo loại lỗi, nghiệp vụ, trạng thái.
- Theo thời gian phản hồi và SLA.
- Drill-down đến assignment/case.

### 13.6. API nội bộ

Các endpoint phải là POST/PATCH cho mutation, có CSRF, permission và validation rõ ràng. Ví dụ:

```text
GET  /book-loi-chung-tu/
POST /book-loi-chung-tu/campaigns/
POST /book-loi-chung-tu/campaigns/<id>/snapshot/
POST /book-loi-chung-tu/campaigns/<id>/publish/
GET  /book-loi-chung-tu/assignments/<uuid>/
PATCH /api/book-loi-chung-tu/cases/<uuid>/shop-response/
POST /api/book-loi-chung-tu/assignments/<uuid>/submit/
POST /api/book-loi-chung-tu/assignments/<uuid>/excel/preview/
POST /api/book-loi-chung-tu/assignments/<uuid>/excel/import/
PATCH /api/book-loi-chung-tu/cases/<uuid>/ops-review/
PATCH /api/book-loi-chung-tu/cases/<uuid>/manager-confirmation/
```

## 14. Phân quyền

Đề xuất quyền Django riêng:

- `error_booking.view_campaign`
- `error_booking.create_campaign`
- `error_booking.snapshot_campaign`
- `error_booking.publish_campaign`
- `error_booking.respond_as_shop`
- `error_booking.review_as_ops`
- `error_booking.confirm_as_manager`
- `error_booking.finalize_campaign`
- `error_booking.reopen_assignment`
- `error_booking.cancel_case`
- `error_booking.manage_configuration`
- `error_booking.view_audit_log`

Quy tắc scope:

- Shop user: `UserProfile.shop`.
- Checker/PVH: vùng được cấp hoặc toàn quốc.
- QLKV/manager: mapping manager code/email/user cần model hoặc rule rõ ràng; không chỉ tin email request.
- Admin: toàn bộ nhưng mutation nhạy cảm vẫn cần permission riêng.
- Tất cả query detail/export/API phải áp dụng scope server-side.

## 15. Bảo mật và tuân thủ

- Không anonymous edit link.
- Không log token/secret/auth code.
- Secret lấy từ secret manager/environment.
- Hạn chế PII trong Excel và email.
- Không đưa email ẩn/ID kỹ thuật không cần thiết vào file.
- Filename/path phải sanitize, chống path traversal.
- Upload Excel phải giới hạn kích thước và MIME/signature.
- Không xử lý macro `.xlsm` ở MVP.
- Formula injection: escape giá trị bắt đầu bằng `=`, `+`, `-`, `@` khi xuất dữ liệu người dùng.
- Chống SSRF: Graph endpoint/base URL không lấy từ input người dùng.
- Audit các hành động publish, submit, reopen, finalize, permission change.
- Định nghĩa retention và quyền truy cập file sau khi đóng kỳ.
- Có quy trình thu hồi quyền khi nhân sự đổi vị trí hoặc PGD đóng cửa.

## 16. Observability và vận hành

### 16.1. Structured logs

Mỗi log job có:

- `campaign_id`
- `assignment_id`
- `artifact_id`
- `job_id`
- `celery_task_id`
- `graph_request_id` nếu có
- event/status/duration

Không log raw workbook, access token hoặc PII không cần thiết.

### 16.2. Metrics

- Số candidate/case/assignment theo campaign.
- Thời gian snapshot/generate/upload/sync.
- Tỷ lệ Graph/email thành công.
- Retry count và failed job.
- Import rejection theo error code.
- Assignment quá hạn.
- SLA phản hồi PGD/PVH/QLKV.

### 16.3. Cảnh báo

- Campaign snapshot/publish/finalize thất bại.
- Graph 401/403 hoặc permission drift.
- Job running quá timeout.
- File schema invalid.
- Email PGD thiếu/không hợp lệ.
- Delta token hết hạn hoặc reset.
- Số case khác biệt bất thường so với preview.

## 17. Migration từ quy trình hiện tại

### Giai đoạn chạy song song

1. Hệ thống tạo snapshot và dashboard nhưng notebook vẫn phát hành chính thức.
2. So sánh số case theo PGD/loại lỗi giữa hệ thống và notebook.
3. Hệ thống sinh file thử nghiệm, đối chiếu nội dung/hình thức.
4. Một nhóm pilot phản hồi trên web/Excel mới.
5. So sánh kết quả tổng hợp với Power Query.
6. Khi đạt tiêu chí, hệ thống trở thành nguồn chính; notebook chuyển read-only/archive.

Không nhập ngược lịch sử Excel cũ vào database nếu không có mapping tin cậy. Có thể chỉ lưu file lịch sử dưới dạng artifact tham chiếu.

## 18. Kế hoạch triển khai theo phase

Ước lượng là tương đối cho một developer hiểu hệ thống, chưa tính thời gian chờ IT/Security/nghiệp vụ. Mỗi phase phải có demo và sign-off trước khi chuyển phase kế tiếp.

### Phase 0 — Discovery và chốt nghiệp vụ (5–8 ngày công)

Mục tiêu: biến notebook và quy trình vận hành thành đặc tả có thể kiểm thử.

### Phase 1 — Domain model và candidate snapshot (8–12 ngày công)

Mục tiêu: tạo campaign/case ổn định trong DB, chưa tích hợp SharePoint.

### Phase 2 — Web workflow PGD/PVH/QLKV (12–18 ngày công)

Mục tiêu: chạy được end-to-end hoàn toàn trên web.

### Phase 3 — Excel export/import (8–12 ngày công)

Mục tiêu: giữ trải nghiệm Excel nhưng DB vẫn là nguồn chính.

### Phase 4 — Microsoft Graph và thông báo (10–15 ngày công + thời gian phê duyệt)

Mục tiêu: tự động phát hành, chia sẻ và đồng bộ file.

### Phase 5 — Dashboard, final export và vận hành (8–12 ngày công)

Mục tiêu: báo cáo đầy đủ, chốt kỳ và quan sát hệ thống.

### Phase 6 — Pilot, đối soát và cutover (10–20 ngày lịch)

Mục tiêu: chạy song song, chứng minh kết quả và bỏ Power Query khỏi luồng chính.

Tổng kỹ thuật tham khảo: khoảng 51–77 ngày công, chưa tính thời gian nghiệp vụ/IT/Security chờ duyệt. Có thể rút ngắn MVP bằng cách hoãn Excel sync tự động và chỉ triển khai web response trước.

## 19. Backlog task chi tiết

Quy ước:

- Priority: `P0` bắt buộc, `P1` quan trọng, `P2` cải tiến.
- Size: `S` ≤ 1 ngày, `M` 1–3 ngày, `L` 3–5 ngày, `XL` cần tách thêm khi bắt đầu sprint.
- Mỗi task chỉ được đánh dấu hoàn tất khi đạt Acceptance Criteria (AC).

Tổng quan backlog tại thời điểm lập tài liệu:

| Epic | Nội dung | Số task |
|---|---|---:|
| EB-00 | Discovery và đặc tả nghiệp vụ | 12 |
| EB-10 | Nền tảng code và cấu hình | 6 |
| EB-20 | Database và migration | 10 |
| EB-30 | Candidate, snapshot và campaign | 10 |
| EB-40 | Web response workflow | 15 |
| EB-50 | Excel export/import | 14 |
| EB-60 | Microsoft Graph và SharePoint | 17 |
| EB-70 | Notification và scheduler | 10 |
| EB-80 | Dashboard và báo cáo | 8 |
| EB-90 | Test, security và performance | 12 |
| EB-100 | Pilot và cutover | 12 |
| **Tổng** |  | **126** |

### Epic EB-00 — Discovery và đặc tả nghiệp vụ

- [ ] **EB-001 — Vẽ BPMN/as-is flow từ notebook** (`P0`, `M`)
  - Phụ thuộc: không.
  - Nội dung: ghi rõ nguồn dữ liệu, người thực hiện, file master, Power Automate, Power Query, các điểm can thiệp thủ công.
  - AC: PVH xác nhận sơ đồ phản ánh đúng quy trình hiện tại.

- [ ] **EB-002 — Chốt thuật ngữ Shop/PGD/QLV/QLKV/PVH** (`P0`, `S`)
  - AC: có glossary và mapping tương ứng với model hiện tại.

- [ ] **EB-003 — Chốt rule quyển chưa gửi** (`P0`, `M`)
  - Nội dung: điều kiện ngày, nhận, phát hành, bản gốc, ngoại lệ, view loại trừ.
  - AC: có ví dụ đúng/sai và SQL kiểm chứng được nghiệp vụ ký duyệt.

- [ ] **EB-004 — Chốt rule chứng từ kiểm duyệt lỗi** (`P0`, `M`)
  - AC: danh sách status code/flag và ngoại lệ; không phụ thuộc PK.

- [ ] **EB-005 — Chốt business type trong phạm vi** (`P0`, `S`)
  - AC: danh sách code ổn định và người chịu trách nhiệm duy trì.

- [ ] **EB-006 — Chốt rule gom case/dedupe** (`P0`, `M`)
  - AC: cùng dataset notebook cho ra số case mong đợi theo từng loại lỗi.

- [ ] **EB-007 — Chốt state machine và quyền chuyển trạng thái** (`P0`, `M`)
  - AC: bảng from/to/action/role/validation được duyệt.

- [ ] **EB-008 — Chốt danh mục phản hồi PGD và hướng dẫn PVH** (`P0`, `M`)
  - AC: mỗi response code có trường bắt buộc và hướng xử lý mặc định.

- [ ] **EB-009 — Chốt quyết định PVH và xác nhận QLKV** (`P0`, `S`)
  - AC: mã ổn định và điều kiện note bắt buộc.

- [ ] **EB-010 — Chốt SLA/deadline/reminder/escalation** (`P0`, `M`)
  - AC: lịch từng vòng, ngày nghỉ và cách xử lý quá hạn rõ ràng.

- [ ] **EB-011 — Chốt schema đầu ra QTRR** (`P1`, `M`)
  - AC: có mẫu file/API contract và mapping nguồn.

- [ ] **EB-012 — Lập bộ dữ liệu golden sample** (`P0`, `L`)
  - Nội dung: dữ liệu đã ẩn PII, bao phủ mọi loại phản hồi và ngoại lệ.
  - AC: có expected case count và expected final decision.

### Epic EB-10 — Nền tảng code và cấu hình

- [ ] **EB-101 — Tạo module `error_booking`** (`P0`, `M`)
  - AC: module/services/urls/templates/tests được tổ chức, không thêm logic mới vào view khổng lồ hiện tại.

- [ ] **EB-102 — Tạo choices/constants có mã ổn định** (`P0`, `M`)
  - AC: campaign/case/assignment/job/decision states có test.

- [ ] **EB-103 — Tạo feature flag** (`P0`, `S`)
  - AC: có thể tắt menu/API/job mà không rollback code.

- [ ] **EB-104 — Tạo settings validation** (`P0`, `M`)
  - AC: cấu hình thiếu chỉ làm integration unavailable với thông báo rõ, không crash toàn app.

- [ ] **EB-105 — Thêm UI screen và permissions migration** (`P0`, `M`)
  - AC: quyền mới xuất hiện trong màn phân quyền hiện tại.

- [ ] **EB-106 — Viết coding convention cho workflow** (`P1`, `S`)
  - AC: quy định service/selector/transaction/audit/idempotency được ghi trong docs.

### Epic EB-20 — Database và migration

- [ ] **EB-201 — Model RuleSet và response catalogs** (`P0`, `M`)
  - AC: migration + admin + constraint + test deactivate.

- [ ] **EB-202 — Model Campaign** (`P0`, `M`)
  - AC: state/default/index/constraint đúng thiết kế.

- [ ] **EB-203 — Model Case** (`P0`, `L`)
  - AC: unique dedupe, UUID ổn định, snapshot JSON validation.

- [ ] **EB-204 — Model Assignment và AssignmentCase** (`P0`, `L`)
  - AC: không liên kết chéo campaign; unique constraint hoạt động.

- [ ] **EB-205 — Model Response/OpsReview/ManagerConfirmation** (`P0`, `L`)
  - AC: version history và chỉ một current revision.

- [ ] **EB-206 — Model Artifact/SyncJob/Rejection** (`P0`, `L`)
  - AC: idempotency key và index cho scheduler query.

- [ ] **EB-207 — Model Notification/AuditLog** (`P0`, `M`)
  - AC: log append-only qua application service.

- [ ] **EB-208 — Data migration seed catalogs** (`P0`, `M`)
  - AC: seed chạy lặp không trùng, có reverse/no-op phù hợp.

- [ ] **EB-209 — Review index/query plan** (`P1`, `M`)
  - AC: index cho campaign/status/shop/manager/due_at/job status; có EXPLAIN trên dữ liệu giả lập.

- [ ] **EB-210 — Backup/rollback migration rehearsal** (`P0`, `M`)
  - AC: migration được chạy thử trên bản sao staging và có kế hoạch rollback.

### Epic EB-30 — Candidate, snapshot và campaign

- [ ] **EB-301 — Selector quyển chưa gửi** (`P0`, `L`)
  - AC: khớp golden dataset/notebook theo rule đã duyệt.

- [ ] **EB-302 — Selector chứng từ kiểm duyệt lỗi** (`P0`, `L`)
  - AC: dùng code/flag, khớp golden dataset.

- [ ] **EB-303 — Org chart snapshot resolver** (`P0`, `L`)
  - AC: lưu riêng người chịu lỗi lúc phát sinh và người xử lý hiện tại; báo thiếu mapping.

- [ ] **EB-304 — Candidate preview service** (`P0`, `M`)
  - AC: đếm theo loại/vùng/PGD và không ghi DB.

- [ ] **EB-305 — Snapshot service** (`P0`, `L`)
  - AC: transaction/chunking/idempotency; retry không tạo case trùng.

- [ ] **EB-306 — Build shop assignments** (`P0`, `M`)
  - AC: mỗi active PGD có tối đa một assignment/vòng/version theo rule.

- [ ] **EB-307 — Validate readiness** (`P0`, `M`)
  - AC: chặn phát hành nếu thiếu email, deadline, case, catalog hoặc mapping bắt buộc.

- [ ] **EB-308 — Campaign list/create/preview UI** (`P0`, `L`)
  - AC: permission, filter, preview và error summary hoạt động.

- [ ] **EB-309 — Campaign detail/progress UI** (`P0`, `L`)
  - AC: xem count và drill-down assignment/case.

- [ ] **EB-310 — Snapshot Celery task** (`P1`, `M`)
  - AC: job state/retry/progress; không để state treo khi lỗi cuối.

### Epic EB-40 — Web response workflow

- [ ] **EB-401 — Permission selectors theo role/scope** (`P0`, `L`)
  - AC: test chống truy cập chéo PGD/vùng/QLKV cho list/detail/export/API.

- [ ] **EB-402 — PGD assignment list/detail** (`P0`, `L`)
  - AC: chỉ xem dữ liệu đúng shop, pagination/filter đầy đủ.

- [ ] **EB-403 — Save draft response API** (`P0`, `L`)
  - AC: conditional validation, revision history và optimistic locking.

- [ ] **EB-404 — Bulk PGD response** (`P1`, `M`)
  - AC: chỉ áp dụng cho case hợp lệ, preview số dòng trước commit.

- [ ] **EB-405 — PGD submit assignment** (`P0`, `M`)
  - AC: chặn thiếu phản hồi/trường bắt buộc; khóa edit sau submit.

- [ ] **EB-406 — Reopen PGD assignment** (`P0`, `M`)
  - AC: quyền riêng, lý do bắt buộc, audit và notification.

- [ ] **EB-407 — PVH review queue/detail** (`P0`, `L`)
  - AC: xem snapshot/current state/response/history.

- [ ] **EB-408 — PVH review action** (`P0`, `L`)
  - AC: state validation, revision và bulk rule.

- [ ] **EB-409 — Return-to-shop action** (`P1`, `M`)
  - AC: mở đúng case/assignment, deadline mới và log.

- [ ] **EB-410 — Build QLKV assignments** (`P0`, `L`)
  - AC: group đúng manager snapshot, chỉ lấy case cần xác nhận.

- [ ] **EB-411 — QLKV list/detail/confirmation** (`P0`, `L`)
  - AC: scope đúng; disagree bắt buộc note; revision.

- [ ] **EB-412 — QLKV submit** (`P0`, `M`)
  - AC: validation toàn assignment và lock sau submit.

- [ ] **EB-413 — Final decision service** (`P0`, `L`)
  - AC: transaction, mapping đầy đủ, không finalize khi còn unresolved.

- [ ] **EB-414 — Close/reopen campaign** (`P0`, `M`)
  - AC: quyền, reason, audit và protection trạng thái.

- [ ] **EB-415 — Audit timeline UI** (`P1`, `M`)
  - AC: hiển thị chronological history, actor và state change.

### Epic EB-50 — Excel export/import

- [ ] **EB-501 — Chốt Excel schema v1** (`P0`, `M`)
  - AC: tài liệu cột/type/editability/validation/version.

- [ ] **EB-502 — Workbook builder dùng `openpyxl` hoặc `xlsxwriter`** (`P0`, `L`)
  - AC: workbook PGD đúng format, không cần Excel desktop.

- [ ] **EB-503 — Workbook QLKV builder** (`P0`, `L`)
  - AC: cột đúng vòng, summary server-generated.

- [ ] **EB-504 — Metadata/checksum writer** (`P0`, `M`)
  - AC: phát hiện file sai campaign/assignment/version và cột nguồn bị sửa.

- [ ] **EB-505 — Formula injection protection** (`P0`, `M`)
  - AC: test chuỗi bắt đầu bằng ký tự công thức.

- [ ] **EB-506 — Export download endpoints** (`P0`, `M`)
  - AC: scope/permission, filename an toàn, streaming/memory limit.

- [ ] **EB-507 — Excel parser** (`P0`, `L`)
  - AC: đọc đúng v1, không thực thi macro/formula, giới hạn tài nguyên.

- [ ] **EB-508 — File-level validator** (`P0`, `M`)
  - AC: error code rõ cho thiếu sheet/schema/version/metadata.

- [ ] **EB-509 — Row-level validator** (`P0`, `L`)
  - AC: bao phủ UUID/scope/missing/extra/modified source/conditional fields.

- [ ] **EB-510 — Import preview UI/API** (`P0`, `L`)
  - AC: hiển thị create/update/no-op/rejection trước commit.

- [ ] **EB-511 — Import commit service** (`P0`, `L`)
  - AC: atomic revision update và idempotency.

- [ ] **EB-512 — Rejection report export** (`P1`, `M`)
  - AC: người dùng tải danh sách dòng lỗi có hướng sửa.

- [ ] **EB-513 — Round-trip tests** (`P0`, `L`)
  - AC: export → edit allowed cells → import giữ đúng case và phản hồi.

- [ ] **EB-514 — Large workbook performance test** (`P1`, `M`)
  - AC: chốt giới hạn dòng/file và thời gian/memory chấp nhận được.

### Epic EB-60 — Microsoft Graph và SharePoint

- [ ] **EB-601 — Làm việc với IT để cấp app registration/site test** (`P0`, external)
  - AC: tenant/client/site/drive và quyền test sẵn sàng, không lưu secret trong repo.

- [ ] **EB-602 — POC authentication app-only** (`P0`, M)
  - AC: lấy token, cache, refresh mà không cần user tương tác.

- [ ] **EB-603 — POC selected permissions** (`P0`, M)
  - AC: chứng minh app không truy cập site ngoài phạm vi.

- [ ] **EB-604 — POC upload/download/metadata** (`P0`, M)
  - AC: upload file, nhận item ID/eTag/webUrl, tải đúng nội dung.

- [ ] **EB-605 — POC invite/permission/revoke** (`P0`, L)
  - AC: PGD cụ thể write, QLKV read/write đúng vòng, thu hồi được; không anonymous.

- [ ] **EB-606 — Graph authentication client** (`P0`, M)
  - AC: timeout/cache/redacted logs/test mock.

- [ ] **EB-607 — Graph drive client** (`P0`, L)
  - AC: folder ensure/upload/download/get metadata/version-safe.

- [ ] **EB-608 — Graph permission client** (`P0`, L)
  - AC: invite/list/revoke và lưu permission ID.

- [ ] **EB-609 — Retry/throttling middleware** (`P0`, M)
  - AC: 429 Retry-After, backoff/jitter, non-retryable errors.

- [ ] **EB-610 — Artifact upload task** (`P0`, L)
  - AC: content hash/idempotency/job status.

- [ ] **EB-611 — Permission grant task** (`P0`, M)
  - AC: partial failure quan sát được, retry không cấp trùng.

- [ ] **EB-612 — Poll metadata MVP** (`P0`, M)
  - AC: chỉ enqueue artifact có eTag đổi và đang mở.

- [ ] **EB-613 — Stable-file guard** (`P0`, M)
  - AC: không import khi file đang được ghi/autosave.

- [ ] **EB-614 — Download/import sync task** (`P0`, L)
  - AC: eTag/hash idempotency, rejection, status/progress.

- [ ] **EB-615 — Delta sync optimization** (`P2`, L)
  - AC: delta token persisted/resumable/reset handling.

- [ ] **EB-616 — Permission cleanup khi đóng kỳ** (`P0`, M)
  - AC: thu hồi write/chuyển read-only và ghi audit.

- [ ] **EB-617 — Graph integration test trên site sandbox** (`P0`, L)
  - AC: end-to-end upload/share/edit/download/revoke.

### Epic EB-70 — Notification và scheduler

- [ ] **EB-701 — Recipient resolver** (`P0`, M)
  - AC: TO/CC snapshot, validate/dedupe email, báo missing.

- [ ] **EB-702 — Template publish PGD** (`P0`, M)
  - AC: HTML/text, deadline, web/SharePoint link, template version.

- [ ] **EB-703 — Template QLKV confirmation** (`P0`, S)
  - AC: nội dung và scope đúng vòng.

- [ ] **EB-704 — Reminder/escalation templates** (`P1`, M)
  - AC: before due/due/overdue stages được nghiệp vụ duyệt.

- [ ] **EB-705 — Email send service/task** (`P0`, L)
  - AC: retry/idempotency/log/provider response; không gửi trùng.

- [ ] **EB-706 — GAPO reminder optional** (`P2`, M)
  - AC: chỉ gửi user có mapping và không ảnh hưởng email nếu lỗi.

- [ ] **EB-707 — Chọn/cấu hình scheduler** (`P0`, M)
  - AC: lịch production, timezone và singleton behavior.

- [ ] **EB-708 — Overdue marker task** (`P0`, M)
  - AC: đúng deadline/timezone; không đổi assignment đã submit.

- [ ] **EB-709 — Reminder scheduler task** (`P1`, M)
  - AC: mỗi stage gửi tối đa một lần/assignment.

- [ ] **EB-710 — Stuck-job reconciler** (`P1`, M)
  - AC: job quá lease được retry/fail rõ ràng.

### Epic EB-80 — Dashboard và báo cáo

- [ ] **EB-801 — Dashboard query service** (`P0`, L)
  - AC: số liệu thống nhất với detail, query có index/pagination.

- [ ] **EB-802 — Campaign progress cards** (`P0`, M)
  - AC: tổng/partial/submitted/overdue/review/confirm/final.

- [ ] **EB-803 — Breakdown vùng/QLV/QLKV/PGD** (`P0`, L)
  - AC: drill-down và permission scope.

- [ ] **EB-804 — Breakdown loại lỗi/decision** (`P1`, M)
  - AC: tổng khớp campaign.

- [ ] **EB-805 — Integration health panel** (`P1`, M)
  - AC: failed jobs/artifacts/notifications/rejections.

- [ ] **EB-806 — Final export builder** (`P0`, L)
  - AC: schema QTRR, snapshot/audit metadata, count reconciliation.

- [ ] **EB-807 — Shop response summary export** (`P1`, M)
  - AC: shop đã/chưa/partial/overdue và timestamp.

- [ ] **EB-808 — KPI/SLA metrics** (`P1`, L)
  - AC: định nghĩa denominator/timezone/business calendar rõ ràng.

### Epic EB-90 — Test, security và performance

- [ ] **EB-901 — Unit tests state machine** (`P0`, L)
  - AC: mọi transition hợp lệ/không hợp lệ được test.

- [ ] **EB-902 — Candidate golden-data tests** (`P0`, L)
  - AC: match kết quả đã duyệt của EB-012.

- [ ] **EB-903 — Idempotency/concurrency tests** (`P0`, L)
  - AC: snapshot/generate/upload/sync/notify retry không trùng; concurrent workers an toàn.

- [ ] **EB-904 — Permission matrix tests** (`P0`, L)
  - AC: deny chéo PGD/vùng/QLKV trên mọi endpoint/export.

- [ ] **EB-905 — Excel malformed/adversarial tests** (`P0`, L)
  - AC: missing UUID, duplicate, extra row, changed source, formula injection, zip bomb guard theo khả năng thư viện.

- [ ] **EB-906 — Graph failure tests** (`P0`, M)
  - AC: 401/403/404/409/429/5xx/timeout/partial permission.

- [ ] **EB-907 — End-to-end web workflow test** (`P0`, L)
  - AC: campaign → PGD → PVH → QLKV → finalize.

- [ ] **EB-908 — End-to-end Excel/Graph workflow test** (`P0`, L)
  - AC: generate → upload → edit fixture → sync → submit/finalize.

- [ ] **EB-909 — Security review** (`P0`, L/external)
  - AC: Graph scopes, PII, object-level auth, secret/log review được phê duyệt.

- [ ] **EB-910 — Load test candidate snapshot** (`P1`, M)
  - AC: chốt volume mục tiêu và thời gian/memory.

- [ ] **EB-911 — Load test dashboard** (`P1`, M)
  - AC: response time/pagination/query count đạt SLO.

- [ ] **EB-912 — Backup/restore audit data test** (`P1`, M)
  - AC: khôi phục campaign/case/history/artifact metadata thành công.

### Epic EB-100 — Pilot và cutover

- [ ] **EB-1001 — Chuẩn bị staging giống production** (`P0`, M)
  - AC: worker/beat/Redis/DB/Graph sandbox/email test sẵn sàng.

- [ ] **EB-1002 — Import/cấu hình rule set production đầu tiên** (`P0`, M)
  - AC: nghiệp vụ review JSON/config và ký duyệt.

- [ ] **EB-1003 — Dry-run một kỳ lịch sử** (`P0`, L)
  - AC: case count và nội dung khớp notebook trong sai số đã giải thích.

- [ ] **EB-1004 — Pilot 3–5 PGD đại diện** (`P0`, L theo lịch)
  - AC: đủ các nhóm vùng/quản lý/loại lỗi, phản hồi hoàn tất.

- [ ] **EB-1005 — Đối chiếu hệ thống với Power Query** (`P0`, L)
  - AC: 100% case có mapping; khác biệt có biên bản giải thích.

- [ ] **EB-1006 — Thu thập feedback và sửa lỗi pilot** (`P0`, XL)
  - AC: không còn issue blocker/high trước rollout.

- [ ] **EB-1007 — Viết runbook vận hành** (`P0`, L)
  - AC: publish/resend/retry/reopen/finalize/Graph failure/manual fallback.

- [ ] **EB-1008 — Đào tạo admin/PVH/PGD/QLKV** (`P0`, M)
  - AC: tài liệu và buổi hướng dẫn; có người phụ trách hỗ trợ.

- [ ] **EB-1009 — Production rollout theo vùng** (`P0`, L theo lịch)
  - AC: checklist mỗi batch, monitoring và rollback criteria.

- [ ] **EB-1010 — Chạy song song tối thiểu một kỳ** (`P0`, theo lịch)
  - AC: kết quả hệ thống được nghiệp vụ ký duyệt là nguồn chính.

- [ ] **EB-1011 — Ngừng Power Query khỏi luồng chính** (`P1`, M)
  - AC: Power Query chỉ còn read-only/fallback; không quyết định trạng thái.

- [ ] **EB-1012 — Archive notebook và file master cũ** (`P1`, S)
  - AC: lưu đúng retention, đánh dấu không còn dùng production, không xóa lịch sử cần thiết.

## 20. Thứ tự phụ thuộc chính

```text
EB-00 Discovery
  ↓
EB-20 Models ──────────────┐
  ↓                        │
EB-30 Candidate/Snapshot   │
  ↓                        │
EB-40 Web Workflow         │
  ↓                        │
EB-50 Excel                │
  ↓                        │
EB-60 Graph ← IT approval ─┘
  ↓
EB-70 Notification/Scheduler
  ↓
EB-80 Dashboard/Export
  ↓
EB-90 Hardening
  ↓
EB-100 Pilot/Cutover
```

Graph POC và IT approval nên bắt đầu song song từ Phase 0 vì thường có thời gian chờ dài.

## 21. Definition of Ready cho một task

Task chỉ vào sprint khi:

- Nghiệp vụ liên quan đã được chốt hoặc assumption được ghi rõ.
- Có acceptance criteria kiểm thử được.
- Biết role/scope dữ liệu tác động.
- Có thiết kế error handling và audit nếu là mutation/job.
- Dependency bên ngoài đã sẵn sàng hoặc có mock hợp lệ.
- Không chứa secret/dữ liệu production trong fixture.

## 22. Definition of Done chung

Một task implementation chỉ hoàn tất khi:

- Code review đạt yêu cầu.
- Migration có forward/reverse hoặc rollback strategy.
- Unit/integration tests được thêm và pass.
- Toàn bộ test `app_documents` hiện có vẫn pass.
- Permission/object scope được test.
- Log không lộ secret/PII không cần thiết.
- UI có trạng thái loading/empty/error/success phù hợp.
- Job có timeout/retry/final failure state.
- Tài liệu/runbook/API contract được cập nhật.
- Có demo hoặc bằng chứng acceptance criteria.

## 23. Tiêu chí nghiệm thu toàn hệ thống

1. Cùng một campaign chạy snapshot lại không tạo case trùng.
2. Số candidate theo golden dataset khớp rule được duyệt.
3. PGD A không thể xem/tải/import/sửa dữ liệu PGD B.
4. Mỗi case giữ được snapshot và lịch sử phản hồi/review/xác nhận.
5. PGD/QLKV không thể submit khi thiếu trường bắt buộc.
6. Retry generate/upload/sync/email không tạo file, response hoặc thông báo trùng.
7. File Excel sai UUID/scope/schema bị từ chối với lỗi rõ ràng.
8. SharePoint không có anonymous edit link.
9. Dashboard hiển thị đúng đã/chưa/partial/overdue và khớp drill-down.
10. Final export khớp toàn bộ final decision trong database.
11. Production không cần Excel desktop, `win32com`, Power Query hoặc OneDrive sync cá nhân.
12. Có thể điều tra một quyết định cuối từ audit log đến dữ liệu nguồn và mọi phản hồi liên quan.
13. Khi Graph/email lỗi, hệ thống không mất dữ liệu và admin biết chính xác đối tượng cần retry.
14. Một kỳ pilot cho kết quả được PVH xác nhận tương đương hoặc chính xác hơn quy trình cũ.

## 24. Rủi ro và phương án giảm thiểu

| Rủi ro | Mức | Giảm thiểu |
|---|---:|---|
| Rule notebook chưa phản ánh hết ngoại lệ thực tế | Cao | Golden dataset, sign-off nghiệp vụ, versioned rule |
| Master email/org chart thiếu hoặc thay đổi | Cao | Snapshot + readiness validation + error queue |
| Graph permission không được IT duyệt | Cao | POC sớm; web workflow không phụ thuộc Graph; manual download/upload fallback |
| Anonymous link làm lộ dữ liệu | Cao | Cấm trong code/config; security test |
| Excel bị sửa/xóa dòng/cột nguồn | Cao | UUID, metadata, checksum, row validation |
| Hai worker sync cùng file | Cao | Lease/select_for_update + idempotency key |
| File đang autosave khi tải | Trung bình | stable-file guard + retry |
| Campaign lớn gây timeout/memory | Trung bình | chunking, background jobs, streaming/row limit |
| Người dùng quen Excel, không dùng web | Trung bình | chạy song song, UX đơn giản, import/export hỗ trợ |
| State machine quá phức tạp | Trung bình | transition table, service duy nhất, exhaustive tests |
| Dữ liệu PII nằm trong file/email | Cao | data minimization, scope, retention, security review |
| Notebook và hệ thống cho kết quả khác | Cao | reconciliation report theo từng rule/case |

## 25. MVP khuyến nghị

Để giảm rủi ro, MVP đầu tiên nên gồm:

- Campaign và snapshot case.
- Web response PGD.
- Web review PVH.
- Web confirmation QLKV.
- Dashboard đã/chưa phản hồi.
- Audit log và final export.
- Email gửi link web.

Chưa cần trong MVP đầu:

- SharePoint delta/webhook.
- Đồng bộ Excel tự động.
- GAPO reminder.
- Final API sang QTRR.

Sau khi web workflow ổn định mới thêm Excel/Graph. Cách này cho phép chứng minh domain model và state machine trước khi xử lý phần integration phức tạp nhất.

## 26. Checklist trước khi bắt đầu implementation

- [ ] BR-01 đến BR-18 đã có người trả lời và ký duyệt.
- [ ] Có golden dataset đã ẩn PII.
- [ ] Chốt tên module/model/URL hiển thị.
- [ ] Chốt MVP có hay không có Excel/Graph.
- [ ] IT nhận yêu cầu app registration và SharePoint sandbox.
- [ ] Security nhận danh sách Graph scopes dự kiến.
- [ ] Có owner nghiệp vụ duyệt response/decision catalogs.
- [ ] Có owner kỹ thuật cho Celery/Redis/worker/beat production.
- [ ] Có kế hoạch staging và test email.
- [ ] Có tiêu chí đối chiếu với notebook/Power Query.
