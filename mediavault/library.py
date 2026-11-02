"""Qt-free library operations: grid filtering and indexing the media folder.

The GUI decides when to run these; what they do lives here so startup scan,
manual folder sync and tests share one implementation.
"""

import os
from collections.abc import Iterable

from mediavault.config import MODE_AI, LibraryRoot
from mediavault.importer import ImportResult, import_paths
from mediavault.models import MediaDatabase, MediaItem, MediaType
from mediavault.scanner import IMAGE_EXTS, VIDEO_EXTS, find_new_media
from mediavault.volumes import path_key

ALL_GROUPS = "Alle Gruppen"

# (key, label) pairs; the key is what visible_entries understands.
SORT_MODES = (
    ("title", "Titel A–Z"),
    ("score_desc", "Score ↓"),
    ("score_asc", "Score ↑"),
    ("last_watched", "Zuletzt gesehen"),
)


def _matches(entry: MediaItem, needle: str) -> bool:
    """Return True if the search text occurs in any searchable field."""
    haystacks = (
        entry.title,
        entry.description,
        entry.group,
        entry.ai_meta.get("prompt"),
        entry.ai_meta.get("negative_prompt"),
    )
    return any(needle in (text or "").casefold() for text in haystacks)


def visible_entries(
    entries: Iterable[MediaItem],
    group_filter: str,
    query: str,
    sort_mode: str,
) -> list[MediaItem]:
    """Filter entries by group and text, then sort them for the card grid."""
    entries = list(entries)
    if group_filter and group_filter != ALL_GROUPS:
        entries = [entry for entry in entries if entry.group == group_filter]
    needle = query.strip().casefold()
    if needle:
        entries = [entry for entry in entries if _matches(entry, needle)]

    if sort_mode == "score_desc":
        entries.sort(key=lambda entry: (-entry.score, entry.title.casefold()))
    elif sort_mode == "score_asc":
        entries.sort(key=lambda entry: (entry.score, entry.title.casefold()))
    elif sort_mode == "last_watched":
        entries.sort(
            key=lambda entry: (entry.last_watched > 0, entry.last_watched),
            reverse=True,
        )
    else:
        entries.sort(key=lambda entry: entry.title.casefold())
    return entries


def media_exts(mode: str) -> dict[MediaType, set[str]]:
    """Return the file extensions a config of ``mode`` indexes, per media type.

    AI configs only take PNGs, the format that carries generation metadata.
    """
    if mode == MODE_AI:
        return {MediaType.IMAGE: {".png"}, MediaType.VIDEO: set()}
    return {MediaType.IMAGE: IMAGE_EXTS, MediaType.VIDEO: VIDEO_EXTS}


def file_filter(media_type: MediaType) -> str:
    """Return the file-dialog filter for one media type."""
    label = "Bilder" if media_type == MediaType.IMAGE else "Videos"
    exts = IMAGE_EXTS if media_type == MediaType.IMAGE else VIDEO_EXTS
    patterns = " ".join(f"*{ext}" for ext in sorted(exts))
    return f"{label} ({patterns});;Alle Dateien (*.*)"


def find_unindexed(
    db: MediaDatabase,
    mode: str,
    location: LibraryRoot,
    ignored: Iterable[str] = (),
) -> dict[MediaType, list[str]]:
    """Return the files in the library folder the database does not know yet.

    Stored paths may be relative to the volume, so every comparison goes
    through the location's volume root.
    """
    exts = media_exts(mode)
    known = [entry.file_path for entry in db.snapshot()]
    known.extend(ignored)
    images, videos = find_new_media(
        location.folder,
        known,
        image_exts=exts[MediaType.IMAGE],
        video_exts=exts[MediaType.VIDEO],
        root=location.volume,
    )
    return {MediaType.IMAGE: images, MediaType.VIDEO: videos}


def index_files(
    db: MediaDatabase,
    found: dict[MediaType, list[str]],
    mode: str,
    location: LibraryRoot,
) -> ImportResult:
    """Import found files into the database and return the combined counts."""
    total = ImportResult()
    for media_type, paths in found.items():
        if not paths:
            continue
        result = import_paths(
            db,
            paths,
            type_str=media_type,
            group="",
            mode=mode,
            root=location.volume,
        )
        total.added += result.added
        total.duplicates += result.duplicates
        total.skipped_no_ai += result.skipped_no_ai
        total.failed += result.failed
    return total


def scan(db: MediaDatabase, mode: str, location: LibraryRoot) -> ImportResult:
    """Index every new file of the library folder; no-op while unavailable."""
    if not location.available or not os.path.isdir(location.folder):
        return ImportResult()
    return index_files(db, find_unindexed(db, mode, location), mode, location)


def not_indexed(
    db: MediaDatabase, paths: Iterable[str], location: LibraryRoot
) -> set[str]:
    """Return the paths that an import run left out of the database."""
    stored = {path_key(entry.file_path, location.volume) for entry in db.snapshot()}
    return {path for path in paths if path_key(path, location.volume) not in stored}
