"""Application entry point."""

import sys

from PyQt6.QtCore import QCoreApplication, Qt, QTimer
from PyQt6.QtGui import QColor, QFont, QPainter, QPixmap
from PyQt6.QtWidgets import QApplication, QSplashScreen

from mediavault.config import setup_logging
from mediavault.gui.main_window import MainWindow
from mediavault.gui.theme import ThemeManager


def _build_splash_pixmap(colors: dict[str, str]) -> QPixmap:
    """Build a splash image matching the active theme."""
    pixmap = QPixmap(420, 240)
    pixmap.fill(QColor(colors["bg"]))

    painter = QPainter(pixmap)
    painter.setPen(QColor(colors["text"]))
    title_font = QFont("Segoe UI", 22, QFont.Weight.Bold)
    painter.setFont(title_font)
    painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, "MediaVault")

    painter.setPen(QColor(colors["primary"]))
    sub_font = QFont("Segoe UI", 11)
    painter.setFont(sub_font)
    painter.drawText(
        pixmap.rect().adjusted(0, 60, 0, 0),
        Qt.AlignmentFlag.AlignCenter,
        "Lade Bibliothek …",
    )
    painter.end()
    return pixmap


def main() -> None:
    """Start the Qt application with the stored theme and a splash screen."""
    setup_logging()
    QCoreApplication.setOrganizationName("MediaVault")
    QCoreApplication.setApplicationName("MediaVault")

    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    theme = ThemeManager()
    theme.apply(app)

    splash = QSplashScreen(_build_splash_pixmap(theme.palette()))
    splash.show()
    app.processEvents()

    window = MainWindow(theme)

    # Keep the splash visible for at least 1.2 s so it does not just flash.
    def _show_main() -> None:
        window.show()
        splash.finish(window)

    QTimer.singleShot(1200, _show_main)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
