"""Dialogs for the rule34 import: settings, tag help and post preview."""

import urllib.parse
from typing import Any

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QPixmap, QTextCursor
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QGridLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from mediavault.config import VaultConfig, save_configs
from mediavault.gui.widgets import field_label
from mediavault.gui.worker import Worker
from mediavault.rule34 import Post, fetch_tag_suggestions, split_queries, tag_at


class Rule34Dialog(QDialog):
    """Collect rule34 credentials and search settings for the active config."""

    def __init__(
        self, parent: QWidget | None, config: VaultConfig, configs: list[VaultConfig]
    ) -> None:
        """Initialize the form from the config's saved values."""
        super().__init__(parent)
        self.setWindowTitle("rule34.xxx Import")
        self.setMinimumWidth(480)
        self.config = config
        self.configs = configs
        self._suggest_worker: Worker | None = None
        self._suggest_word = ""
        self._suggest_range = (0, 0)
        self._suggest_pending = False
        self._build_ui(config)

    def _build_ui(self, config: VaultConfig) -> None:
        """Build the credential, tag and download settings form."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(8)

        layout.addWidget(field_label("Zugangsdaten einfügen"))
        self.inp_credentials = QLineEdit()
        self.inp_credentials.setPlaceholderText(
            "&api_key=…&user_id=… oder komplette URL einfügen"
        )
        self.inp_credentials.textChanged.connect(self._apply_credentials)
        layout.addWidget(self.inp_credentials)

        layout.addWidget(field_label("API-Key"))
        self.inp_key = QLineEdit(config.rule34.api_key)
        self.inp_key.setEchoMode(QLineEdit.EchoMode.Password)
        layout.addWidget(self.inp_key)

        layout.addWidget(field_label("User-ID"))
        self.inp_user = QLineEdit(config.rule34.user_id)
        layout.addWidget(self.inp_user)

        layout.addWidget(field_label("Tags / Charaktere (eine Suche pro Zeile)"))
        self.inp_tags = QPlainTextEdit(config.rule34.tags)
        self.inp_tags.setPlaceholderText(
            "z. B. character_name other_tag\noder eine Suche pro Zeile"
        )
        self.inp_tags.setFixedHeight(90)
        self.inp_tags.setTabChangesFocus(True)
        self.inp_tags.textChanged.connect(self._schedule_suggestions)
        self.inp_tags.cursorPositionChanged.connect(self._schedule_suggestions)
        layout.addWidget(self.inp_tags)

        self.lst_tags = QListWidget()
        self.lst_tags.setMaximumHeight(110)
        self.lst_tags.setVisible(False)
        self.lst_tags.itemClicked.connect(self._apply_suggestion)
        self.lst_tags.itemActivated.connect(self._apply_suggestion)
        layout.addWidget(self.lst_tags)

        saved_row = QHBoxLayout()
        self.combo_saved_tags = QComboBox()
        self.combo_saved_tags.activated.connect(self._load_saved_tags)
        btn_save_tags = QPushButton("Tags speichern")
        btn_save_tags.setProperty("variant", "ghost")
        btn_save_tags.clicked.connect(self._save_saved_tags)
        btn_delete_tags = QPushButton("Löschen")
        btn_delete_tags.setProperty("variant", "ghost")
        btn_delete_tags.clicked.connect(self._delete_saved_tags)
        saved_row.addWidget(self.combo_saved_tags, 1)
        saved_row.addWidget(btn_save_tags)
        saved_row.addWidget(btn_delete_tags)
        layout.addLayout(saved_row)
        self._refresh_saved_tags()

        self._suggest_timer = QTimer(self)
        self._suggest_timer.setSingleShot(True)
        self._suggest_timer.setInterval(350)
        self._suggest_timer.timeout.connect(self._request_suggestions)

        layout.addWidget(field_label("Anzahl der neuesten Posts"))
        self.spin_count = QSpinBox()
        self.spin_count.setRange(1, 200)
        self.spin_count.setValue(config.rule34.count)
        layout.addWidget(self.spin_count)

        self.chk_webm = QCheckBox("Nur Videos (webm)")
        self.chk_webm.setChecked(config.rule34.webm)
        layout.addWidget(self.chk_webm)

        self.chk_reset = QCheckBox("Cache zurücksetzen (neueste Posts erneut holen)")
        self.chk_reset.setToolTip(
            "Ignoriert die zuletzt importierte ID. Bereits vorhandene Dateien "
            "werden trotzdem übersprungen."
        )
        layout.addWidget(self.chk_reset)

        hint = QLabel(
            "Key und User-ID stehen unter rule34.xxx → Account options → "
            "API Access Credentials; du kannst beide auch zusammen in das "
            "obere Feld einfügen. Beides wird im Klartext in configs.json "
            "gespeichert. Eine Suche pro Zeile; die Anzahl gilt pro Zeile. "
            "Eigene sort:-Tags werden ignoriert; die neuesten IDs kommen zuerst."
        )
        hint.setObjectName("MutedLabel")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        buttons = QHBoxLayout()
        buttons.addStretch()
        btn_cancel = QPushButton("Abbrechen")
        btn_cancel.setProperty("variant", "ghost")
        btn_cancel.clicked.connect(self.reject)
        btn_start = QPushButton("Importieren")
        btn_start.setProperty("variant", "primary")
        btn_start.clicked.connect(self._accept)
        buttons.addWidget(btn_cancel)
        buttons.addWidget(btn_start)
        layout.addLayout(buttons)

    def _apply_credentials(self, text: str) -> None:
        """Fill key and user ID from a pasted parameter string or URL."""
        query = urllib.parse.urlsplit(text.strip()).query or text.strip().lstrip("&")
        values = urllib.parse.parse_qs(query)
        if values.get("api_key"):
            self.inp_key.setText(values["api_key"][0])
        if values.get("user_id"):
            self.inp_user.setText(values["user_id"][0])

    def _schedule_suggestions(self) -> None:
        """Restart the debounce timer for tag suggestions."""
        self._suggest_timer.start()

    def _request_suggestions(self) -> None:
        """Ask rule34 for tags matching the word at the cursor."""
        if self._suggest_worker is not None:
            self._suggest_pending = True
            return
        word, start, end = tag_at(
            self.inp_tags.toPlainText(), self.inp_tags.textCursor().position()
        )
        if len(word) < 2 or ":" in word:
            self._hide_suggestions()
            return
        self._suggest_word = word
        self._suggest_range = (start, end)
        self._suggest_worker = Worker(self, fetch_tag_suggestions, prefix=word)
        self._suggest_worker.finished.connect(self._on_suggestions)
        self._suggest_worker.start()

    def _on_suggestions(self) -> None:
        """Show suggestions if the requested word is still current."""
        worker = self._suggest_worker
        self._suggest_worker = None
        if worker is not None:
            names = worker.result if worker.error is None else []
            start, end = self._suggest_range
            if names and self.inp_tags.toPlainText()[start:end] == self._suggest_word:
                self._show_suggestions(names)
            else:
                self._hide_suggestions()
        if self._suggest_pending:
            self._suggest_pending = False
            self._suggest_timer.start()

    def _show_suggestions(self, names: list[str]) -> None:
        """Fill and show the suggestion list."""
        self.lst_tags.clear()
        self.lst_tags.addItems(names)
        self.lst_tags.setVisible(True)

    def _hide_suggestions(self) -> None:
        """Hide and empty the suggestion list."""
        self.lst_tags.clear()
        self.lst_tags.setVisible(False)

    def _apply_suggestion(self, item: QListWidgetItem) -> None:
        """Replace the current word with the clicked suggestion."""
        start, end = self._suggest_range
        if self.inp_tags.toPlainText()[start:end] != self._suggest_word:
            self._hide_suggestions()
            return
        cursor = self.inp_tags.textCursor()
        cursor.setPosition(start)
        cursor.setPosition(end, QTextCursor.MoveMode.KeepAnchor)
        cursor.insertText(item.text() + " ")
        self.inp_tags.setTextCursor(cursor)
        self.inp_tags.setFocus()
        self._suggest_word = ""
        self._hide_suggestions()

    def _refresh_saved_tags(self, selected: str | None = None) -> None:
        """Rebuild the preset list and optionally select one entry."""
        self.combo_saved_tags.clear()
        self.combo_saved_tags.addItem("Gespeicherte Tag-Configs …", "")
        for name in sorted(self.config.rule34.saved_tags, key=str.casefold):
            self.combo_saved_tags.addItem(name, name)
        if selected:
            self.combo_saved_tags.setCurrentIndex(
                max(self.combo_saved_tags.findData(selected), 0)
            )

    def _load_saved_tags(self) -> None:
        """Replace the tag field with the selected saved preset."""
        name = self.combo_saved_tags.currentData()
        if name:
            self.inp_tags.setPlainText(self.config.rule34.saved_tags[name])

    def _save_saved_tags(self) -> None:
        """Store the current tag text under a name the user chooses."""
        text = "\n".join(split_queries(self.inp_tags.toPlainText()))
        if not text:
            QMessageBox.warning(self, "Fehler", "Mindestens ein Tag ist erforderlich.")
            return
        name, ok = QInputDialog.getText(
            self, "Tags speichern", "Name für diese Tag-Config:", text=text.splitlines()[0]
        )
        name = name.strip()
        if not ok or not name:
            return
        # An existing name is overwritten on purpose: that is how a preset
        # gets updated after the user changed the tags.
        self.config.rule34.saved_tags[name] = text
        save_configs(self.configs, self.config.db_path)
        self._refresh_saved_tags(name)

    def _delete_saved_tags(self) -> None:
        """Remove the selected preset after confirmation."""
        name = self.combo_saved_tags.currentData()
        if not name:
            return
        answer = QMessageBox.question(
            self, "Tags löschen", f"Gespeicherte Tags „{name}“ löschen?"
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self.config.rule34.saved_tags.pop(name, None)
        save_configs(self.configs, self.config.db_path)
        self._refresh_saved_tags()

    def done(self, result: int) -> None:
        """Stop the suggestion timer and worker before the dialog closes."""
        self._suggest_timer.stop()
        worker = self._suggest_worker
        self._suggest_worker = None
        if worker is not None:
            worker.finished.disconnect(self._on_suggestions)
            worker.wait()
        super().done(result)

    def _accept(self) -> None:
        """Validate the required fields before closing."""
        if not self.inp_key.text().strip():
            QMessageBox.warning(self, "Fehler", "API-Key ist erforderlich.")
            return
        if not self.inp_user.text().strip():
            QMessageBox.warning(self, "Fehler", "User-ID ist erforderlich.")
            return
        if not split_queries(self.inp_tags.toPlainText()):
            QMessageBox.warning(self, "Fehler", "Mindestens ein Tag ist erforderlich.")
            return
        self.accept()

    def settings(self) -> dict[str, Any]:
        """Return the entered settings as config field values."""
        return {
            "api_key": self.inp_key.text().strip(),
            "user_id": self.inp_user.text().strip(),
            "tags": "\n".join(split_queries(self.inp_tags.toPlainText())),
            "count": self.spin_count.value(),
            "webm": self.chk_webm.isChecked(),
        }


class Rule34PreviewDialog(QDialog):
    """Show fetched posts and let the user pick which ones to download."""

    COLUMNS = 4
    THUMB = 160

    def __init__(
        self,
        parent: QWidget | None,
        posts: list[Post],
        previews: dict[int, bytes],
    ) -> None:
        """Initialize the preview grid from fetched posts and thumbnails."""
        super().__init__(parent)
        self.setWindowTitle("rule34.xxx – Posts auswählen")
        self.resize(900, 700)
        self._boxes: dict[int, QCheckBox] = {}
        self._build_ui(posts, previews)

    def _build_ui(self, posts: list[Post], previews: dict[int, bytes]) -> None:
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
        btn_cancel = QPushButton("Abbrechen")
        btn_cancel.setProperty("variant", "ghost")
        btn_cancel.clicked.connect(self.reject)
        btn_start = QPushButton("Auswahl importieren")
        btn_start.setProperty("variant", "primary")
        btn_start.clicked.connect(self.accept)
        buttons.addWidget(btn_cancel)
        buttons.addWidget(btn_start)
        layout.addLayout(buttons)

    def _item(self, post: Post, data: bytes | None) -> QWidget:
        """Build one thumbnail with its selection checkbox."""
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
        box.setToolTip(post.group)
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

    def selected_ids(self) -> set[int]:
        """Return the IDs of the checked posts."""
        return {post_id for post_id, box in self._boxes.items() if box.isChecked()}
