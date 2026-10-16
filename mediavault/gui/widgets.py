from PyQt6.QtWidgets import QFrame, QVBoxLayout, QLabel, QCheckBox
from PyQt6.QtCore import Qt, pyqtSignal, QTimer

class MediaCard(QFrame):
    """Kachel-Widget, das einen Medien-Eintrag mit Bild, Titel und Score zeigt."""

    # Qt Signals für saubere Kommunikation mit dem Hauptfenster
    double_clicked = pyqtSignal(object)
    selection_changed = pyqtSignal(object, bool)

    def __init__(self, entry, pixmap):
        """Erstellt die Kachel für einen Eintrag mit optionalem Vorschaubild."""
        super().__init__()
        self.entry = entry
        self.setFixedSize(180, 240)
        self.setObjectName("MediaCard") # Für CSS Styling

        self._pending_single_click = False
        self.click_timer = QTimer(self)
        self.click_timer.setSingleShot(True)
        self.click_timer.setInterval(200)
        self.click_timer.timeout.connect(self._handle_single_click)

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

    def _update_visual_state(self, is_checked):
        """Hebt die Kachel bei aktivierter Auswahl optisch hervor."""
        self.setStyleSheet(
            "QFrame#MediaCard { border: 2px solid #3b8ed0; background-color: #2a2a2a; }"
            if is_checked else ""
        )

    def _on_checkbox_toggled(self, state):
        """Sendet Auswahländerung und hebt die Kachel bei Aktivierung hervor."""
        is_checked = (state == Qt.CheckState.Checked.value)
        self._update_visual_state(is_checked)
        self.selection_changed.emit(self.entry, is_checked)

    def set_checked(self, state: bool, emit=True):
        """Setzt den Auswahlstatus der Kachel-Checkbox."""
        if self.checkbox.isChecked() == state:
            self._update_visual_state(state)
            return

        if not emit:
            self.checkbox.blockSignals(True)
        self.checkbox.setChecked(state)
        if not emit:
            self.checkbox.blockSignals(False)
            self._update_visual_state(state)

    def mousePressEvent(self, event):
        """Startet den Timer für einen einfachen Klick (Toggle der Auswahl)."""
        if event.button() == Qt.MouseButton.LeftButton:
            self._pending_single_click = True
            self.click_timer.start()
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event):
        """Öffnet bei Doppelklick die Detailansicht des Eintrags."""
        if event.button() == Qt.MouseButton.LeftButton:
            self._pending_single_click = False
            self.click_timer.stop()
            self.double_clicked.emit(self.entry)
        super().mouseDoubleClickEvent(event)

    def _handle_single_click(self):
        """Toggelt die Auswahl, wenn kein Doppelklick gefolgt ist."""
        if self._pending_single_click:
            self._pending_single_click = False
            self.checkbox.toggle()
