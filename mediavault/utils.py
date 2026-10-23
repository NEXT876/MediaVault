"""Platform helpers for opening files and producing thumbnails."""

import hashlib
import logging
import os
import pathlib
import shutil
import subprocess
import sys

from PyQt6.QtCore import QUrl
from PyQt6.QtGui import QDesktopServices, QImage
from PyQt6.QtWidgets import QFileDialog, QWidget

logger = logging.getLogger(__name__)

try:
    import cv2

    HAS_CV2 = True
except ImportError:
    HAS_CV2 = False


class OSHelper:
    """Collection of platform-specific file and thumbnail helpers."""

    @staticmethod
    def open_file(path: str) -> None:
        """Open a file or URL with the system's default application."""
        if not path:
            return
        # Qt offers a portable way to open both local files and URLs.
        if path.startswith(("http://", "https://")):
            QDesktopServices.openUrl(QUrl(path))
        else:
            QDesktopServices.openUrl(QUrl.fromLocalFile(os.path.abspath(path)))

    @staticmethod
    def _linux_dialog_available() -> bool:
        """Return whether kdialog or zenity is available."""
        return bool(shutil.which("kdialog") or shutil.which("zenity"))

    @staticmethod
    def _filter_patterns(file_filter: str) -> str:
        """Extract the glob patterns from the first filter group.

        ``"Bilder (*.png *.jpg);;Alle (*.*)"`` becomes ``"*.png *.jpg"``.
        """
        if "(" not in file_filter or ")" not in file_filter:
            return ""
        first_group = file_filter.split(";;")[0]
        return first_group.split("(", 1)[1].rsplit(")", 1)[0]

    @staticmethod
    def _native_pick(
        multiple: bool, title: str, file_filter: str, start_dir: str
    ) -> list[str] | None:
        """Run the native Linux picker, or return ``None`` to use Qt instead."""
        if sys.platform != "linux" or not OSHelper._linux_dialog_available():
            return None

        patterns = OSHelper._filter_patterns(file_filter)
        if shutil.which("kdialog"):
            cmd = [
                "kdialog",
                "--title",
                title,
                "--getopenfilename",
                start_dir or os.path.expanduser("~"),
            ]
            if patterns:
                cmd.append(patterns)
            if multiple:
                cmd += ["--multiple", "--separate-output"]
        else:
            cmd = ["zenity", "--file-selection"]
            if multiple:
                cmd += ["--multiple", "--separator=\n"]
            cmd += ["--title", title]
            if patterns:
                cmd += ["--file-filter", patterns]
            if start_dir:
                cmd += ["--filename", start_dir + os.sep]

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=False)
            if result.returncode != 0:
                return None
            output = result.stdout.strip()
            if not multiple:
                return [output]
            return [path for path in output.split("\n") if path]
        except (OSError, subprocess.SubprocessError):
            logger.debug(
                "Nativer Dateidialog fehlgeschlagen, nutze Qt-Dialog", exc_info=True
            )
            return None

    @staticmethod
    def pick_file(
        parent: QWidget | None,
        title: str,
        file_filter: str,
        start_dir: str = "",
    ) -> tuple[str, str]:
        """Open a file picker for a single file and return its path."""
        paths = OSHelper._native_pick(False, title, file_filter, start_dir)
        if paths is not None:
            return (paths[0] if paths else ""), ""
        return QFileDialog.getOpenFileName(parent, title, start_dir, file_filter)

    @staticmethod
    def pick_files(
        parent: QWidget | None,
        title: str,
        file_filter: str,
        start_dir: str = "",
    ) -> tuple[list[str], str]:
        """Open a file picker for multiple files and return their paths."""
        paths = OSHelper._native_pick(True, title, file_filter, start_dir)
        if paths is not None:
            return paths, ""
        return QFileDialog.getOpenFileNames(parent, title, start_dir, file_filter)

    @staticmethod
    def get_os_thumbnail(video_path: str) -> str:
        """Return a system-cached thumbnail for a video (Linux only)."""
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

    @staticmethod
    def get_video_frame_image(video_path: str) -> QImage | None:
        """Extract a video frame as a QImage via OpenCV.

        QImage may be created in a worker thread; callers convert it to a
        QPixmap in the GUI thread.
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
