"""Data model and JSON persistence for the media library."""

import json
import logging
import os
import random
import shutil
import threading
import time
from collections.abc import Iterable, Iterator, Mapping
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field, fields
from typing import Any

from mediavault import volumes

logger = logging.getLogger(__name__)


@dataclass(eq=False)
class MediaItem:
    """A single media entry (image or video).

    Identity semantics are intentional: entries are stored in sets and compared
    with ``in`` throughout the GUI, so equality must remain object identity.
    """

    title: str
    image_path: str = ""
    score: int = 50
    description: str = ""
    entry_type: str = "Bilder"
    video_link: str = ""
    watched_counter: int = 0
    last_watched: float = 0.0
    rating_count: int = 0
    group: str = ""
    ai_meta: dict[str, Any] = field(default_factory=dict)
    content_hash: str = ""

    @property
    def media_path(self) -> str:
        """Primary stored path: the preview image if present, else the video."""
        return self.image_path or self.video_link

    @property
    def file_path(self) -> str:
        """Stored path of the entry's own file, chosen by entry type."""
        return self.video_link if self.entry_type == "Videos" else self.image_path

    def set_file(self, path: str) -> None:
        """Store a file path in the field that matches the entry type."""
        if self.entry_type == "Videos":
            self.video_link = path
        else:
            self.image_path = path

    def resolve(self, root: str) -> str:
        """Return the entry's file path resolved against a volume root."""
        return volumes.absolute_path(self.file_path, root)

    def to_dict(self) -> dict[str, Any]:
        """Serialize the entry as a detached dictionary for JSON storage."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "MediaItem":
        """Build an entry from a dictionary, ignoring unknown keys."""
        known = {key: value for key, value in data.items() if key in _ITEM_FIELDS}
        return cls(**known)


_ITEM_FIELDS = frozenset(field.name for field in fields(MediaItem))


class MediaDatabase:
    """Stores media entries and persists them to a JSON file."""

    def __init__(self, filepath: str = "media_data.json") -> None:
        """Create a database bound to ``filepath`` with no loaded entries."""
        self.filepath = filepath
        self.entries: list[MediaItem] = []
        # Background downloads write while the GUI thread reads and edits.
        self._lock = threading.RLock()
        # Set by load() when the file could not be read; the GUI reports it.
        self.load_error = ""
        self.backup_path = ""
        # True when the file exists but could not be read: saving would
        # replace data that was never loaded, so writes are refused.
        self.read_only = False

    @contextmanager
    def transaction(self) -> Iterator["MediaDatabase"]:
        """Hold the database lock for a read-check-write sequence."""
        with self._lock:
            yield self

    def load(self) -> None:
        """Load entries from the JSON file, if it exists."""
        with self._lock:
            self.load_error = ""
            self.backup_path = ""
            self.read_only = False
            try:
                os.makedirs(
                    os.path.dirname(os.path.abspath(self.filepath)), exist_ok=True
                )
            except OSError:
                logger.warning("Datenordner nicht anlegbar: %s", self.filepath)
            if not os.path.exists(self.filepath):
                return
            try:
                with open(self.filepath, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if not isinstance(data, list) or not all(
                        isinstance(item, dict) for item in data
                    ):
                        raise ValueError("Unerwartetes Datenformat")
                    self.entries = [MediaItem.from_dict(item) for item in data]
            except OSError as exc:
                logger.error("Datenbank nicht lesbar: %s", self.filepath)
                self.load_error = f"Datei nicht lesbar: {exc}"
                self.read_only = True
            except (json.JSONDecodeError, ValueError):
                logger.error("JSON beschädigt: %s", self.filepath)
                self.load_error = "Datei beschädigt"
                backup = f"{self.filepath}.corrupt.{int(time.time())}"
                try:
                    shutil.copy(self.filepath, backup)
                    self.backup_path = backup
                    logger.info("Backup angelegt: %s", backup)
                except OSError:
                    pass

    def relativize(self, root: str) -> int:
        """Store paths inside a volume root relative to it; return changed entries."""
        changed = 0
        for entry in self.snapshot():
            image = volumes.stored_path(entry.image_path, root)
            video = volumes.stored_path(entry.video_link, root)
            if (image, video) != (entry.image_path, entry.video_link):
                entry.image_path, entry.video_link = image, video
                changed += 1
        if changed:
            self.save()
        return changed

    def save(self) -> None:
        """Write all entries atomically to the JSON file."""
        with self._lock:
            if self.read_only:
                logger.warning("Nicht gespeichert, Datei war unlesbar: %s", self.filepath)
                return
            parent = os.path.dirname(os.path.abspath(self.filepath))
            os.makedirs(parent, exist_ok=True)
            tmp = self.filepath + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(
                    [e.to_dict() for e in self.entries],
                    f,
                    indent=4,
                    ensure_ascii=False,
                )
            os.replace(tmp, self.filepath)

    def add(self, entry: MediaItem) -> None:
        """Append one entry and persist the database."""
        with self._lock:
            self.entries.append(entry)
            self.save()

    def add_many(self, entries: Iterable[MediaItem]) -> None:
        """Append several entries and persist once."""
        with self._lock:
            self.entries.extend(entries)
            self.save()

    def delete_multiple(self, entries_to_delete: Iterable[MediaItem]) -> None:
        """Remove the given entries and persist the database."""
        with self._lock:
            doomed = set(entries_to_delete)
            self.entries = [e for e in self.entries if e not in doomed]
            self.save()

    def snapshot(self) -> list[MediaItem]:
        """Return a copy of the entry list taken under the lock."""
        with self._lock:
            return list(self.entries)

    def get_by_type(self, entry_type: str) -> list[MediaItem]:
        """Return all entries of the given media type."""
        return [e for e in self.snapshot() if e.entry_type == entry_type]

    def get_all_groups(self) -> list[str]:
        """Return all non-empty group names in sorted order."""
        return sorted({e.group for e in self.snapshot() if e.group.strip()})

    def get_random(
        self,
        pool: list[MediaItem],
        smart: bool = False,
        recent_picks: list[MediaItem] | None = None,
    ) -> MediaItem | None:
        """Pick a random entry from ``pool``, optionally score-weighted.

        Entries in ``recent_picks`` are excluded unless they are the whole pool.
        Smart weighting favors high scores and entries not watched recently.
        """
        if not pool:
            return None
        recent_picks = recent_picks or []
        filtered = [e for e in pool if e not in recent_picks]
        if not filtered:
            filtered = pool

        if not smart:
            return random.choice(filtered)

        current_time = time.time()
        weights = []
        for entry in filtered:
            weight = entry.score + 20
            weight *= 0.85**entry.watched_counter
            if entry.last_watched > 0:
                days_since = (current_time - entry.last_watched) / 86400
                if days_since < 1:
                    weight *= 0.3
                elif days_since < 7:
                    weight *= 0.6
            weights.append(max(1, weight))

        return random.choices(filtered, weights=weights, k=1)[0]
