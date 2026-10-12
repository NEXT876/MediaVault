from PyQt6.QtWidgets import QFrame, QVBoxLayout, QLabel, QCheckBox
from PyQt6.QtCore import Qt, pyqtSignal

class MediaCard(QFrame):
    # Qt Signals für saubere Kommunikation mit dem Hauptfenster
    clicked = pyqtSignal(object) 
    selection_changed = pyqtSignal(object, bool)

    def __init__(self, entry, pixmap):
        super().__init__()
        self.entry = entry
        self.setFixedSize(180, 240)
        self.setObjectName("MediaCard") # Für CSS Styling

        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)

        # Checkbox oben links
        self.checkbox = QCheckBox(self)
        self.checkbox.move(10, 10)
        self.checkbox.stateChanged.connect(self._on_checkbox_toggled)

        # Bild
        self.img_lbl = QLabel()
        self.img_lbl.setFixedSize(140, 140)
        self.img_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        if pixmap:
            # Skaliert das Bild nativ und hochqualitativ
            scaled = pixmap.scaled(140, 140, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            self.img_lbl.setPixmap(scaled)
        else:
            self.img_lbl.setText("[Kein Bild]")
            self.img_lbl.setStyleSheet("background-color: #333; color: #888;")
        layout.addWidget(self.img_lbl)

        # Titel
        title_text = self.entry.title[:15] + "..." if len(self.entry.title) > 18 else self.entry.title
        self.title_lbl = QLabel(title_text)
        self.title_lbl.setStyleSheet("font-weight: bold; font-size: 13px;")
        layout.addWidget(self.title_lbl, alignment=Qt.AlignmentFlag.AlignHCenter)

        # Score
        self.score_lbl = QLabel(f"Score: {self.entry.score}")
        self.score_lbl.setStyleSheet("color: #3b8ed0; font-size: 12px;")
        layout.addWidget(self.score_lbl, alignment=Qt.AlignmentFlag.AlignHCenter)

    def _on_checkbox_toggled(self, state):
        is_checked = (state == Qt.CheckState.Checked.value)
        self.selection_changed.emit(self.entry, is_checked)
        self.setStyleSheet("QFrame#MediaCard { border: 2px solid #3b8ed0; background-color: #2a2a2a; }" if is_checked else "")

    def set_checked(self, state: bool):
        self.checkbox.setChecked(state)

    def mousePressEvent(self, event):
        # Klick auf die Kachel öffnet die Details (außer man trifft exakt die Checkbox)
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.entry)