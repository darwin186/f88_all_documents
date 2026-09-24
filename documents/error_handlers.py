import logging
import os
import unicodedata
from urllib.parse import unquote

from django.conf import settings
from django.core.files.storage import default_storage
from django.shortcuts import render


logger = logging.getLogger("media_diagnostics")


def _safe_media_candidate(relative_path):
    media_root = os.path.realpath(str(settings.MEDIA_ROOT))
    candidate_path = os.path.realpath(os.path.join(media_root, relative_path))
    try:
        is_safe = os.path.commonpath((media_root, candidate_path)) == media_root
    except ValueError:
        is_safe = False
    return media_root, candidate_path, is_safe


def _log_admindocument_media_404(request):
    media_prefix = f"/{settings.MEDIA_URL.strip('/')}" + "/"
    request_path = unquote(request.path)
    if not request_path.startswith(f"{media_prefix}admindocuments/"):
        return False

    relative_path = request_path[len(media_prefix):].lstrip("/")
    media_root, candidate_path, path_is_safe = _safe_media_candidate(relative_path)
    diagnostics = {
        "exists": False,
        "is_file": False,
        "readable": False,
        "parent_exists": False,
        "storage_exists": False,
        "nfc_exists": False,
        "nfd_exists": False,
    }

    if path_is_safe:
        diagnostics.update(
            exists=os.path.exists(candidate_path),
            is_file=os.path.isfile(candidate_path),
            readable=os.access(candidate_path, os.R_OK),
            parent_exists=os.path.isdir(os.path.dirname(candidate_path)),
            nfc_exists=os.path.exists(unicodedata.normalize("NFC", candidate_path)),
            nfd_exists=os.path.exists(unicodedata.normalize("NFD", candidate_path)),
        )
        try:
            diagnostics["storage_exists"] = default_storage.exists(relative_path)
        except Exception as exc:  # Diagnostics must never replace the original 404.
            diagnostics["storage_error"] = f"{type(exc).__name__}: {exc}"

    user_id = None
    if getattr(request, "user", None) is not None and request.user.is_authenticated:
        user_id = request.user.pk
    raw_uri = (
        request.META.get("RAW_URI")
        or request.META.get("REQUEST_URI")
        or request.get_full_path()
    ).split("?", 1)[0]

    logger.error(
        "ADMINDOCUMENT_MEDIA_404 method=%s path=%r raw_uri=%r user_id=%r "
        "media_root=%r relative_path=%r candidate_path=%r path_safe=%s "
        "exists=%s is_file=%s readable=%s parent_exists=%s "
        "storage_exists=%s nfc_exists=%s nfd_exists=%s storage_error=%r",
        request.method,
        request.path,
        raw_uri,
        user_id,
        media_root,
        relative_path,
        candidate_path,
        path_is_safe,
        diagnostics["exists"],
        diagnostics["is_file"],
        diagnostics["readable"],
        diagnostics["parent_exists"],
        diagnostics["storage_exists"],
        diagnostics["nfc_exists"],
        diagnostics["nfd_exists"],
        diagnostics.get("storage_error"),
    )
    return True


def handle_404(request, exception):
    is_admindocument_media = _log_admindocument_media_404(request)
    if not is_admindocument_media:
        logger.warning(
            "HTTP_404 method=%s path=%r user_id=%r",
            request.method,
            request.path,
            request.user.pk
            if getattr(request, "user", None) is not None
            and request.user.is_authenticated
            else None,
        )
    return render(
        request,
        "404.html",
        {"is_admindocument_media_missing": is_admindocument_media},
        status=404,
    )
