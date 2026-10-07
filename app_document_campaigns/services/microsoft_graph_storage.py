from __future__ import annotations

import logging
import random
import threading
import time
import uuid
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import BinaryIO
from urllib.parse import quote, unquote, urlparse

import requests
from django.conf import settings


logger = logging.getLogger(__name__)
GRAPH_ROOT = "https://graph.microsoft.com/v1.0"
RETRYABLE_STATUSES = {429, 502, 503, 504}
UPLOAD_SESSION_THRESHOLD = 10 * 1024 * 1024
UPLOAD_CHUNK_SIZE = 32 * 320 * 1024


class MicrosoftGraphStorageError(RuntimeError):
    def __init__(self, message, *, code="graph_storage_error", retryable=False, http_status=None):
        super().__init__(message)
        self.code = code
        self.retryable = retryable
        self.http_status = http_status


class MicrosoftGraphStorageConfigurationError(MicrosoftGraphStorageError):
    pass


def _configured_root_folder(site_url, explicit_folder):
    if explicit_folder:
        return explicit_folder
    parsed = urlparse(site_url)
    parts = [unquote(value) for value in parsed.path.split("/") if value]
    for index, value in enumerate(parts):
        if value.casefold() in ("shared documents", "documents"):
            inferred = "/".join(parts[index + 1 :])
            if inferred:
                return inferred
            break
    return "DocumentArchive"


@dataclass(frozen=True)
class GraphStorageConfig:
    enabled: bool
    tenant_id: str
    client_id: str
    client_secret: str
    site_url: str
    drive_id: str = ""
    root_folder: str = "DocumentArchive"
    connect_timeout: float = 10.0
    read_timeout: float = 60.0
    max_retries: int = 3

    @classmethod
    def from_settings(cls):
        site_url = getattr(settings, "MICROSOFT_GRAPH_STORAGE_SITE_URL", "")
        root_folder = _configured_root_folder(
            site_url,
            getattr(settings, "MICROSOFT_GRAPH_STORAGE_ROOT_FOLDER", ""),
        )
        return cls(
            enabled=bool(getattr(settings, "MICROSOFT_GRAPH_STORAGE_ENABLED", False)),
            tenant_id=getattr(settings, "MICROSOFT_GRAPH_STORAGE_TENANT_ID", ""),
            client_id=getattr(settings, "MICROSOFT_GRAPH_STORAGE_CLIENT_ID", ""),
            client_secret=getattr(settings, "MICROSOFT_GRAPH_STORAGE_CLIENT_SECRET", ""),
            site_url=site_url,
            drive_id=getattr(settings, "MICROSOFT_GRAPH_STORAGE_DRIVE_ID", ""),
            root_folder=root_folder,
            connect_timeout=getattr(settings, "MICROSOFT_GRAPH_CONNECT_TIMEOUT", 10.0),
            read_timeout=getattr(settings, "MICROSOFT_GRAPH_STORAGE_READ_TIMEOUT", 60.0),
            max_retries=getattr(settings, "MICROSOFT_GRAPH_STORAGE_MAX_RETRIES", 3),
        )


@dataclass(frozen=True)
class ArchiveResult:
    stored: bool
    reason: str = ""
    item_id: str = ""
    drive_id: str = ""
    name: str = ""
    path: str = ""
    web_url: str = ""
    e_tag: str = ""
    size: int = 0


def _response_error(response):
    try:
        payload = response.json()
        error = payload.get("error") or {}
        return error.get("code") or "graph_error", error.get("message") or "Microsoft Graph từ chối yêu cầu."
    except (TypeError, ValueError):
        return "graph_error", "Microsoft Graph trả phản hồi không hợp lệ."


def _file_bytes(content: bytes | bytearray | memoryview | BinaryIO) -> bytes:
    if isinstance(content, bytes):
        return content
    if isinstance(content, (bytearray, memoryview)):
        return bytes(content)
    if hasattr(content, "read"):
        value = content.read()
        if isinstance(value, str):
            return value.encode("utf-8")
        if isinstance(value, (bytes, bytearray, memoryview)):
            return bytes(value)
    raise TypeError("content phải là bytes hoặc file-like object trả về bytes.")


def _path_parts(value: str, *, allow_empty=False):
    normalized = str(value or "").replace("\\", "/").strip("/")
    if not normalized and allow_empty:
        return []
    parts = list(PurePosixPath(normalized).parts)
    invalid_chars = set('"*:<>?|')
    if not parts or any(
        part in ("", ".", "..")
        or part.endswith(".")
        or any(char in invalid_chars for char in part)
        for part in parts
    ):
        raise ValueError("Đường dẫn lưu trữ chứa tên thư mục hoặc tên file không hợp lệ.")
    return parts


class MicrosoftGraphArchiveStorage:
    """Optional archive adapter for a SharePoint/OneDrive for Business drive.

    Calling ``archive(..., requested=False)`` is always a no-op. When requested
    is true, a disabled adapter also returns a skipped result. Once enabled,
    configuration or transport failures are raised so the calling workflow can
    record and retry the failed archive operation instead of silently losing it.
    """

    def __init__(self, config: GraphStorageConfig | None = None, *, session=None):
        self.config = config or GraphStorageConfig.from_settings()
        self.session = session or requests.Session()
        self._lock = threading.Lock()
        self._token = ""
        self._token_expires_at = 0.0
        self._site_id = ""
        self._drive_id = self.config.drive_id

    @property
    def enabled(self):
        return self.config.enabled

    def archive(
        self,
        content: bytes | bytearray | memoryview | BinaryIO,
        *,
        filename: str,
        folder: str = "",
        content_type: str = "application/octet-stream",
        requested: bool = True,
    ) -> ArchiveResult:
        if not requested:
            return ArchiveResult(stored=False, reason="not_requested")
        if not self.enabled:
            return ArchiveResult(stored=False, reason="disabled")
        self._validate_configuration()
        filename_parts = _path_parts(filename)
        if len(filename_parts) != 1:
            raise ValueError("filename chỉ được chứa tên file; dùng folder cho đường dẫn thư mục.")
        root_parts = _path_parts(self.config.root_folder, allow_empty=True)
        folder_parts = _path_parts(folder, allow_empty=True)
        data = _file_bytes(content)
        drive_id = self._resolve_drive_id()
        parent_id = self._ensure_folders(drive_id, root_parts + folder_parts)
        if len(data) > UPLOAD_SESSION_THRESHOLD:
            payload = self._upload_large(drive_id, parent_id, filename_parts[0], data)
        else:
            payload = self._upload_small(
                drive_id, parent_id, filename_parts[0], data, content_type=content_type
            )
        stored_path = "/".join(root_parts + folder_parts + filename_parts)
        return ArchiveResult(
            stored=True,
            item_id=payload.get("id", ""),
            drive_id=drive_id,
            name=payload.get("name", filename_parts[0]),
            path=stored_path,
            web_url=payload.get("webUrl", ""),
            e_tag=payload.get("eTag", ""),
            size=int(payload.get("size", len(data))),
        )

    def ensure_folder(self, folder: str, *, requested: bool = True) -> ArchiveResult:
        if not requested:
            return ArchiveResult(stored=False, reason="not_requested")
        if not self.enabled:
            return ArchiveResult(stored=False, reason="disabled")
        self._validate_configuration()
        root_parts = _path_parts(self.config.root_folder, allow_empty=True)
        folder_parts = _path_parts(folder, allow_empty=True)
        drive_id = self._resolve_drive_id()
        item_id = self._ensure_folders(drive_id, root_parts + folder_parts)
        payload = self._request(
            "GET",
            f"{GRAPH_ROOT}/drives/{quote(drive_id, safe='')}/items/{quote(item_id, safe='')}"
            "?$select=id,name,webUrl,eTag",
            expected={200},
        ).json()
        stored_path = "/".join(root_parts + folder_parts)
        return ArchiveResult(
            stored=True,
            item_id=payload.get("id", item_id),
            drive_id=drive_id,
            name=payload.get("name", folder_parts[-1] if folder_parts else ""),
            path=stored_path,
            web_url=payload.get("webUrl", ""),
            e_tag=payload.get("eTag", ""),
        )

    def _validate_configuration(self):
        missing = [
            name
            for name, value in (
                ("MS_SP_TENANT_ID", self.config.tenant_id),
                ("MS_SP_APPLICATION_ID", self.config.client_id),
                ("MS_SP_VALUE", self.config.client_secret),
            )
            if not value
        ]
        if not self.config.drive_id and not self.config.site_url:
            missing.append("MS_SP_SITE_URL hoặc MS_SP_DRIVE_ID")
        if missing:
            raise MicrosoftGraphStorageConfigurationError(
                f"Thiếu cấu hình lưu trữ Microsoft Graph: {', '.join(missing)}.",
                code="missing_configuration",
            )

    def _access_token(self, *, force_refresh=False):
        now = time.monotonic()
        if not force_refresh and self._token and now < self._token_expires_at - 60:
            return self._token
        with self._lock:
            now = time.monotonic()
            if not force_refresh and self._token and now < self._token_expires_at - 60:
                return self._token
            request_id = str(uuid.uuid4())
            try:
                response = self.session.post(
                    f"https://login.microsoftonline.com/{quote(self.config.tenant_id, safe='')}/oauth2/v2.0/token",
                    data={
                        "client_id": self.config.client_id,
                        "client_secret": self.config.client_secret,
                        "scope": "https://graph.microsoft.com/.default",
                        "grant_type": "client_credentials",
                    },
                    headers={"Accept": "application/json", "client-request-id": request_id},
                    timeout=(self.config.connect_timeout, self.config.read_timeout),
                )
            except requests.RequestException as exc:
                raise MicrosoftGraphStorageError(
                    "Không kết nối được Microsoft identity token endpoint.",
                    code="token_connection_error",
                    retryable=True,
                ) from exc
            if response.status_code != 200:
                raise MicrosoftGraphStorageError(
                    f"Microsoft identity từ chối thông tin ứng dụng (HTTP {response.status_code}).",
                    code="token_rejected",
                    retryable=response.status_code in RETRYABLE_STATUSES,
                    http_status=response.status_code,
                )
            try:
                payload = response.json()
                self._token = payload["access_token"]
                expires_in = max(120, int(payload.get("expires_in", 3600)))
            except (KeyError, TypeError, ValueError) as exc:
                raise MicrosoftGraphStorageError(
                    "Microsoft identity trả token không hợp lệ.", code="invalid_token_response"
                ) from exc
            self._token_expires_at = time.monotonic() + expires_in
            return self._token

    def _request(self, method, url, *, expected, retry_auth=True, **kwargs):
        provided_headers = dict(kwargs.pop("headers", {}) or {})
        for attempt in range(self.config.max_retries + 1):
            request_id = str(uuid.uuid4())
            headers = dict(provided_headers)
            headers.update({
                "Authorization": f"Bearer {self._access_token()}",
                "Accept": "application/json",
                "client-request-id": request_id,
                "return-client-request-id": "true",
            })
            try:
                response = self.session.request(
                    method,
                    url,
                    headers=headers,
                    timeout=(self.config.connect_timeout, self.config.read_timeout),
                    **kwargs,
                )
            except (requests.Timeout, requests.ConnectionError) as exc:
                if attempt >= self.config.max_retries:
                    raise MicrosoftGraphStorageError(
                        "Không kết nối được Microsoft Graph sau nhiều lần thử.",
                        code="graph_connection_error",
                        retryable=True,
                    ) from exc
                self._backoff(attempt, None)
                continue
            if response.status_code in expected:
                return response
            if response.status_code == 401 and retry_auth:
                self._access_token(force_refresh=True)
                return self._request(
                    method,
                    url,
                    expected=expected,
                    retry_auth=False,
                    headers=provided_headers,
                    **kwargs,
                )
            if response.status_code in RETRYABLE_STATUSES and attempt < self.config.max_retries:
                self._backoff(attempt, response)
                continue
            code, message = _response_error(response)
            raise MicrosoftGraphStorageError(
                f"Microsoft Graph từ chối thao tác lưu trữ: {message}",
                code=code,
                retryable=response.status_code in RETRYABLE_STATUSES,
                http_status=response.status_code,
            )
        raise AssertionError("unreachable")

    @staticmethod
    def _backoff(attempt, response):
        retry_after = response.headers.get("Retry-After") if response is not None else None
        try:
            delay = min(30.0, float(retry_after)) if retry_after else None
        except (TypeError, ValueError):
            delay = None
        time.sleep(delay if delay is not None else min(8.0, (2**attempt) + random.random()))

    def _resolve_site_id(self):
        if self._site_id:
            return self._site_id
        parsed = urlparse(self.config.site_url)
        if parsed.scheme != "https" or not parsed.hostname:
            raise MicrosoftGraphStorageConfigurationError(
                "MS_SP_SITE_URL phải là URL HTTPS của site SharePoint.", code="invalid_site_url"
            )
        segments = [value for value in parsed.path.split("/") if value]
        if len(segments) >= 2 and segments[0].lower() in ("sites", "teams"):
            site_path = "/" + "/".join(segments[:2])
        else:
            site_path = "/"
        endpoint = (
            f"{GRAPH_ROOT}/sites/{quote(parsed.hostname, safe='.')}:"
            f"{quote(site_path, safe='/')}?$select=id"
        )
        response = self._request("GET", endpoint, expected={200})
        try:
            self._site_id = response.json()["id"]
        except (KeyError, TypeError, ValueError) as exc:
            raise MicrosoftGraphStorageError(
                "Microsoft Graph không trả site ID hợp lệ.", code="invalid_site_response"
            ) from exc
        return self._site_id

    def _resolve_drive_id(self):
        if self._drive_id:
            return self._drive_id
        site_id = self._resolve_site_id()
        response = self._request(
            "GET", f"{GRAPH_ROOT}/sites/{quote(site_id, safe=',-')}/drive?$select=id", expected={200}
        )
        try:
            self._drive_id = response.json()["id"]
        except (KeyError, TypeError, ValueError) as exc:
            raise MicrosoftGraphStorageError(
                "Microsoft Graph không trả drive ID hợp lệ.", code="invalid_drive_response"
            ) from exc
        return self._drive_id

    def _ensure_folders(self, drive_id, parts):
        root = self._request(
            "GET", f"{GRAPH_ROOT}/drives/{quote(drive_id, safe='')}/root?$select=id", expected={200}
        ).json()
        parent_id = root["id"]
        for name in parts:
            item_url = (
                f"{GRAPH_ROOT}/drives/{quote(drive_id, safe='')}/items/"
                f"{quote(parent_id, safe='')}:{quote('/' + name, safe='/')}?$select=id,folder"
            )
            try:
                existing = self._request("GET", item_url, expected={200}).json()
            except MicrosoftGraphStorageError as exc:
                if exc.http_status != 404:
                    raise
                create_url = (
                    f"{GRAPH_ROOT}/drives/{quote(drive_id, safe='')}/items/"
                    f"{quote(parent_id, safe='')}/children"
                )
                try:
                    existing = self._request(
                        "POST",
                        create_url,
                        expected={201},
                        headers={"Content-Type": "application/json"},
                        json={
                            "name": name,
                            "folder": {},
                            "@microsoft.graph.conflictBehavior": "fail",
                        },
                    ).json()
                except MicrosoftGraphStorageError as create_exc:
                    if create_exc.http_status != 409:
                        raise
                    existing = self._request("GET", item_url, expected={200}).json()
            if "folder" not in existing:
                raise MicrosoftGraphStorageError(
                    f"Đường dẫn đích bị trùng với file: {name}.", code="folder_path_is_file"
                )
            parent_id = existing["id"]
        return parent_id

    def _upload_small(self, drive_id, parent_id, filename, data, *, content_type):
        endpoint = (
            f"{GRAPH_ROOT}/drives/{quote(drive_id, safe='')}/items/{quote(parent_id, safe='')}:"
            f"/{quote(filename, safe='')}:/content"
        )
        response = self._request(
            "PUT",
            endpoint,
            expected={200, 201},
            headers={"Content-Type": content_type},
            data=data,
        )
        return response.json()

    def _upload_large(self, drive_id, parent_id, filename, data):
        endpoint = (
            f"{GRAPH_ROOT}/drives/{quote(drive_id, safe='')}/items/{quote(parent_id, safe='')}:"
            f"/{quote(filename, safe='')}:/createUploadSession"
        )
        response = self._request(
            "POST",
            endpoint,
            expected={200, 201},
            headers={"Content-Type": "application/json"},
            json={"item": {"@microsoft.graph.conflictBehavior": "replace", "name": filename}},
        )
        try:
            upload_url = response.json()["uploadUrl"]
        except (KeyError, TypeError, ValueError) as exc:
            raise MicrosoftGraphStorageError(
                "Microsoft Graph không trả upload session hợp lệ.", code="invalid_upload_session"
            ) from exc
        total = len(data)
        offset = 0
        try:
            while offset < total:
                chunk = data[offset : offset + UPLOAD_CHUNK_SIZE]
                end = offset + len(chunk) - 1
                upload = self._upload_chunk(upload_url, chunk, offset, end, total)
                if upload.status_code in (200, 201):
                    return upload.json()
                offset = end + 1
        except Exception:
            try:
                self.session.delete(upload_url, timeout=(self.config.connect_timeout, self.config.read_timeout))
            except requests.RequestException:
                logger.warning("GRAPH_STORAGE_UPLOAD_SESSION_CANCEL_FAILED")
            raise
        raise MicrosoftGraphStorageError(
            "Upload session kết thúc nhưng không trả metadata file.", code="incomplete_upload"
        )

    def _upload_chunk(self, upload_url, chunk, start, end, total):
        for attempt in range(self.config.max_retries + 1):
            try:
                response = self.session.put(
                    upload_url,
                    data=chunk,
                    headers={
                        "Content-Length": str(len(chunk)),
                        "Content-Range": f"bytes {start}-{end}/{total}",
                    },
                    timeout=(self.config.connect_timeout, self.config.read_timeout),
                )
            except (requests.Timeout, requests.ConnectionError) as exc:
                if attempt >= self.config.max_retries:
                    raise MicrosoftGraphStorageError(
                        "Upload file lên Microsoft Graph bị gián đoạn.",
                        code="upload_connection_error",
                        retryable=True,
                    ) from exc
                self._backoff(attempt, None)
                continue
            if response.status_code in (200, 201, 202):
                return response
            if response.status_code in RETRYABLE_STATUSES and attempt < self.config.max_retries:
                self._backoff(attempt, response)
                continue
            code, message = _response_error(response)
            raise MicrosoftGraphStorageError(
                f"Microsoft Graph từ chối upload file: {message}",
                code=code,
                retryable=response.status_code in RETRYABLE_STATUSES,
                http_status=response.status_code,
            )
        raise AssertionError("unreachable")
