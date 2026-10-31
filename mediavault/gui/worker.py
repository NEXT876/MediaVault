"""Run one blocking call outside the GUI thread."""

from collections.abc import Callable
from typing import Any

from PyQt6.QtCore import QThread
from PyQt6.QtWidgets import QWidget


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
