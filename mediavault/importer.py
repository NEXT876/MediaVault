"""Import pipeline: build entries, detect duplicates and persist additions.

Deliberately free of Qt so the same code can serve the file pickers and a
future API downloader.
"""

import hashlib
import logging
import os
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from mediavault import volumes
from mediavault.ai_meta import ai_duplicate_key, extract_ai_metadata
from mediavault.config import MODE_AI
from mediavault.models import MediaDatabase, MediaItem

logger = logging.getLogger(__name__)

_CHUNK = 1024 * 1024


def norm_path(path: str) -> str:
    """Normalize a file path for duplicate checks."""
    return os.path.normcase(os.path.abspath(path))


def content_hash(path: str) -> str:
    """Return an identity hash for the bytes of a file.

    Hashes the file size plus its first and last MiB, so hashing a library
    with large videos stays cheap.
    shortcut: partial hash, switch to a full hash if crafted collisions matter.
    """
    size = os.path.getsize(path)
    digest = hashlib.sha256(str(size).encode())
    with open(path, "rb") as f:
        digest.update(f.read(_CHUNK))
        if size > _CHUNK:
            f.seek(size - _CHUNK)
            digest.update(f.read(_CHUNK))
    return digest.hexdigest()


@dataclass
class ImportResult:
    """Counts from one import run."""

    added: int = 0
    duplicates: int = 0
    skipped_no_ai: int = 0


def build_entry(
    path: str, type_str: str, group: str, mode: str, root: str = ""
) -> MediaItem | None:
    """Build an entry from a file, requiring AI metadata in AI configs.

    With a volume root the stored path is relative to that root, so the entry
    survives a changing drive letter.
    """
    meta: dict[str, Any] = {}
    if mode == MODE_AI:
        meta = extract_ai_metadata(path) or {}
        if not meta:
            logger.info("Kein KI-Bild, übersprungen: %s", path)
            return None
    title = os.path.splitext(os.path.basename(path))[0]
    stored = volumes.stored_path(path, root)
    img, vid = (stored, "") if type_str == "Bilder" else ("", stored)
    try:
        file_hash = content_hash(path)
    except OSError:
        file_hash = ""
    return MediaItem(
        title,
        img,
        50,
        "",
        type_str,
        vid,
        group=group,
        ai_meta=meta,
        content_hash=file_hash,
    )


class _Index:
    """Lookup sets for the entries already stored for one media type."""

    def __init__(self, db: MediaDatabase, type_str: str, root: str = "") -> None:
        """Collect paths, content hashes and AI generation keys from ``db``."""
        self.paths: set[str] = set()
        self.hashes: set[str] = set()
        self.keys: set[tuple[str, str, str, str]] = set()
        self.titles: set[str] = set()
        self.dirty = False
        for entry in db.get_by_type(type_str):
            self.titles.add(entry.title)
            if entry.media_path:
                self.paths.add(volumes.path_key(entry.media_path))
            if not entry.content_hash and entry.media_path:
                # Backfill legacy entries once; missing files stay unhashed.
                try:
                    entry.content_hash = content_hash(
                        volumes.absolute_path(entry.media_path, root)
                    )
                    self.dirty = True
                except OSError:
                    pass
            self._remember(entry)

    def _remember(self, entry: MediaItem) -> None:
        """Add an entry's content hash and AI generation key to the sets."""
        if entry.content_hash:
            self.hashes.add(entry.content_hash)
        key = ai_duplicate_key(entry.ai_meta)
        if key is not None:
            self.keys.add(key)

    def is_known(self, path_key: str, meta: dict[str, Any], file_hash: str) -> bool:
        """Return True if path, content or generation is already stored."""
        key = ai_duplicate_key(meta)
        return (
            path_key in self.paths
            or (bool(file_hash) and file_hash in self.hashes)
            or (key is not None and key in self.keys)
        )

    def add(self, entry: MediaItem) -> None:
        """Register a freshly added entry in all lookup sets."""
        self.titles.add(entry.title)
        self.paths.add(volumes.path_key(entry.media_path))
        self._remember(entry)


def find_duplicate(
    db: MediaDatabase, path: str, type_str: str, meta: dict[str, Any], root: str = ""
) -> bool:
    """Return True if the file or its AI generation is already stored."""
    index = _Index(db, type_str, root)
    try:
        file_hash = content_hash(path)
    except OSError:
        file_hash = ""
    found = index.is_known(volumes.path_key(path, root), meta, file_hash)
    if index.dirty:
        db.save()
    return found


def import_paths(
    db: MediaDatabase,
    paths: Iterable[str],
    *,
    type_str: str,
    group: str,
    mode: str,
    root: str = "",
) -> ImportResult:
    """Import files as entries, skipping duplicates and files without AI metadata."""
    result = ImportResult()
    index = _Index(db, type_str, root)
    new_entries: list[MediaItem] = []
    for path in paths:
        title = os.path.splitext(os.path.basename(path))[0]
        path_key = volumes.path_key(path, root)
        if path_key in index.paths or title in index.titles:
            result.duplicates += 1
            continue
        entry = build_entry(path, type_str, group, mode, root)
        if entry is None:
            result.skipped_no_ai += 1
            continue
        if index.is_known(path_key, entry.ai_meta, entry.content_hash):
            result.duplicates += 1
            continue
        index.add(entry)
        new_entries.append(entry)
    if new_entries:
        db.add_many(new_entries)
    elif index.dirty:
        db.save()
    result.added = len(new_entries)
    return result
