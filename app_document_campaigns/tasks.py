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


@shared_task(soft_time_limit=60, time_limit=90)
def send_campaign_shop_link(link_id, url, delivery_id=None):
    from django.core.mail import EmailMessage
    from django.db.models import F
    from urllib.parse import urlparse
    from app_document_campaigns.models import ShopEmailDelivery
    from app_document_campaigns.services.access_links import token_digest
    from app_document_campaigns.services.email_templates import campaign_email_config, render_campaign_email
    from app_document_campaigns.services.email_html import email_body_html

    if delivery_id is None:
        delivery_id = ShopEmailDelivery.objects.create(link_id=link_id).pk
    delivery = ShopEmailDelivery.objects.filter(pk=delivery_id, link_id=link_id)
    if not delivery.filter(status="queued").update(status="sending"):
        return {"status": "skipped", "delivery_id": delivery_id}
    try:
        link = ShopAccessLink.objects.select_related("campaign", "shop__manager_id__areaManager", "shop__manager_id__regionManager").get(pk=link_id)
        if token_digest(urlparse(url).path.strip("/").split("/")[-1]) != link.token_digest or not link.is_editable or link.campaign.status != Campaign.Status.ACTIVE or ShopSubmission.objects.filter(campaign=link.campaign, shop=link.shop).exists():
            delivery.update(status="skipped", message="Link không còn nhận phản hồi.", finished_at=timezone.now())
            return {"status": "skipped", "delivery_id": delivery_id}
        config = campaign_email_config(link.campaign)
        rendered = render_campaign_email(config, link.campaign, link.shop, url)
        delivery.update(
            to_email=rendered.to[0],
            cc_emails=rendered.cc,
            bcc_emails=rendered.bcc,
            area_email=rendered.area_email,
            area_manager_id=rendered.area_manager_id,
            subject=rendered.subject,
            template_version=config.template_version,
            attempt_count=F("attempt_count") + 1,
        )
        if settings.EMAIL_TRANSPORT == "power_automate":
            from app_document_campaigns.services.power_automate_email import dispatch_shop_email
            result = dispatch_shop_email(link, rendered, config.template_version, ShopEmailDelivery.objects.get(pk=delivery_id))
            delivery.update(status="sending", message="Power Automate đã nhận email; đang chờ kết quả gửi.")
            return {"status": "accepted", "link_id": link_id, "delivery_id": delivery_id, "provider_batch_id": result.provider_batch_id}
        if settings.EMAIL_TRANSPORT == "microsoft_graph":
            from app_document_campaigns.services.microsoft_graph_email import send_rendered_email
            result = send_rendered_email(rendered)
            delivery.update(
                status="sent",
                message="Microsoft Graph đã nhận yêu cầu gửi email.",
                finished_at=timezone.now(),
            )
            return {
                "status": "sent",
                "link_id": link_id,
                "delivery_id": delivery_id,
                "provider_message_id": result.request_id,
            }
        message = EmailMessage(
            subject=rendered.subject,
            body=email_body_html(rendered.body),
            from_email=rendered.from_email,
            to=rendered.to,
            cc=rendered.cc,
            bcc=rendered.bcc,
        )
        message.content_subtype = "html"
        if message.send(fail_silently=False) != 1:
            raise RuntimeError("Email chưa được gửi.")
        delivery.update(status="sent", message="Đã gửi email thành công.", finished_at=timezone.now())
        return {"status": "sent", "link_id": link_id, "delivery_id": delivery_id}
    except Exception:
        delivery.update(status="failed", message="Không gửi được email. Kiểm tra cấu hình và log gửi thư.", finished_at=timezone.now())
        raise


@shared_task(soft_time_limit=60, time_limit=90)
def send_area_manager_view_link(link_id, url):
    from urllib.parse import urlparse
    from django.core.mail import EmailMessage
    from django.core.validators import validate_email
    from app_document_campaigns.models import AreaManagerAccessLink
    from app_document_campaigns.services.access_links import token_digest
    from app_document_campaigns.services.email_templates import campaign_area_email_config, render_area_email

    link = AreaManagerAccessLink.objects.select_related("campaign", "area_manager").get(pk=link_id)
    try:
        supplied = urlparse(url).path.strip("/").split("/")[-1]
        if token_digest(supplied) != link.token_digest or link.revoked_at or link.is_expired:
            raise ValueError("Link QLKV không còn hiệu lực.")
        validate_email(link.allowed_email)
        confirmation_mode = link.stage == AreaManagerAccessLink.Stage.CONFIRMATION
        rendered = render_area_email(
            campaign_area_email_config(link.campaign), link.campaign, link.area_manager, url,
            confirmation_mode=confirmation_mode, expires_at=link.expires_at,
        )
        if settings.EMAIL_TRANSPORT == "power_automate":
            from app_document_campaigns.services.power_automate_email import dispatch_area_email
            config = campaign_area_email_config(link.campaign)
            result = dispatch_area_email(link, rendered, config.template_version)
            AreaManagerAccessLink.objects.filter(pk=link.pk).update(
                email_status=AreaManagerAccessLink.EmailStatus.QUEUED,
                email_message="Power Automate đã nhận email; đang chờ kết quả gửi.",
            )
            return {"status": "accepted", "link_id": link.pk, "provider_batch_id": result.provider_batch_id}
        if settings.EMAIL_TRANSPORT == "microsoft_graph":
            from app_document_campaigns.services.microsoft_graph_email import send_rendered_email
            result = send_rendered_email(rendered)
            AreaManagerAccessLink.objects.filter(pk=link.pk).update(
                email_status=AreaManagerAccessLink.EmailStatus.SENT,
                email_message="Microsoft Graph đã nhận yêu cầu gửi email QLKV.",
                emailed_at=timezone.now(),
            )
            return {"status": "sent", "link_id": link.pk, "provider_message_id": result.request_id}
        from app_document_campaigns.services.email_html import email_body_html
        message = EmailMessage(subject=rendered.subject, body=email_body_html(rendered.body), from_email=rendered.from_email,
                               to=rendered.to, cc=rendered.cc, bcc=rendered.bcc)
        message.content_subtype = "html"
        if message.send(fail_silently=False) != 1:
            raise RuntimeError("Email chưa được gửi.")
        AreaManagerAccessLink.objects.filter(pk=link.pk).update(
            email_status=AreaManagerAccessLink.EmailStatus.SENT,
            email_message="Đã gửi email QLKV thành công.",
            emailed_at=timezone.now(),
        )
        return {"status": "sent", "link_id": link.pk}
    except Exception:
        AreaManagerAccessLink.objects.filter(pk=link.pk).update(
            email_status=AreaManagerAccessLink.EmailStatus.FAILED,
            email_message="Không gửi được email QLKV. Kiểm tra cấu hình gửi thư.",
        )
        raise


@shared_task(soft_time_limit=300, time_limit=360)
def send_bulk_campaign_email_batches(items):
    """Send selected batches sequentially through the provider saved on each batch."""
    from email.utils import formataddr
    from django.core.mail import EmailMessage, get_connection
    from django.db.models import Count, F, Q
    from app_document_campaigns.models import (
        AreaManagerAccessLink,
        CampaignEmailBatch,
        CampaignEmailDelivery,
        ShopEmailDelivery,
    )
    from app_document_campaigns.services.power_automate_email import dispatch_email_chunk

    def finish_smtp_batch(batch, messages):
        now = timezone.now()
        CampaignEmailBatch.objects.filter(pk=batch.pk).update(
            status=CampaignEmailBatch.Status.DISPATCHING,
            submitted_at=now,
            provider_batch_id=f"smtp:{batch.pk}",
        )
        connection = get_connection()
        connection.open()
        try:
            for payload in messages:
                delivery = CampaignEmailDelivery.objects.get(pk=payload["message_id"], batch=batch)
                CampaignEmailDelivery.objects.filter(pk=delivery.pk).update(
                    status=CampaignEmailDelivery.Status.SUBMITTING,
                    attempt_count=F("attempt_count") + 1,
                )
                try:
                    sender = payload.get("from") or {}
                    from_email = formataddr((sender.get("name", ""), sender.get("address", "")))
                    body = payload.get("body") or {}
                    message = EmailMessage(
                        subject=payload.get("subject", ""),
                        body=body.get("content", ""),
                        from_email=from_email,
                        to=payload.get("to") or [],
                        cc=payload.get("cc") or [],
                        bcc=payload.get("bcc") or [],
                        connection=connection,
                    )
                    message.content_subtype = "html"
                    if connection.send_messages([message]) != 1:
                        raise RuntimeError("SMTP không xác nhận đã gửi email.")
                    sent_at = timezone.now()
                    CampaignEmailDelivery.objects.filter(pk=delivery.pk).update(
                        status=CampaignEmailDelivery.Status.SENT,
                        sent_at=sent_at,
                        failed_at=None,
                        error_code="",
                        error_message="",
                    )
                    if delivery.legacy_shop_delivery_id:
                        ShopEmailDelivery.objects.filter(pk=delivery.legacy_shop_delivery_id).update(
                            status="sent", message="Đã gửi email thành công qua SMTP.", finished_at=sent_at,
                        )
                    if delivery.area_access_link_id:
                        AreaManagerAccessLink.objects.filter(pk=delivery.area_access_link_id).update(
                            email_status=AreaManagerAccessLink.EmailStatus.SENT,
                            email_message="Đã gửi email QLKV thành công qua SMTP.",
                            emailed_at=sent_at,
                        )
                except Exception as exc:
                    failed_at = timezone.now()
                    CampaignEmailDelivery.objects.filter(pk=delivery.pk).update(
                        status=CampaignEmailDelivery.Status.FAILED,
                        failed_at=failed_at,
                        error_code="smtp_send_failed",
                        error_message=str(exc)[:500],
                    )
                    if delivery.legacy_shop_delivery_id:
                        ShopEmailDelivery.objects.filter(pk=delivery.legacy_shop_delivery_id).update(
                            status="failed", message="Không gửi được email qua SMTP.", finished_at=failed_at,
                        )
                    if delivery.area_access_link_id:
                        AreaManagerAccessLink.objects.filter(pk=delivery.area_access_link_id).update(
                            email_status=AreaManagerAccessLink.EmailStatus.FAILED,
                            email_message="Không gửi được email QLKV qua SMTP.",
                        )
        finally:
            connection.close()
        counts = batch.deliveries.aggregate(
            sent=Count("id", filter=Q(status=CampaignEmailDelivery.Status.SENT)),
            failed=Count("id", filter=Q(status=CampaignEmailDelivery.Status.FAILED)),
        )
        status = CampaignEmailBatch.Status.COMPLETED
        if counts["failed"]:
            status = (
                CampaignEmailBatch.Status.FAILED
                if counts["failed"] == batch.total_count
                else CampaignEmailBatch.Status.PARTIALLY_FAILED
            )
        CampaignEmailBatch.objects.filter(pk=batch.pk).update(
            status=status,
            sent_count=counts["sent"],
            failed_count=counts["failed"],
            completed_at=timezone.now(),
        )
        return counts

    results = []
    for item in items:
        batch_id = item.get("batch_id")
        messages = item.get("messages") or []
        try:
            batch = CampaignEmailBatch.objects.select_related("campaign").get(pk=batch_id)
            transport = item.get("transport") or batch.transport_provider
            if transport != batch.transport_provider:
                raise ValueError("Kênh gửi trong task không khớp batch.")
            if transport == CampaignEmailBatch.TransportProvider.SMTP:
                counts = finish_smtp_batch(batch, messages)
                batch.refresh_from_db(fields=["status"])
                results.append({"batch_id": str(batch.pk), "status": batch.status, **counts})
            elif transport == CampaignEmailBatch.TransportProvider.MICROSOFT_GRAPH:
                from app_document_campaigns.services.microsoft_graph_email import dispatch_email_batch
                counts = dispatch_email_batch(batch, messages)
                batch.refresh_from_db(fields=["status"])
                results.append({"batch_id": str(batch.pk), "status": batch.status, **counts})
            else:
                result = dispatch_email_chunk(batch, messages)
                results.append({"batch_id": str(batch.pk), "status": "accepted", "accepted": len(result.accepted_message_ids)})
        except Exception as exc:
            now = timezone.now()
            CampaignEmailBatch.objects.filter(pk=batch_id).update(
                status=CampaignEmailBatch.Status.FAILED,
                failed_count=len(messages),
                completed_at=now,
                last_error_code="submit_failed",
                last_error_message=str(exc)[:500],
            )
            CampaignEmailDelivery.objects.filter(batch_id=batch_id).exclude(
                status__in=[CampaignEmailDelivery.Status.ACCEPTED, CampaignEmailDelivery.Status.SENT]
            ).update(
                status=CampaignEmailDelivery.Status.FAILED,
                failed_at=now,
                error_code="submit_failed",
                error_message="Không gửi được batch qua kênh đã chọn.",
            )
            results.append({"batch_id": str(batch_id), "status": "failed"})
    return {"status": "processed", "batches": results}


@shared_task(soft_time_limit=540, time_limit=600)
def process_team_review_excel(job_id):
    from app_document_campaigns.models import TeamReviewExcelJob
    from app_document_campaigns.services.team_review_excel import build_workbook, import_workbook, MAX_FILE_SIZE

    if not TeamReviewExcelJob.objects.filter(pk=job_id, status="queued").update(status="running", progress=5, updated_at=timezone.now()):
        return {"status": "skipped"}
    job = TeamReviewExcelJob.objects.select_related("campaign", "requested_by").get(pk=job_id)
    def update(**fields):
        TeamReviewExcelJob.objects.filter(pk=job_id).update(updated_at=timezone.now(), **fields)
    try:
        user = job.requested_by
        if not user.is_active or not (user.is_superuser or user.groups.filter(name="admin").exists()):
            raise ValueError("Tài khoản không còn quyền admin.")
        if job.kind == "export":
            content, rows = build_workbook(job.campaign, lambda value: update(progress=max(5, value)))
            job.output_file.save(f"team-review-{job.campaign.code}-{job.pk}.xlsx", ContentFile(content), save=False)
            summary = {"rows": rows}
            update(output_file=job.output_file.name, status="succeeded", progress=100, summary=summary, message="Đã tạo file Team review.")
        else:
            with job.input_file.open("rb") as stream:
                content = stream.read(MAX_FILE_SIZE + 1)
            summary = import_workbook(job.campaign_id, user, content, lambda value: update(progress=max(5, value)))
            update(status="succeeded", progress=100, summary=summary, message=f"Đã cập nhật {summary['updated']} dòng review.")
        return {"status": "succeeded", "summary": summary}
    except Exception as exc:
        update(status="failed", message=f"Không hoàn tất: {str(exc)[:1500]}")
        return {"status": "failed"}


@shared_task(soft_time_limit=540, time_limit=600)
def process_area_confirmation_excel(job_id):
    from app_document_campaigns.models import AreaConfirmationExcelJob
    from app_document_campaigns.services.area_confirmation_excel import build_workbook, import_workbook, MAX_FILE_SIZE

    if not AreaConfirmationExcelJob.objects.filter(pk=job_id, status="queued").update(status="running", progress=5, updated_at=timezone.now()):
        return {"status": "skipped"}
    job = AreaConfirmationExcelJob.objects.select_related("campaign", "requested_by").get(pk=job_id)
    def update(**fields):
        AreaConfirmationExcelJob.objects.filter(pk=job_id).update(updated_at=timezone.now(), **fields)
    try:
        if job.kind == "export":
            content, rows = build_workbook(job.campaign, lambda value: update(progress=max(5, value)))
            job.output_file.save(f"qlkv-confirmation-{job.campaign.code}-{job.pk}.xlsx", ContentFile(content), save=False)
            summary = {"rows": rows}
            update(output_file=job.output_file.name, status="succeeded", progress=100, summary=summary, message="Đã tạo file xác nhận QLKV.")
        else:
            with job.input_file.open("rb") as stream:
                content = stream.read(MAX_FILE_SIZE + 1)
            summary = import_workbook(job.campaign_id, job.requested_by, content, lambda value: update(progress=max(5, value)))
            update(status="succeeded", progress=100, summary=summary, message=f"Đã cập nhật {summary['updated']} dòng xác nhận QLKV.")
        return {"status": "succeeded", "summary": summary}
    except Exception as exc:
        update(status="failed", message=f"Không hoàn tất: {str(exc)[:1500]}")
        return {"status": "failed"}


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
        from app_document_campaigns.models import CampaignImportSource, CampaignVersion

        if job.version.status == CampaignVersion.Status.PUBLISHED or job.version.campaign.status in (Campaign.Status.ACTIVE, Campaign.Status.CLOSED, Campaign.Status.CANCELLED):
            raise ValueError("Dữ liệu đã khóa; không thể truy xuất lại.")
        job.version.import_sources.filter(source_type=CampaignVersion.SourceType.EXCEL).update(status=CampaignImportSource.Status.STAGED)
        CampaignVersion.objects.filter(pk=job.version_id, status=CampaignVersion.Status.VALIDATED).update(status=CampaignVersion.Status.DRAFT)

        result = stage_monthly_sql_sources(
            version=job.version,
            created_by=job.created_by,
            progress_callback=record_progress,
            **({"source_names": job.summary["source_names"]} if "source_names" in job.summary else {}),
        )
        if job.summary.get("prepare_excel"):
            from app_document_campaigns.services.excel_exports import build_cleaning_workbook
            CampaignImportJob.objects.filter(pk=job_id).update(summary={**result, "message": "Đang chuẩn bị file Excel để review."})
            workbook = build_cleaning_workbook(job.version)
            filename = f"error-campaign-{slugify(job.version.campaign.code)}-{job.pk}.xlsx"
            job.output_file.save(filename, ContentFile(workbook.getvalue()), save=False)
            CampaignImportJob.objects.filter(pk=job_id).update(output_file=job.output_file.name, output_filename=filename)
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
            error_message="Không thể truy xuất dữ liệu. Vui lòng kiểm tra log tiến trình xử lý và chạy lại.",
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
            error_message="Không thể tạo file Excel. Vui lòng kiểm tra dữ liệu staging và log tiến trình xử lý.",
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
            error_message="Không thể đối chiếu file Excel. Vui lòng kiểm tra log tiến trình xử lý và thử lại.",
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
