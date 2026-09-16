from celery import shared_task
from celery.exceptions import SoftTimeLimitExceeded
from django.conf import settings
from django.core.files.base import ContentFile
from django.core.mail import send_mail
from django.utils import timezone
from django.utils.text import slugify

from app_document_campaigns.models import (
    Campaign,
    CampaignImportJob,
    ShopAccessLink,
    ShopSubmission,
)


@shared_task
def campaign_health_ping(campaign_id):
    """Small foundation task used to verify Celery app discovery."""
    return Campaign.objects.filter(pk=campaign_id).values_list("status", flat=True).first()


@shared_task(bind=True, max_retries=3, default_retry_delay=120)
def process_shop_submission(self, submission_id):
    """Send post-submit notifications outside the HTTP transaction.

    Snapshot and aggregate metric generation intentionally stays in DEC-10;
    creating a snapshot for every Shop submit would make that data too noisy.
    """
    try:
        submission = ShopSubmission.objects.select_related("campaign", "shop").get(
            pk=submission_id
        )
    except ShopSubmission.DoesNotExist:
        return {"status": "missing", "submission_id": submission_id}

    try:
        recipient = ShopAccessLink.objects.values_list("allowed_email", flat=True).get(
            campaign=submission.campaign,
            shop=submission.shop,
        )
        send_mail(
            subject=f"Đã nhận phản hồi {submission.campaign.code}",
            message=(
                f"Hệ thống đã nhận {submission.response_count} phản hồi của "
                f"{submission.shop.shop_name} lúc "
                f"{submission.submitted_at:%d/%m/%Y %H:%M}."
            ),
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[recipient],
            fail_silently=False,
        )
    except ShopAccessLink.DoesNotExist:
        return {"status": "missing_access_link", "submission_id": submission_id}
    except Exception as exc:
        raise self.retry(exc=exc)

    return {"status": "sent", "submission_id": submission_id, "recipient": recipient}


@shared_task(soft_time_limit=900, time_limit=960)
def run_campaign_sql_import(job_id):
    now = timezone.now()
    claimed = CampaignImportJob.objects.filter(
        pk=job_id,
        status=CampaignImportJob.Status.QUEUED,
        job_type=CampaignImportJob.JobType.SQL_STAGE,
    ).update(
        status=CampaignImportJob.Status.RUNNING,
        started_at=now,
        error_message="",
    )
    if not claimed:
        return {"status": "skipped", "job_id": job_id}

    job = CampaignImportJob.objects.select_related("version", "created_by").get(pk=job_id)

    def record_progress(source_name, step, summary):
        current_summary = dict(
            CampaignImportJob.objects.filter(pk=job_id).values_list("summary", flat=True).get()
            or {}
        )
        current_summary[source_name] = summary
        CampaignImportJob.objects.filter(pk=job_id).update(
            current_step=step,
            summary=current_summary,
        )

    try:
        from app_document_campaigns.services.sql_sources import stage_monthly_sql_sources

        result = stage_monthly_sql_sources(
            version=job.version,
            created_by=job.created_by,
            progress_callback=record_progress,
        )
    except SoftTimeLimitExceeded:
        CampaignImportJob.objects.filter(pk=job_id).update(
            status=CampaignImportJob.Status.FAILED,
            error_message="Job vượt quá thời gian xử lý 15 phút.",
            finished_at=timezone.now(),
        )
        raise
    except Exception:
        CampaignImportJob.objects.filter(pk=job_id).update(
            status=CampaignImportJob.Status.FAILED,
            error_message="Không thể truy xuất dữ liệu. Vui lòng kiểm tra log worker và chạy lại.",
            finished_at=timezone.now(),
        )
        raise

    CampaignImportJob.objects.filter(pk=job_id).update(
        status=CampaignImportJob.Status.SUCCEEDED,
        current_step=job.total_steps,
        summary=result,
        finished_at=timezone.now(),
    )
    return {"status": "succeeded", "job_id": job_id, "summary": result}


@shared_task(soft_time_limit=300, time_limit=360)
def run_campaign_excel_export(job_id):
    claimed = CampaignImportJob.objects.filter(
        pk=job_id,
        status=CampaignImportJob.Status.QUEUED,
        job_type=CampaignImportJob.JobType.EXCEL_EXPORT,
    ).update(status=CampaignImportJob.Status.RUNNING, started_at=timezone.now(), error_message="")
    if not claimed:
        return {"status": "skipped", "job_id": job_id}
    job = CampaignImportJob.objects.select_related("version__campaign").get(pk=job_id)
    try:
        from app_document_campaigns.services.excel_exports import build_cleaning_workbook

        reviewed = job.summary.get("export_kind") == "reviewed"
        if reviewed:
            source = job.version.import_sources.get(source_type="excel", name="team-cleaning-excel")
            if source.source_checksum != job.summary.get("source_checksum"):
                raise ValueError("File review đã thay đổi sau khi yêu cầu xuất; hãy tạo lại file.")
        workbook = build_cleaning_workbook(job.version, reviewed=True) if reviewed else build_cleaning_workbook(job.version)
        filename = (
            f"error-campaign-{slugify(job.version.campaign.code)}-"
            f"v{job.version.version_number}{'-team-reviewed' if reviewed else ''}.xlsx"
        )
        job.output_file.save(filename, ContentFile(workbook.getvalue()), save=False)
        job.output_filename = filename
        job.status = CampaignImportJob.Status.SUCCEEDED
        job.current_step = job.total_steps
        job.finished_at = timezone.now()
        job.save(
            update_fields=[
                "output_file",
                "output_filename",
                "status",
                "current_step",
                "finished_at",
            ]
        )
    except Exception:
        CampaignImportJob.objects.filter(pk=job_id).update(
            status=CampaignImportJob.Status.FAILED,
            error_message="Không thể tạo file Excel. Vui lòng kiểm tra dữ liệu staging và log worker.",
            finished_at=timezone.now(),
        )
        raise
    return {"status": "succeeded", "job_id": job_id, "filename": filename}


@shared_task(soft_time_limit=600, time_limit=660)
def run_campaign_excel_import(job_id):
    claimed = CampaignImportJob.objects.filter(
        pk=job_id,
        status=CampaignImportJob.Status.QUEUED,
        job_type=CampaignImportJob.JobType.EXCEL_IMPORT,
    ).update(status=CampaignImportJob.Status.RUNNING, started_at=timezone.now(), error_message="")
    if not claimed:
        return {"status": "skipped", "job_id": job_id}
    job = CampaignImportJob.objects.select_related("version__campaign", "created_by").get(pk=job_id)

    def record_progress(message, step):
        CampaignImportJob.objects.filter(pk=job_id).update(
            current_step=step,
            summary={"message": message},
        )

    try:
        from app_document_campaigns.services.excel_imports import import_cleaning_workbook
        from app_document_campaigns.services.imports import CampaignImportError

        with job.input_file.open("rb") as uploaded_file:
            source, summary = import_cleaning_workbook(
                version=job.version,
                created_by=job.created_by,
                uploaded_file=uploaded_file,
                progress_callback=record_progress,
            )
    except CampaignImportError as exc:
        CampaignImportJob.objects.filter(pk=job_id).update(
            status=CampaignImportJob.Status.FAILED,
            error_message=str(exc),
            finished_at=timezone.now(),
        )
        return {"status": "failed", "job_id": job_id, "error": str(exc)}
    except Exception:
        CampaignImportJob.objects.filter(pk=job_id).update(
            status=CampaignImportJob.Status.FAILED,
            error_message="Không thể đối chiếu file Excel. Vui lòng kiểm tra log worker và thử lại.",
            finished_at=timezone.now(),
        )
        raise

    CampaignImportJob.objects.filter(pk=job_id).update(
        status=CampaignImportJob.Status.SUCCEEDED,
        current_step=job.total_steps,
        summary=summary,
        finished_at=timezone.now(),
    )
    return {"status": "succeeded", "job_id": job_id, "source_id": source.pk, "summary": summary}
