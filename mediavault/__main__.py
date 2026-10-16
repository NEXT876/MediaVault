import sys
from PyQt6.QtWidgets import QApplication, QSplashScreen
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QPixmap, QPainter, QColor, QFont
from mediavault.gui.main_window import MainWindow
from mediavault.config import setup_logging

# Ein einfaches, modernes Dark-Theme für PyQt6
DARK_STYLE = """
QWidget {
    background-color: #1e1e1e;
    color: #e0e0e0;
    font-family: Arial;
}
QLineEdit, QTextEdit, QComboBox {
    background-color: #2a2a2a;
    border: 1px solid #444;
    border-radius: 4px;
    padding: 4px;
}
QPushButton {
    background-color: #333;
    border: 1px solid #555;
    border-radius: 4px;
    padding: 6px;
}
QPushButton:hover {
    background-color: #444;
}
QScrollBar:vertical {
    border: none;
    background: #1e1e1e;
    width: 12px;
}
QScrollBar::handle:vertical {
    background: #555;
    border-radius: 6px;
}
"""

def _build_splash_pixmap():
    """Erzeugt ein einfaches Splash-Bild im Dark-Theme (ohne externe Datei)."""
    pixmap = QPixmap(420, 240)
    pixmap.fill(QColor("#1e1e1e"))

    painter = QPainter(pixmap)
    painter.setPen(QColor("#e0e0e0"))
    title_font = QFont("Arial", 22, QFont.Weight.Bold)
    painter.setFont(title_font)
    painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, "Media Tracker")

    painter.setPen(QColor("#3b8ed0"))
    sub_font = QFont("Arial", 11)
    painter.setFont(sub_font)
    painter.drawText(
        pixmap.rect().adjusted(0, 60, 0, 0),
        Qt.AlignmentFlag.AlignCenter,
        "Lade Bibliothek …",
    )
    painter.end()
    return pixmap


def main():
    """Startet die Qt-Anwendung mit Dark-Theme, Splash-Screen und Hauptfenster."""
    setup_logging()
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setStyleSheet(DARK_STYLE)

    splash = QSplashScreen(_build_splash_pixmap())
    splash.show()
    app.processEvents()

    window = MainWindow()

    # Splash mindestens 1,2 s sichtbar halten, damit er nicht nur aufblitzt.
    def _show_main():
        window.show()
        splash.finish(window)

    QTimer.singleShot(1200, _show_main)
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
