"""JSON persistence for the media library.

:class:`MediaDatabase` keeps all entries (:class:`mediavault.models.MediaItem`)
of one config in memory and writes them as a JSON list to the config's
database file.

Threading: background downloads add entries while the GUI thread reads and
edits, so every access to the entry list goes through an ``RLock``. Callers
read via :meth:`MediaDatabase.snapshot` and use
:meth:`MediaDatabase.transaction` for read-check-write sequences.

Safety: saves are atomic (temp file + ``os.replace``). A corrupt file is
backed up and the app starts empty; an unreadable file puts the database into
read-only mode, so a save can never overwrite data that was never loaded.
"""

import json
import logging
import os
import random
import shutil
import threading
import time
from collections.abc import Iterable, Iterator
from contextlib import contextmanager, suppress

from mediavault import volumes
from mediavault.models import MediaItem

logger = logging.getLogger(__name__)


class MediaDatabase:
    """Stores the media entries of one config and persists them to a JSON file.

    Attributes:
        filepath: Path of the JSON database.
        entries: The loaded entries; read through :meth:`snapshot` from other
            threads.
        load_error: Human-readable reason when :meth:`load` failed, else empty.
        backup_path: Copy of a corrupt file made by :meth:`load`, else empty.
        read_only: True when the file exists but could not be read; all saves
            are refused to protect it.
    """

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
        """Hold the database lock for a read-check-write sequence.

        Use it when a decision depends on the current entries, e.g. checking for a
        duplicate before adding, so no other thread can add in between.
        """
        with self._lock:
            yield self

    def load(self) -> None:
        """Load entries from the JSON file, if it exists.

        A missing file leaves the database empty. An unreadable file sets
        ``load_error`` and ``read_only``. A corrupt file or one with an unexpected
        shape is copied to ``<file>.corrupt.<timestamp>`` (``backup_path``) and the
        database starts empty; the GUI reports both cases to the user.
        """
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
                with open(self.filepath, encoding="utf-8") as f:
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
                with suppress(OSError):
                    shutil.copy(self.filepath, backup)
                    self.backup_path = backup
                    logger.info("Backup angelegt: %s", backup)

    def relativize(self, root: str) -> int:
        """Store paths inside a volume root relative to it and save if anything changed.

        Used when a local library moves onto a stick, so the database keeps working
        under any mount point.

        Args:
            root: Mount point of the vault volume.

        Returns:
            Number of entries whose paths were rewritten.
        """
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
        """Write all entries atomically to the JSON file.

        Does nothing (and logs a warning) in read-only mode.

        Raises:
            OSError: When the file cannot be written.
        """
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
        """Remove the given entries and persist the database.

        Only the database entries are removed; the media files stay on disk.
        """
        with self._lock:
            doomed = set(entries_to_delete)
            self.entries = [e for e in self.entries if e not in doomed]
            self.save()

    def snapshot(self) -> list[MediaItem]:
        """Return a copy of the entry list taken under the lock."""
        with self._lock:
            return list(self.entries)

    def get_by_type(self, entry_type: str) -> list[MediaItem]:
        """Return all entries of the given :class:`MediaType` value."""
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
        """Pick a random entry from ``pool``, optionally weighted.

        Entries in ``recent_picks`` are excluded unless they make up the whole pool,
        so repeated picks do not show the same entries again and again.

        Smart weighting starts at ``score + 20``, multiplies by ``0.85`` for every
        previous viewing, and further by ``0.3`` if the entry was watched in the
        last day or ``0.6`` in the last week. Every weight is at least 1, so nothing
        is ever impossible to pick.

        Args:
            pool: Candidate entries.
            smart: True for weighted picking, False for uniform picking.
            recent_picks: Entries picked recently.

        Returns:
            The chosen entry, or None if ``pool`` is empty.
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
