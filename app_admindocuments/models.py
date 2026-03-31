from datetime import date, time
from pathlib import Path
import re
import uuid

from django.utils import timezone

from django.contrib.auth.models import User
from django.db import models
from django.db.models.signals import post_delete
from django.dispatch import receiver
from app_documents.models import GapoScheduledMessage, Shop


class AdmDocumentType(models.Model):
    """Document Type: Decision / Authorization / Announcement / Dispatch"""

    code = models.CharField(max_length=10, unique=True)
    name = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="adm_documenttype_created_by",
    )
    updated_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="adm_documenttype_updated_by",
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "adm_document_type"
        verbose_name = "Document Type"
        verbose_name_plural = "Document Types"

    def __str__(self):
        return f"{self.name} ({self.code})"


class AdmContentType(models.Model):
    """Content Type: New / Amended / Replaced"""

    code = models.CharField(max_length=20, unique=True)
    name = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="adm_contenttype_created_by",
    )
    updated_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="adm_contenttype_updated_by",
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "adm_content_type"
        verbose_name = "Content Type"
        verbose_name_plural = "Content Types"

    def __str__(self):
        return self.name


class AdmSignerRole(models.Model):
    """Signer Role: Director / CEO"""

    code = models.CharField(max_length=10, unique=True)
    title = models.CharField(max_length=100)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="adm_signerrole_created_by",
    )
    updated_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="adm_signerrole_updated_by",
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "adm_signer_role"
        verbose_name = "Signer Role"
        verbose_name_plural = "Signer Roles"

    def __str__(self):
        return self.title


class AdmDocumentStatus(models.Model):
    """Document Status: Draft / Pending / Issued / Expired"""

    CODE_DRAFT = "100"
    CODE_PENDING = "101"
    CODE_ISSUED = "102"
    CODE_EXPIRED = "103"

    code = models.CharField(max_length=20, unique=True)
    name = models.CharField(max_length=100)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="adm_documentstatus_created_by",
    )
    updated_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="adm_documentstatus_updated_by",
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "adm_document_status"
        verbose_name = "Document Status"
        verbose_name_plural = "Document Statuses"

    def __str__(self):
        return self.name


class AdmCompany(models.Model):
    code = models.CharField(max_length=50, unique=True)
    name = models.CharField(max_length=255)
    badge_text_color = models.CharField(max_length=20, blank=True, null=True)
    badge_bg_color = models.CharField(max_length=20, blank=True, null=True)
    badge_logo_url = models.URLField(max_length=500, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="adm_company_created_by",
    )
    updated_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="adm_company_updated_by",
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "adm_company"
        verbose_name = "Company"
        verbose_name_plural = "Companies"

    def __str__(self):
        return self.name


class AdmDepartment(models.Model):
    code = models.CharField(max_length=50, unique=True)
    name = models.CharField(max_length=255)
    company = models.ForeignKey(
        AdmCompany, on_delete=models.CASCADE, related_name="departments"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="adm_department_created_by",
    )
    updated_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="adm_department_updated_by",
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "adm_department"
        verbose_name = "Department"
        verbose_name_plural = "Departments"

    def __str__(self):
        return f"{self.name} ({self.company.code})"


class AdmAdministrativeDocument(models.Model):
    """Main table for managing administrative documents (issued, draft, etc.)"""

    doc_type = models.ForeignKey(AdmDocumentType, on_delete=models.PROTECT)
    running_number = models.PositiveIntegerField()
    content_type = models.ForeignKey(AdmContentType, on_delete=models.PROTECT)
    reference_number = models.CharField(max_length=200, blank=True, null=True)
    title = models.CharField(max_length=500)
    signer_role = models.ForeignKey(AdmSignerRole, on_delete=models.PROTECT)
    issuing_company = models.ForeignKey(AdmCompany, on_delete=models.PROTECT)
    issuing_department = models.ForeignKey(AdmDepartment, on_delete=models.PROTECT)
    is_reference_document = models.BooleanField(default=False)
    reference_document = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="referenced_by",
    )
    issue_date = models.DateField(blank=True, null=True)
    effective_date = models.DateField(blank=True, null=True)
    expiry_date = models.DateField(blank=True, null=True)
    is_void = models.BooleanField(default=False)
    voided_at = models.DateTimeField(null=True, blank=True)
    voided_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="adm_document_voided_by",
    )
    attachment = models.FileField(
        upload_to="admindocuments/files/%Y/%m/", blank=True, null=True
    )
    status = models.ForeignKey(AdmDocumentStatus, on_delete=models.PROTECT)
    ticket_code = models.CharField(max_length=200, blank=True, null=True)
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name="adm_document_created_by",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="adm_document_updated_by",
    )
    updated_at = models.DateTimeField(auto_now=True)
    note = models.TextField(blank=True, null=True)
    document_number_full = models.CharField(max_length=255, editable=False, unique=True)

    class Meta:
        db_table = "adm_administrative_document"
        verbose_name = "Administrative Document"
        verbose_name_plural = "Administrative Documents"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.title} ({self.document_number_full})"

    def save(self, *args, **kwargs):
        """Generate immutable document number; only allow VOID suffix on first void."""
        is_create = self.pk is None
        previous = None
        if not is_create:
            try:
                previous = AdmAdministrativeDocument.objects.get(pk=self.pk)
            except AdmAdministrativeDocument.DoesNotExist:
                previous = None

        if is_create and not self.running_number:
            current_year = date.today().year
            last_doc = (
                AdmAdministrativeDocument.objects.filter(
                    doc_type=self.doc_type,
                    issuing_company=self.issuing_company,
                    created_at__year=current_year,
                )
                .order_by("-running_number")
                .first()
            )
            self.running_number = last_doc.running_number + 1 if last_doc else 1

        if is_create:
            year_now = date.today().year
            company_code = self.issuing_company.code if self.issuing_company else "UNK"
            signer_code = self.signer_role.code if self.signer_role else "NA"
            doc_type_code = self.doc_type.code if self.doc_type else "NA"
            self.document_number_full = (
                f"{self.running_number:03d}/{year_now}/{doc_type_code}-{company_code}/{signer_code}"
            )
        elif previous:
            # Running number is immutable after first creation.
            self.running_number = previous.running_number

            # Number is immutable, except one valid transition to VOID.
            valid_void_transition = (
                (not previous.is_void)
                and self.is_void
                and self.document_number_full == f"{previous.document_number_full}-VOID"
            )
            if not valid_void_transition:
                self.document_number_full = previous.document_number_full

        super().save(*args, **kwargs)

        try:
            if is_create:
                AdmAdministrativeDocumentHistory.objects.create(
                    document=self,
                    changed_by=self.created_by,
                    change_type=AdmAdministrativeDocumentHistory.CHANGE_CREATED,
                    changes={"new_values": self._serialize_fields()},
                )
            else:
                changes = self._diff_with(previous) if previous else {}
                if changes:
                    AdmAdministrativeDocumentHistory.objects.create(
                        document=self,
                        changed_by=self.updated_by or self.created_by,
                        change_type=AdmAdministrativeDocumentHistory.CHANGE_UPDATED,
                        changes=changes,
                    )
        except Exception:
            pass

    def _serialize_fields(self):
        """Snapshot of key fields for history (stringified for readability)."""
        return {
            "doc_type": str(self.doc_type) if self.doc_type_id else None,
            "running_number": self.running_number,
            "content_type": str(self.content_type) if self.content_type_id else None,
            "reference_number": self.reference_number,
            "title": self.title,
            "signer_role": str(self.signer_role) if self.signer_role_id else None,
            "issuing_company": str(self.issuing_company)
            if self.issuing_company_id
            else None,
            "issuing_department": str(self.issuing_department)
            if self.issuing_department_id
            else None,
            "is_reference_document": self.is_reference_document,
            "reference_document": self.reference_document_id,
            "is_void": self.is_void,
            "issue_date": self.issue_date.isoformat() if self.issue_date else None,
            "effective_date": self.effective_date.isoformat()
            if self.effective_date
            else None,
            "expiry_date": self.expiry_date.isoformat() if self.expiry_date else None,
            "attachment": self.attachment.name if self.attachment else None,
            "status": str(self.status) if self.status_id else None,
            "ticket_code": self.ticket_code,
            "note": self.note,
            "document_number_full": self.document_number_full,
        }

    def _diff_with(self, previous):
        if not previous:
            return {}
        current = self._serialize_fields()
        old = previous._serialize_fields()
        diff = {}
        for key in current.keys():
            if current[key] != old.get(key):
                diff[key] = {"old": old.get(key), "new": current[key]}
        return diff


class AdmPaperType(models.Model):
    code = models.CharField(max_length=20, unique=True)
    name = models.CharField(max_length=100)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "adm_paper_type"
        verbose_name = "Paper Type"
        verbose_name_plural = "Paper Types"

    def __str__(self):
        return f"{self.name} ({self.code})"


class AdmCourierCompany(models.Model):
    name = models.CharField(max_length=100, unique=True)
    contact = models.CharField(max_length=255, blank=True, null=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "adm_courier_company"
        verbose_name = "Courier Company"
        verbose_name_plural = "Courier Companies"

    def __str__(self):
        return self.name


class AdmPaperDocument(models.Model):
    """For managing letters, paper-based docs, and delivery tracking."""

    paper_type = models.ForeignKey(AdmPaperType, on_delete=models.PROTECT)
    running_number = models.PositiveIntegerField()
    region = models.CharField(max_length=50, blank=True, null=True)
    responsible_person = models.CharField(max_length=255)
    document_number_full = models.CharField(max_length=255, unique=True, editable=False)
    requested_department = models.ForeignKey(
        Shop, on_delete=models.PROTECT, null=True, blank=True
    )
    department = models.ForeignKey(
        AdmDepartment,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        help_text="Phòng ban nội bộ phụ trách",
    )
    ticket_code = models.CharField(max_length=200, blank=True, null=True)
    summary = models.CharField(max_length=500)
    courier_company = models.ForeignKey(
        AdmCourierCompany, on_delete=models.SET_NULL, null=True, blank=True
    )
    courier_tracking_code = models.CharField(max_length=255, blank=True, null=True)
    status = models.CharField(max_length=255, blank=True, null=True)
    note = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="adm_paperdoc_created_by",
    )
    updated_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="adm_paperdoc_updated_by",
    )
    is_deleted = models.BooleanField(default=False)
    deleted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "adm_paper_document"
        verbose_name = "Paper Document"
        verbose_name_plural = "Paper Documents"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.paper_type} - {self.summary}"


class AdmIncomingDispatchType(models.Model):
    code = models.CharField(max_length=50, primary_key=True)
    name = models.CharField(max_length=255)
    is_active = models.BooleanField(default=True)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = "adm_incoming_dispatch_type"
        verbose_name = "Incoming Dispatch Type"
        verbose_name_plural = "Incoming Dispatch Types"
        ordering = ["sort_order", "name"]

    def __str__(self):
        return self.name


class AdmIncomingDispatchStatus(models.Model):
    code = models.CharField(max_length=50, primary_key=True)
    name = models.CharField(max_length=255)
    is_active = models.BooleanField(default=True)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = "adm_incoming_dispatch_status"
        verbose_name = "Incoming Dispatch Status"
        verbose_name_plural = "Incoming Dispatch Statuses"
        ordering = ["sort_order", "name"]

    def __str__(self):
        return self.name


class AdmIncomingGapoGroup(models.Model):
    code = models.CharField(max_length=80, primary_key=True)
    name = models.CharField(max_length=255)
    gapo_group_id = models.CharField(max_length=255, unique=True)
    is_active = models.BooleanField(default=True)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = "adm_incoming_gapo_group"
        verbose_name = "Incoming Gapo Group"
        verbose_name_plural = "Incoming Gapo Groups"
        ordering = ["sort_order", "name"]

    def __str__(self):
        return self.name


class AdmIncomingDispatch(models.Model):

    document_number = models.CharField(max_length=255, unique=True, null=True, blank=True)
    responsible_user = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name="adm_incoming_dispatch_responsible",
    )
    sending_unit = models.CharField(max_length=255)
    received_date = models.DateField(default=date.today, editable=False, db_index=True)
    signer_name = models.CharField(max_length=255)
    summary = models.TextField()
    processing_departments = models.ManyToManyField(
        AdmDepartment,
        related_name="incoming_dispatches",
    )
    incoming_item_type = models.ForeignKey(
        AdmIncomingDispatchType,
        to_field="code",
        db_column="incoming_item_type",
        on_delete=models.PROTECT,
        related_name="incoming_dispatches",
        null=True,
        blank=True,
    )
    receiving_company = models.ForeignKey(
        AdmCompany,
        to_field="code",
        db_column="receiving_company",
        on_delete=models.PROTECT,
        related_name="incoming_dispatches_received",
    )
    status = models.ForeignKey(
        AdmIncomingDispatchStatus,
        to_field="code",
        db_column="status",
        on_delete=models.PROTECT,
        related_name="incoming_dispatches",
    )
    gapo_group = models.ForeignKey(
        AdmIncomingGapoGroup,
        to_field="code",
        db_column="gapo_group",
        on_delete=models.PROTECT,
        related_name="incoming_dispatches",
        null=True,
        blank=True,
    )
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="adm_incoming_dispatch_created_by",
    )
    updated_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="adm_incoming_dispatch_updated_by",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "adm_incoming_dispatch"
        verbose_name = "Incoming Dispatch"
        verbose_name_plural = "Incoming Dispatches"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.document_number or '-'} - {self.sending_unit}"

    def save(self, *args, **kwargs):
        """Responsible user and received date are immutable after creation."""
        if self.pk:
            try:
                previous = AdmIncomingDispatch.objects.get(pk=self.pk)
            except AdmIncomingDispatch.DoesNotExist:
                previous = None
            if previous:
                self.responsible_user_id = previous.responsible_user_id
                self.received_date = previous.received_date
        super().save(*args, **kwargs)


def _incoming_dispatch_image_upload_path(instance, filename):
    dispatch_part = instance.dispatch_id or "tmp"
    unique = uuid.uuid4().hex[:8]
    return f"admindocuments/incoming_dispatch/{dispatch_part}/{timezone.now():%Y/%m}/{unique}_{filename}"


class AdmIncomingDispatchImage(models.Model):
    dispatch = models.ForeignKey(
        AdmIncomingDispatch,
        on_delete=models.CASCADE,
        related_name="images",
    )
    image = models.FileField(upload_to=_incoming_dispatch_image_upload_path)
    uploaded_at = models.DateTimeField(auto_now_add=True)
    uploaded_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="adm_incoming_dispatch_images_uploaded",
    )

    class Meta:
        db_table = "adm_incoming_dispatch_image"
        verbose_name = "Incoming Dispatch Image"
        verbose_name_plural = "Incoming Dispatch Images"
        ordering = ["-uploaded_at"]

    def __str__(self):
        return f"Dispatch {self.dispatch_id} image {self.id}"

    @property
    def filename(self):
        return Path(self.image.name or "").name

    @property
    def file_extension(self):
        return Path(self.image.name or "").suffix.lower().lstrip(".")

    @property
    def is_image_preview(self):
        return self.file_extension in {
            "jpg",
            "jpeg",
            "png",
            "gif",
            "webp",
            "bmp",
            "svg",
        }


class AdmIncomingDispatchStatusLog(models.Model):
    dispatch = models.ForeignKey(
        AdmIncomingDispatch,
        on_delete=models.CASCADE,
        related_name="status_logs",
    )
    from_status = models.ForeignKey(
        "AdmIncomingDispatchStatus",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="incoming_dispatch_logs_from_status",
    )
    to_status = models.ForeignKey(
        "AdmIncomingDispatchStatus",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="incoming_dispatch_logs_to_status",
    )
    changed_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="adm_incoming_dispatch_status_logs",
    )
    changed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "adm_incoming_dispatch_status_log"
        verbose_name = "Incoming Dispatch Status Log"
        verbose_name_plural = "Incoming Dispatch Status Logs"
        ordering = ["-changed_at", "-id"]

    def __str__(self):
        return f"Dispatch {self.dispatch_id}: {self.from_status_id or '-'} -> {self.to_status_id or '-'}"


def _parcel_token():
    return uuid.uuid4().hex


class AdmParcelReceipt(models.Model):
    class ParcelType(models.TextChoices):
        DOSSIER = "hoso", "Hồ sơ"
        GOODS = "hanghoa", "Hàng hóa"
        OTHER = "khac", "Khác"

    document_number = models.CharField(max_length=255, unique=True, null=True, blank=True)
    received_by = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name="adm_parcel_receipt_received_by",
        null=True,
        blank=True,
    )
    received_at = models.DateTimeField(default=timezone.now, editable=False, db_index=True, null=True, blank=True)
    recipient_department = models.CharField(max_length=100, db_index=True, blank=True, default="")
    recipient_directory = models.ForeignKey(
        "AdmParcelRecipientCatalog",
        on_delete=models.PROTECT,
        related_name="parcel_receipts",
        null=True,
        blank=True,
    )
    recipient_user = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name="adm_parcel_receipt_recipient_user",
        null=True,
        blank=True,
    )
    recipient_name = models.CharField(max_length=255, blank=True, default="")
    recipient_employee_code = models.CharField(max_length=50, blank=True, default="")
    recipient_gapo_user_id = models.CharField(max_length=100, blank=True, default="")
    parcel_type = models.CharField(max_length=20, choices=ParcelType.choices, default=ParcelType.OTHER)
    sender_unit = models.CharField(max_length=255, blank=True, default="")
    content = models.CharField(max_length=255, blank=True)
    tracking_code = models.CharField(max_length=100, blank=True)
    receiving_company = models.ForeignKey(
        AdmCompany,
        to_field="code",
        db_column="receiving_company",
        on_delete=models.PROTECT,
        related_name="parcel_receipts_received",
    )
    status = models.ForeignKey(
        AdmIncomingDispatchStatus,
        to_field="code",
        db_column="status",
        on_delete=models.PROTECT,
        related_name="parcel_receipts",
    )
    confirmation_token = models.CharField(max_length=64, unique=True, default=_parcel_token, editable=False)
    proxy_qr_token = models.CharField(max_length=64, unique=True, null=True, blank=True)
    proxy_receiver_name = models.CharField(max_length=255, blank=True)
    proxy_receiver_employee_code = models.CharField(max_length=50, blank=True)
    actual_receiver_name = models.CharField(max_length=255, blank=True)
    actual_receiver_employee_code = models.CharField(max_length=50, blank=True)
    notified_at = models.DateTimeField(null=True, blank=True)
    confirmed_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    reminder_scheduled_at = models.DateTimeField(null=True, blank=True)
    reminded_at = models.DateTimeField(null=True, blank=True)
    notification_schedule = models.ForeignKey(
        GapoScheduledMessage,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="adm_parcel_receipt_notification_schedule",
    )
    reminder_schedule = models.ForeignKey(
        GapoScheduledMessage,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="adm_parcel_receipt_reminder_schedule",
    )
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="adm_parcel_receipt_created_by",
    )
    updated_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="adm_parcel_receipt_updated_by",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "adm_parcel_receipt"
        verbose_name = "Parcel Receipt"
        verbose_name_plural = "Parcel Receipts"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.document_number or '-'} - {self.sender_unit}"

    def save(self, *args, **kwargs):
        if self.pk:
            try:
                previous = AdmParcelReceipt.objects.get(pk=self.pk)
            except AdmParcelReceipt.DoesNotExist:
                previous = None
            if previous:
                self.received_by_id = previous.received_by_id
                self.received_at = previous.received_at
                self.confirmation_token = previous.confirmation_token
                self.proxy_qr_token = previous.proxy_qr_token
        super().save(*args, **kwargs)


def _parcel_receipt_image_upload_path(instance, filename):
    parcel_part = instance.parcel_receipt_id or "tmp"
    unique = uuid.uuid4().hex[:8]
    return f"admindocuments/parcel_receipt/{parcel_part}/{timezone.now():%Y/%m}/{unique}_{filename}"


class AdmParcelReceiptImage(models.Model):
    parcel_receipt = models.ForeignKey(
        AdmParcelReceipt,
        on_delete=models.CASCADE,
        related_name="images",
    )
    image = models.FileField(upload_to=_parcel_receipt_image_upload_path)
    uploaded_at = models.DateTimeField(auto_now_add=True)
    uploaded_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="adm_parcel_receipt_images_uploaded",
    )

    class Meta:
        db_table = "adm_parcel_receipt_image"
        verbose_name = "Parcel Receipt Image"
        verbose_name_plural = "Parcel Receipt Images"
        ordering = ["-uploaded_at"]

    def __str__(self):
        return f"Parcel {self.parcel_receipt_id} image {self.id}"


class AdmParcelNotificationBatch(models.Model):
    class Status(models.TextChoices):
        CREATED = "created", "Created"
        SENT = "sent", "Sent"
        CONFIRMED = "confirmed", "Confirmed"

    token = models.CharField(max_length=64, unique=True, default=_parcel_token, editable=False)
    recipient_directory = models.ForeignKey(
        "AdmParcelRecipientCatalog",
        on_delete=models.PROTECT,
        related_name="notification_batches",
        null=True,
        blank=True,
    )
    recipient_name = models.CharField(max_length=255, blank=True, default="")
    recipient_employee_code = models.CharField(max_length=50, blank=True, default="")
    recipient_gapo_user_id = models.CharField(max_length=100, blank=True, default="")
    recipient_department = models.CharField(max_length=255, blank=True, default="")
    parcel_count = models.PositiveIntegerField(default=0)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.CREATED)
    message_text = models.TextField(blank=True, default="")
    notified_at = models.DateTimeField(null=True, blank=True)
    confirmed_at = models.DateTimeField(null=True, blank=True)
    actual_receiver_name = models.CharField(max_length=255, blank=True, default="")
    actual_receiver_employee_code = models.CharField(max_length=50, blank=True, default="")
    notification_send_count = models.PositiveIntegerField(default=0)
    parcels = models.ManyToManyField(
        AdmParcelReceipt,
        related_name="notification_batches",
        blank=True,
    )
    reminder_schedule = models.ForeignKey(
        GapoScheduledMessage,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="adm_parcel_notification_batch_reminder_schedule",
    )
    reminder_scheduled_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="adm_parcel_notification_batches_created",
    )
    updated_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="adm_parcel_notification_batches_updated",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "adm_parcel_notification_batch"
        verbose_name = "Parcel Notification Batch"
        verbose_name_plural = "Parcel Notification Batches"
        ordering = ["-created_at"]

    def __str__(self):
        if self.recipient_name:
            return f"{self.recipient_name} ({self.parcel_count})"
        return f"Batch {self.id or '-'}"


def _parcel_default_reminder_time():
    return time(hour=9, minute=0)


class AdmParcelAutoNotifySetting(models.Model):
    code = models.CharField(max_length=50, unique=True, default="default")
    name = models.CharField(max_length=255, default="Nhắc lại bưu kiện")
    reminder_send_time = models.TimeField(default=_parcel_default_reminder_time)
    reminder_send_times = models.CharField(
        max_length=255,
        default="09:00",
        help_text="Nhập nhiều khung giờ, phân tách bằng dấu phẩy. Ví dụ: 09:00, 14:00, 16:30",
    )
    skip_weekends = models.BooleanField(default=True)
    is_active = models.BooleanField(default=True)
    updated_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="adm_parcel_auto_notify_settings_updated",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "adm_parcel_auto_notify_setting"
        verbose_name = "Parcel Auto Notify Setting"
        verbose_name_plural = "Parcel Auto Notify Settings"
        ordering = ["code"]

    def __str__(self):
        return self.name

    def get_reminder_time_slots(self):
        raw_value = (self.reminder_send_times or "").strip()
        if not raw_value and self.reminder_send_time:
            return [self.reminder_send_time]

        slots = []
        seen = set()
        for chunk in re.split(r"[\n,;]+", raw_value):
            normalized = chunk.strip()
            if not normalized:
                continue
            try:
                parsed = time.fromisoformat(normalized)
            except ValueError:
                continue
            slot_key = parsed.strftime("%H:%M")
            if slot_key in seen:
                continue
            seen.add(slot_key)
            slots.append(parsed)

        if slots:
            return sorted(slots)
        if self.reminder_send_time:
            return [self.reminder_send_time]
        return [_parcel_default_reminder_time()]

    @property
    def reminder_send_times_display(self):
        return ", ".join(slot.strftime("%H:%M") for slot in self.get_reminder_time_slots())


class AdmParcelDynamicTemplate(models.Model):
    TEMPLATE_PARCEL_NOTIFY_CONFIRM = "parcel_notify_confirm"
    TEMPLATE_CHOICES = [
        (TEMPLATE_PARCEL_NOTIFY_CONFIRM, "Thông báo nhận bưu kiện"),
    ]
    SAMPLE_CONTEXT = {
        "recipient_name": "Nguyen Van A",
        "parcel_count": "3",
        "primary_sender": "Viettel Post",
        "company_name": "F88",
        "confirm_url": "https://chungtu.f88.vn/admindocuments/parcel-receipts/batches/confirm/sample-token",
    }

    template_type = models.CharField(
        max_length=50,
        choices=TEMPLATE_CHOICES,
        unique=True,
        default=TEMPLATE_PARCEL_NOTIFY_CONFIRM,
    )
    name = models.CharField(max_length=255, default="Thông báo nhận bưu kiện")
    title_template = models.CharField(
        max_length=255,
        default="Bưu kiện đang chờ bạn nhận",
    )
    body_template = models.TextField(
        default=(
            "Hiện có {{parcel_count}} kiện từ {{primary_sender}}. "
            "Liên hệ lễ tân để nhận và bấm nút bên dưới để xác nhận."
        )
    )
    button_text = models.CharField(
        max_length=255,
        default="Bấm vào đây để xác nhận bưu kiện",
    )
    hero_image_url = models.URLField(max_length=500, blank=True, default="")
    button_bg_color = models.CharField(max_length=20, default="#16A34A")
    button_text_color = models.CharField(max_length=20, default="#FFFFFF")
    card_border_color = models.CharField(max_length=20, default="#DADDE1")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "adm_parcel_dynamic_template"
        verbose_name = "Parcel Dynamic Template"
        verbose_name_plural = "Parcel Dynamic Templates"
        ordering = ["template_type", "-updated_at"]

    def __str__(self):
        return self.name

    @classmethod
    def available_variables(cls):
        return tuple(sorted(cls.SAMPLE_CONTEXT.keys()))

    @classmethod
    def sample_context(cls):
        return dict(cls.SAMPLE_CONTEXT)

    def render_text(self, template, context):
        rendered = template or ""
        for key, value in (context or {}).items():
            rendered = rendered.replace(f"{{{{{key}}}}}", str(value or ""))
        return rendered


class AdmParcelSenderSuggestion(models.Model):
    name = models.CharField(max_length=255, unique=True)
    is_active = models.BooleanField(default=True)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = "adm_parcel_sender_suggestion"
        verbose_name = "Parcel Sender Suggestion"
        verbose_name_plural = "Parcel Sender Suggestions"
        ordering = ["sort_order", "name"]

    def __str__(self):
        return self.name


def _parcel_recipient_import_upload_path(instance, filename):
    batch_part = instance.id or "tmp"
    unique = uuid.uuid4().hex[:8]
    return (
        f"admindocuments/parcel_recipient_imports/{batch_part}/"
        f"{timezone.now():%Y/%m}/{unique}_{filename}"
    )


class AdmParcelRecipientImportBatch(models.Model):
    original_name = models.CharField(max_length=255)
    file = models.FileField(upload_to=_parcel_recipient_import_upload_path)
    sheet_name = models.CharField(max_length=255, blank=True, default="")
    checksum = models.CharField(max_length=64, blank=True, default="")
    total_rows = models.PositiveIntegerField(default=0)
    imported_rows = models.PositiveIntegerField(default=0)
    active_rows = models.PositiveIntegerField(default=0)
    has_errors = models.BooleanField(default=False)
    summary = models.JSONField(default=dict, blank=True)
    is_current = models.BooleanField(default=False, db_index=True)
    imported_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="adm_parcel_recipient_import_batches",
    )
    activated_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "adm_parcel_recipient_import_batch"
        verbose_name = "Parcel Recipient Import Batch"
        verbose_name_plural = "Parcel Recipient Import Batches"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.original_name} @ {self.created_at:%Y-%m-%d %H:%M}"


class AdmParcelRecipientCatalog(models.Model):
    import_batch = models.ForeignKey(
        AdmParcelRecipientImportBatch,
        on_delete=models.CASCADE,
        related_name="recipients",
    )
    row_number = models.PositiveIntegerField()
    gapo_user_id = models.CharField(max_length=100, blank=True, default="", db_index=True)
    employee_code = models.CharField(max_length=50, blank=True, default="", db_index=True)
    full_name = models.CharField(max_length=255, blank=True, default="", db_index=True)
    email = models.EmailField(max_length=255, blank=True, default="")
    phone_number = models.CharField(max_length=50, blank=True, default="")
    phone_number_normalized = models.CharField(max_length=30, blank=True, default="", db_index=True)
    employment_status = models.CharField(max_length=100, blank=True, default="", db_index=True)
    permission_name = models.CharField(max_length=100, blank=True, default="")
    org_chart = models.CharField(max_length=255, blank=True, default="")
    position_name = models.CharField(max_length=255, blank=True, default="")
    department_full = models.CharField(max_length=1000, blank=True, default="")
    department_name = models.CharField(max_length=255, blank=True, default="", db_index=True)
    region_name = models.CharField(max_length=255, blank=True, default="")
    birth_date = models.CharField(max_length=50, blank=True, default="")
    company_join_date = models.CharField(max_length=50, blank=True, default="")
    contract_start_date = models.CharField(max_length=50, blank=True, default="")
    leave_date = models.CharField(max_length=50, blank=True, default="")
    source_created_at = models.CharField(max_length=50, blank=True, default="")
    is_active_member = models.BooleanField(default=True, db_index=True)
    raw_data = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "adm_parcel_recipient_catalog"
        verbose_name = "Parcel Recipient Catalog"
        verbose_name_plural = "Parcel Recipient Catalog"
        ordering = ["department_name", "full_name", "employee_code"]
        unique_together = ("import_batch", "row_number")

    def __str__(self):
        if self.employee_code:
            return f"{self.full_name} - {self.employee_code}"
        return self.full_name or self.gapo_user_id or f"row {self.row_number}"

    @staticmethod
    def mask_phone_number(value):
        phone = (value or "").strip()
        digits = re.sub(r"\D", "", phone)
        if len(digits) <= 6:
            return digits or ""
        return f"{digits[:3]}{'*' * (len(digits) - 6)}{digits[-3:]}"

    @staticmethod
    def mask_email(value):
        email = (value or "").strip()
        if not email or "@" not in email:
            return email
        local, domain = email.split("@", 1)
        if len(local) <= 2:
            masked_local = local[:1] + "*"
        else:
            masked_local = f"{local[:2]}{'*' * max(len(local) - 2, 1)}"
        return f"{masked_local}@{domain}"

    @staticmethod
    def mask_birth_date(value):
        text = (value or "").strip()
        if len(text) < 4:
            return text
        return f"**/**/{text[-4:]}"


class AdmParcelReceiptLog(models.Model):
    ACTION_CREATED = "created"
    ACTION_NOTIFIED = "notified"
    ACTION_CONFIRMED = "confirmed"
    ACTION_HANDED_OVER = "handed_over"
    ACTION_PROXY_REGISTERED = "proxy_registered"
    ACTION_UPDATED = "updated"

    ACTION_CHOICES = [
        (ACTION_CREATED, "Created"),
        (ACTION_NOTIFIED, "Notified"),
        (ACTION_CONFIRMED, "Confirmed"),
        (ACTION_HANDED_OVER, "Handed Over"),
        (ACTION_PROXY_REGISTERED, "Proxy Registered"),
        (ACTION_UPDATED, "Updated"),
    ]

    parcel_receipt = models.ForeignKey(
        AdmParcelReceipt,
        on_delete=models.CASCADE,
        related_name="audit_logs",
    )
    action = models.CharField(max_length=30, choices=ACTION_CHOICES)
    from_status = models.ForeignKey(
        AdmIncomingDispatchStatus,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="parcel_logs_from_status",
    )
    to_status = models.ForeignKey(
        AdmIncomingDispatchStatus,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="parcel_logs_to_status",
    )
    actor = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="adm_parcel_receipt_logs",
    )
    note = models.CharField(max_length=255, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "adm_parcel_receipt_log"
        verbose_name = "Parcel Receipt Log"
        verbose_name_plural = "Parcel Receipt Logs"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.parcel_receipt_id} - {self.action} @ {self.created_at}"


def _attachment_upload_path(instance, filename):
    doc_part = instance.document_id or "tmp"
    unique = uuid.uuid4().hex[:8]
    return f"admindocuments/files/{doc_part}/{timezone.now():%Y/%m}/{unique}_{filename}"


class AdmDocumentAttachment(models.Model):
    document = models.ForeignKey(
        AdmAdministrativeDocument,
        on_delete=models.CASCADE,
        related_name="attachments",
    )
    version = models.PositiveIntegerField()
    file = models.FileField(upload_to=_attachment_upload_path, null=True, blank=True)
    original_name = models.CharField(max_length=255, blank=True, null=True)
    link = models.URLField(max_length=1000, blank=True, null=True)
    is_latest = models.BooleanField(default=True)
    is_deleted = models.BooleanField(default=False)
    note = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="adm_doc_attachment_created",
    )
    deleted_at = models.DateTimeField(null=True, blank=True)
    deleted_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="adm_doc_attachment_deleted",
    )

    class Meta:
        db_table = "adm_document_attachment"
        unique_together = ("document", "version")
        ordering = ["-version"]

    def __str__(self):
        return f"{self.document_id} v{self.version} ({self.original_name or self.link or 'file'})"


class AdmDocumentCounter(models.Model):
    """Per doc_type and year counter to allocate running numbers safely."""

    doc_type = models.ForeignKey(AdmDocumentType, on_delete=models.CASCADE)
    company = models.ForeignKey(AdmCompany, on_delete=models.CASCADE)
    year = models.PositiveIntegerField()
    next_number = models.PositiveIntegerField(default=1)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "adm_document_counter"
        unique_together = ("doc_type", "company", "year")
        verbose_name = "Document Counter"
        verbose_name_plural = "Document Counters"

    def __str__(self):
        return f"{self.doc_type.code}-{self.company.code}-{self.year}: next={self.next_number}"


class AdmPaperCounter(models.Model):
    """Counter quản lý số hiệu cho giấy hành chính theo loại giấy/năm."""

    paper_type = models.ForeignKey(AdmPaperType, on_delete=models.CASCADE)
    year = models.PositiveIntegerField()
    next_number = models.PositiveIntegerField(default=1)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "adm_paper_counter"
        unique_together = ("paper_type", "year")
        verbose_name = "Paper Counter"
        verbose_name_plural = "Paper Counters"

    def __str__(self):
        return f"{self.paper_type.code if hasattr(self.paper_type, 'code') else self.paper_type}-{self.year}: next={self.next_number}"


class AdmAdministrativeDocumentHistory(models.Model):
    CHANGE_CREATED = "created"
    CHANGE_UPDATED = "updated"
    CHANGE_DELETED = "deleted"

    CHANGE_CHOICES = [
        (CHANGE_CREATED, "Created"),
        (CHANGE_UPDATED, "Updated"),
        (CHANGE_DELETED, "Deleted"),
    ]

    document = models.ForeignKey(
        AdmAdministrativeDocument,
        on_delete=models.CASCADE,
        related_name="history",
    )
    changed_at = models.DateTimeField(auto_now_add=True)
    changed_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True
    )
    change_type = models.CharField(max_length=20, choices=CHANGE_CHOICES)
    changes = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = "adm_administrative_document_history"
        verbose_name = "Administrative Document History"
        verbose_name_plural = "Administrative Document Histories"
        ordering = ["-changed_at"]

    def __str__(self):
        return f"{self.document_id} - {self.change_type} @ {self.changed_at}"


@receiver(post_delete, sender=AdmAdministrativeDocument)
def log_document_delete(sender, instance, **kwargs):
    try:
        AdmAdministrativeDocumentHistory.objects.create(
            document=instance,
            changed_by=getattr(instance, "updated_by", None)
            or getattr(instance, "created_by", None),
            change_type=AdmAdministrativeDocumentHistory.CHANGE_DELETED,
            changes={"last_known": instance._serialize_fields()},
        )
    except Exception:
        pass
