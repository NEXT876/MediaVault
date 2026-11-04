"""Modal dialogs of the main window.

- :class:`DetailDialog`: preview, statistics, quick rating and playback of
  one entry.
- :class:`EditDialog`: create or edit an entry (title, group, description,
  score, file paths).
- :class:`GroupRandomDialog` / :class:`GroupPickDialog`: choose groups for
  a random pick or for the wheel of fortune.
- :class:`ConfigDialog`: switch to another config or create a new one.
- :class:`FolderPreviewDialog`: confirm files found by a folder sync.
- :class:`AnalysisDialog`: prompt statistics of an AI config.

Dialogs that change entries save the database themselves, except
:class:`EditDialog` edits of existing entries, which the caller saves.
"""

import os
import time
from collections.abc import Callable
from functools import partial
from html import escape
from typing import Any

from PyQt6.QtCore import QSize, Qt
from PyQt6.QtGui import QIcon, QPixmap
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QScrollArea,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from mediavault import volumes
from mediavault.ai_meta import format_ai_meta, summarize_prompts
from mediavault.config import (
    MODE_AI,
    MODE_NORMAL,
    VaultConfig,
    create_config,
    locate,
    save_configs,
)
from mediavault.gui import file_dialogs
from mediavault.gui.widgets import button, field_label, hint_label, rounded_pixmap
from mediavault.importer import content_hash
from mediavault.models import MediaDatabase, MediaItem, MediaType


class DetailDialog(QDialog):
    """Dialog with preview, statistics and rating buttons for one entry.

    Rating buttons 1-5 change the score by -10/-5/0/+5/+10 (clamped to 1-100)
    and also count as a viewing. Opening the file counts as a viewing too.
    Every change is saved immediately.

    Attributes:
        edit_requested: True when the user asked to edit the entry; the caller
            then opens :class:`EditDialog`.
    """

    def __init__(
        self,
        parent: QWidget | None,
        entry: MediaItem,
        db: MediaDatabase,
        get_pixmap_func: Callable[[MediaItem], QPixmap | None],
        root: str = "",
    ) -> None:
        """Initialize the detail dialog for ``entry``.

        Args:
            parent: Parent window.
            entry: Entry to show.
            db: Database that is saved after ratings and viewings.
            get_pixmap_func: Returns the entry's preview (the grid's cache).
            root: Volume root to resolve relative paths.
        """
        super().__init__(parent)
        self.entry = entry
        self.db = db
        self.get_pixmap = get_pixmap_func
        self.root = root
        self.setWindowTitle(entry.title)
        self.setMinimumSize(540, 720)
        self.resize(560, 760)
        self.edit_requested = False
        self._build_ui()

    def _build_ui(self) -> None:
        """Build the layout from top to bottom.

        Preview, title, group, play button, description, AI metadata and prompts,
        statistics, rating buttons and the edit/close actions; optional parts only
        appear when the entry has them.
        """
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(12)

        img_lbl = QLabel()
        img_lbl.setObjectName("DialogImage")
        img_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        img_lbl.setMinimumHeight(330)
        pixmap = self.get_pixmap(self.entry)
        if pixmap and not pixmap.isNull():
            img_lbl.setPixmap(rounded_pixmap(pixmap, size=320, radius=12))
        else:
            img_lbl.setText("Kein Vorschaubild")
        layout.addWidget(img_lbl, alignment=Qt.AlignmentFlag.AlignHCenter)

        title_lbl = QLabel(self.entry.title)
        title_lbl.setObjectName("DialogTitle")
        title_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_lbl.setWordWrap(True)
        layout.addWidget(title_lbl)

        grp_text = f"📂 {self.entry.group}" if self.entry.group else "📂 Keine Gruppe"
        grp_lbl = QLabel(grp_text)
        grp_lbl.setObjectName("MutedLabel")
        grp_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(grp_lbl)

        if self.entry.file_path:
            btn_play = button(
                "▶  Abspielen / Öffnen",
                "primary",
                self._play_media,
                cursor=True,
            )
            layout.addWidget(btn_play)

        if self.entry.description:
            desc = QTextEdit()
            desc.setReadOnly(True)
            desc.setPlainText(self.entry.description)
            desc.setMaximumHeight(110)
            layout.addWidget(desc)

        if self.entry.ai_meta:
            summary = format_ai_meta(self.entry.ai_meta)
            if summary:
                meta_lbl = hint_label(summary, "MutedLabel")
                layout.addWidget(meta_lbl)
            for label, key in (
                ("Prompt", "prompt"),
                ("Negative Prompt", "negative_prompt"),
            ):
                value = self.entry.ai_meta.get(key, "")
                if not value:
                    continue
                layout.addWidget(field_label(label))
                box = QTextEdit()
                box.setReadOnly(True)
                box.setPlainText(value)
                box.setMaximumHeight(100)
                layout.addWidget(box)

        self.lbl_stats = QLabel(self._get_stats_text())
        self.lbl_stats.setObjectName("MutedLabel")
        self.lbl_stats.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.lbl_stats)

        rating_layout = QHBoxLayout()
        rating_layout.setSpacing(8)
        for rating in range(1, 6):
            btn = button(
                str(rating),
                "secondary",
                lambda value=rating: self._apply_rating(value),
                tooltip=f"Bewertung {rating}: Score {self._rating_delta(rating):+d}",
                cursor=True,
            )
            rating_layout.addWidget(btn)
        layout.addLayout(rating_layout)

        buttons = QHBoxLayout()
        buttons.setSpacing(8)
        btn_edit = button(
            "✏️  Manuell bearbeiten",
            "secondary",
            self._trigger_edit,
            cursor=True,
        )
        btn_close = button("Schließen", "ghost", self.reject, cursor=True)
        buttons.addWidget(btn_edit)
        buttons.addStretch()
        buttons.addWidget(btn_close)
        layout.addLayout(buttons)

    @staticmethod
    def _rating_delta(rating: int) -> int:
        """Return the score change for a rating: 1 → -10, 3 → 0, 5 → +10."""
        return {1: -10, 2: -5, 3: 0, 4: 5, 5: 10}[rating]

    def _get_stats_text(self) -> str:
        """Format score, viewings and rating count as rich text."""
        return (
            f"<b>Score {self.entry.score}/100</b> · "
            f"{self.entry.watched_counter}× angesehen · "
            f"{self.entry.rating_count} Bewertungen"
        )

    def _persist_stats(self) -> None:
        """Save the database and refresh the statistics line."""
        self.db.save()
        self.lbl_stats.setText(self._get_stats_text())

    def _play_media(self) -> None:
        """Open the entry's file with the system application and count a viewing.

        Shows a warning instead when the file is not reachable, e.g. because the
        stick is unplugged.
        """
        path = self.entry.resolve(self.root)
        if not path or not os.path.isfile(path):
            QMessageBox.warning(
                self,
                "Nicht verfügbar",
                "Die Datei ist nicht erreichbar. Ist der Stick mit dieser "
                "Mediathek verbunden?"
                if not self.root
                else "Die Datei wurde auf dem Stick nicht gefunden.",
            )
            return
        file_dialogs.open_file(path)
        self.entry.watched_counter += 1
        self.entry.last_watched = time.time()
        self._persist_stats()

    def _apply_rating(self, rating: int) -> None:
        """Apply a 1-5 rating to the score and persist it.

        Also increments the viewing and rating counters and sets the last viewing
        time, which lowers the entry's weight in smart random picks.
        """
        self.entry.score = max(
            1, min(100, self.entry.score + self._rating_delta(rating))
        )
        self.entry.watched_counter += 1
        self.entry.rating_count += 1
        self.entry.last_watched = time.time()
        self._persist_stats()

    def _trigger_edit(self) -> None:
        """Flag an edit request and close the dialog."""
        self.edit_requested = True
        self.accept()


class EditDialog(QDialog):
    """Dialog for creating or editing a media entry.

    New entries are added to the database on save. Edits of an existing entry
    change the entry object in place; the caller saves the database after
    ``exec()`` returned accepted. Paths inside the volume are stored relative
    to it, and the content hash is recomputed from the entry's own file.

    Attributes:
        entry: The edited entry, or the newly created one after saving.
        inp_img: Preview image path field; callers may prefill it.
        inp_video: Video path field (video entries only).
    """

    def __init__(
        self,
        parent: QWidget | None,
        db: MediaDatabase,
        entry_type: str,
        entry: MediaItem | None = None,
        ai_meta: dict[str, Any] | None = None,
        root: str = "",
    ) -> None:
        """Initialize the edit dialog for a new or existing entry.

        Args:
            parent: Parent window.
            db: Database for group suggestions and new entries.
            entry_type: :class:`MediaType` value for a new entry; ignored when
                ``entry`` is given.
            entry: Existing entry to edit, or None to create one.
            ai_meta: AI metadata stored with a new entry.
            root: Volume root, so paths are stored relative to the stick.
        """
        super().__init__(parent)
        self.db = db
        self.entry = entry
        self.ai_meta = ai_meta or {}
        self.root = root
        self.entry_type = entry.entry_type if entry else entry_type
        self.setWindowTitle("Bearbeiten" if entry else "Erstellen")
        self.setMinimumSize(460, 640)
        self.resize(480, 680)
        self._build_ui()
        self._populate()

    def _build_ui(self) -> None:
        """Build the inputs for title, group, description, score and file paths."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(10)

        layout.addWidget(field_label("Titel"))
        self.inp_title = QLineEdit()
        layout.addWidget(self.inp_title)

        layout.addWidget(field_label("Gruppe"))
        self.inp_group = QComboBox()
        self.inp_group.setEditable(True)
        self.inp_group.addItems([""] + self.db.get_all_groups())
        layout.addWidget(self.inp_group)

        layout.addWidget(field_label("Beschreibung"))
        self.inp_desc = QTextEdit()
        self.inp_desc.setFixedHeight(120)
        layout.addWidget(self.inp_desc)

        if self.entry_type == MediaType.VIDEO:
            self.inp_video = self._path_row(
                layout,
                "Video-Datei",
                "Video wählen",
                "Videos (*.mp4 *.mkv *.avi *.mov *.webm)",
            )

        layout.addWidget(field_label("Score (1-100)"))
        self.inp_score = QLineEdit("50")
        layout.addWidget(self.inp_score)

        self.inp_img = self._path_row(
            layout,
            "Vorschaubild",
            "Bild wählen",
            "Bilder (*.png *.jpg *.jpeg *.bmp *.webp)",
        )

        layout.addStretch()

        buttons = QHBoxLayout()
        buttons.setSpacing(8)
        btn_cancel = button("Abbrechen", "ghost", self.reject)
        btn_save = button("Speichern", "primary", self._save)
        buttons.addStretch()
        buttons.addWidget(btn_cancel)
        buttons.addWidget(btn_save)
        layout.addLayout(buttons)

    def _populate(self) -> None:
        """Fill the inputs with the values of an existing entry."""
        if self.entry:
            self.inp_title.setText(self.entry.title)
            self.inp_group.setCurrentText(self.entry.group)
            self.inp_desc.setPlainText(self.entry.description)
            self.inp_score.setText(str(self.entry.score))
            self.inp_img.setText(self.entry.image_path)
            if self.entry_type == MediaType.VIDEO:
                self.inp_video.setText(self.entry.video_link)

    def _path_row(
        self, layout: QVBoxLayout, label: str, title: str, file_filter: str
    ) -> QLineEdit:
        """Add a labelled path input with a button that opens a file picker."""
        layout.addWidget(field_label(label))
        row = QHBoxLayout()
        row.setSpacing(8)
        line = QLineEdit()
        row.addWidget(line)
        choose = partial(self._choose, line, title, file_filter)
        row.addWidget(button("Wählen", "secondary", choose))
        layout.addLayout(row)
        return line

    def _choose(self, line: QLineEdit, title: str, file_filter: str) -> None:
        """Open a file dialog and put the chosen path into ``line``."""
        path, _ = file_dialogs.pick_file(self, title, file_filter)
        if path:
            line.setText(path)

    def _save(self) -> None:
        """Validate the inputs and save the entry.

        A title is required; an invalid score falls back to 50 and is clamped to
        1-100. If the file cannot be hashed, an existing entry keeps its old hash.
        """
        if not self.inp_title.text().strip():
            QMessageBox.warning(self, "Fehler", "Titel ist erforderlich.")
            return

        try:
            score = max(1, min(100, int(self.inp_score.text())))
        except ValueError:
            score = 50

        title = self.inp_title.text().strip()
        group = self.inp_group.currentText().strip()
        desc = self.inp_desc.toPlainText().strip()
        img = volumes.stored_path(self.inp_img.text().strip(), self.root)
        vid = (
            volumes.stored_path(self.inp_video.text().strip(), self.root)
            if self.entry_type == MediaType.VIDEO
            else ""
        )

        own_file = vid if self.entry_type == MediaType.VIDEO else img
        media = volumes.absolute_path(own_file, self.root)
        try:
            file_hash = content_hash(media) if media else ""
        except OSError:
            file_hash = self.entry.content_hash if self.entry else ""

        if self.entry:
            self.entry.title = title
            self.entry.group = group
            self.entry.description = desc
            self.entry.image_path = img
            self.entry.video_link = vid
            self.entry.score = score
            self.entry.content_hash = file_hash
        else:
            self.entry = MediaItem(
                title,
                img,
                score,
                desc,
                self.entry_type,
                vid,
                group=group,
                ai_meta=dict(self.ai_meta),
                content_hash=file_hash,
            )
            self.db.add(self.entry)

        self.accept()


def _group_checklist(groups: list[str]) -> tuple[QScrollArea, dict[str, QCheckBox]]:
    """Build a scrollable list with one checked checkbox per group.

    Returns:
        ``(scroll area, {group: checkbox})``.
    """
    content = QWidget()
    vbox = QVBoxLayout(content)
    vbox.setContentsMargins(4, 4, 4, 4)
    vbox.setSpacing(6)
    boxes: dict[str, QCheckBox] = {}
    for group in groups:
        boxes[group] = box = QCheckBox(group)
        box.setChecked(True)
        vbox.addWidget(box)
    vbox.addStretch()
    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setWidget(content)
    return scroll, boxes


def _checked_groups(boxes: dict[str, QCheckBox]) -> list[str]:
    """Return the groups whose checkbox is checked."""
    return [group for group, box in boxes.items() if box.isChecked()]


class GroupRandomDialog(QDialog):
    """Dialog to choose groups and media types for a random pick.

    Attributes:
        result_pool: Entries matching the chosen groups and types, set when the
            dialog was accepted.
        smart: True when the user asked for a weighted ("Smart") pick.
    """

    def __init__(self, parent: QWidget | None, db: MediaDatabase) -> None:
        """Initialize the dialog with the groups of ``db``."""
        super().__init__(parent)
        self.db = db
        self.result_pool: list[MediaItem] = []
        self.smart = False
        self.setWindowTitle("Gruppen-Zufall")
        self.setMinimumSize(380, 480)
        self.resize(400, 520)
        self._build_ui()

    def _build_ui(self) -> None:
        """Build group checkboxes, type selection and action buttons."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(12)

        layout.addWidget(field_label("Gruppen"))

        scroll, self.group_boxes = _group_checklist(self.db.get_all_groups())
        layout.addWidget(scroll, 1)

        layout.addWidget(field_label("Medientyp"))
        type_row = QHBoxLayout()
        type_row.setSpacing(16)
        self.cb_img = QCheckBox("Bilder")
        self.cb_img.setChecked(True)
        self.cb_vid = QCheckBox("Videos")
        self.cb_vid.setChecked(True)
        type_row.addWidget(self.cb_img)
        type_row.addWidget(self.cb_vid)
        type_row.addStretch()
        layout.addLayout(type_row)

        button_row = QHBoxLayout()
        button_row.setSpacing(8)
        btn_cancel = button("Abbrechen", "ghost", self.reject)
        btn_normal = button("🎲  Normal", "secondary", lambda: self._execute(False))
        btn_smart = button("⚖️  Smart", "primary", lambda: self._execute(True))
        button_row.addWidget(btn_cancel)
        button_row.addStretch()
        button_row.addWidget(btn_normal)
        button_row.addWidget(btn_smart)
        layout.addLayout(button_row)

    def _execute(self, smart: bool) -> None:
        """Build the pick pool from the chosen groups and types and close the dialog.

        Requires at least one group and one media type.
        """
        selected_groups = _checked_groups(self.group_boxes)
        selected_types = []
        if self.cb_img.isChecked():
            selected_types.append(MediaType.IMAGE)
        if self.cb_vid.isChecked():
            selected_types.append(MediaType.VIDEO)

        if not selected_groups or not selected_types:
            QMessageBox.warning(
                self,
                "Hinweis",
                "Bitte mindestens eine Gruppe und einen Typ wählen.",
            )
            return

        self.result_pool = [
            entry
            for entry in self.db.entries
            if entry.group in selected_groups and entry.entry_type in selected_types
        ]
        self.smart = smart
        self.accept()


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

        scroll, self.group_boxes = _group_checklist(groups)
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
        self.selected_groups = _checked_groups(self.group_boxes)
        self.accept()


class ConfigDialog(QDialog):
    """Dialog to open an existing vault config or create a new one.

    Lists every config with its mode and location (local folder or stick with
    its connection state). Creating a config optionally takes a local folder;
    stick configs are handed over to :class:`StickDialog`. The configs file is
    saved by the dialog.

    Attributes:
        selected_config: Config to activate after the dialog was accepted.
        wants_stick_setup: True when the user chose "Vom Stick…"; the caller
            then opens the stick dialog.
    """

    def __init__(
        self,
        parent: QWidget | None,
        configs: list[VaultConfig],
        current_db_path: str,
    ) -> None:
        """Initialize the dialog with the known configs.

        Args:
            parent: Parent window.
            configs: All configs; the dialog works on a copy of the list.
            current_db_path: Database path of the active config, preselected.
        """
        super().__init__(parent)
        self.configs = list(configs)
        self.selected_config: VaultConfig | None = None
        self.wants_stick_setup = False
        self.setWindowTitle("Config wechseln")
        self.setMinimumSize(520, 560)
        self._build_ui(current_db_path)

    def _build_ui(self, current_db_path: str) -> None:
        """Build the config list, the create form and the action buttons."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(10)

        layout.addWidget(field_label("Bestehende Configs"))
        self.list_configs = QListWidget()
        for config in self.configs:
            mode = "KI-Bilder" if config.mode == MODE_AI else "Normal"
            if config.volume_uuid:
                state = "verbunden" if locate(config).available else "nicht verbunden"
                location = f"{config.volume_label or 'Stick'} · {state}"
            else:
                location = config.folder or "kein Ordner"
            item = QListWidgetItem(f"{config.name} · {mode} · {location}")
            item.setData(Qt.ItemDataRole.UserRole, config.db_path)
            self.list_configs.addItem(item)
            if config.db_path == current_db_path:
                self.list_configs.setCurrentItem(item)
        self.list_configs.itemDoubleClicked.connect(lambda _item: self._open_selected())
        layout.addWidget(self.list_configs, 1)

        btn_open = button("Ausgewählte Config öffnen", "secondary", self._open_selected)
        layout.addWidget(btn_open)

        layout.addWidget(field_label("Neu erstellen"))
        self.inp_name = QLineEdit()
        self.inp_name.setPlaceholderText("Name")
        layout.addWidget(self.inp_name)

        self.combo_mode = QComboBox()
        self.combo_mode.addItem("Normale Medien", MODE_NORMAL)
        self.combo_mode.addItem("KI-Bilder", MODE_AI)
        layout.addWidget(self.combo_mode)

        folder_row = QHBoxLayout()
        folder_row.setSpacing(8)
        self.inp_folder = QLineEdit()
        self.inp_folder.setPlaceholderText(
            "Ordner (optional) – beim Start oder per Knopf scannen"
        )
        folder_row.addWidget(self.inp_folder)
        btn_folder = button("Ordner wählen…", "secondary", self._choose_folder)
        folder_row.addWidget(btn_folder)
        btn_stick = button(
            "Vom Stick…",
            "secondary",
            self._request_stick_setup,
            tooltip="Ordner auf einem Stick als eigene Config einrichten",
        )
        folder_row.addWidget(btn_stick)
        layout.addLayout(folder_row)

        hint = hint_label(
            "Ohne Ordner startet die Config leer; Medien danach einzeln importieren. "
            "\"Vom Stick\" legt die Config direkt auf einem USB-Stick an.",
            "MutedLabel",
        )
        layout.addWidget(hint)

        buttons = QHBoxLayout()
        buttons.setSpacing(8)
        btn_cancel = button("Abbrechen", "ghost", self.reject)
        btn_create = button("Erstellen & öffnen", "primary", self._create)
        buttons.addStretch()
        buttons.addWidget(btn_cancel)
        buttons.addWidget(btn_create)
        layout.addLayout(buttons)

    def _choose_folder(self) -> None:
        """Pick a local media folder for a new config."""
        folder = QFileDialog.getExistingDirectory(self, "Ordner wählen")
        if folder:
            self.inp_folder.setText(folder)

    def _request_stick_setup(self) -> None:
        """Hand the stick flow over to StickDialog, which owns volume binding."""
        self.wants_stick_setup = True
        self.accept()

    def _open_selected(self) -> None:
        """Select the highlighted config, store it as the last used one and close."""
        item = self.list_configs.currentItem()
        if item is None:
            QMessageBox.warning(self, "Hinweis", "Bitte eine Config auswählen.")
            return
        db_path = item.data(Qt.ItemDataRole.UserRole)
        self.selected_config = next(
            config for config in self.configs if config.db_path == db_path
        )
        save_configs(self.configs, db_path)
        self.accept()

    def _create(self) -> None:
        """Validate the form, create and save the config and select it.

        Requires a unique name (case-insensitive) and, if given, an existing folder.
        """
        name = self.inp_name.text().strip()
        if not name:
            QMessageBox.warning(self, "Fehler", "Name ist erforderlich.")
            return
        if any(config.name.casefold() == name.casefold() for config in self.configs):
            QMessageBox.warning(
                self, "Fehler", "Eine Config mit diesem Namen existiert bereits."
            )
            return
        folder = self.inp_folder.text().strip()
        if folder and not os.path.isdir(folder):
            QMessageBox.warning(self, "Fehler", "Der Ordner existiert nicht.")
            return

        config = create_config(
            name, self.combo_mode.currentData(), folder, self.configs
        )
        self.configs.append(config)
        save_configs(self.configs, config.db_path)
        self.selected_config = config
        self.accept()


class FolderPreviewDialog(QDialog):
    """Show the files found in the config folder before they are imported.

    Displays every file as an icon with its name; accepting imports all of
    them. Used by :class:`mediavault.gui.folder_sync.FolderSync`.
    """

    THUMB = 96

    def __init__(self, parent: QWidget | None, paths: list[str]) -> None:
        """Initialize the thumbnail grid from the found image paths."""
        super().__init__(parent)
        self.setWindowTitle("Neue Bilder importieren")
        self.resize(760, 600)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        heading = QLabel(f"{len(paths)} neue Bild(er) gefunden")
        heading.setObjectName("DialogTitle")
        layout.addWidget(heading)

        hint = hint_label("Nur Bilder mit KI-Metadaten werden übernommen.")
        layout.addWidget(hint)

        self.list_files = QListWidget()
        self.list_files.setViewMode(QListWidget.ViewMode.IconMode)
        self.list_files.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.list_files.setMovement(QListWidget.Movement.Static)
        self.list_files.setSelectionMode(QListWidget.SelectionMode.NoSelection)
        self.list_files.setWordWrap(True)
        self.list_files.setIconSize(QSize(self.THUMB, self.THUMB))
        self.list_files.setGridSize(QSize(self.THUMB + 30, self.THUMB + 44))
        for path in paths:
            item = QListWidgetItem(QIcon(path), os.path.basename(path))
            item.setToolTip(path)
            self.list_files.addItem(item)
        layout.addWidget(self.list_files, 1)

        buttons = QHBoxLayout()
        buttons.addStretch()
        btn_cancel = button("Abbrechen", "ghost", self.reject)
        btn_import = button(f"{len(paths)} importieren", "primary", self.accept)
        buttons.addWidget(btn_cancel)
        buttons.addWidget(btn_import)
        layout.addLayout(buttons)


class AnalysisDialog(QDialog):
    """Read-only local prompt statistics for the current AI config.

    Shows the result of :func:`ai_meta.summarize_prompts`: counts and averages,
    top tags, models, samplers, the best-rated tags and prompts.
    """

    def __init__(self, parent: QWidget | None, db: MediaDatabase) -> None:
        """Initialize the dialog from the database entries."""
        super().__init__(parent)
        self.setWindowTitle("Prompt-Analyse")
        self.setMinimumSize(560, 600)
        self.resize(620, 700)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(10)

        text = QTextEdit()
        text.setReadOnly(True)
        text.setHtml(self._build_html(summarize_prompts(db.entries)))
        layout.addWidget(text)

        btn_close = button("Schließen", "secondary", self.accept)
        layout.addWidget(btn_close, alignment=Qt.AlignmentFlag.AlignRight)

    @staticmethod
    def _build_html(summary: dict[str, Any]) -> str:
        """Format the summary dictionary as rich text; all user text is HTML-escaped."""
        if not summary["count"]:
            return "<h2>Prompt-Analyse</h2><p>Keine KI-Bilder mit Prompt gefunden.</p>"

        def listing(rows: list[Any], formatter: Callable[[Any], str]) -> str:
            """Join formatted rows with line breaks, or a dash when there are none."""
            return "<br>".join(formatter(row) for row in rows) or "–"

        def counted(row: Any) -> str:
            """Format a ``(name, count)`` row as "name (n×)"."""
            return f"{escape(row[0])} ({row[1]}×)"

        tags = listing(summary["top_tags"], counted)
        models = listing(summary["models"], counted)
        samplers = listing(summary["samplers"], counted)
        scored = listing(
            summary["top_tags_by_score"],
            lambda row: f"{escape(row[0])} · Ø {row[2]:.0f} ({row[1]}×)",
        )
        prompts = listing(
            summary["top_prompts"],
            lambda row: (
                f"<b>{escape(row['title'])}</b> ({row['score']}) – "
                f"{escape(row['prompt'])}"
            ),
        )
        return (
            "<h2>Prompt-Analyse</h2>"
            f"<p><b>{summary['count']}</b> Bilder mit Prompt · "
            f"Ø Score <b>{summary['average_score']:.0f}/100</b> · "
            f"Ø Prompt-Länge {summary['average_prompt_length']:.0f} Zeichen</p>"
            f"<h3>Top-Tags</h3><p>{tags}</p>"
            f"<h3>Modelle</h3><p>{models}</p>"
            f"<h3>Sampler</h3><p>{samplers}</p>"
            f"<h3>Tags nach Score (min. 3×)</h3><p>{scored}</p>"
            f"<h3>Bestbewertete Prompts</h3><p>{prompts}</p>"
        )
