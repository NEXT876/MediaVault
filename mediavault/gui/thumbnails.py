"""Preview loading and the on-disk preview cache.

Images are loaded directly; for videos a frame is extracted with OpenCV,
falling back to the system thumbnail (:mod:`mediavault.media_preview`).
Every preview is scaled to at most 512 px and stored as WebP under
``~/.mediavault/thumbs``, keyed by the entry's content hash, so a library on
a removable volume stays browsable while the volume is unplugged and
repeated starts do not decode the originals again.

Loading is safe outside the GUI thread: ``QImage`` may be built there, and
the caller converts it to a ``QPixmap`` on the GUI thread.
"""

import hashlib
import logging
import os

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QImage

from mediavault import media_preview, volumes
from mediavault.config import APP_DIR
from mediavault.models import MediaItem, MediaType

logger = logging.getLogger(__name__)

CACHE_DIR = os.path.join(APP_DIR, "thumbs")
_MAX_EDGE = 512


def cache_key(entry: MediaItem, scope: str = "") -> str:
    """Return the identity an entry preview is cached under.

    The content hash when known, so moved or renamed files keep their preview.
    Without a content hash the stored path is only unique inside one volume, so
    the volume scope is part of the key.

    Args:
        entry: The entry.
        scope: Identifies the library (e.g. the volume UUID).

    Returns:
        The key, or an empty string for entries without any path.
    """
    if entry.content_hash:
        return entry.content_hash
    return f"{scope}|{entry.media_path}" if entry.media_path else ""


def cache_path(entry: MediaItem, scope: str = "") -> str:
    """Return the WebP cache file for an entry, or an empty string if uncacheable."""
    key = cache_key(entry, scope)
    if not key:
        return ""
    digest = hashlib.sha1(key.encode("utf-8")).hexdigest()
    return os.path.join(CACHE_DIR, f"{digest}.webp")


def _scaled(image: QImage) -> QImage:
    """Shrink an image to the cache bounds; smaller images stay as they are."""
    if image.width() <= _MAX_EDGE and image.height() <= _MAX_EDGE:
        return image
    return image.scaled(
        _MAX_EDGE,
        _MAX_EDGE,
        Qt.AspectRatioMode.KeepAspectRatio,
        Qt.TransformationMode.SmoothTransformation,
    )


def _read_cache(entry: MediaItem, scope: str = "") -> QImage | None:
    """Return the cached preview for an entry, if one exists."""
    path = cache_path(entry, scope)
    if not path or not os.path.isfile(path):
        return None
    image = QImage(path)
    return None if image.isNull() else image


def _write_cache(entry: MediaItem, image: QImage, scope: str = "") -> None:
    """Store a preview atomically in the cache; failures only cost a reload."""
    path = cache_path(entry, scope)
    if not path:
        return
    tmp = f"{path}.{os.getpid()}.tmp"
    try:
        os.makedirs(CACHE_DIR, exist_ok=True)
        if image.save(tmp, "WEBP"):
            os.replace(tmp, path)
        elif os.path.exists(tmp):
            os.remove(tmp)
    except OSError:
        logger.debug("Vorschau nicht cachebar: %s", path, exc_info=True)


def _render(entry: MediaItem, root: str) -> QImage | None:
    """Build a preview from the source file on the volume.

    Uses the entry's image when set; for videos without one, an OpenCV frame,
    then the system thumbnail. Returns None when nothing can be loaded, e.g.
    while the stick is unplugged.
    """
    if entry.image_path:
        path = volumes.absolute_path(entry.image_path, root)
        image = QImage(path) if path else QImage()
        if image.isNull():
            logger.debug("Bild konnte nicht geladen werden: %s", entry.image_path)
            return None
        return image
    if entry.entry_type == MediaType.VIDEO:
        path = volumes.absolute_path(entry.video_link, root)
        image = media_preview.get_video_frame_image(path)
        if image is None:
            os_thumb = media_preview.get_os_thumbnail(path)
            if os_thumb:
                image = QImage(os_thumb)
        return None if image is None or image.isNull() else image
    return None


def load_thumbnail(
    entry: MediaItem, root: str = "", scope: str = ""
) -> QImage | None:
    """Load one preview, using and filling the on-disk cache.

    Args:
        entry: The entry to preview.
        root: Volume root to resolve relative paths.
        scope: Library identity, see :func:`cache_key`.

    Returns:
        A preview of at most 512 px, or None when no source is available.
    """
    cached = _read_cache(entry, scope)
    if cached is not None:
        return cached
    image = _render(entry, root)
    if image is None:
        return None
    preview = _scaled(image)
    _write_cache(entry, preview, scope)
    return preview


def load_thumbnails(
    entries: list[MediaItem], root: str = "", scope: str = ""
) -> dict[str, QImage | None]:
    """Load previews for several entries, keyed by media path.

    Called in a worker thread by the card grid. One broken file must not
    discard the previews of the whole batch; it maps to None instead.
    """
    previews: dict[str, QImage | None] = {}
    for entry in entries:
        try:
            previews[entry.media_path] = load_thumbnail(entry, root, scope)
        except Exception:  # One bad file must not stop the batch.
            logger.debug(
                "Vorschau fehlgeschlagen: %s", entry.media_path, exc_info=True
            )
            previews[entry.media_path] = None
    return previews
