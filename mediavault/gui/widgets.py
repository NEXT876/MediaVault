"""Kachel-Widget für die Medienübersicht."""

from PyQt6.QtCore import QPointF, QRectF, Qt, pyqtSignal
from PyQt6.QtGui import QPainter, QPainterPath, QPixmap
from PyQt6.QtWidgets import QApplication, QFrame, QHBoxLayout, QLabel, QVBoxLayout

from mediavault.gui.theme import repolish

CARD_WIDTH = 200
CARD_HEIGHT = 270
IMAGE_SIZE = 176
IMAGE_RADIUS = 10


def score_tier(score):
    """Kategorisiert einen Score für das farbige Badge."""
    if score >= 75:
        return "high"
    if score >= 50:
        return "mid"
    if score >= 25:
        return "low"
    return "bad"


def rounded_pixmap(pixmap, size=IMAGE_SIZE, radius=IMAGE_RADIUS):
    """Skaliert ein Pixmap und rundet die Ecken für die Kartenoptik."""
    scaled = pixmap.scaled(
        size,
        size,
        Qt.AspectRatioMode.KeepAspectRatio,
        Qt.TransformationMode.SmoothTransformation,
    )
    canvas = QPixmap(size, size)
    canvas.fill(Qt.GlobalColor.transparent)

    painter = QPainter(canvas)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    path = QPainterPath()
    path.addRoundedRect(QRectF(0, 0, size, size), radius, radius)
    painter.setClipPath(path)
    x = (size - scaled.width()) / 2
    y = (size - scaled.height()) / 2
    painter.drawPixmap(QPointF(x, y), scaled)
    painter.end()
    return canvas


class MediaCard(QFrame):
    """Kachel mit Vorschau, Titel, Score und Auswahlzustand."""

    clicked = pyqtSignal(object, object)
    double_clicked = pyqtSignal(object)
    drag_pressed = pyqtSignal(object, object)
    drag_moved = pyqtSignal(object)
    drag_finished = pyqtSignal()

    def __init__(self, entry, pixmap):
        """Erstellt die Kachel für einen Eintrag mit optionalem Vorschaubild."""
        super().__init__()
        self.entry = entry
        self._selected = False
        self._press_global = None
        self._dragging = False
        self._suppress_release = False

        self.setObjectName("MediaCard")
        self.setFixedSize(CARD_WIDTH, CARD_HEIGHT)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        self.setProperty("selected", "false")
        self.setToolTip(entry.title)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(6)

        self.img_lbl = QLabel()
        self.img_lbl.setObjectName("CardImage")
        self.img_lbl.setFixedSize(IMAGE_SIZE, IMAGE_SIZE)
        self.img_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.img_lbl.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        if pixmap and not pixmap.isNull():
            self.img_lbl.setPixmap(rounded_pixmap(pixmap))
        else:
            self.img_lbl.setText("Kein Vorschaubild")
        layout.addWidget(self.img_lbl, alignment=Qt.AlignmentFlag.AlignHCenter)

        self.title_lbl = QLabel()
        self.title_lbl.setObjectName("CardTitle")
        self.title_lbl.setFixedSize(IMAGE_SIZE, 20)
        self.title_lbl.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.title_lbl.setText(
            self.title_lbl.fontMetrics().elidedText(
                entry.title, Qt.TextElideMode.ElideRight, IMAGE_SIZE
            )
        )
        self.title_lbl.setToolTip(entry.title)
        layout.addWidget(self.title_lbl)

        bottom = QHBoxLayout()
        bottom.setSpacing(6)

        self.score_lbl = QLabel(f"Score {entry.score}")
        self.score_lbl.setObjectName("ScoreBadge")
        self.score_lbl.setProperty("tier", score_tier(entry.score))
        self.score_lbl.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        bottom.addWidget(self.score_lbl)

        bottom.addStretch()

        group_text = entry.group or "Ohne Gruppe"
        self.group_lbl = QLabel()
        self.group_lbl.setObjectName("CardGroup")
        self.group_lbl.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.group_lbl.setText(
            self.group_lbl.fontMetrics().elidedText(
                group_text, Qt.TextElideMode.ElideRight, 82
            )
        )
        self.group_lbl.setToolTip(group_text)
        bottom.addWidget(self.group_lbl)
        layout.addLayout(bottom)

        layout.addStretch()

        self.selection_badge = QLabel("✓", self)
        self.selection_badge.setObjectName("SelectionBadge")
        self.selection_badge.setFixedSize(22, 22)
        self.selection_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.selection_badge.setAttribute(
            Qt.WidgetAttribute.WA_TransparentForMouseEvents, True
        )
        self.selection_badge.move(12, 12)
        self.selection_badge.hide()
        self.selection_badge.raise_()

    def set_selected(self, selected):
        """Hebt die Kachel bei aktiver Auswahl optisch hervor."""
        selected = bool(selected)
        if self._selected == selected:
            return
        self._selected = selected
        self.setProperty("selected", "true" if selected else "false")
        self.selection_badge.setVisible(selected)
        repolish(self)

    def mousePressEvent(self, event):
        """Merkt den Druckpunkt und meldet ihn vor jeder Auswahländerung."""
        if event.button() == Qt.MouseButton.LeftButton:
            self.setFocus()
            self._press_global = event.globalPosition().toPoint()
            self._dragging = False
            self._suppress_release = False
            self.drag_pressed.emit(self.entry, self._press_global)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        """Startet nach Überschreiten der Schwelle eine Rechteckauswahl."""
        if self._press_global is not None and (
            event.buttons() & Qt.MouseButton.LeftButton
        ):
            current = event.globalPosition().toPoint()
            distance = (current - self._press_global).manhattanLength()
            if not self._dragging and distance >= QApplication.startDragDistance():
                self._dragging = True
            if self._dragging:
                self.drag_moved.emit(current)
                event.accept()
                return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        """Sendet einen Klick oder beendet die Rechteckauswahl."""
        if event.button() == Qt.MouseButton.LeftButton:
            if self._suppress_release:
                self._suppress_release = False
                self._reset_press()
                event.accept()
                return

            if self._dragging:
                self.drag_moved.emit(event.globalPosition().toPoint())
                self.drag_finished.emit()
            else:
                self.clicked.emit(self.entry, event.modifiers())

            self._reset_press()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event):
        """Öffnet die Detailansicht und unterdrückt den folgenden Release."""
        if event.button() == Qt.MouseButton.LeftButton:
            self._suppress_release = True
            self._dragging = False
            self._press_global = None
            self.double_clicked.emit(self.entry)
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def _reset_press(self):
        """Setzt den internen Mauszustand zurück."""
        self._press_global = None
        self._dragging = False
