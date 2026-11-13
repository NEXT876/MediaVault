"""Run one blocking call outside the GUI thread.

Folder scans and imports can take seconds on large libraries or slow
volumes. :func:`run_with_progress` runs such a call in a :class:`Worker`
thread behind a modal busy dialog and hands the result back on the GUI
thread, so the window stays responsive and cannot be edited meanwhile.
"""

from collections.abc import Callable
from typing import Any

from PyQt6.QtCore import Qt, QThread
from PyQt6.QtWidgets import QProgressDialog, QWidget


class Worker(QThread):
    """Run one blocking call outside the GUI thread.

    The outcome is stored instead of emitted: after ``finished`` fires, read
    ``result`` or ``error`` on the GUI thread.

    Attributes:
        result: Return value of the call, or None.
        error: Exception raised by the call, or None.
    """

    def __init__(self, parent: QWidget, fn: Callable[..., Any], **kwargs: Any) -> None:
        """Prepare the call; nothing runs until :meth:`start`.

        Args:
            parent: Owner widget, keeps the thread alive.
            fn: Blocking function to call.
            **kwargs: Keyword arguments passed to ``fn``.
        """
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
    """Run ``fn`` in the background behind a modal busy dialog.

    The dialog has no cancel button and blocks its parent window until the call
    finished. ``on_done`` receives the finished worker after the dialog closed;
    it must check ``worker.error`` before using ``worker.result``. The worker is
    deleted afterwards.

    Args:
        parent: Window the dialog is modal to.
        text: Message shown in the busy dialog.
        fn: Blocking function to call.
        on_done: Callback on the GUI thread.
        **kwargs: Keyword arguments passed to ``fn``.
    """
    progress = QProgressDialog(text, "", 0, 0, parent)
    progress.setCancelButton(None)
    progress.setWindowModality(Qt.WindowModality.WindowModal)
    progress.setMinimumDuration(0)
    worker = Worker(parent, fn, **kwargs)

    def finish() -> None:
        """Close the dialog, schedule cleanup and report back."""
        progress.close()
        progress.deleteLater()
        worker.deleteLater()
        on_done(worker)

    worker.finished.connect(finish)
    worker.start()
    progress.show()
