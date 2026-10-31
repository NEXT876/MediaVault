"""Inline offer to set up a removable volume that no config uses yet."""

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QWidget

from mediavault.volumes import VolumeInfo


class StickBanner(QWidget):
    """Offer the first unused vault volume and remember dismissals."""

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
        self._label = QLabel("")
        self._label.setObjectName("HintLabel")
        self._label.setWordWrap(True)
        row.addWidget(self._label, 1)
        setup = QPushButton("Einrichten…")
        setup.setProperty("variant", "primary")
        setup.clicked.connect(self.setup_requested.emit)
        row.addWidget(setup)
        close = QPushButton("×")
        close.setProperty("variant", "ghost")
        close.setFixedWidth(34)
        close.setToolTip("Diesen Stick in dieser Sitzung nicht mehr anbieten")
        close.clicked.connect(self._dismiss)
        row.addWidget(close)
        self.hide()

    def offer(self, unused: list[tuple[str, VolumeInfo]]) -> None:
        """Show the first stick that no config uses yet."""
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
