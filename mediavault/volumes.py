"""Identity and path helpers for media stored on removable volumes.

A vault volume is any mounted filesystem that carries a small marker file
('.mediavault-vault'). The marker stores a UUID, so a config keeps working
when the drive letter changes or the drive moves to another machine.

Everything here is Qt-free at import time: the mount list is read lazily
through QStorageInfo inside mounted_roots().
"""

import json
import logging
import os
import uuid
from collections.abc import Iterable
from dataclasses import dataclass

logger = logging.getLogger(__name__)

MARKER_NAME = ".mediavault-vault"
MARKER_VERSION = 1


@dataclass(frozen=True)
class VolumeInfo:
    """Identity and display label of one marked volume."""

    uuid: str
    label: str = ""


def new_uuid() -> str:
    """Return a fresh identifier for a new vault volume."""
    return uuid.uuid4().hex


def mounted_roots() -> list[str]:
    """Return the mount points of every connected volume."""
    try:
        from PyQt6.QtCore import QStorageInfo
    except ImportError:  # pragma: no cover - PyQt6 is a hard dependency
        logger.debug("QStorageInfo nicht verfuegbar", exc_info=True)
        return []
    roots = (v.rootPath() for v in QStorageInfo.mountedVolumes() if v.isValid())
    return [root for root in dict.fromkeys(roots) if root]


def marker_path(root: str) -> str:
    """Return the marker file path inside a volume root."""
    return os.path.join(root, MARKER_NAME)


def read_marker(root: str) -> VolumeInfo | None:
    """Return the marker stored in root, or None if there is none."""
    if not root:
        return None
    try:
        with open(marker_path(root), encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    uid = data.get("uuid")
    if not isinstance(uid, str) or not uid.strip():
        return None
    label = data.get("label")
    return VolumeInfo(uid.strip(), label.strip() if isinstance(label, str) else "")


def write_marker(root: str, volume_uuid: str = "", label: str = "") -> VolumeInfo:
    """Write the marker atomically and return the identity it now carries."""
    info = VolumeInfo(volume_uuid or new_uuid(), label)
    target = marker_path(root)
    tmp = f"{target}.{os.getpid()}.tmp"
    payload = {"version": MARKER_VERSION, "uuid": info.uuid, "label": info.label}
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    os.replace(tmp, target)
    return info


def vaults(
    roots: Iterable[str] | None = None,
) -> list[tuple[str, VolumeInfo]]:
    """Return every connected volume that carries a vault marker."""
    candidates = list(roots) if roots is not None else mounted_roots()
    return [(root, info) for root in candidates if (info := read_marker(root))]


def find_volume(volume_uuid: str, roots: Iterable[str] | None = None) -> str:
    """Return the mount point currently carrying volume_uuid, else an empty string."""
    if not volume_uuid:
        return ""
    return next((root for root, info in vaults(roots) if info.uuid == volume_uuid), "")


def volume_for_path(
    path: str, roots: Iterable[str] | None = None
) -> tuple[str, VolumeInfo | None]:
    """Return the mount point that contains path and its marker, if any."""
    candidates = list(roots) if roots is not None else mounted_roots()
    containing = [root for root in candidates if is_inside(path, root)]
    if not containing:
        return "", None
    # The deepest mount point wins; on a tie the first one is kept.
    best = max(containing, key=lambda root: len(_norm(root)))
    return best, read_marker(best)


def _norm(path: str) -> str:
    return os.path.normcase(os.path.abspath(path))


def is_inside(path: str, folder: str) -> bool:
    """Return True if path is folder itself or lives inside it."""
    if not path or not folder:
        return False
    target, base = _norm(path), _norm(folder)
    return target == base or target.startswith(base.rstrip(os.sep) + os.sep)


def relative_to_root(path: str, root: str) -> str:
    """Return path relative to root, always with forward slashes."""
    relative = os.path.relpath(os.path.abspath(path), os.path.abspath(root))
    if relative == ".":
        return ""
    return relative.replace(os.sep, "/")


def _safe_parts(relative: str) -> list[str] | None:
    """Split a stored path into parts, or return None when it tries to escape."""
    normalized = relative.replace(chr(92), "/")
    parts = [part for part in normalized.split("/") if part not in ("", ".")]
    if any(part == ".." for part in parts):
        return None
    return parts


def folder_path(root: str, relative: str) -> str:
    """Resolve a stored folder path; an empty value means the root itself."""
    if not root:
        return ""
    parts = _safe_parts(relative)
    if parts is None:
        return ""
    return os.path.join(root, *parts) if parts else root


def stored_path(path: str, root: str) -> str:
    """Return the value to persist: relative inside the volume, else absolute."""
    return relative_to_root(path, root) if is_inside(path, root) else path


def absolute_path(value: str, root: str) -> str:
    """Turn a stored file path into a usable absolute path."""
    if not value:
        return ""
    if os.path.isabs(value):
        return value
    if not root:
        return ""
    parts = _safe_parts(value)
    if not parts:
        return ""
    return os.path.join(root, *parts)


def path_key(value: str, root: str = "") -> str:
    """Return a comparable key for a stored path or an absolute file path."""
    if not value:
        return ""
    return os.path.normcase(stored_path(value, root).replace(chr(92), "/"))
