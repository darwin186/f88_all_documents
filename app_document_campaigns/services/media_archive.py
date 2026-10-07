from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from django.conf import settings


class MediaPathError(ValueError):
    pass


@dataclass(frozen=True)
class MediaSource:
    relative_path: str
    absolute_path: Path
    is_dir: bool


def normalize_media_path(value):
    raw_value = str(value or "").replace("\\", "/")
    if raw_value.startswith("/"):
        raise MediaPathError("Đường dẫn media không hợp lệ.")
    raw = raw_value.strip("/")
    if not raw:
        return ""
    path = PurePosixPath(raw)
    if path.is_absolute() or any(part in ("", ".", "..") for part in path.parts):
        raise MediaPathError("Đường dẫn media không hợp lệ.")
    return path.as_posix()


def resolve_media_source(value, *, must_exist=True):
    relative = normalize_media_path(value)
    root = Path(settings.MEDIA_ROOT).resolve()
    candidate = root / Path(relative)
    if candidate.is_symlink():
        raise MediaPathError("Không đồng bộ symbolic link.")
    target = candidate.resolve()
    try:
        target.relative_to(root)
    except ValueError as exc:
        raise MediaPathError("Đường dẫn nằm ngoài MEDIA_ROOT.") from exc
    if must_exist and not target.exists():
        raise MediaPathError("File hoặc thư mục media không còn tồn tại.")
    return MediaSource(relative_path=relative, absolute_path=target, is_dir=target.is_dir())


def iter_media_files(source):
    if not source.is_dir:
        yield source.relative_path, source.absolute_path
        return
    root = Path(settings.MEDIA_ROOT).resolve()
    for path in sorted(source.absolute_path.rglob("*")):
        if not path.is_file() or path.is_symlink():
            continue
        resolved = path.resolve()
        try:
            relative = resolved.relative_to(root).as_posix()
        except ValueError:
            continue
        yield relative, resolved


def remote_folder_for(relative_file):
    relative = PurePosixPath(normalize_media_path(relative_file))
    prefix = str(
        getattr(settings, "MICROSOFT_GRAPH_STORAGE_MEDIA_PREFIX", "app_documents_campaigns")
        or "app_documents_campaigns"
    ).replace("\\", "/").strip("/")
    prefix_parts = PurePosixPath(prefix).parts
    parent_parts = relative.parent.parts if str(relative.parent) != "." else ()
    if tuple(relative.parts[: len(prefix_parts)]) == tuple(prefix_parts):
        return "/".join(parent_parts)
    return "/".join((*prefix_parts, *parent_parts))


def directory_tree(*, current_path="", limit=1000):
    root = Path(settings.MEDIA_ROOT).resolve()
    normalized_current = normalize_media_path(current_path)
    expanded_paths = {""}
    current_parts = PurePosixPath(normalized_current).parts if normalized_current else ()
    for index in range(1, len(current_parts) + 1):
        expanded_paths.add("/".join(current_parts[:index]))
    seen = 0

    def build(path):
        nonlocal seen
        relative = path.relative_to(root).as_posix()
        children = []
        try:
            candidates = sorted(
                (item for item in path.iterdir() if item.is_dir() and not item.is_symlink()),
                key=lambda item: item.name.casefold(),
            )
        except OSError:
            candidates = []
        for child in candidates:
            if seen >= limit:
                break
            seen += 1
            children.append(build(child))
        node_path = "" if relative == "." else relative
        return {
            "name": path.name if relative != "." else "media",
            "path": node_path,
            "children": children,
            "is_open": node_path in expanded_paths,
        }

    tree = build(root)
    tree["truncated"] = seen >= limit
    return tree


def directory_entries(relative_directory):
    source = resolve_media_source(relative_directory)
    if not source.is_dir:
        raise MediaPathError("Đường dẫn đang xem không phải thư mục.")
    entries = []
    try:
        candidates = sorted(
            (item for item in source.absolute_path.iterdir() if not item.is_symlink()),
            key=lambda item: (not item.is_dir(), item.name.casefold()),
        )
    except OSError as exc:
        raise MediaPathError("Không đọc được thư mục media.") from exc
    root = Path(settings.MEDIA_ROOT).resolve()
    for item in candidates:
        try:
            stat = item.stat()
        except OSError:
            continue
        entries.append({
            "name": item.name,
            "path": item.resolve().relative_to(root).as_posix(),
            "is_dir": item.is_dir(),
            "size": None if item.is_dir() else stat.st_size,
            "modified_at": stat.st_mtime,
        })
    return entries


def breadcrumbs(relative_directory):
    parts = PurePosixPath(normalize_media_path(relative_directory)).parts if relative_directory else ()
    result = [{"name": "media", "path": ""}]
    current = []
    for part in parts:
        current.append(part)
        result.append({"name": part, "path": "/".join(current)})
    return result
