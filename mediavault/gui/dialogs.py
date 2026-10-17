"""Dialoge für Detailansicht, Bearbeiten und Gruppen-Zufall."""

import time

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from mediavault.gui.widgets import rounded_pixmap
from mediavault.models import MediaItem
from mediavault.utils import OSHelper


def _field_label(text):
    """Erzeugt ein gedämpftes Formularlabel."""
    label = QLabel(text)
    label.setObjectName("FieldLabel")
    return label


class DetailDialog(QDialog):
    """Dialog mit Vorschau, Statistiken und Bewertungsbuttons für einen Eintrag."""

    def __init__(self, parent, entry, db, get_pixmap_func):
        """Initialisiert den Detaildialog für den übergebenen Eintrag."""
        super().__init__(parent)
        self.entry = entry
        self.db = db
        self.get_pixmap = get_pixmap_func
        self.setWindowTitle(entry.title)
        self.setMinimumSize(540, 720)
        self.resize(560, 760)
        self.edit_requested = False
        self._build_ui()

    def _build_ui(self):
        """Erstellt das Layout mit Bild, Infos, Rating und Aktionsbuttons."""
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

        has_media = (
            self.entry.entry_type == "Videos" and self.entry.video_link
        ) or (self.entry.entry_type == "Bilder" and self.entry.image_path)
        if has_media:
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

        self.lbl_stats = QLabel(self._get_stats_text())
        self.lbl_stats.setObjectName("MutedLabel")
        self.lbl_stats.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.lbl_stats)

        rating_layout = QHBoxLayout()
        rating_layout.setSpacing(8)
        for rating in range(1, 6):
            btn = QPushButton(str(rating))
            btn.setProperty("variant", "secondary")
            btn.setToolTip(
                f"Bewertung {rating}: Score {self._rating_delta(rating):+d}"
            )
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
    def _rating_delta(rating):
        """Liefert die Score-Änderung einer Bewertung."""
        return {1: -10, 2: -5, 3: 0, 4: 5, 5: 10}[rating]

    def _get_stats_text(self):
        """Formatiert Score und Zähler als Statistik-Text."""
        return (
            f"<b>Score {self.entry.score}/100</b> · "
            f"{self.entry.watched_counter}× angesehen · "
            f"{self.entry.rating_count} Bewertungen"
        )

    def _play_media(self):
        """Öffnet die Mediendatei und aktualisiert Zähler sowie Zeitstempel."""
        path = (
            self.entry.video_link
            if self.entry.entry_type == "Videos"
            else self.entry.image_path
        )
        OSHelper.open_file(path)
        self.entry.watched_counter += 1
        self.entry.last_watched = time.time()
        self.db.save()
        self.lbl_stats.setText(self._get_stats_text())

    def _apply_rating(self, rating):
        """Passt den Score anhand der Bewertung (1-5) an und speichert."""
        self.entry.score = max(
            1, min(100, self.entry.score + self._rating_delta(rating))
        )
        self.entry.watched_counter += 1
        self.entry.rating_count += 1
        self.entry.last_watched = time.time()
        self.db.save()
        self.lbl_stats.setText(self._get_stats_text())

    def _trigger_edit(self):
        """Markiert den Wunsch zu bearbeiten und schließt den Dialog."""
        self.edit_requested = True
        self.accept()


class EditDialog(QDialog):
    """Dialog zum Erstellen oder Bearbeiten eines Medien-Eintrags."""

    def __init__(self, parent, db, entry_type, entry=None):
        """Initialisiert den Bearbeiten-Dialog für einen neuen oder bestehenden Eintrag."""
        super().__init__(parent)
        self.db = db
        self.entry = entry
        self.entry_type = entry.entry_type if entry else entry_type
        self.setWindowTitle("Bearbeiten" if entry else "Erstellen")
        self.setMinimumSize(460, 640)
        self.resize(480, 680)
        self._build_ui()
        self._populate()

    def _build_ui(self):
        """Erstellt die Eingabefelder für Titel, Gruppe, Beschreibung, Score und Pfade."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(10)

        layout.addWidget(_field_label("Titel"))
        self.inp_title = QLineEdit()
        layout.addWidget(self.inp_title)

        layout.addWidget(_field_label("Gruppe"))
        self.inp_group = QComboBox()
        self.inp_group.setEditable(True)
        self.inp_group.addItems([""] + self.db.get_all_groups())
        layout.addWidget(self.inp_group)

        layout.addWidget(_field_label("Beschreibung"))
        self.inp_desc = QTextEdit()
        self.inp_desc.setFixedHeight(120)
        layout.addWidget(self.inp_desc)

        if self.entry_type == "Videos":
            layout.addWidget(_field_label("Video-Datei"))
            video_row = QHBoxLayout()
            video_row.setSpacing(8)
            self.inp_video = QLineEdit()
            video_row.addWidget(self.inp_video)
            btn_v = QPushButton("Wählen")
            btn_v.setProperty("variant", "secondary")
            btn_v.clicked.connect(self._choose_vid)
            video_row.addWidget(btn_v)
            layout.addLayout(video_row)

        layout.addWidget(_field_label("Score (1-100)"))
        self.inp_score = QLineEdit("50")
        layout.addWidget(self.inp_score)

        layout.addWidget(_field_label("Vorschaubild"))
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

    def _populate(self):
        """Füllt die Eingabefelder mit den Werten eines bestehenden Eintrags."""
        if self.entry:
            self.inp_title.setText(self.entry.title)
            self.inp_group.setCurrentText(self.entry.group)
            self.inp_desc.setPlainText(self.entry.description)
            self.inp_score.setText(str(self.entry.score))
            self.inp_img.setText(self.entry.image_path)
            if self.entry_type == "Videos":
                self.inp_video.setText(self.entry.video_link)

    def _choose_vid(self):
        """Öffnet einen Dateidialog zur Auswahl einer Videodatei."""
        path, _ = OSHelper.pick_file(
            self,
            "Video wählen",
            "Videos (*.mp4 *.mkv *.avi *.mov *.webm)",
        )
        if path:
            self.inp_video.setText(path)

    def _choose_img(self):
        """Öffnet einen Dateidialog zur Auswahl einer Bilddatei."""
        path, _ = OSHelper.pick_file(
            self,
            "Bild wählen",
            "Bilder (*.png *.jpg *.jpeg *.bmp *.webp)",
        )
        if path:
            self.inp_img.setText(path)

    def _save(self):
        """Validiert die Eingaben und speichert den Eintrag in der Datenbank."""
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
        img = self.inp_img.text()
        vid = self.inp_video.text() if self.entry_type == "Videos" else ""

        if self.entry:
            self.entry.title = title
            self.entry.group = group
            self.entry.description = desc
            self.entry.image_path = img
            self.entry.video_link = vid
            self.entry.score = score
        else:
            self.entry = MediaItem(
                title, img, score, desc, self.entry_type, vid, group=group
            )
            self.db.add(self.entry)

        self.accept()


class GroupRandomDialog(QDialog):
    """Dialog zur Auswahl von Gruppen und Medientypen für einen Zufallspick."""

    def __init__(self, parent, db):
        """Initialisiert den Gruppen-Zufallsdialog mit der Datenbank."""
        super().__init__(parent)
        self.db = db
        self.result_pool = []
        self.smart = False
        self.setWindowTitle("Gruppen-Zufall")
        self.setMinimumSize(380, 480)
        self.resize(400, 520)
        self._build_ui()

    def _build_ui(self):
        """Erstellt die Gruppen-Checkboxen, Typauswahl und Aktionsbuttons."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(12)

        layout.addWidget(_field_label("Gruppen"))

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        self.vbox = QVBoxLayout(content)
        self.vbox.setContentsMargins(4, 4, 4, 4)
        self.vbox.setSpacing(6)

        self.group_boxes = {}
        for group in self.db.get_all_groups():
            box = QCheckBox(group)
            box.setChecked(True)
            self.vbox.addWidget(box)
            self.group_boxes[group] = box
        self.vbox.addStretch()

        scroll.setWidget(content)
        layout.addWidget(scroll, 1)

        layout.addWidget(_field_label("Medientyp"))
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

    def _execute(self, smart):
        """Baut den Auswahl-Pool aus Gruppen/Typen und schließt den Dialog."""
        selected_groups = [
            group
            for group, box in self.group_boxes.items()
            if box.isChecked()
        ]
        selected_types = []
        if self.cb_img.isChecked():
            selected_types.append("Bilder")
        if self.cb_vid.isChecked():
            selected_types.append("Videos")

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
