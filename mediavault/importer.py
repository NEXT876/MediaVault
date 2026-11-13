"""Import pipeline: build entries, detect duplicates and persist additions.

A file is a duplicate when any of these is already stored for the same
media type: the same path, the same content (:func:`content_hash`) or, for
AI images, the same generation (prompt, seed, model …, see
:func:`ai_meta.ai_duplicate_key`). The same file name in another folder is
not a duplicate.

Used by the manual import in the main window, the folder sync
(:mod:`mediavault.library`) and the plugin downloads (:mod:`mediavault.remote`).
Deliberately free of Qt, so all callers share one implementation.
"""

import hashlib
import logging
import os
from collections.abc import Callable, Iterable
from typing import Any

from mediavault import volumes
from mediavault.ai_meta import ai_duplicate_key, extract_ai_metadata
from mediavault.database import MediaDatabase
from mediavault.models import MODE_AI, ImportResult, MediaItem

logger = logging.getLogger(__name__)

_CHUNK = 1024 * 1024


def content_hash(path: str) -> str:
    """Return an identity hash for the bytes of a file.

    Hashes the file size plus its first and last MiB with SHA-256, so hashing a
    library with large videos stays cheap.
    shortcut: partial hash, switch to a full hash if crafted collisions matter.

    Raises:
        OSError: When the file cannot be read.
    """
    size = os.path.getsize(path)
    digest = hashlib.sha256(str(size).encode())
    with open(path, "rb") as f:
        digest.update(f.read(_CHUNK))
        if size > _CHUNK:
            f.seek(size - _CHUNK)
            digest.update(f.read(_CHUNK))
    return digest.hexdigest()


def _try_hash(path: str) -> str:
    """Return ``content_hash(path)``, or an empty string if the file is unreadable."""
    try:
        return content_hash(path)
    except OSError:
        return ""


def build_entry(
    path: str, type_str: str, group: str, mode: str, root: str = ""
) -> MediaItem | None:
    """Build an entry from a file, requiring AI metadata in AI configs.

    The title is the file name without extension. With a volume root the stored
    path is relative to that root, so the entry survives a changing drive letter.

    Args:
        path: Absolute path of the media file.
        type_str: :class:`MediaType` value of the new entry.
        group: Group to assign.
        mode: Config mode; :data:`MODE_AI` reads and requires AI metadata.
        root: Volume root for relative storage, or empty.

    Returns:
        The unsaved entry, or None when an AI config gets a file without AI
        metadata.
    """
    meta: dict[str, Any] = {}
    if mode == MODE_AI:
        meta = extract_ai_metadata(path) or {}
        if not meta:
            logger.info("Kein KI-Bild, übersprungen: %s", path)
            return None
    entry = MediaItem(
        os.path.splitext(os.path.basename(path))[0],
        entry_type=type_str,
        group=group,
        ai_meta=meta,
    )
    entry.set_file(volumes.stored_path(path, root))
    entry.content_hash = _try_hash(path)
    return entry


class _Index:
    """Lookup sets for the entries already stored for one media type.

    Built once per import run so each file is checked in constant time. While
    building, legacy entries without a content hash get one (``dirty`` is then
    True and the caller saves).
    """

    def __init__(self, db: MediaDatabase, type_str: str, root: str = "") -> None:
        """Collect paths, content hashes and AI generation keys from ``db``."""
        self.paths: set[str] = set()
        self.hashes: set[str] = set()
        self.keys: set[tuple[str, str, str, str]] = set()
        self.dirty = False
        for entry in db.get_by_type(type_str):
            if entry.media_path:
                self.paths.add(volumes.path_key(entry.media_path))
            if not entry.content_hash and entry.media_path:
                # Backfill legacy entries once; missing files stay unhashed.
                entry.content_hash = _try_hash(
                    volumes.absolute_path(entry.media_path, root)
                )
                self.dirty = self.dirty or bool(entry.content_hash)
            self._remember(entry)

    def _remember(self, entry: MediaItem) -> None:
        """Add an entry's content hash and AI generation key to the sets."""
        if entry.content_hash:
            self.hashes.add(entry.content_hash)
        key = ai_duplicate_key(entry.ai_meta)
        if key is not None:
            self.keys.add(key)

    def is_known(self, path_key: str, meta: dict[str, Any], file_hash: str) -> bool:
        """Return True if path, content hash or AI generation is already stored."""
        key = ai_duplicate_key(meta)
        return (
            path_key in self.paths
            or (bool(file_hash) and file_hash in self.hashes)
            or (key is not None and key in self.keys)
        )

    def add(self, entry: MediaItem) -> None:
        """Register a freshly added entry in all lookup sets."""
        self.paths.add(volumes.path_key(entry.media_path))
        self._remember(entry)


def find_duplicate(
    db: MediaDatabase, path: str, type_str: str, meta: dict[str, Any], root: str = ""
) -> bool:
    """Return True if the file or its AI generation is already stored.

    Used for single imports, where the user edits the entry before it is saved.

    Args:
        db: Database of the active config.
        path: Absolute path of the candidate file.
        type_str: Media type to compare against.
        meta: AI metadata of the file, or an empty dict.
        root: Volume root, so relative stored paths compare correctly.
    """
    with db.transaction():
        index = _Index(db, type_str, root)
        found = index.is_known(volumes.path_key(path, root), meta, _try_hash(path))
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
    transfer: Callable[[str], str | None] | None = None,
) -> ImportResult:
    """Import files as entries, skipping duplicates and files without AI metadata.

    ``transfer``, if given, copies an accepted file into the library and
    returns its new path (None on failure). It only runs once the file passed
    every check, so rejected files never leave stray copies behind.

    The whole run holds the database lock, so a concurrent add from another
    thread cannot slip past the duplicate check. New entries are saved in one
    write at the end.

    Args:
        db: Database of the active config.
        paths: Absolute paths of the files to import.
        type_str: :class:`MediaType` value for all new entries.
        group: Group for all new entries.
        mode: Config mode, see :func:`build_entry`.
        root: Volume root for relative storage, or empty.
        transfer: Optional copy step, see above.

    Returns:
        Counts of added, duplicate, skipped and failed files.
    """
    with db.transaction():
        result = ImportResult()
        index = _Index(db, type_str, root)
        new_entries: list[MediaItem] = []
        for path in paths:
            # Same file name in another folder is fine; path, content hash and AI
            # generation key decide what counts as a duplicate.
            path_key = volumes.path_key(path, root)
            if path_key in index.paths:
                result.duplicates += 1
                continue
            entry = build_entry(path, type_str, group, mode, root)
            if entry is None:
                result.skipped_no_ai += 1
                continue
            if index.is_known(path_key, entry.ai_meta, entry.content_hash):
                result.duplicates += 1
                continue
            if transfer is not None:
                stored = transfer(path)
                if stored is None:
                    result.failed += 1
                    continue
                entry.set_file(volumes.stored_path(stored, root))
            index.add(entry)
            new_entries.append(entry)
        if new_entries:
            db.add_many(new_entries)
        elif index.dirty:
            db.save()
        result.added = len(new_entries)
        return result
