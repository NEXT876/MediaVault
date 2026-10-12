import os
import sys
import pathlib
import hashlib
from PyQt6.QtGui import QDesktopServices, QPixmap, QImage
from PyQt6.QtCore import QUrl

try:
    import cv2
    HAS_CV2 = True
except ImportError:
    HAS_CV2 = False

class OSHelper:
    @staticmethod
    def open_file(path):
        if not path: return
        # Qt hat eine plattformunabhängige native Methode zum Öffnen von Dateien/URLs
        if path.startswith("http://") or path.startswith("https://"):
            QDesktopServices.openUrl(QUrl(path))
        else:
            QDesktopServices.openUrl(QUrl.fromLocalFile(os.path.abspath(path)))

    @staticmethod
    def get_os_thumbnail(video_path):
        if sys.platform != "linux" or not video_path: return ""
        try:
            abs_path = os.path.abspath(video_path)
            uri = pathlib.Path(abs_path).as_uri()
            hash_md5 = hashlib.md5(uri.encode('utf-8')).hexdigest()
            cache_dir = os.path.expanduser("~/.cache/thumbnails")
            for size in ["large", "normal"]:
                thumb_path = os.path.join(cache_dir, size, f"{hash_md5}.png")
                if os.path.exists(thumb_path): return thumb_path
        except Exception: pass
        return ""

    @staticmethod
    def get_video_frame_pixmap(video_path):
        if not HAS_CV2 or not video_path: return None
        try:
            cap = cv2.VideoCapture(video_path)
            cap.set(cv2.CAP_PROP_POS_FRAMES, 60)
            ret, frame = cap.read()
            cap.release()
            if ret:
                frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                h, w, ch = frame_rgb.shape
                bytes_per_line = ch * w
                qimg = QImage(frame_rgb.data, w, h, bytes_per_line, QImage.Format.Format_RGB888)
                return QPixmap.fromImage(qimg)
        except Exception: pass
        return None