import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.utils import timezone


class CampaignType(models.Model):
    code = models.SlugField(max_length=60, unique=True)
    code_prefix = models.CharField(max_length=20, unique=True)
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    shop_checklist_template = models.ForeignKey(
        "ChecklistTemplate",
        related_name="campaign_types",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        help_text="Cấu hình dropdown/câu hỏi dành cho PGD phản hồi.",
    )
    is_active = models.BooleanField(default=True)
    sort_order = models.PositiveSmallIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "dec_campaign_type"
        ordering = ["sort_order", "name"]

    def __str__(self):
        return self.name


class Campaign(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "Nháp"
        DATA_REVIEW = "data_review", "Chờ kiểm tra dữ liệu"
        READY = "ready", "Sẵn sàng phát hành"
        ACTIVE = "active", "Đang phản hồi"
        CLOSED = "closed", "Đã chốt"
        CANCELLED = "cancelled", "Đã hủy"

    code = models.CharField(max_length=30, unique=True, editable=False)
    name = models.CharField(max_length=255)
    campaign_type = models.ForeignKey(
        CampaignType,
        related_name="campaigns",
        on_delete=models.PROTECT,
    )
    report_month = models.DateField(help_text="Ngày đầu tiên của tháng chiến dịch")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT, db_index=True)
    response_opens_at = models.DateTimeField(null=True, blank=True)
    response_deadline = models.DateTimeField(null=True, blank=True)
    link_expires_at = models.DateTimeField(null=True, blank=True)
    current_version = models.ForeignKey(
        "CampaignVersion",
        related_name="current_for_campaigns",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name="document_campaigns_created",
        on_delete=models.PROTECT,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "dec_campaign"
        ordering = ["-report_month"]
        constraints = [
            models.UniqueConstraint(
                fields=["campaign_type", "report_month"],
                name="dec_uq_campaign_type_month",
            )
        ]

    def clean(self):
        super().clean()
        if self.report_month and self.report_month.day != 1:
            raise ValidationError({"report_month": "Tháng chiến dịch phải lưu bằng ngày đầu tháng."})
        if self.response_opens_at and self.response_deadline:
            if self.response_deadline <= self.response_opens_at:
                raise ValidationError({"response_deadline": "Hạn phản hồi phải sau thời điểm phát hành."})
        if self.response_deadline and self.link_expires_at:
            if self.link_expires_at < self.response_deadline:
                raise ValidationError({"link_expires_at": "Link không được hết hạn trước hạn phản hồi."})

    def save(self, *args, **kwargs):
        if not self.code and self.campaign_type_id and self.report_month:
            prefix = self.campaign_type.code_prefix.strip().upper().rstrip("-")
            self.code = f"{prefix}-{self.report_month:%Y%m}"
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.code} - {self.name}"


class CampaignVersion(models.Model):
    class SourceType(models.TextChoices):
        SQL = "sql", "SQL"
        EXCEL = "excel", "Excel"
        ADJUSTMENT = "adjustment", "Điều chỉnh"

    class Status(models.TextChoices):
        DRAFT = "draft", "Nháp"
        VALIDATED = "validated", "Đã kiểm tra"
        PUBLISHED = "published", "Đã phát hành"
        SUPERSEDED = "superseded", "Đã thay thế"

    campaign = models.ForeignKey(Campaign, related_name="versions", on_delete=models.CASCADE)
    version_number = models.PositiveIntegerField()
    source_type = models.CharField(max_length=20, choices=SourceType.choices)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    source_filename = models.CharField(max_length=255, blank=True)
    source_checksum = models.CharField(max_length=64, blank=True)
    import_summary = models.JSONField(default=dict, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name="document_campaign_versions_created",
        on_delete=models.PROTECT,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    published_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "dec_campaign_version"
        ordering = ["campaign_id", "-version_number"]
        constraints = [
            models.UniqueConstraint(
                fields=["campaign", "version_number"],
                name="dec_uq_campaign_version",
            )
        ]

    def __str__(self):
        return f"{self.campaign.code} v{self.version_number}"


class CampaignImportSource(models.Model):
    class Status(models.TextChoices):
        STAGED = "staged", "Đã đưa vào staging"
        VALIDATED = "validated", "Đã kiểm tra"
        CONFIRMED = "confirmed", "Đã xác nhận"

    version = models.ForeignKey(CampaignVersion, related_name="import_sources", on_delete=models.CASCADE)
    name = models.CharField(max_length=100)
    source_type = models.CharField(max_length=20, choices=CampaignVersion.SourceType.choices)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.STAGED)
    source_filename = models.CharField(max_length=255, blank=True)
    source_checksum = models.CharField(max_length=64, blank=True)
    row_count = models.PositiveIntegerField(default=0)
    invalid_count = models.PositiveIntegerField(default=0)
    preview_summary = models.JSONField(default=dict, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name="document_campaign_import_sources_created",
        on_delete=models.PROTECT,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "dec_campaign_import_source"
        constraints = [
            models.UniqueConstraint(
                fields=["version", "name"],
                name="dec_uq_version_import_source",
            )
        ]

    def __str__(self):
        return f"{self.version} - {self.name}"

    @property
    def display_name(self):
        return {
            "folder-fail-sql": "Lỗi quyển chứng từ",
            "document-fail-sql": "Lỗi chứng từ",
            "team-cleaning-excel": "Dữ liệu Excel team đã làm sạch",
        }.get(self.name, self.name)


class CampaignImportJob(models.Model):
    class JobType(models.TextChoices):
        SQL_STAGE = "sql_stage", "Truy xuất dữ liệu SQL"
        EXCEL_EXPORT = "excel_export", "Tạo file Excel"
        EXCEL_IMPORT = "excel_import", "Đối chiếu file Excel"

    class Status(models.TextChoices):
        QUEUED = "queued", "Đang chờ"
        RUNNING = "running", "Đang chạy"
        SUCCEEDED = "succeeded", "Thành công"
        FAILED = "failed", "Thất bại"

    version = models.ForeignKey(CampaignVersion, related_name="import_jobs", on_delete=models.CASCADE)
    job_type = models.CharField(max_length=30, choices=JobType.choices, default=JobType.SQL_STAGE)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.QUEUED, db_index=True)
    current_step = models.PositiveSmallIntegerField(default=0)
    total_steps = models.PositiveSmallIntegerField(default=2)
    summary = models.JSONField(default=dict, blank=True)
    error_message = models.TextField(blank=True)
    celery_task_id = models.CharField(max_length=100, blank=True)
    output_file = models.FileField(upload_to="document_campaigns/exports/%Y/%m/", blank=True)
    output_filename = models.CharField(max_length=255, blank=True)
    input_file = models.FileField(upload_to="document_campaigns/imports/%Y/%m/", blank=True)
    input_filename = models.CharField(max_length=255, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name="document_campaign_import_jobs_created",
        on_delete=models.PROTECT,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "dec_campaign_import_job"
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["version", "job_type"],
                condition=Q(status__in=["queued", "running"]),
                name="dec_uq_active_import_job",
            )
        ]
        indexes = [
            models.Index(fields=["version", "-created_at"], name="dec_job_version_time_idx"),
        ]


class CampaignStagingRow(models.Model):
    source = models.ForeignKey(CampaignImportSource, related_name="rows", on_delete=models.CASCADE)
    row_number = models.PositiveIntegerField()
    source_key = models.CharField(max_length=255, blank=True)
    raw_payload = models.JSONField(default=dict)
    normalized_payload = models.JSONField(default=dict, blank=True)
    content_hash = models.CharField(max_length=64, blank=True)
    validation_errors = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "dec_campaign_staging_row"
        ordering = ["source_id", "row_number"]
        constraints = [
            models.UniqueConstraint(
                fields=["source", "row_number"],
                name="dec_uq_staging_source_row",
            )
        ]
        indexes = [
            models.Index(fields=["source", "source_key"], name="dec_stage_source_key_idx"),
        ]


class ChecklistTemplate(models.Model):
    code = models.CharField(max_length=50)
    name = models.CharField(max_length=255)
    version_number = models.PositiveIntegerField(default=1)
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name="document_checklists_created",
        on_delete=models.PROTECT,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "dec_checklist_template"
        constraints = [
            models.UniqueConstraint(
                fields=["code", "version_number"],
                name="dec_uq_checklist_version",
            )
        ]

    def __str__(self):
        return f"{self.name} · v{self.version_number}"


class ChecklistQuestion(models.Model):
    class QuestionType(models.TextChoices):
        SINGLE = "single", "Một lựa chọn"
        MULTIPLE = "multiple", "Nhiều lựa chọn"
        TEXT = "text", "Nội dung tự do"

    template = models.ForeignKey(ChecklistTemplate, related_name="questions", on_delete=models.CASCADE)
    code = models.CharField(max_length=50)
    label = models.CharField(max_length=500)
    question_type = models.CharField(max_length=20, choices=QuestionType.choices)
    error_type = models.CharField(max_length=20, blank=True, help_text="Để trống nếu áp dụng cho mọi loại lỗi")
    options = models.JSONField(default=list, blank=True)
    is_required = models.BooleanField(default=False)
    sort_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "dec_checklist_question"
        ordering = ["sort_order", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["template", "code"],
                name="dec_uq_question_code",
            )
        ]

    def __str__(self):
        return self.label


class CampaignError(models.Model):
    class ErrorType(models.TextChoices):
        FOLDER = "folder", "Lỗi thiếu quyển chứng từ"
        DOCUMENT = "document", "Lỗi chứng từ không hợp lệ"

    class Status(models.TextChoices):
        READY = "ready", "Sẵn sàng phát hành"
        WAITING_SHOP = "waiting_shop", "Chờ PGD phản hồi"
        SHOP_DRAFT = "shop_draft", "PGD đang cập nhật"
        SHOP_SUBMITTED = "shop_submitted", "Chờ team kiểm tra"
        SHOP_SUPPLEMENT = "shop_supplement", "Yêu cầu PGD bổ sung"
        WAITING_AREA = "waiting_area", "Chờ Area xác nhận"
        AREA_RETURNED = "area_returned", "Area yêu cầu xử lý lại"
        AREA_CONFIRMED = "area_confirmed", "Area đã xác nhận"
        CLOSED = "closed", "Đã chốt"
        EXCLUDED = "excluded", "Loại khỏi chiến dịch"
        CANCELLED = "cancelled", "Đã hủy"

    error_uid = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    campaign = models.ForeignKey(Campaign, related_name="errors", on_delete=models.CASCADE)
    version = models.ForeignKey(CampaignVersion, related_name="errors", on_delete=models.PROTECT)
    source_key = models.CharField(max_length=255)
    error_type = models.CharField(max_length=20, choices=ErrorType.choices)
    source_object_id = models.BigIntegerField(null=True, blank=True)
    code = models.TextField(blank=True)
    shop = models.ForeignKey("app_documents.Shop", related_name="document_campaign_errors", on_delete=models.PROTECT)
    area_manager = models.ForeignKey(
        "app_documents.AreaManager",
        related_name="document_campaign_errors",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
    )
    region = models.ForeignKey(
        "app_documents.Region",
        related_name="document_campaign_errors",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
    )
    folder = models.ForeignKey(
        "app_documents.Folder",
        related_name="document_campaign_errors",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
    )
    document = models.ForeignKey(
        "app_documents.DocumentsDetail",
        related_name="document_campaign_errors",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
    )
    manager_snapshot = models.JSONField(default=dict, blank=True)
    contract_code = models.CharField(max_length=50, blank=True)
    customer_code = models.CharField(max_length=100, blank=True)
    customer_name = models.CharField(max_length=255, blank=True)
    employee_code = models.CharField(max_length=100, blank=True)
    employee_name = models.CharField(max_length=255, blank=True)
    business_type_name = models.CharField(max_length=500, blank=True)
    document_type_name = models.TextField(blank=True)
    checking_issue = models.TextField()
    source_created_at = models.DateTimeField(null=True, blank=True)
    checklist_template = models.ForeignKey(
        ChecklistTemplate,
        related_name="campaign_errors",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
    )
    status = models.CharField(max_length=30, choices=Status.choices, default=Status.READY)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "dec_campaign_error"
        constraints = [
            models.UniqueConstraint(
                fields=["campaign", "source_key"],
                name="dec_uq_campaign_source",
            ),
            models.CheckConstraint(
                check=Q(folder__isnull=False) | Q(document__isnull=False) | Q(source_object_id__isnull=False),
                name="dec_ck_error_source",
            ),
        ]
        indexes = [
            models.Index(fields=["campaign", "shop", "status"], name="dec_err_campaign_shop_idx"),
            models.Index(fields=["campaign", "area_manager", "status"], name="dec_err_campaign_area_idx"),
            models.Index(fields=["campaign", "region", "status"], name="dec_err_campaign_region_idx"),
            models.Index(fields=["campaign", "error_type"], name="dec_err_campaign_type_idx"),
            models.Index(fields=["campaign", "version"], name="dec_err_campaign_ver_idx"),
        ]


class ShopAccessLink(models.Model):
    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    campaign = models.ForeignKey(Campaign, related_name="shop_links", on_delete=models.CASCADE)
    shop = models.ForeignKey("app_documents.Shop", related_name="document_campaign_links", on_delete=models.PROTECT)
    allowed_email = models.EmailField(max_length=254)
    token_digest = models.CharField(max_length=64, unique=True, editable=False)
    response_deadline = models.DateTimeField()
    expires_at = models.DateTimeField()
    revoked_at = models.DateTimeField(null=True, blank=True)
    last_accessed_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name="document_campaign_links_created",
        on_delete=models.PROTECT,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "dec_shop_access_link"
        constraints = [
            models.UniqueConstraint(
                fields=["campaign", "shop"],
                name="dec_uq_campaign_shop_link",
            )
        ]

    @property
    def is_expired(self):
        return timezone.now() >= self.expires_at

    @property
    def is_editable(self):
        now = timezone.now()
        return not self.revoked_at and now < self.response_deadline and now < self.expires_at


class ShopResponse(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "Nháp"
        SUBMITTED = "submitted", "Đã gửi"
        REOPENED = "reopened", "Đã mở bổ sung"

    error = models.OneToOneField(CampaignError, related_name="shop_response", on_delete=models.CASCADE)
    shop = models.ForeignKey("app_documents.Shop", related_name="document_campaign_responses", on_delete=models.PROTECT)
    answer_code = models.CharField(max_length=100, blank=True)
    answer_payload = models.JSONField(default=dict, blank=True)
    note = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    version_no = models.PositiveIntegerField(default=1)
    submitted_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "dec_shop_response"
        indexes = [
            models.Index(fields=["shop", "-updated_at"], name="dec_resp_shop_updated_idx"),
            models.Index(fields=["status", "updated_at"], name="dec_resp_status_updated_idx"),
        ]


class ChecklistAnswer(models.Model):
    response = models.ForeignKey(ShopResponse, related_name="checklist_answers", on_delete=models.CASCADE)
    question = models.ForeignKey(ChecklistQuestion, related_name="answers", on_delete=models.PROTECT)
    value = models.JSONField(default=dict, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "dec_checklist_answer"
        constraints = [
            models.UniqueConstraint(
                fields=["response", "question"],
                name="dec_uq_response_question",
            )
        ]


class ShopSubmission(models.Model):
    campaign = models.ForeignKey(Campaign, related_name="shop_submissions", on_delete=models.CASCADE)
    shop = models.ForeignKey("app_documents.Shop", related_name="document_campaign_submissions", on_delete=models.PROTECT)
    idempotency_key = models.CharField(max_length=100, unique=True)
    response_count = models.PositiveIntegerField(default=0)
    submitted_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "dec_shop_submission"
        constraints = [
            models.UniqueConstraint(fields=["campaign", "shop"], name="dec_uq_campaign_shop_submit")
        ]


class TeamReview(models.Model):
    class Decision(models.TextChoices):
        APPROVED = "approved", "Phê duyệt"
        SUPPLEMENT = "supplement", "Yêu cầu bổ sung"
        EXCLUDED = "excluded", "Loại khỏi chiến dịch"

    error = models.ForeignKey(CampaignError, related_name="team_reviews", on_delete=models.CASCADE)
    decision = models.CharField(max_length=20, choices=Decision.choices)
    classification = models.CharField(max_length=100, blank=True)
    note = models.TextField(blank=True)
    reviewed_by = models.ForeignKey(settings.AUTH_USER_MODEL, related_name="document_campaign_reviews", on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "dec_team_review"
        indexes = [models.Index(fields=["error", "-created_at"], name="dec_review_error_time_idx")]


class AreaConfirmation(models.Model):
    class Decision(models.TextChoices):
        CONFIRMED = "confirmed", "Xác nhận"
        RETURNED = "returned", "Trả lại team"

    error = models.ForeignKey(CampaignError, related_name="area_confirmations", on_delete=models.CASCADE)
    decision = models.CharField(max_length=20, choices=Decision.choices)
    note = models.TextField(blank=True)
    confirmed_by = models.ForeignKey(settings.AUTH_USER_MODEL, related_name="document_campaign_area_actions", on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "dec_area_confirmation"
        indexes = [models.Index(fields=["error", "-created_at"], name="dec_area_error_time_idx")]


class CampaignSnapshot(models.Model):
    class Trigger(models.TextChoices):
        SCHEDULED = "scheduled", "Định kỳ"
        PUBLISHED = "published", "Phát hành"
        DEADLINE = "deadline", "Hết hạn phản hồi"
        TEAM_APPROVED = "team_approved", "Team hoàn tất"
        AREA_CONFIRMED = "area_confirmed", "Area hoàn tất"
        CLOSED = "closed", "Chốt chiến dịch"

    campaign = models.ForeignKey(Campaign, related_name="snapshots", on_delete=models.CASCADE)
    trigger = models.CharField(max_length=30, choices=Trigger.choices)
    captured_at = models.DateTimeField(default=timezone.now)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = "dec_campaign_snapshot"
        indexes = [models.Index(fields=["campaign", "-captured_at"], name="dec_snap_campaign_time_idx")]


class CampaignSnapshotMetric(models.Model):
    class ScopeType(models.TextChoices):
        GLOBAL = "global", "Toàn chiến dịch"
        REGION = "region", "Region"
        AREA = "area", "Area"
        SHOP = "shop", "PGD"

    snapshot = models.ForeignKey(CampaignSnapshot, related_name="metrics", on_delete=models.CASCADE)
    scope_type = models.CharField(max_length=10, choices=ScopeType.choices)
    scope_key = models.CharField(max_length=50)
    status = models.CharField(max_length=30)
    total = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = "dec_campaign_snapshot_metric"
        constraints = [
            models.UniqueConstraint(
                fields=["snapshot", "scope_type", "scope_key", "status"],
                name="dec_uq_snapshot_metric",
            )
        ]
        indexes = [
            models.Index(fields=["snapshot", "scope_type", "scope_key"], name="dec_metric_scope_idx")
        ]


class CampaignStatusHistory(models.Model):
    campaign = models.ForeignKey(Campaign, related_name="status_history", on_delete=models.CASCADE)
    error = models.ForeignKey(CampaignError, related_name="status_history", on_delete=models.CASCADE, null=True, blank=True)
    from_status = models.CharField(max_length=30, blank=True)
    to_status = models.CharField(max_length=30)
    reason = models.TextField(blank=True)
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name="document_campaign_status_changes",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
    )
    changed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "dec_campaign_status_history"
        indexes = [
            models.Index(fields=["campaign", "-changed_at"], name="dec_hist_campaign_time_idx"),
            models.Index(fields=["error", "-changed_at"], name="dec_hist_error_time_idx"),
        ]
