"""Preview sources for videos, safe to call outside the GUI thread.

Two sources are tried by :mod:`mediavault.gui.thumbnails`: a thumbnail the
desktop environment already cached (Linux freedesktop thumbnail spec) and,
as fallback, a frame extracted with OpenCV. OpenCV is optional; without it
:data:`HAS_CV2` is False and no frames are extracted.

Only ``QImage`` is used from Qt, so workers may call these freely; callers
turn the image into a ``QPixmap`` on the GUI thread.
"""

import hashlib
import logging
import os
import pathlib
import sys

from PyQt6.QtGui import QImage

logger = logging.getLogger(__name__)

try:
    import cv2

    HAS_CV2 = True
except ImportError:
    HAS_CV2 = False


def get_os_thumbnail(video_path: str) -> str:
    """Return a system-cached thumbnail for a video (Linux only).

    Looks up ``~/.cache/thumbnails/{large,normal}/<md5 of file URI>.png`` as
    defined by the freedesktop thumbnail specification.

    Returns:
        The thumbnail path, or an empty string on other platforms or when the
        desktop has not created one.
    """
    if sys.platform != "linux" or not video_path:
        return ""
    try:
        abs_path = os.path.abspath(video_path)
        uri = pathlib.Path(abs_path).as_uri()
        hash_md5 = hashlib.md5(uri.encode("utf-8")).hexdigest()
        cache_dir = os.path.expanduser("~/.cache/thumbnails")
        for size in ["large", "normal"]:
            thumb_path = os.path.join(cache_dir, size, f"{hash_md5}.png")
            if os.path.exists(thumb_path):
                return thumb_path
    except (OSError, ValueError):
        logger.debug(
            "System-Thumbnail konnte nicht ermittelt werden", exc_info=True
        )
    return ""


def get_video_frame_image(video_path: str) -> QImage | None:
    """Extract a video frame as a QImage via OpenCV.

    Takes frame 60 (about two seconds in, past black intros) and falls back to
    the first frame for very short videos.

    Returns:
        A detached RGB image, or None without OpenCV or when the video cannot
        be decoded.
    """
    if not HAS_CV2 or not video_path:
        return None
    try:
        cap = cv2.VideoCapture(video_path)
        cap.set(cv2.CAP_PROP_POS_FRAMES, 60)
        ret, frame = cap.read()
        if not ret:
            cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            ret, frame = cap.read()
        cap.release()
        if ret:
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            h, w, ch = frame_rgb.shape
            bytes_per_line = ch * w
            # copy(): the image must not keep pointing at the numpy buffer.
            return QImage(
                frame_rgb.data,
                w,
                h,
                bytes_per_line,
                QImage.Format.Format_RGB888,
            ).copy()
    except cv2.error:
        logger.debug("Videoframe konnte nicht extrahiert werden", exc_info=True)
    return None
