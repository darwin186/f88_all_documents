from __future__ import annotations

from datetime import datetime
import mimetypes
from pathlib import Path

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import FileResponse, HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from app_document_campaigns.models import MediaArchiveJob
from app_document_campaigns.services.media_archive import (
    MediaPathError,
    breadcrumbs,
    directory_entries,
    directory_tree,
    normalize_media_path,
    resolve_media_source,
)
from app_document_campaigns.tasks import process_media_archive


def _is_admin(user):
    return user.is_superuser or user.groups.filter(name="admin").exists()


def _admin_denied(request):
    if not _is_admin(request.user):
        return HttpResponse("Chỉ Admin được quản lý lưu trữ media.", status=403)
    return None


def enqueue_archive_job(job):
    try:
        if settings.FILE_JOBS_RUN_ON_WEB:
            process_media_archive.apply(args=[job.pk], throw=False)
        else:
            result = process_media_archive.delay(job.pk)
            MediaArchiveJob.objects.filter(pk=job.pk).update(celery_task_id=result.id)
    except Exception as exc:
        MediaArchiveJob.objects.filter(pk=job.pk).update(
            status=MediaArchiveJob.Status.FAILED,
            error_message=f"Không đưa được job lưu trữ vào hàng đợi: {str(exc)[:1000]}",
            finished_at=timezone.now(),
        )
    return MediaArchiveJob.objects.get(pk=job.pk)


@login_required
def media_storage_browser(request):
    denied = _admin_denied(request)
    if denied:
        return denied
    requested_path = request.GET.get("path", "")
    try:
        current = resolve_media_source(requested_path)
        if not current.is_dir:
            parent = current.absolute_path.parent.relative_to(Path(settings.MEDIA_ROOT).resolve()).as_posix()
            current = resolve_media_source("" if parent == "." else parent)
        entries = directory_entries(current.relative_path)
    except (MediaPathError, ValueError):
        messages.error(request, "Đường dẫn media không hợp lệ hoặc không còn tồn tại.")
        return redirect("media_storage_browser")

    paths = [entry["path"] for entry in entries]
    latest_by_path = {}
    if paths:
        for job in MediaArchiveJob.objects.filter(source_path__in=paths).order_by("-created_at"):
            latest_by_path.setdefault(job.source_path, job)
    for entry in entries:
        entry["latest_job"] = latest_by_path.get(entry["path"])
        if entry["modified_at"]:
            entry["modified_at"] = datetime.fromtimestamp(entry["modified_at"], tz=timezone.get_current_timezone())

    return render(request, "app_document_campaigns/media_storage_browser.html", {
        "tree": directory_tree(current_path=current.relative_path),
        "entries": entries,
        "current_path": current.relative_path,
        "breadcrumbs": breadcrumbs(current.relative_path),
        "recent_jobs": MediaArchiveJob.objects.select_related("requested_by")[:20],
        "storage_enabled": bool(getattr(settings, "MICROSOFT_GRAPH_STORAGE_ENABLED", False)),
        "storage_destination": getattr(settings, "MICROSOFT_GRAPH_STORAGE_SITE_URL", ""),
    })


@login_required
def media_file_preview(request):
    denied = _admin_denied(request)
    if denied:
        return denied
    try:
        source = resolve_media_source(request.GET.get("path", ""))
        if source.is_dir:
            raise MediaPathError("Chỉ có thể mở file.")
    except MediaPathError as exc:
        return HttpResponse(str(exc), status=404)
    content_type = mimetypes.guess_type(source.absolute_path.name)[0] or "application/octet-stream"
    return FileResponse(
        source.absolute_path.open("rb"),
        content_type=content_type,
        as_attachment=False,
        filename=source.absolute_path.name,
    )


@login_required
@require_POST
def queue_media_archive(request):
    denied = _admin_denied(request)
    if denied:
        return denied
    try:
        source = resolve_media_source(request.POST.get("source_path", ""))
    except MediaPathError as exc:
        messages.error(request, str(exc))
        return redirect("media_storage_browser")
    active = MediaArchiveJob.objects.filter(
        source_path=source.relative_path,
        status__in=[MediaArchiveJob.Status.QUEUED, MediaArchiveJob.Status.RUNNING],
    ).first()
    if active:
        messages.warning(request, "File hoặc thư mục này đang được đồng bộ.")
    else:
        job = MediaArchiveJob.objects.create(
            source_path=source.relative_path,
            source_kind=MediaArchiveJob.SourceKind.FOLDER if source.is_dir else MediaArchiveJob.SourceKind.FILE,
            requested_by=request.user,
        )
        job = enqueue_archive_job(job)
        if job.status == MediaArchiveJob.Status.FAILED:
            messages.error(request, job.error_message or "Không thể đồng bộ SharePoint.")
        elif job.status == MediaArchiveJob.Status.SUCCEEDED:
            messages.success(request, "Đã lưu trữ lên SharePoint.")
        else:
            messages.success(request, "Đã đưa yêu cầu lưu trữ vào hàng đợi.")
    try:
        return_path = normalize_media_path(request.POST.get("return_path", ""))
    except MediaPathError:
        return_path = ""
    url = reverse("media_storage_browser")
    return redirect(f"{url}?path={return_path}" if return_path else url)


@login_required
def media_archive_job_status(request, job_id):
    denied = _admin_denied(request)
    if denied:
        return denied
    try:
        job = MediaArchiveJob.objects.get(pk=job_id)
    except MediaArchiveJob.DoesNotExist:
        return JsonResponse({"ok": False, "error": "Job không tồn tại."}, status=404)
    return JsonResponse({
        "ok": True,
        "id": job.pk,
        "status": job.status,
        "status_label": job.get_status_display(),
        "total_files": job.total_files,
        "archived_files": job.archived_files,
        "failed_files": job.failed_files,
        "error": job.error_message,
        "remote_url": job.remote_url,
    })
