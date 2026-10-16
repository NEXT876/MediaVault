import os
import sys
import shutil
import pathlib
import hashlib
import subprocess
from PyQt6.QtGui import QDesktopServices, QPixmap, QImage
from PyQt6.QtCore import QUrl
from PyQt6.QtWidgets import QFileDialog

try:
    import cv2
    HAS_CV2 = True
except ImportError:
    HAS_CV2 = False

class OSHelper:
    """Sammlung plattformbezogener Hilfsfunktionen für Dateien und Thumbnails."""

    @staticmethod
    def open_file(path):
        """Öffnet eine Datei oder URL mit der Standard-Anwendung des Systems."""
        if not path:
            return
        # Qt hat eine plattformunabhängige native Methode zum Öffnen von Dateien/URLs
        if path.startswith("http://") or path.startswith("https://"):
            QDesktopServices.openUrl(QUrl(path))
        else:
            QDesktopServices.openUrl(QUrl.fromLocalFile(os.path.abspath(path)))

    @staticmethod
    def _linux_dialog_available():
        """Prüft, ob kdialog oder zenity auf dem System verfügbar ist."""
        return shutil.which("kdialog") or shutil.which("zenity")

    @staticmethod
    def pick_file(parent, title, file_filter, start_dir=""):
        """Öffnet den nativen System-Dateidialog (Linux: kdialog/zenity, sonst Qt)."""
        if sys.platform == "linux" and OSHelper._linux_dialog_available():
            # Filter für kdialog/zenity aufbereiten: "Bilder (*.png *.jpg)" -> "*.png *.jpg"
            patterns = ""
            if "(" in file_filter and ")" in file_filter:
                first_group = file_filter.split(";;")[0]
                patterns = first_group.split("(", 1)[1].rsplit(")", 1)[0]

            if shutil.which("kdialog"):
                cmd = ["kdialog", "--title", title, "--getopenfilename", start_dir or os.path.expanduser("~")]
                if patterns:
                    cmd.append(patterns)
            else:
                cmd = ["zenity", "--file-selection", "--title", title]
                if patterns:
                    cmd += ["--file-filter", patterns]
                if start_dir:
                    cmd += ["--filename", start_dir + os.sep]

            try:
                result = subprocess.run(cmd, capture_output=True, text=True)
                if result.returncode == 0:
                    return result.stdout.strip(), ""
            except Exception:
                pass

        return QFileDialog.getOpenFileName(parent, title, start_dir, file_filter)

    @staticmethod
    def pick_files(parent, title, file_filter, start_dir=""):
        """Öffnet den nativen System-Dateidialog für Mehrfachauswahl."""
        if sys.platform == "linux" and OSHelper._linux_dialog_available():
            patterns = ""
            if "(" in file_filter and ")" in file_filter:
                first_group = file_filter.split(";;")[0]
                patterns = first_group.split("(", 1)[1].rsplit(")", 1)[0]

            if shutil.which("kdialog"):
                cmd = ["kdialog", "--title", title, "--getopenfilename", start_dir or os.path.expanduser("~")]
                if patterns:
                    cmd.append(patterns)
                cmd += ["--multiple", "--separate-output"]
            else:
                sep = "\n"
                cmd = ["zenity", "--file-selection", "--multiple", "--separator=" + sep, "--title", title]
                if patterns:
                    cmd += ["--file-filter", patterns]
                if start_dir:
                    cmd += ["--filename", start_dir + os.sep]

            try:
                result = subprocess.run(cmd, capture_output=True, text=True)
                if result.returncode == 0:
                    paths = [p for p in result.stdout.strip().split("\n") if p]
                    return paths, ""
            except Exception:
                pass

        return QFileDialog.getOpenFileNames(parent, title, start_dir, file_filter)

    @staticmethod
    def get_os_thumbnail(video_path):
        """Sucht ein vom System gecachtes Vorschaubild (nur Linux)."""
        if sys.platform != "linux" or not video_path:
            return ""
        try:
            abs_path = os.path.abspath(video_path)
            uri = pathlib.Path(abs_path).as_uri()
            hash_md5 = hashlib.md5(uri.encode('utf-8')).hexdigest()
            cache_dir = os.path.expanduser("~/.cache/thumbnails")
            for size in ["large", "normal"]:
                thumb_path = os.path.join(cache_dir, size, f"{hash_md5}.png")
                if os.path.exists(thumb_path):
                    return thumb_path
        except Exception:
            pass
        return ""

    @staticmethod
    def get_video_frame_pixmap(video_path):
        """Extrahiert einen Videoframe als QPixmap via OpenCV."""
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
                qimg = QImage(frame_rgb.data, w, h, bytes_per_line, QImage.Format.Format_RGB888)
                return QPixmap.fromImage(qimg)
        except Exception:
            pass
        return None
