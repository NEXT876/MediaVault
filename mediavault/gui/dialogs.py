"""Dialogs for the detail view, editing, configs and prompt analysis."""

import os
import time
from collections.abc import Callable
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
    QPushButton,
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
from mediavault.gui.widgets import field_label, rounded_pixmap
from mediavault.importer import content_hash
from mediavault.models import MediaDatabase, MediaItem, MediaType
from mediavault.utils import OSHelper


class DetailDialog(QDialog):
    """Dialog with preview, statistics and rating buttons for one entry."""

    def __init__(
        self,
        parent: QWidget | None,
        entry: MediaItem,
        db: MediaDatabase,
        get_pixmap_func: Callable[[MediaItem], QPixmap | None],
        root: str = "",
    ) -> None:
        """Initialize the detail dialog for ``entry``."""
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
        """Build the layout with image, info, rating and action buttons."""
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
            btn_play = QPushButton("▶  Abspielen / Öffnen")
            btn_play.setProperty("variant", "primary")
            btn_play.setCursor(Qt.CursorShape.PointingHandCursor)
            btn_play.clicked.connect(self._play_media)
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
                meta_lbl = QLabel(summary)
                meta_lbl.setObjectName("MutedLabel")
                meta_lbl.setWordWrap(True)
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
            btn = QPushButton(str(rating))
            btn.setProperty("variant", "secondary")
            btn.setToolTip(f"Bewertung {rating}: Score {self._rating_delta(rating):+d}")
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(
                lambda checked=False, value=rating: self._apply_rating(value)
            )
            rating_layout.addWidget(btn)
        layout.addLayout(rating_layout)

        buttons = QHBoxLayout()
        buttons.setSpacing(8)
        btn_edit = QPushButton("✏️  Manuell bearbeiten")
        btn_edit.setProperty("variant", "secondary")
        btn_edit.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_edit.clicked.connect(self._trigger_edit)
        btn_close = QPushButton("Schließen")
        btn_close.setProperty("variant", "ghost")
        btn_close.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_close.clicked.connect(self.reject)
        buttons.addWidget(btn_edit)
        buttons.addStretch()
        buttons.addWidget(btn_close)
        layout.addLayout(buttons)

    @staticmethod
    def _rating_delta(rating: int) -> int:
        """Return the score change for a rating."""
        return {1: -10, 2: -5, 3: 0, 4: 5, 5: 10}[rating]

    def _get_stats_text(self) -> str:
        """Format score and counters as statistics text."""
        return (
            f"<b>Score {self.entry.score}/100</b> · "
            f"{self.entry.watched_counter}× angesehen · "
            f"{self.entry.rating_count} Bewertungen"
        )

    def _persist_stats(self) -> None:
        """Persist the updated statistics and refresh their display."""
        self.db.save()
        self.lbl_stats.setText(self._get_stats_text())

    def _play_media(self) -> None:
        """Open the media file and update counters and timestamp."""
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
        OSHelper.open_file(path)
        self.entry.watched_counter += 1
        self.entry.last_watched = time.time()
        self._persist_stats()

    def _apply_rating(self, rating: int) -> None:
        """Adjust the score based on the rating (1-5) and persist it."""
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
    """Dialog for creating or editing a media entry."""

    def __init__(
        self,
        parent: QWidget | None,
        db: MediaDatabase,
        entry_type: str,
        entry: MediaItem | None = None,
        ai_meta: dict[str, Any] | None = None,
        root: str = "",
    ) -> None:
        """Initialize the edit dialog for a new or existing entry."""
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
        """Build the inputs for title, group, description, score and paths."""
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
            layout.addWidget(field_label("Video-Datei"))
            video_row = QHBoxLayout()
            video_row.setSpacing(8)
            self.inp_video = QLineEdit()
            video_row.addWidget(self.inp_video)
            btn_v = QPushButton("Wählen")
            btn_v.setProperty("variant", "secondary")
            btn_v.clicked.connect(self._choose_vid)
            video_row.addWidget(btn_v)
            layout.addLayout(video_row)

        layout.addWidget(field_label("Score (1-100)"))
        self.inp_score = QLineEdit("50")
        layout.addWidget(self.inp_score)

        layout.addWidget(field_label("Vorschaubild"))
        image_row = QHBoxLayout()
        image_row.setSpacing(8)
        self.inp_img = QLineEdit()
        image_row.addWidget(self.inp_img)
        btn_i = QPushButton("Wählen")
        btn_i.setProperty("variant", "secondary")
        btn_i.clicked.connect(self._choose_img)
        image_row.addWidget(btn_i)
        layout.addLayout(image_row)

        layout.addStretch()

        buttons = QHBoxLayout()
        buttons.setSpacing(8)
        btn_cancel = QPushButton("Abbrechen")
        btn_cancel.setProperty("variant", "ghost")
        btn_cancel.clicked.connect(self.reject)
        btn_save = QPushButton("Speichern")
        btn_save.setProperty("variant", "primary")
        btn_save.clicked.connect(self._save)
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

    def _choose_vid(self) -> None:
        """Open a file dialog to choose a video file."""
        path, _ = OSHelper.pick_file(
            self,
            "Video wählen",
            "Videos (*.mp4 *.mkv *.avi *.mov *.webm)",
        )
        if path:
            self.inp_video.setText(path)

    def _choose_img(self) -> None:
        """Open a file dialog to choose an image file."""
        path, _ = OSHelper.pick_file(
            self,
            "Bild wählen",
            "Bilder (*.png *.jpg *.jpeg *.bmp *.webp)",
        )
        if path:
            self.inp_img.setText(path)

    def _save(self) -> None:
        """Validate the inputs and save the entry to the database."""
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


class GroupRandomDialog(QDialog):
    """Dialog to choose groups and media types for a random pick."""

    def __init__(self, parent: QWidget | None, db: MediaDatabase) -> None:
        """Initialize the group random dialog with the database."""
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

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        self.vbox = QVBoxLayout(content)
        self.vbox.setContentsMargins(4, 4, 4, 4)
        self.vbox.setSpacing(6)

        self.group_boxes: dict[str, QCheckBox] = {}
        for group in self.db.get_all_groups():
            box = QCheckBox(group)
            box.setChecked(True)
            self.vbox.addWidget(box)
            self.group_boxes[group] = box
        self.vbox.addStretch()

        scroll.setWidget(content)
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
        btn_cancel = QPushButton("Abbrechen")
        btn_cancel.setProperty("variant", "ghost")
        btn_cancel.clicked.connect(self.reject)
        btn_normal = QPushButton("🎲  Normal")
        btn_normal.setProperty("variant", "secondary")
        btn_normal.clicked.connect(lambda: self._execute(False))
        btn_smart = QPushButton("⚖️  Smart")
        btn_smart.setProperty("variant", "primary")
        btn_smart.clicked.connect(lambda: self._execute(True))
        button_row.addWidget(btn_cancel)
        button_row.addStretch()
        button_row.addWidget(btn_normal)
        button_row.addWidget(btn_smart)
        layout.addLayout(button_row)

    def _execute(self, smart: bool) -> None:
        """Build the selection pool from groups/types and close the dialog."""
        selected_groups = [
            group for group, box in self.group_boxes.items() if box.isChecked()
        ]
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


class ConfigDialog(QDialog):
    """Dialog to open an existing vault config or create a new one."""

    def __init__(
        self,
        parent: QWidget | None,
        configs: list[VaultConfig],
        current_db_path: str,
    ) -> None:
        """Initialize the dialog with the known configs."""
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

        btn_open = QPushButton("Ausgewählte Config öffnen")
        btn_open.setProperty("variant", "secondary")
        btn_open.clicked.connect(self._open_selected)
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
        btn_folder = QPushButton("Ordner wählen…")
        btn_folder.setProperty("variant", "secondary")
        btn_folder.clicked.connect(self._choose_folder)
        folder_row.addWidget(btn_folder)
        btn_stick = QPushButton("Vom Stick…")
        btn_stick.setProperty("variant", "secondary")
        btn_stick.setToolTip("Ordner auf einem Stick als eigene Config einrichten")
        btn_stick.clicked.connect(self._request_stick_setup)
        folder_row.addWidget(btn_stick)
        layout.addLayout(folder_row)

        hint = QLabel(
            "Ohne Ordner startet die Config leer; Medien danach einzeln importieren. "
            "\"Vom Stick\" legt die Config direkt auf einem USB-Stick an."
        )
        hint.setObjectName("MutedLabel")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        buttons = QHBoxLayout()
        buttons.setSpacing(8)
        btn_cancel = QPushButton("Abbrechen")
        btn_cancel.setProperty("variant", "ghost")
        btn_cancel.clicked.connect(self.reject)
        btn_create = QPushButton("Erstellen & öffnen")
        btn_create.setProperty("variant", "primary")
        btn_create.clicked.connect(self._create)
        buttons.addStretch()
        buttons.addWidget(btn_cancel)
        buttons.addWidget(btn_create)
        layout.addLayout(buttons)

    def _choose_folder(self) -> None:
        """Pick a scan folder for a new config."""
        folder = QFileDialog.getExistingDirectory(self, "Ordner wählen")
        if folder:
            self.inp_folder.setText(folder)

    def _request_stick_setup(self) -> None:
        """Hand the stick flow over to StickDialog, which owns volume binding."""
        self.wants_stick_setup = True
        self.accept()

    def _open_selected(self) -> None:
        """Select the highlighted config and remember it as the last one."""
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
        """Validate the form, create the config and make it the selected one."""
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
        self.selected_config = config
        self.accept()


class FolderPreviewDialog(QDialog):
    """Show images found in the config folder before they are imported."""

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

        hint = QLabel("Nur Bilder mit KI-Metadaten werden übernommen.")
        hint.setObjectName("HintLabel")
        hint.setWordWrap(True)
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
        btn_cancel = QPushButton("Abbrechen")
        btn_cancel.setProperty("variant", "ghost")
        btn_cancel.clicked.connect(self.reject)
        btn_import = QPushButton(f"{len(paths)} importieren")
        btn_import.setProperty("variant", "primary")
        btn_import.clicked.connect(self.accept)
        buttons.addWidget(btn_cancel)
        buttons.addWidget(btn_import)
        layout.addLayout(buttons)


class AnalysisDialog(QDialog):
    """Read-only local prompt statistics for the current AI config."""

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

        btn_close = QPushButton("Schließen")
        btn_close.setProperty("variant", "secondary")
        btn_close.clicked.connect(self.accept)
        layout.addWidget(btn_close, alignment=Qt.AlignmentFlag.AlignRight)

    @staticmethod
    def _build_html(summary: dict[str, Any]) -> str:
        """Format the summary dictionary as simple rich text."""
        if not summary["count"]:
            return "<h2>Prompt-Analyse</h2><p>Keine KI-Bilder mit Prompt gefunden.</p>"

        def listing(rows: list[Any], formatter: Callable[[Any], str]) -> str:
            return "<br>".join(formatter(row) for row in rows) or "–"

        tags = listing(summary["top_tags"], lambda row: f"{escape(row[0])} ({row[1]}×)")
        models = listing(summary["models"], lambda row: f"{escape(row[0])} ({row[1]}×)")
        samplers = listing(
            summary["samplers"], lambda row: f"{escape(row[0])} ({row[1]}×)"
        )
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
