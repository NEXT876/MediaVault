from PyQt6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QLineEdit, QTextEdit, QComboBox, QFileDialog, QScrollArea, QWidget, QCheckBox, QMessageBox
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPixmap
import time
from mediavault.models import MediaItem
from mediavault.utils import OSHelper

class DetailDialog(QDialog):
    def __init__(self, parent, entry, db, get_pixmap_func):
        super().__init__(parent)
        self.entry = entry
        self.db = db
        self.get_pixmap = get_pixmap_func
        self.setWindowTitle(entry.title)
        self.setFixedSize(500, 750)
        self.edit_requested = False 
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        # Bild
        img_lbl = QLabel()
        img_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        pixmap = self.get_pixmap(self.entry)
        if pixmap:
            img_lbl.setPixmap(pixmap.scaled(300, 300, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        else:
            img_lbl.setText("Kein Vorschaubild")
        layout.addWidget(img_lbl)

        # Infos
        title_lbl = QLabel(self.entry.title)
        title_lbl.setStyleSheet("font-size: 22px; font-weight: bold;")
        title_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title_lbl)

        grp_text = f"📂 {self.entry.group}" if self.entry.group else "📂 Keine Gruppe"
        grp_lbl = QLabel(grp_text)
        grp_lbl.setStyleSheet("color: gray;")
        grp_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(grp_lbl)

        # Medien Button
        if (self.entry.entry_type == "Videos" and self.entry.video_link) or (self.entry.entry_type == "Bilder" and self.entry.image_path):
            btn_play = QPushButton("▶ Abspielen / Öffnen")
            btn_play.setStyleSheet("background-color: #E50914; color: white; font-weight: bold; padding: 8px;")
            btn_play.clicked.connect(self._play_media)
            layout.addWidget(btn_play)

        if self.entry.description:
            desc = QTextEdit()
            desc.setReadOnly(True)
            desc.setText(self.entry.description)
            desc.setMaximumHeight(100)
            layout.addWidget(desc)

        self.lbl_stats = QLabel(self._get_stats_text())
        self.lbl_stats.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.lbl_stats)

        # Rating
        rating_layout = QHBoxLayout()
        for i in range(1, 6):
            btn = QPushButton(str(i))
            btn.clicked.connect(lambda checked, r=i: self._apply_rating(r))
            rating_layout.addWidget(btn)
        layout.addLayout(rating_layout)

        btn_edit = QPushButton("✏️ Manuell bearbeiten")
        btn_edit.clicked.connect(self._trigger_edit)
        layout.addWidget(btn_edit)

    def _get_stats_text(self):
        return f"Score: {self.entry.score}/100  |  Watched: {self.entry.watched_counter}"

    def _play_media(self):
        path = self.entry.video_link if self.entry.entry_type == "Videos" else self.entry.image_path
        OSHelper.open_file(path)
        self.entry.watched_counter += 1
        self.entry.last_watched = time.time()
        self.db.save()
        self.lbl_stats.setText(self._get_stats_text())

    def _apply_rating(self, rating):
        adjustments = {1: -10, 2: -5, 3: 0, 4: 5, 5: 10}
        self.entry.score = max(1, min(100, self.entry.score + adjustments[rating]))
        self.entry.watched_counter += 1
        self.entry.rating_count += 1
        self.entry.last_watched = time.time()
        self.db.save()
        self.lbl_stats.setText(self._get_stats_text())

    def _trigger_edit(self):
        self.edit_requested = True
        self.accept()

class EditDialog(QDialog):
    def __init__(self, parent, db, entry_type, entry=None):
        super().__init__(parent)
        self.db = db
        self.entry = entry
        self.entry_type = entry.entry_type if entry else entry_type
        self.setWindowTitle("Bearbeiten" if entry else "Erstellen")
        self.setFixedSize(400, 650)
        self._build_ui()
        self._populate()

    def _build_ui(self):
        layout = QVBoxLayout(self)

        layout.addWidget(QLabel("Titel:"))
        self.inp_title = QLineEdit()
        layout.addWidget(self.inp_title)

        layout.addWidget(QLabel("Gruppe:"))
        self.inp_group = QComboBox()
        self.inp_group.setEditable(True)
        self.inp_group.addItems([""] + self.db.get_all_groups())
        layout.addWidget(self.inp_group)

        layout.addWidget(QLabel("Beschreibung:"))
        self.inp_desc = QTextEdit()
        layout.addWidget(self.inp_desc)

        if self.entry_type == "Videos":
            layout.addWidget(QLabel("Video Datei:"))
            hl = QHBoxLayout()
            self.inp_video = QLineEdit()
            hl.addWidget(self.inp_video)
            btn_v = QPushButton("Wählen")
            btn_v.clicked.connect(self._choose_vid)
            hl.addWidget(btn_v)
            layout.addLayout(hl)

        layout.addWidget(QLabel("Score (1-100):"))
        self.inp_score = QLineEdit("50")
        layout.addWidget(self.inp_score)

        layout.addWidget(QLabel("Vorschaubild:"))
        hl2 = QHBoxLayout()
        self.inp_img = QLineEdit()
        hl2.addWidget(self.inp_img)
        btn_i = QPushButton("Wählen")
        btn_i.clicked.connect(self._choose_img)
        hl2.addWidget(btn_i)
        layout.addLayout(hl2)

        btn_save = QPushButton("Speichern")
        btn_save.setStyleSheet("background-color: #2FA572; color: white; font-weight: bold;")
        btn_save.clicked.connect(self._save)
        layout.addWidget(btn_save)

    def _populate(self):
        if self.entry:
            self.inp_title.setText(self.entry.title)
            self.inp_group.setCurrentText(self.entry.group)
            self.inp_desc.setPlainText(self.entry.description)
            self.inp_score.setText(str(self.entry.score))
            self.inp_img.setText(self.entry.image_path)
            if self.entry_type == "Videos":
                self.inp_video.setText(self.entry.video_link)

    def _choose_vid(self):
        path, _ = QFileDialog.getOpenFileName(self, "Video wählen", "", "Videos (*.mp4 *.mkv *.avi *.mov *.webm)")
        if path: self.inp_video.setText(path)

    def _choose_img(self):
        path, _ = QFileDialog.getOpenFileName(self, "Bild wählen", "", "Bilder (*.png *.jpg *.jpeg *.bmp *.webp)")
        if path: self.inp_img.setText(path)

    def _save(self):
        if not self.inp_title.text().strip():
            QMessageBox.warning(self, "Fehler", "Titel ist erforderlich.")
            return

        try: score = max(1, min(100, int(self.inp_score.text())))
        except ValueError: score = 50

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
            self.entry = MediaItem(title, img, score, desc, self.entry_type, vid, group=group)
            self.db.add(self.entry)

        self.accept()

class GroupRandomDialog(QDialog):
    def __init__(self, parent, db):
        super().__init__(parent)
        self.db = db
        self.result_pool = []
        self.smart = False
        self.setWindowTitle("Gruppen Zufall")
        self.setFixedSize(300, 400)
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("<b>Wähle Gruppen:</b>"))

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        self.vbox = QVBoxLayout(content)
        
        self.group_boxes = {}
        for g in self.db.get_all_groups():
            cb = QCheckBox(g)
            cb.setChecked(True)
            self.vbox.addWidget(cb)
            self.group_boxes[g] = cb
            
        scroll.setWidget(content)
        layout.addWidget(scroll)

        layout.addWidget(QLabel("<b>Medientyp:</b>"))
        hl = QHBoxLayout()
        self.cb_img = QCheckBox("Bilder")
        self.cb_img.setChecked(True)
        self.cb_vid = QCheckBox("Videos")
        self.cb_vid.setChecked(True)
        hl.addWidget(self.cb_img)
        hl.addWidget(self.cb_vid)
        layout.addLayout(hl)

        hl2 = QHBoxLayout()
        btn_norm = QPushButton("🎲 Normal")
        btn_norm.clicked.connect(lambda: self._execute(False))
        btn_smart = QPushButton("⚖️ Smart")
        btn_smart.clicked.connect(lambda: self._execute(True))
        hl2.addWidget(btn_norm)
        hl2.addWidget(btn_smart)
        layout.addLayout(hl2)

    def _execute(self, smart):
        sel_grps = [g for g, cb in self.group_boxes.items() if cb.isChecked()]
        sel_types = []
        if self.cb_img.isChecked(): sel_types.append("Bilder")
        if self.cb_vid.isChecked(): sel_types.append("Videos")

        self.result_pool = [e for e in self.db.entries if e.group in sel_grps and e.entry_type in sel_types]
        self.smart = smart
        self.accept()
