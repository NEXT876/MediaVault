"""Media entries: the kind of an entry and the entry itself."""

from collections.abc import Mapping
from dataclasses import asdict, dataclass, field, fields
from enum import Enum
from typing import Any


class MediaType(str, Enum):
    """Kind of a media entry; the values are what the JSON file stores.

    The German values ("Bilder", "Videos") double as page names in the GUI and
    must not change, or existing database files would no longer match.
    """

    IMAGE = "Bilder"
    VIDEO = "Videos"

    def __str__(self) -> str:
        """Format as the stored value on every Python version."""
        return self.value


@dataclass(eq=False)
class MediaItem:
    """A single media entry (image or video).

    Paths are stored as given by :func:`volumes.stored_path`: absolute for local
    files, relative to the stick root for media on a vault volume;
    :func:`mediavault.volumes.absolute_path` turns them into usable paths.

    Identity semantics are intentional: entries are stored in sets and compared
    with ``in`` throughout the GUI, so equality must remain object identity.

    Attributes:
        title: Display title of the card.
        image_path: Image file, or the preview image of a video entry.
        score: User rating, 1-100.
        description: Free text shown in the detail dialog.
        entry_type: A :class:`MediaType` value.
        video_link: Video file of a video entry; empty for images.
        watched_counter: How often the entry was opened for viewing.
        last_watched: Unix time of the last viewing, 0 if never.
        rating_count: How often the entry was rated.
        group: Optional single group name used for filtering and random picks.
        ai_meta: Generation metadata of AI images (prompt, model, seed …).
        content_hash: :func:`importer.content_hash` of the file, used for
            duplicate detection and as the thumbnail cache key.
    """

    title: str
    image_path: str = ""
    score: int = 50
    description: str = ""
    entry_type: str = MediaType.IMAGE
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
        if self.entry_type == MediaType.VIDEO:
            return self.video_link
        return self.image_path

    def set_file(self, path: str) -> None:
        """Store a file path in the field that matches the entry type."""
        if self.entry_type == MediaType.VIDEO:
            self.video_link = path
        else:
            self.image_path = path

    def to_dict(self) -> dict[str, Any]:
        """Serialize the entry as a detached dictionary for JSON storage."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "MediaItem":
        """Build an entry from a stored dictionary, ignoring unknown keys.

        Unknown keys are dropped so files written by newer versions still load;
        missing keys take the dataclass defaults so older files load too.
        Numbers stored as text (``"80"``) are converted.

        Raises:
            TypeError: When ``title`` is missing.
            ValueError: When a number field holds something that is not a number.
        """
        known = {key: value for key, value in data.items() if key in _ITEM_FIELDS}
        for key, convert in _NUMBER_FIELDS.items():
            if key in known:
                known[key] = convert(known[key])
        return cls(**known)


_ITEM_FIELDS = frozenset(field.name for field in fields(MediaItem))
_NUMBER_FIELDS = {
    "score": int,
    "watched_counter": int,
    "rating_count": int,
    "last_watched": float,
}
