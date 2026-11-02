"""Collapsible sidebar section whose open/closed state is remembered."""

from PyQt6.QtCore import QSettings, Qt, pyqtSignal
from PyQt6.QtWidgets import QPushButton, QVBoxLayout, QWidget

from mediavault.gui.theme import APPLICATION, ORGANIZATION

ARROW_OPEN = "▾"
ARROW_CLOSED = "▸"


class CollapsibleSection(QWidget):
    """A clickable section header that shows or hides the widgets below it."""

    toggled = pyqtSignal(bool)

    def __init__(
        self,
        title: str,
        settings_key: str,
        *,
        expanded: bool = False,
        settings: QSettings | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._title = title
        self._settings_key = settings_key
        self._settings = settings or QSettings(ORGANIZATION, APPLICATION)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        self.header = QPushButton()
        self.header.setObjectName("SectionToggle")
        self.header.setCheckable(True)
        self.header.setCursor(Qt.CursorShape.PointingHandCursor)
        layout.addWidget(self.header)

        self.body = QWidget()
        self.body_layout = QVBoxLayout(self.body)
        self.body_layout.setContentsMargins(0, 0, 0, 0)
        self.body_layout.setSpacing(6)
        layout.addWidget(self.body)

        stored = self._settings.value(settings_key, expanded)
        self.set_expanded(stored in (True, "true", "1", 1), persist=False)
        self.header.toggled.connect(self.set_expanded)

    def add_widget(self, widget: QWidget) -> None:
        self.body_layout.addWidget(widget)

    def is_expanded(self) -> bool:
        return self.header.isChecked()

    def set_expanded(self, expanded: bool, persist: bool = True) -> None:
        """Open or close the section and remember the choice."""
        self.header.blockSignals(True)
        self.header.setChecked(expanded)
        self.header.blockSignals(False)
        arrow = ARROW_OPEN if expanded else ARROW_CLOSED
        self.header.setText(f"{arrow}  {self._title}")
        self.header.setToolTip("Zuklappen" if expanded else "Aufklappen")
        self.body.setVisible(expanded)
        if persist:
            self._settings.setValue(self._settings_key, expanded)
        self.toggled.emit(expanded)
