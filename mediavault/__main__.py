"""Application entry point: ``python -m mediavault`` or the ``mediavault`` script.

Sets up logging and the Qt application (Fusion style, shared font fallback,
stored theme), shows a themed splash screen while :class:`MainWindow` builds,
and then hands control to the Qt event loop. The first folder scan runs only
after the main window has painted, so the splash never freezes mid-redraw.
"""

import sys

from PyQt6.QtCore import QCoreApplication, Qt, QTimer
from PyQt6.QtGui import QColor, QFont, QPainter, QPixmap
from PyQt6.QtWidgets import QApplication, QSplashScreen

from mediavault.config import setup_logging
from mediavault.gui.main_window import MainWindow
from mediavault.gui.theme import FONT_FAMILIES, ThemeManager


def _splash_font(point_size: int, weight: QFont.Weight = QFont.Weight.Normal) -> QFont:
    """Return a splash font using the same cross-platform family fallback as the app.

    Args:
        point_size: Font size in points.
        weight: Font weight, normal by default.

    Returns:
        A ``QFont`` configured with :data:`FONT_FAMILIES`.
    """
    font = QFont()
    font.setFamilies(FONT_FAMILIES)
    font.setPointSize(point_size)
    font.setWeight(weight)
    return font


def _build_splash_pixmap(colors: dict[str, str]) -> QPixmap:
    """Paint the splash image: the app name and a loading hint in theme colors.

    Args:
        colors: Theme palette from :meth:`ThemeManager.palette`; uses the
            ``bg``, ``text`` and ``primary`` keys.

    Returns:
        A 420x240 pixmap for ``QSplashScreen``.
    """
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
    """Start the Qt application with the stored theme and a splash screen.

    Order of work: configure logging and the Qt organization/app name (used by
    ``QSettings``), apply the theme, show the splash, build :class:`MainWindow`,
    then after at least 1.2 s show the window and schedule the first folder scan.
    Never returns; exits the process with the Qt event loop's return code.
    """
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
        """Index the config folder and fill the grid once the window is visible."""
        window.auto_scan_folder()
        window.refresh_data()

    # Keep the splash visible for at least 1.2 s so it does not just flash.
    def _show_main() -> None:
        """Swap the splash for the main window and queue the first scan."""
        window.show()
        splash.finish(window)
        # Scan after the first paint so the splash is not frozen mid-redraw.
        QTimer.singleShot(0, _scan_after_show)

    QTimer.singleShot(1200, _show_main)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
