"""Native file pickers and opening files with the system application.

On Linux the Qt file dialog does not match KDE/GNOME, so ``kdialog`` or
``zenity`` is used when installed; otherwise, and on other platforms, the
Qt dialog is the fallback. The pick functions return the same tuple shape
as ``QFileDialog`` so callers do not care which dialog ran.
"""

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
    """Open a local file or an http(s) URL with the system's default application."""
    if not path:
        return
    # Qt offers a portable way to open both local files and URLs.
    if path.startswith(("http://", "https://")):
        QDesktopServices.openUrl(QUrl(path))
    else:
        QDesktopServices.openUrl(QUrl.fromLocalFile(os.path.abspath(path)))


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
    """Run the native Linux picker, or return None to use Qt instead.

    Prefers ``kdialog`` over ``zenity``. None means "no native picker or it
    failed"; an empty list means the user cancelled.
    """
    has_picker = shutil.which("kdialog") or shutil.which("zenity")
    if sys.platform != "linux" or not has_picker:
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
            "Native file dialog failed, using the Qt dialog", exc_info=True
        )
        return None


def pick_file(
    parent: QWidget | None,
    title: str,
    file_filter: str,
    start_dir: str = "",
) -> tuple[str, str]:
    """Open a file picker for a single file.

    Args:
        parent: Parent of the Qt fallback dialog.
        title: Dialog title.
        file_filter: Qt filter string, e.g. from :func:`library.file_filter`.
        start_dir: Folder to open first.

    Returns:
        ``(path, selected filter)``; the path is empty when cancelled.
    """
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
    """Open a file picker for multiple files.

    Returns:
        ``(paths, selected filter)``; the list is empty when cancelled.
    """
    paths = _native_pick(True, title, file_filter, start_dir)
    if paths is not None:
        return paths, ""
    return QFileDialog.getOpenFileNames(parent, title, start_dir, file_filter)
