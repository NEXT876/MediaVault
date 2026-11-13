"""Preview of fetched plugin posts: a thumbnail grid with checkboxes.

All posts start checked; the user picks which ones go to the download queue.
"""

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import (
    QCheckBox,
    QDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from mediavault.gui.widgets import button
from mediavault.models import RemotePost


class PreviewDialog(QDialog):
    """Show fetched posts and let the user pick which ones to download.

    Each post is a 160 px thumbnail (or "keine Vorschau") with a checkbox
    labelled with its ID; the tooltip shows its title or group.
    """

    COLUMNS = 4
    THUMB = 160

    def __init__(
        self,
        parent: QWidget | None,
        title: str,
        posts: list[RemotePost],
        previews: dict[str, bytes],
    ) -> None:
        """Initialize the preview grid from fetched posts and thumbnails.

        Args:
            parent: Parent window.
            title: Plugin name, shown in the window title.
            posts: Fetched posts, newest first.
            previews: Thumbnail bytes by post ID; missing posts show a placeholder.
        """
        super().__init__(parent)
        self.setWindowTitle(f"{title} – Posts auswählen")
        self.resize(900, 700)
        self._boxes: dict[str, QCheckBox] = {}
        self._build_ui(posts, previews)

    def _build_ui(self, posts: list[RemotePost], previews: dict[str, bytes]) -> None:
        """Build the selection toolbar, image grid and dialog buttons."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(8)

        toolbar = QHBoxLayout()
        btn_all = QPushButton("Alle auswählen")
        btn_none = QPushButton("Keine")
        btn_all.clicked.connect(lambda: self._set_all(True))
        btn_none.clicked.connect(lambda: self._set_all(False))
        toolbar.addWidget(btn_all)
        toolbar.addWidget(btn_none)
        toolbar.addStretch()
        layout.addLayout(toolbar)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        grid = QGridLayout(content)
        for index, post in enumerate(posts):
            grid.addWidget(
                self._item(post, previews.get(post.id)),
                index // self.COLUMNS,
                index % self.COLUMNS,
            )
        grid.setRowStretch(grid.rowCount(), 1)
        scroll.setWidget(content)
        layout.addWidget(scroll)

        buttons = QHBoxLayout()
        buttons.addStretch()
        btn_cancel = button("Abbrechen", "ghost", self.reject)
        btn_start = button("Auswahl importieren", "primary", self.accept)
        buttons.addWidget(btn_cancel)
        buttons.addWidget(btn_start)
        layout.addLayout(buttons)

    def _item(self, post: RemotePost, data: bytes | None) -> QWidget:
        """Build one thumbnail with its selection checkbox, checked by default."""
        label = QLabel()
        label.setFixedSize(self.THUMB, self.THUMB)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        pixmap = QPixmap()
        if data and pixmap.loadFromData(data):
            label.setPixmap(
                pixmap.scaled(
                    self.THUMB,
                    self.THUMB,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )
        else:
            label.setText("keine Vorschau")

        box = QCheckBox(f"#{post.id}")
        box.setChecked(True)
        box.setToolTip(post.title or post.group)
        self._boxes[post.id] = box

        item = QWidget()
        column = QVBoxLayout(item)
        column.setContentsMargins(4, 4, 4, 4)
        column.addWidget(label)
        column.addWidget(box)
        return item

    def _set_all(self, checked: bool) -> None:
        """Check or uncheck every post."""
        for box in self._boxes.values():
            box.setChecked(checked)

    def selected_ids(self) -> set[str]:
        """Return the IDs of the checked posts."""
        return {post_id for post_id, box in self._boxes.items() if box.isChecked()}
