"""Dialog to choose which library groups are put on the wheel of fortune."""

from PyQt6.QtWidgets import QDialog, QHBoxLayout, QVBoxLayout, QWidget

from mediavault.gui.dialogs import checked_groups, group_checklist
from mediavault.gui.widgets import button, field_label


class GroupPickDialog(QDialog):
    """Dialog to choose which groups are put on the wheel of fortune.

    Attributes:
        selected_groups: The checked groups, set when the dialog was accepted.
    """

    def __init__(self, parent: QWidget | None, groups: list[str]) -> None:
        """Show one checkbox per group, all checked at first."""
        super().__init__(parent)
        self.selected_groups: list[str] = []
        self.setWindowTitle("Gruppen aufs Glücksrad")
        self.setMinimumSize(340, 420)
        self.resize(380, 480)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(12)
        layout.addWidget(field_label("Gruppen"))

        scroll, self.group_boxes = group_checklist(groups)
        for box in self.group_boxes.values():
            box.toggled.connect(self._sync_ok)
        layout.addWidget(scroll, 1)

        row = QHBoxLayout()
        row.setSpacing(8)
        btn_all = button("Alle", "ghost", lambda: self._set_all(True))
        btn_none = button("Keine", "ghost", lambda: self._set_all(False))
        btn_cancel = button("Abbrechen", "ghost", self.reject)
        self.btn_ok = button("Übernehmen", "primary", self._accept)
        row.addWidget(btn_all)
        row.addWidget(btn_none)
        row.addStretch()
        row.addWidget(btn_cancel)
        row.addWidget(self.btn_ok)
        layout.addLayout(row)
        self._sync_ok()

    def _set_all(self, checked: bool) -> None:
        """Check or uncheck every group."""
        for box in self.group_boxes.values():
            box.setChecked(checked)

    def _sync_ok(self) -> None:
        """Allow confirming only while at least one group is checked."""
        self.btn_ok.setEnabled(any(b.isChecked() for b in self.group_boxes.values()))

    def _accept(self) -> None:
        """Remember the checked groups and close the dialog."""
        self.selected_groups = checked_groups(self.group_boxes)
        self.accept()
