from datetime import date

from django.contrib.auth.models import User
from django.db import models
from django.db.models.signals import post_delete
from django.dispatch import receiver
from app_documents.models import Shop


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
    expiry_date = models.DateField(blank=True, null=True)
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
        """Auto increment per document type + generate official number and log history."""
        is_create = self.pk is None
        previous = None
        if not is_create:
            try:
                previous = AdmAdministrativeDocument.objects.get(pk=self.pk)
            except AdmAdministrativeDocument.DoesNotExist:
                previous = None

        if not self.running_number:
            current_year = date.today().year
            last_doc = (
                AdmAdministrativeDocument.objects.filter(
                    doc_type=self.doc_type, created_at__year=current_year
                )
                .order_by("-running_number")
                .first()
            )
            self.running_number = last_doc.running_number + 1 if last_doc else 1

        year_now = date.today().year
        company_code = self.issuing_company.code if self.issuing_company else "UNK"
        signer_code = self.signer_role.code if self.signer_role else "NA"
        doc_type_code = self.doc_type.code if self.doc_type else "NA"
        self.document_number_full = (
            f"{self.running_number:03d}-{year_now}-{doc_type_code}-{company_code}/{signer_code}"
        )

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
    requested_department = models.ForeignKey(Shop, on_delete=models.PROTECT)
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

    class Meta:
        db_table = "adm_paper_document"
        verbose_name = "Paper Document"
        verbose_name_plural = "Paper Documents"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.paper_type} - {self.summary}"


class AdmDocumentCounter(models.Model):
    """Per doc_type and year counter to allocate running numbers safely."""

    doc_type = models.ForeignKey(AdmDocumentType, on_delete=models.CASCADE)
    year = models.PositiveIntegerField()
    next_number = models.PositiveIntegerField(default=1)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "adm_document_counter"
        unique_together = ("doc_type", "year")
        verbose_name = "Document Counter"
        verbose_name_plural = "Document Counters"

    def __str__(self):
        return f"{self.doc_type.code}-{self.year}: next={self.next_number}"


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
