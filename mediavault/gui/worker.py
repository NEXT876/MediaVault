"""Run one blocking call outside the GUI thread."""

from collections.abc import Callable
from typing import Any

from PyQt6.QtCore import Qt, QThread
from PyQt6.QtWidgets import QProgressDialog, QWidget


class Worker(QThread):
    """Run one blocking call outside the GUI thread."""

    def __init__(self, parent: QWidget, fn: Callable[..., Any], **kwargs: Any) -> None:
        super().__init__(parent)
        self._fn = fn
        self._kwargs = kwargs
        self.result: Any = None
        self.error: Exception | None = None

    def run(self) -> None:
        """Run the call and store its outcome for the GUI thread."""
        try:
            self.result = self._fn(**self._kwargs)
        except Exception as exc:  # noqa: BLE001 - reported in the GUI thread
            self.error = exc


def run_with_progress(
    parent: QWidget,
    text: str,
    fn: Callable[..., Any],
    on_done: Callable[[Worker], None],
    **kwargs: Any,
) -> None:
    """Run fn in the background behind a modal busy dialog.

    on_done receives the finished worker after the dialog closed; the worker
    is deleted afterwards.
    """
    progress = QProgressDialog(text, "", 0, 0, parent)
    progress.setCancelButton(None)
    progress.setWindowModality(Qt.WindowModality.WindowModal)
    progress.setMinimumDuration(0)
    worker = Worker(parent, fn, **kwargs)

    def finish() -> None:
        progress.close()
        progress.deleteLater()
        worker.deleteLater()
        on_done(worker)

    worker.finished.connect(finish)
    worker.start()
    progress.show()
