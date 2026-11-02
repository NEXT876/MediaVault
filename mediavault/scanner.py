"""Find media files in a folder that the database does not know yet."""

import logging
import os
from collections.abc import Iterable

from mediavault import volumes

logger = logging.getLogger(__name__)

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".bmp", ".webp"}
VIDEO_EXTS = {".mp4", ".mkv", ".avi", ".mov", ".webm", ".m4v", ".wmv"}


def is_video(path: str) -> bool:
    """Return True if a path has a video extension."""
    return os.path.splitext(path)[1].casefold() in VIDEO_EXTS


def find_new_media(
    folder: str,
    known_paths: Iterable[str],
    *,
    image_exts: Iterable[str] = IMAGE_EXTS,
    video_exts: Iterable[str] = VIDEO_EXTS,
    root: str = "",
) -> tuple[list[str], list[str]]:
    """Return the images and videos in folder that are not yet known.

    Known paths are compared through volumes.path_key, so entries stored
    relative to a volume still match the absolute paths found on disk.
    """
    if not os.path.isdir(folder):
        logger.warning("Ordner nicht gefunden: %s", folder)
        return [], []
    known = {volumes.path_key(path, root) for path in known_paths if path}
    images_ext = {extension.casefold() for extension in image_exts}
    videos_ext = {extension.casefold() for extension in video_exts}
    images: list[str] = []
    videos: list[str] = []
    for current, _dirs, files in os.walk(folder):
        for name in files:
            extension = os.path.splitext(name)[1].casefold()
            if extension in images_ext:
                bucket = images
            elif extension in videos_ext:
                bucket = videos
            else:
                continue
            path = os.path.join(current, name)
            if volumes.path_key(path, root) not in known:
                bucket.append(path)
    return sorted(images), sorted(videos)
