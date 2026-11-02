"""Native file pickers and opening files with the system application."""

import logging
import os
import shutil
import subprocess
import sys

from PyQt6.QtCore import QUrl
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import QFileDialog, QWidget

logger = logging.getLogger(__name__)


def open_file(path: str) -> None:
    """Open a file or URL with the system's default application."""
    if not path:
        return
    # Qt offers a portable way to open both local files and URLs.
    if path.startswith(("http://", "https://")):
        QDesktopServices.openUrl(QUrl(path))
    else:
        QDesktopServices.openUrl(QUrl.fromLocalFile(os.path.abspath(path)))


def _linux_dialog_available() -> bool:
    """Return whether kdialog or zenity is available."""
    return bool(shutil.which("kdialog") or shutil.which("zenity"))


def _filter_patterns(file_filter: str) -> str:
    """Extract the glob patterns from the first filter group.

    ``"Bilder (*.png *.jpg);;Alle (*.*)"`` becomes ``"*.png *.jpg"``.
    """
    if "(" not in file_filter or ")" not in file_filter:
        return ""
    first_group = file_filter.split(";;")[0]
    return first_group.split("(", 1)[1].rsplit(")", 1)[0]


def _native_pick(
    multiple: bool, title: str, file_filter: str, start_dir: str
) -> list[str] | None:
    """Run the native Linux picker, or return ``None`` to use Qt instead."""
    if sys.platform != "linux" or not _linux_dialog_available():
        return None

    patterns = _filter_patterns(file_filter)
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


def pick_file(
    parent: QWidget | None,
    title: str,
    file_filter: str,
    start_dir: str = "",
) -> tuple[str, str]:
    """Open a file picker for a single file and return its path."""
    paths = _native_pick(False, title, file_filter, start_dir)
    if paths is not None:
        return (paths[0] if paths else ""), ""
    return QFileDialog.getOpenFileName(parent, title, start_dir, file_filter)


def pick_files(
    parent: QWidget | None,
    title: str,
    file_filter: str,
    start_dir: str = "",
) -> tuple[list[str], str]:
    """Open a file picker for multiple files and return their paths."""
    paths = _native_pick(True, title, file_filter, start_dir)
    if paths is not None:
        return paths, ""
    return QFileDialog.getOpenFileNames(parent, title, start_dir, file_filter)
