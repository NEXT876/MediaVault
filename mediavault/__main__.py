"""Application entry point."""

import sys

from PyQt6.QtCore import QCoreApplication, Qt, QTimer
from PyQt6.QtGui import QColor, QFont, QPainter, QPixmap
from PyQt6.QtWidgets import QApplication, QSplashScreen

from mediavault.config import setup_logging
from mediavault.gui.main_window import MainWindow
from mediavault.gui.theme import FONT_FAMILIES, ThemeManager


def _splash_font(point_size: int, weight: QFont.Weight = QFont.Weight.Normal) -> QFont:
    """Return a font using the same cross-platform family fallback as the app."""
    font = QFont()
    font.setFamilies(FONT_FAMILIES)
    font.setPointSize(point_size)
    font.setWeight(weight)
    return font


def _build_splash_pixmap(colors: dict[str, str]) -> QPixmap:
    """Build a splash image matching the active theme."""
    pixmap = QPixmap(420, 240)
    pixmap.fill(QColor(colors["bg"]))

    painter = QPainter(pixmap)
    painter.setPen(QColor(colors["text"]))
    painter.setFont(_splash_font(22, QFont.Weight.Bold))
    painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, "MediaVault")

    painter.setPen(QColor(colors["primary"]))
    painter.setFont(_splash_font(11))
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
    font = app.font()
    font.setFamilies(FONT_FAMILIES)
    app.setFont(font)

    theme = ThemeManager()
    theme.apply(app)

    splash = QSplashScreen(_build_splash_pixmap(theme.palette()))
    splash.show()
    app.processEvents()

    window = MainWindow(theme)

    def _scan_after_show() -> None:
        window.scan_folder()
        window.refresh_data()

    # Keep the splash visible for at least 1.2 s so it does not just flash.
    def _show_main() -> None:
        window.show()
        splash.finish(window)
        # Scan after the first paint so the splash is not frozen mid-redraw.
        QTimer.singleShot(0, _scan_after_show)

    QTimer.singleShot(1200, _show_main)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
