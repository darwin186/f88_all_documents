import logging
import mimetypes
import posixpath
from pathlib import PurePosixPath

from django.contrib.auth.decorators import login_required
from django.core.files.storage import default_storage
from django.http import FileResponse, Http404
from django.views.decorators.http import require_safe

from .access import has_admin_docs_access
from .models import AdmAdministrativeDocument, AdmDocumentAttachment


logger = logging.getLogger("media_diagnostics")


def _safe_storage_name(relative_path):
    normalized = posixpath.normpath((relative_path or "").replace("\\", "/"))
    path = PurePosixPath(normalized)
    if (
        not normalized
        or normalized in {".", ".."}
        or path.is_absolute()
        or ".." in path.parts
        or "\x00" in normalized
    ):
        raise Http404
    return f"admindocuments/files/{normalized}"


def _file_is_registered(storage_name):
    attachment_qs = AdmDocumentAttachment.objects.filter(file=storage_name)
    if attachment_qs.exists():
        return attachment_qs.filter(is_deleted=False).exists()
    return AdmAdministrativeDocument.objects.filter(attachment=storage_name).exists()


@login_required
@require_safe
def protected_admindocument_file(request, relative_path):
    storage_name = _safe_storage_name(relative_path)
    if not has_admin_docs_access(request.user):
        logger.warning(
            "ADMINDOCUMENT_MEDIA_DENIED user_id=%r storage_name=%r",
            request.user.pk,
            storage_name,
        )
        raise Http404
    if not _file_is_registered(storage_name):
        logger.warning(
            "ADMINDOCUMENT_MEDIA_UNREGISTERED user_id=%r storage_name=%r",
            request.user.pk,
            storage_name,
        )
        raise Http404
    try:
        file_handle = default_storage.open(storage_name, "rb")
    except (FileNotFoundError, OSError):
        raise Http404

    content_type, _ = mimetypes.guess_type(storage_name)
    response = FileResponse(
        file_handle,
        as_attachment=False,
        filename=PurePosixPath(storage_name).name,
        content_type=content_type or "application/octet-stream",
    )
    response["Cache-Control"] = "private, no-store"
    response["X-Content-Type-Options"] = "nosniff"
    return response
