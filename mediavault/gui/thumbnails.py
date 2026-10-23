"""Preview image loading, safe to run outside the GUI thread."""

import logging

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QImage

from mediavault.models import MediaItem
from mediavault.utils import OSHelper

logger = logging.getLogger(__name__)


def load_thumbnail(entry: MediaItem) -> QImage | None:
    """Load and scale one preview image; safe outside the GUI thread."""
    image: QImage | None = None
    if entry.image_path:
        image = QImage(entry.image_path)
        if image.isNull():
            logger.debug("Bild konnte nicht geladen werden: %s", entry.image_path)
            image = None
    elif entry.entry_type == "Videos":
        image = OSHelper.get_video_frame_image(entry.video_link)
        if image is None:
            os_thumb = OSHelper.get_os_thumbnail(entry.video_link)
            if os_thumb:
                image = QImage(os_thumb)
    if image is None or image.isNull():
        return None
    # Cards are ~176 px wide; keep the cache small.
    return image.scaled(
        512,
        512,
        Qt.AspectRatioMode.KeepAspectRatio,
        Qt.TransformationMode.SmoothTransformation,
    )


def load_thumbnails(entries: list[MediaItem]) -> dict[str, QImage | None]:
    """Load previews for several entries, keyed by media path.

    One broken file must not discard the previews of the whole batch.
    """
    previews: dict[str, QImage | None] = {}
    for entry in entries:
        try:
            previews[entry.media_path] = load_thumbnail(entry)
        except Exception:  # One bad file must not stop the batch.
            logger.debug(
                "Vorschau fehlgeschlagen: %s", entry.media_path, exc_info=True
            )
            previews[entry.media_path] = None
    return previews
