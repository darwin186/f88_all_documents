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


class ShopResponseOption(models.Model):
    code = models.CharField(max_length=40, unique=True)
    label = models.CharField(max_length=255)
    description = models.TextField(blank=True, max_length=2000)
    is_active = models.BooleanField(default=True)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "id"]

    def __str__(self):
        return self.label


class ResponseGuidanceTemplate(models.Model):
    code = models.CharField(max_length=40, unique=True)
    name = models.CharField(max_length=255)
    guidance_text = models.TextField(max_length=2000)
    is_active = models.BooleanField(default=True)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = "dec_response_guidance_template"
        ordering = ["sort_order", "id"]

    def __str__(self):
        return self.name


class CampaignResponseOption(models.Model):
    campaign = models.ForeignKey("Campaign", related_name="response_options", on_delete=models.CASCADE)
    option = models.ForeignKey(ShopResponseOption, on_delete=models.PROTECT)
    guidance_template = models.ForeignKey(
        ResponseGuidanceTemplate,
        related_name="campaign_response_options",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
    )
    value = models.CharField(max_length=255)
    label = models.CharField(max_length=255)
    guidance_text = models.TextField(
        blank=True,
        default="",
        max_length=2000,
        help_text="Hướng dẫn hiện dưới ô ghi chú khi PGD chọn phản hồi này.",
    )
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "id"]
        constraints = [models.UniqueConstraint(fields=["campaign", "option"], name="dec_campaign_response_option_unique"), models.UniqueConstraint(fields=["campaign", "value"], name="dec_campaign_response_value_unique")]


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
    carryover_source = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.PROTECT,
        related_name="carryover_campaigns", verbose_name="Nguồn lỗi treo",
    )
    shop_instructions = models.TextField(blank=True, default="", verbose_name="Hướng Dẫn", max_length=10000)
    area_manager_instructions = models.TextField(blank=True, default="", verbose_name="Hướng dẫn Quản lý khu vực", max_length=10000)
    area_monitoring_instructions = models.TextField(
        blank=True, default="", max_length=10000,
        verbose_name="Hướng dẫn QLKV theo dõi PGD",
    )
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT, db_index=True)
    response_opens_at = models.DateTimeField(null=True, blank=True)
    response_deadline = models.DateTimeField(null=True, blank=True)
    area_response_deadline = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Hạn cuối QLKV xác nhận kết quả sau Team review.",
    )
    pgd_email_template = models.ForeignKey(
        "EmailTemplateMaster", related_name="pgd_campaigns", on_delete=models.PROTECT,
        null=True, blank=True,
    )
    area_monitoring_email_template = models.ForeignKey(
        "EmailTemplateMaster", related_name="area_monitoring_campaigns", on_delete=models.PROTECT,
        null=True, blank=True,
    )
    area_confirmation_email_template = models.ForeignKey(
        "EmailTemplateMaster", related_name="area_confirmation_campaigns", on_delete=models.PROTECT,
        null=True, blank=True,
    )
    risk_error_codes = models.ManyToManyField(
        "RiskErrorCode",
        related_name="campaigns",
        blank=True,
        db_table="dec_campaign_risk_error_code",
        help_text="Danh sách mã lỗi được phép sử dụng khi book lỗi gửi QTRR.",
    )
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
        if self.response_deadline and self.area_response_deadline:
            if self.area_response_deadline <= self.response_deadline:
                raise ValidationError(
                    {"area_response_deadline": "Hạn QLKV xác nhận phải sau hạn PGD phản hồi."}
                )

    def save(self, *args, **kwargs):
        if not self.code and self.campaign_type_id and self.report_month:
            prefix = self.campaign_type.code_prefix.strip().upper().rstrip("-")
            self.code = f"{prefix}-{self.report_month:%Y%m}"
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.code} - {self.name}"


class EmailTemplateMaster(models.Model):
    class EmailType(models.TextChoices):
        PGD_RESPONSE = "pgd_response", "Step 2 · PGD phản hồi lỗi"
        AREA_MONITORING = "area_monitoring", "Step 3 · QLKV theo dõi PGD"
        AREA_CONFIRMATION = "area_confirmation", "Step 5 · QLKV xác nhận lỗi"

    name = models.CharField(max_length=200)
    email_type = models.CharField(max_length=30, choices=EmailType.choices, db_index=True)
    subject_template = models.CharField(max_length=500)
    body_template = models.TextField()
    cc_template = models.TextField(blank=True, default="")
    bcc_template = models.TextField(blank=True, default="")
    is_active = models.BooleanField(default=True)
    is_default = models.BooleanField(default=False)
    version = models.PositiveIntegerField(default=1)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, related_name="email_templates_created",
        on_delete=models.SET_NULL, null=True, blank=True,
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, related_name="email_templates_updated",
        on_delete=models.SET_NULL, null=True, blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "dec_email_template_master"
        ordering = ["email_type", "name", "id"]
        constraints = [
            models.UniqueConstraint(fields=["email_type", "name"], name="dec_uq_email_template_type_name"),
            models.UniqueConstraint(
                fields=["email_type"], condition=Q(is_default=True),
                name="dec_uq_default_email_template_type",
            ),
        ]

    def __str__(self):
        return f"{self.get_email_type_display()} · {self.name}"


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
            "suspended-carryover": "Lỗi treo từ kỳ trước",
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
        SUSPENDED = "suspended", "Treo lỗi sang kỳ sau"
        CANCELLED = "cancelled", "Đã hủy"

    error_uid = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    campaign = models.ForeignKey(Campaign, related_name="errors", on_delete=models.CASCADE)
    version = models.ForeignKey(CampaignVersion, related_name="errors", on_delete=models.PROTECT)
    carried_from = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.PROTECT,
        related_name="carried_errors", verbose_name="Lỗi treo từ kỳ trước",
    )
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
    has_deadline_extension = models.BooleanField(default=False)
    expires_at = models.DateTimeField()
    revoked_at = models.DateTimeField(null=True, blank=True)
    first_accessed_at = models.DateTimeField(null=True, blank=True)
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


class ShopEmailDelivery(models.Model):
    class Status(models.TextChoices):
        QUEUED = "queued", "Chờ gửi"
        SENDING = "sending", "Đang gửi"
        SENT = "sent", "Đã gửi"
        FAILED = "failed", "Gửi thất bại"
        SKIPPED = "skipped", "Không gửi"

    link = models.ForeignKey(ShopAccessLink, related_name="email_deliveries", on_delete=models.CASCADE)
    area_manager = models.ForeignKey("app_documents.AreaManager", null=True, blank=True, on_delete=models.SET_NULL)
    area_email = models.EmailField(blank=True)
    to_email = models.EmailField(blank=True)
    cc_emails = models.JSONField(default=list, blank=True)
    bcc_emails = models.JSONField(default=list, blank=True)
    subject = models.CharField(max_length=500, blank=True)
    template_version = models.PositiveIntegerField(default=1)
    attempt_count = models.PositiveIntegerField(default=0)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.QUEUED, db_index=True)
    message = models.CharField(max_length=500, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "dec_shop_email_delivery"


DEFAULT_SHOP_EMAIL_SUBJECT = (
    "BÁO CÁO LỖI chứng từ bản cứng_Tháng {{report_month}}_ {{shop_name}}"
)
DEFAULT_SHOP_EMAIL_BODY = (
    "<p>Kính gửi Anh/Chị PGD <strong>{{shop_name}}</strong>,</p>"
    "<p>PVH gửi báo cáo lỗi chứng từ bản cứng tháng {{report_month}}.</p>"
    "<p>1. Số lượng lỗi cần phản hồi của PGD: <strong>{{error_count}}</strong><br>"
    "2. Link danh sách lỗi chi tiết: <a href=\"{{response_url}}\">{{response_url}}</a><br>"
    "Hướng dẫn điền thông tin phản hồi lỗi, chi tiết trong link Danh sách lỗi.<br>"
    "4. Thời hạn phản hồi: từ {{response_start_date}} - {{response_end_date}}</p>"
    "<p>PGD vui lòng kiểm tra và hoàn tất phản hồi trước 17h ngày {{response_end_date}}. "
    "Trường hợp PGD không thực hiện phản hồi, hệ thống sẽ tự động ghi nhận lỗi và "
    "không thực hiện điều chỉnh (nếu có).</p>"
    "<p>Trân trọng,</p>"
)


class CampaignEmailConfig(models.Model):
    campaign = models.OneToOneField(Campaign, related_name="email_config", on_delete=models.CASCADE)
    subject_template = models.CharField(
        max_length=500,
        default=DEFAULT_SHOP_EMAIL_SUBJECT,
    )
    body_template = models.TextField(
        default=DEFAULT_SHOP_EMAIL_BODY,
    )
    cc_template = models.TextField(blank=True, default="")
    bcc_template = models.TextField(blank=True, default="")
    from_name = models.CharField(max_length=200, blank=True, default="")
    support_email = models.EmailField(blank=True, default="")
    template_version = models.PositiveIntegerField(default=1)
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name="document_campaign_email_configs_updated",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "dec_campaign_email_config"

    def __str__(self):
        return f"Email · {self.campaign.code} · v{self.template_version}"


DEFAULT_AREA_MONITORING_SUBJECT = (
    "Báo cáo lỗi chứng từ bản cứng _ Tháng {{report_month}}_Theo Khu vực"
)
DEFAULT_AREA_MONITORING_BODY = (
    "<p>Kính gửi Anh/Chị <strong>{{area_manager_name}}</strong>,</p>"
    "<p>PVH gửi Anh/Chị báo cáo lỗi chứng từ bản cứng tháng {{report_month}}.</p>"
    "<p>1. Báo cáo lỗi chứng từ: <a href=\"{{report_url}}\">{{report_url}}</a><br>"
    "2. Hướng dẫn cách xem báo cáo: <a href=\"{{report_guide_url}}\">{{report_guide_url}}</a><br>"
    "Trong đó, Power BI là 01 trang báo cáo tổng hợp của PVH về các lỗi chứng từ "
    "của PGD theo khu vực QLKV đang quản lý.<br>"
    "02 nội dung QLKV cần lưu ý và nhắc nhở PGD trong thời gian phản hồi lỗi:<br>"
    "(a) Tỷ lệ phản hồi lỗi của PGD về các lỗi đang được ghi nhận (theo Báo cáo Power BI)<br>"
    "(b) Chi tiết lỗi chứng từ bản cứng theo từng PGD mà QLKV quản lý.<br>"
    "3. Danh sách lỗi chi tiết: <a href=\"{{manager_url}}\">{{manager_url}}</a></p>"
    "<p>Anh/Chị vui lòng theo dõi tỷ lệ phản hồi của PGD thuộc khu vực quản lý, "
    "đảm bảo 100% PGD hoàn tất phản hồi trước 17h ngày {{response_end_date}}.</p>"
    "<p>Mọi thắc mắc vui lòng liên hệ đầu mối Gapo:<br>"
    "- Trần Thị Lan Hương VH<br>"
    "- Lương Hồng Uyên VH<br>"
    "- Nguyễn Thị Hà VH</p>"
    "<p>Trân trọng,</p>"
)
DEFAULT_AREA_CONFIRMATION_SUBJECT = (
    "Chốt Báo cáo ghi nhận lỗi chứng từ bản cứng _ Tháng {{report_month}}"
)
DEFAULT_AREA_CONFIRMATION_BODY = (
    "<p>Kính gửi Anh/Chị <strong>{{area_manager_name}}</strong>,</p>"
    "<p>Sau thời gian nhận phản hồi và kiểm tra thông tin phản hồi của PGD, "
    "PVH gửi Anh/Chị báo cáo kết quả ghi nhận lỗi như sau:</p>"
    "<p>1. Danh sách chi tiết: <a href=\"{{manager_url}}\">{{manager_url}}</a><br>"
    "Anh/Chị QLKV thực hiện kiểm tra xác nhận lỗi với PGD và phản hồi theo link "
    "để PVH xử lý bước tiếp theo.<br>"
    "2. Hướng dẫn QLKV phản hồi: "
    "<a href=\"{{confirmation_guide_url}}\">{{confirmation_guide_url}}</a></p>"
    "<p>Thời hạn phản hồi: Đến hết 17h ngày {{area_response_end_date}}.</p>"
    "<p>Nhờ QLKV lưu ý việc phản hồi tại link danh sách gửi lỗi được đính kèm "
    "trong thời gian quy định. Các thông tin sau thời gian quy định sẽ không được "
    "ghi nhận và gỡ lỗi bởi bộ phận PVH/RRHĐ/Nhân sự.</p>"
    "<p>Mọi thắc mắc cần hỗ trợ, Anh/Chị vui lòng liên hệ theo đầu mối Gapo sau:<br>"
    "- Trần Thị Lan Hương VH<br>"
    "- Nguyễn Thị Hà VH</p>"
    "<p>Trân trọng,</p>"
)


class CampaignAreaEmailConfig(models.Model):
    campaign = models.OneToOneField(Campaign, related_name="area_email_config", on_delete=models.CASCADE)
    monitoring_subject_template = models.CharField(
        max_length=500,
        default=DEFAULT_AREA_MONITORING_SUBJECT,
    )
    monitoring_body_template = models.TextField(
        default=DEFAULT_AREA_MONITORING_BODY,
    )
    monitoring_cc_template = models.TextField(blank=True, default="")
    monitoring_bcc_template = models.TextField(blank=True, default="")
    monitoring_report_url = models.URLField(blank=True, default="")
    monitoring_guide_url = models.URLField(blank=True, default="")
    confirmation_guide_url = models.URLField(blank=True, default="")
    confirmation_subject_template = models.CharField(
        max_length=500,
        default=DEFAULT_AREA_CONFIRMATION_SUBJECT,
    )
    confirmation_body_template = models.TextField(
        default=DEFAULT_AREA_CONFIRMATION_BODY,
    )
    confirmation_cc_template = models.TextField(blank=True, default="")
    confirmation_bcc_template = models.TextField(blank=True, default="")
    from_name = models.CharField(max_length=200, blank=True, default="")
    support_email = models.EmailField(blank=True, default="")
    template_version = models.PositiveIntegerField(default=1)
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name="document_campaign_area_email_configs_updated",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "dec_campaign_area_email_config"

    def __str__(self):
        return f"Email QLKV · {self.campaign.code} · v{self.template_version}"


class CampaignEmailBatch(models.Model):
    class TransportProvider(models.TextChoices):
        MICROSOFT_GRAPH = "microsoft_graph", "Microsoft Graph"

    class EmailType(models.TextChoices):
        PGD_RESPONSE = "pgd_response", "Gửi PGD phản hồi"
        AREA_MONITORING = "area_monitoring", "QLKV theo dõi"
        AREA_CONFIRMATION = "area_confirmation", "QLKV xác nhận"
        SHOP_SUBMISSION_RECEIPT = "shop_submission_receipt", "Xác nhận PGD đã gửi"

    class Status(models.TextChoices):
        QUEUED = "queued", "Chờ gửi"
        DISPATCHING = "dispatching", "Đang chuyển"
        ACCEPTED = "accepted", "Microsoft Graph đã nhận"
        PROCESSING = "processing", "Đang gửi"
        COMPLETED = "completed", "Hoàn tất"
        PARTIALLY_FAILED = "partially_failed", "Hoàn tất một phần"
        FAILED = "failed", "Thất bại"
        CANCELLED = "cancelled", "Đã hủy"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    campaign = models.ForeignKey(Campaign, related_name="email_batches", on_delete=models.CASCADE)
    email_type = models.CharField(max_length=32, choices=EmailType.choices)
    transport_provider = models.CharField(
        max_length=24, choices=TransportProvider.choices, default=TransportProvider.MICROSOFT_GRAPH
    )
    is_test = models.BooleanField(default=False, db_index=True)
    status = models.CharField(max_length=24, choices=Status.choices, default=Status.QUEUED, db_index=True)
    idempotency_key = models.CharField(max_length=255, unique=True)
    total_count = models.PositiveIntegerField(default=0)
    accepted_count = models.PositiveIntegerField(default=0)
    sent_count = models.PositiveIntegerField(default=0)
    failed_count = models.PositiveIntegerField(default=0)
    skipped_count = models.PositiveIntegerField(default=0)
    provider_batch_id = models.CharField(max_length=255, blank=True)
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, related_name="document_campaign_email_batches", on_delete=models.PROTECT
    )
    queued_at = models.DateTimeField(default=timezone.now)
    submitted_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    last_error_code = models.CharField(max_length=100, blank=True)
    last_error_message = models.CharField(max_length=500, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "dec_campaign_email_batch"
        indexes = [models.Index(fields=["campaign", "-created_at"], name="dec_email_batch_campaign_idx")]


class CampaignEmailDelivery(models.Model):
    class TargetType(models.TextChoices):
        SHOP = "shop", "Phòng giao dịch"
        AREA_MANAGER = "area_manager", "Quản lý khu vực"

    class Status(models.TextChoices):
        QUEUED = "queued", "Chờ gửi"
        SUBMITTING = "submitting", "Đang chuyển"
        ACCEPTED = "accepted", "Microsoft Graph đã nhận"
        SENT = "sent", "Đã gửi"
        FAILED = "failed", "Thất bại"
        SKIPPED = "skipped", "Bỏ qua"
        CANCELLED = "cancelled", "Đã hủy"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    batch = models.ForeignKey(CampaignEmailBatch, related_name="deliveries", on_delete=models.CASCADE)
    target_type = models.CharField(max_length=20, choices=TargetType.choices)
    target_id = models.PositiveBigIntegerField()
    shop_access_link = models.ForeignKey(
        "ShopAccessLink", related_name="transport_deliveries", null=True, blank=True, on_delete=models.SET_NULL
    )
    area_access_link = models.ForeignKey(
        "AreaManagerAccessLink", related_name="transport_deliveries", null=True, blank=True, on_delete=models.SET_NULL
    )
    legacy_shop_delivery = models.OneToOneField(
        ShopEmailDelivery, related_name="transport_delivery", null=True, blank=True, on_delete=models.SET_NULL
    )
    to_emails = models.JSONField(default=list)
    cc_emails = models.JSONField(default=list, blank=True)
    bcc_emails = models.JSONField(default=list, blank=True)
    from_email = models.EmailField()
    from_name = models.CharField(max_length=200, blank=True)
    rendered_subject = models.CharField(max_length=500)
    rendered_body_redacted = models.TextField(blank=True)
    encrypted_payload = models.TextField(blank=True)
    template_version = models.PositiveIntegerField(default=1)
    idempotency_key = models.CharField(max_length=255, unique=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.QUEUED, db_index=True)
    attempt_count = models.PositiveIntegerField(default=0)
    provider_batch_id = models.CharField(max_length=255, blank=True)
    provider_message_id = models.CharField(max_length=255, blank=True)
    accepted_at = models.DateTimeField(null=True, blank=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    failed_at = models.DateTimeField(null=True, blank=True)
    error_code = models.CharField(max_length=100, blank=True)
    error_message = models.CharField(max_length=500, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "dec_campaign_email_delivery"
        indexes = [models.Index(fields=["batch", "status"], name="dec_email_delivery_batch_idx")]


class CampaignEmailAttempt(models.Model):
    class Outcome(models.TextChoices):
        ACCEPTED = "accepted", "Đã nhận"
        REJECTED = "rejected", "Bị từ chối"
        TIMEOUT = "timeout", "Timeout"
        TRANSPORT_ERROR = "transport_error", "Lỗi kết nối"

    delivery = models.ForeignKey(CampaignEmailDelivery, related_name="attempts", on_delete=models.CASCADE)
    attempt_number = models.PositiveIntegerField()
    request_id = models.UUIDField(default=uuid.uuid4, editable=False)
    http_status = models.PositiveSmallIntegerField(null=True, blank=True)
    provider_batch_id = models.CharField(max_length=255, blank=True)
    outcome = models.CharField(max_length=20, choices=Outcome.choices)
    duration_ms = models.PositiveIntegerField(default=0)
    error_code = models.CharField(max_length=100, blank=True)
    error_message = models.CharField(max_length=500, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "dec_campaign_email_attempt"
        constraints = [models.UniqueConstraint(fields=["delivery", "attempt_number"], name="dec_uq_email_attempt")]


class CampaignEmailWebhookEvent(models.Model):
    class Status(models.TextChoices):
        PROCESSED = "processed", "Đã xử lý"
        REJECTED = "rejected", "Bị từ chối"

    event_id = models.UUIDField(primary_key=True, editable=False)
    batch = models.ForeignKey(CampaignEmailBatch, related_name="webhook_events", on_delete=models.CASCADE)
    received_at = models.DateTimeField(auto_now_add=True)
    payload_digest = models.CharField(max_length=64)
    processed_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=12, choices=Status.choices)
    message = models.CharField(max_length=500, blank=True)

    class Meta:
        db_table = "dec_campaign_email_webhook_event"


class AreaManagerAccessLink(models.Model):
    class Stage(models.TextChoices):
        MONITORING = "monitoring", "Theo dõi phản hồi PGD"
        CONFIRMATION = "confirmation", "Xác nhận kết quả"

    class EmailStatus(models.TextChoices):
        NOT_SENT = "not_sent", "Chưa gửi"
        QUEUED = "queued", "Chờ gửi"
        SENT = "sent", "Đã gửi"
        FAILED = "failed", "Gửi thất bại"

    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    campaign = models.ForeignKey(Campaign, related_name="area_manager_links", on_delete=models.CASCADE)
    area_manager = models.ForeignKey("app_documents.AreaManager", related_name="document_campaign_links", on_delete=models.PROTECT)
    stage = models.CharField(max_length=20, choices=Stage.choices, default=Stage.MONITORING, db_index=True)
    allowed_email = models.EmailField(max_length=254)
    token_digest = models.CharField(max_length=64, unique=True, editable=False)
    expires_at = models.DateTimeField()
    revoked_at = models.DateTimeField(null=True, blank=True)
    last_accessed_at = models.DateTimeField(null=True, blank=True)
    email_status = models.CharField(max_length=12, choices=EmailStatus.choices, default=EmailStatus.NOT_SENT)
    email_message = models.CharField(max_length=500, blank=True)
    emailed_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, related_name="document_campaign_area_links_created", on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "dec_area_manager_access_link"
        constraints = [models.UniqueConstraint(fields=["campaign", "area_manager", "stage"], name="dec_uq_campaign_area_stage")]

    @property
    def is_expired(self):
        return timezone.now() >= self.expires_at


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
        SUSPENDED = "suspended", "Treo lỗi"

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
    error = models.ForeignKey(CampaignError, related_name="area_confirmations", on_delete=models.CASCADE)
    area_manager = models.ForeignKey(
        "app_documents.AreaManager",
        related_name="document_campaign_confirmations",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
    )
    access_link = models.ForeignKey(
        AreaManagerAccessLink,
        related_name="confirmations",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    is_agreed = models.BooleanField(
        choices=((True, "Đồng thuận"), (False, "Không đồng thuận")),
        verbose_name="QLKV đồng thuận",
    )
    note = models.TextField(blank=True)
    confirmed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name="document_campaign_area_actions",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "dec_area_confirmation"
        indexes = [models.Index(fields=["error", "-created_at"], name="dec_area_error_time_idx")]


class RiskErrorCode(models.Model):
    name = models.CharField(max_length=500)
    source = models.CharField(max_length=100, blank=True, default="")
    code = models.CharField(max_length=50, unique=True)
    is_active = models.BooleanField(default=True)
    sort_order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "dec_risk_error_code"
        ordering = ["sort_order", "code"]

    def __str__(self):
        return f"{self.code} · {self.name}"


class CampaignErrorBooking(models.Model):
    error = models.OneToOneField(CampaignError, related_name="risk_booking", on_delete=models.CASCADE)
    risk_code = models.ForeignKey(RiskErrorCode, related_name="campaign_bookings", on_delete=models.PROTECT)
    note = models.TextField(blank=True, max_length=2000)
    mapped_by = models.ForeignKey(settings.AUTH_USER_MODEL, related_name="document_campaign_risk_mappings", on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "dec_campaign_error_booking"


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


class MediaArchiveJob(models.Model):
    class SourceKind(models.TextChoices):
        FILE = "file", "File"
        FOLDER = "folder", "Thư mục"

    class Status(models.TextChoices):
        QUEUED = "queued", "Đang chờ"
        RUNNING = "running", "Đang đồng bộ"
        SUCCEEDED = "succeeded", "Thành công"
        PARTIAL = "partial", "Thành công một phần"
        FAILED = "failed", "Thất bại"

    source_path = models.CharField(max_length=1000, db_index=True)
    source_kind = models.CharField(max_length=10, choices=SourceKind.choices)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.QUEUED, db_index=True)
    total_files = models.PositiveIntegerField(default=0)
    archived_files = models.PositiveIntegerField(default=0)
    failed_files = models.PositiveIntegerField(default=0)
    total_bytes = models.PositiveBigIntegerField(default=0)
    archived_bytes = models.PositiveBigIntegerField(default=0)
    remote_root = models.CharField(max_length=1200, blank=True)
    remote_url = models.URLField(max_length=1500, blank=True)
    remote_item_id = models.CharField(max_length=255, blank=True)
    summary = models.JSONField(default=dict, blank=True)
    error_message = models.TextField(blank=True)
    celery_task_id = models.CharField(max_length=100, blank=True)
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name="media_archive_jobs",
        on_delete=models.PROTECT,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "dec_media_archive_job"
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["source_path", "-created_at"], name="dec_media_archive_path_idx")]


class TeamReviewExcelJob(models.Model):
    campaign = models.ForeignKey(Campaign, on_delete=models.CASCADE, related_name="review_excel_jobs")
    requested_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    kind = models.CharField(max_length=10, choices=[("export", "Xuất Excel"), ("import", "Import Excel")])
    status = models.CharField(max_length=12, default="queued")
    progress = models.PositiveSmallIntegerField(default=0)
    message = models.TextField(blank=True)
    summary = models.JSONField(default=dict, blank=True)
    input_file = models.FileField(upload_to="document_campaigns/team_review/imports/%Y/%m/", blank=True)
    output_file = models.FileField(upload_to="document_campaigns/team_review/exports/%Y/%m/", blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["campaign", "kind"], condition=Q(status__in=["queued", "running"]), name="dec_one_active_review_excel")]


class AreaConfirmationExcelJob(models.Model):
    campaign = models.ForeignKey(Campaign, on_delete=models.CASCADE, related_name="area_confirmation_excel_jobs")
    requested_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    kind = models.CharField(max_length=10, choices=[("export", "Xuất Excel"), ("import", "Import Excel")])
    status = models.CharField(max_length=12, default="queued")
    progress = models.PositiveSmallIntegerField(default=0)
    message = models.TextField(blank=True)
    summary = models.JSONField(default=dict, blank=True)
    input_file = models.FileField(upload_to="document_campaigns/area_confirmation/imports/%Y/%m/", blank=True)
    output_file = models.FileField(upload_to="document_campaigns/area_confirmation/exports/%Y/%m/", blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["campaign", "kind"],
                condition=Q(status__in=["queued", "running"]),
                name="dec_one_active_area_excel",
            )
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
