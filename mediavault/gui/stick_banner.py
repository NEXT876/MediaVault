"""Inline offer to set up a removable volume that no config uses yet.

The main window periodically checks for connected vault volumes; when one
is not assigned to any config, this banner appears above the grid with a
button that opens the stick setup dialog.
"""

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QHBoxLayout, QWidget

from mediavault.gui.widgets import button, hint_label
from mediavault.volumes import VolumeInfo


class StickBanner(QWidget):
    """Offer the first unused vault volume and remember dismissals.

    Signals:
        setup_requested: The user clicked "Einrichten…".
    """

    setup_requested = pyqtSignal()

    def __init__(self, parent: QWidget | None = None) -> None:
        """Build the banner hidden; offer() decides when it appears."""
        super().__init__(parent)
        self.setObjectName("ActionBar")
        self._offered = ""
        self._dismissed = ""
        row = QHBoxLayout(self)
        row.setContentsMargins(12, 8, 12, 8)
        row.setSpacing(10)
        self._label = hint_label()
        row.addWidget(self._label, 1)
        setup = button("Einrichten…", "primary", self.setup_requested.emit)
        row.addWidget(setup)
        close = button(
            "×",
            "ghost",
            self._dismiss,
            tooltip="Diesen Stick in dieser Sitzung nicht mehr anbieten",
        )
        close.setFixedWidth(34)
        row.addWidget(close)
        self.hide()

    def offer(self, unused: list[tuple[str, VolumeInfo]]) -> None:
        """Show the first stick that no config uses yet, or hide the banner.

        A stick the user dismissed this session is not shown again.

        Args:
            unused: ``(mount point, identity)`` of unassigned vault volumes.
        """
        if not unused:
            self._offered = ""
            self.hide()
            return
        root, info = unused[0]
        if info.uuid == self._dismissed:
            return
        self._offered = info.uuid
        self._label.setText(
            f"🔌 Stick „{info.label or root}“ erkannt ({root}) – noch keiner "
            "Config zugeordnet."
        )
        self.show()

    def _dismiss(self) -> None:
        """Stop offering the current stick for the rest of the session."""
        self._dismissed = self._offered
        self.hide()
