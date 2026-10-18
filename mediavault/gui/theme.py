"""Zentrale Dark-/Light-Themes für die gesamte Oberfläche."""

from string import Template

from PyQt6.QtCore import QObject, QSettings, pyqtSignal
from PyQt6.QtGui import QColor, QPalette
from PyQt6.QtWidgets import QApplication, QWidget

ORGANIZATION = "MediaVault"
APPLICATION = "MediaTracker"
SETTINGS_KEY = "appearance/theme"

PALETTES: dict[str, dict[str, str]] = {
    "dark": {
        "bg": "#14161a",
        "surface": "#1c1f26",
        "surface_alt": "#232833",
        "hover": "#2b3240",
        "input_bg": "#1a1e25",
        "border": "#2c3340",
        "border_strong": "#3d4657",
        "text": "#e6e8ec",
        "text_muted": "#98a2b3",
        "primary": "#4f8cff",
        "primary_hover": "#6ba0ff",
        "primary_text": "#ffffff",
        "danger": "#e05252",
        "danger_hover": "#f06565",
        "selection_bg": "#1e2b42",
        "selection_fill": "rgba(79, 140, 255, 48)",
        "nav_active_bg": "#24324a",
        "scrollbar": "#3a4250",
        "scrollbar_hover": "#4a5466",
        "score_high": "#2f9e6f",
        "score_mid": "#c08a2e",
        "score_low": "#c2703a",
        "score_bad": "#d9534f",
    },
    "light": {
        "bg": "#f4f6fa",
        "surface": "#ffffff",
        "surface_alt": "#eef1f6",
        "hover": "#e8ecf2",
        "input_bg": "#ffffff",
        "border": "#d7dde7",
        "border_strong": "#b9c3d3",
        "text": "#1b1f24",
        "text_muted": "#5b6472",
        "primary": "#2563eb",
        "primary_hover": "#1d4ed8",
        "primary_text": "#ffffff",
        "danger": "#d92d20",
        "danger_hover": "#b91c1c",
        "selection_bg": "#e8efff",
        "selection_fill": "rgba(37, 99, 235, 40)",
        "nav_active_bg": "#e3ecff",
        "scrollbar": "#c7cfdb",
        "scrollbar_hover": "#aeb9c9",
        "score_high": "#12805c",
        "score_mid": "#b45309",
        "score_low": "#c2410c",
        "score_bad": "#d92d20",
    },
}

_STYLESHEET = Template(
    """
QMainWindow, QDialog {
    background-color: $bg;
}

QWidget {
    color: $text;
    font-family: "Segoe UI";
    font-size: 13px;
}

QWidget#Sidebar {
    background-color: $surface;
    border-right: 1px solid $border;
}

QLabel#AppTitle { font-size: 21px; font-weight: 700; }
QLabel#AppSubtitle { color: $text_muted; font-size: 11px; }
QLabel#SectionLabel { color: $text_muted; font-size: 10px; font-weight: 700; }
QLabel#PageTitle { font-size: 24px; font-weight: 700; }
QLabel#DialogTitle { font-size: 20px; font-weight: 700; }
QLabel#MutedLabel, QLabel#CardGroup { color: $text_muted; }
QLabel#FieldLabel { color: $text_muted; font-size: 11px; font-weight: 600; }
QLabel#SelectionCount { font-weight: 700; }
QLabel#HintLabel { color: $text_muted; font-size: 11px; }

QWidget#ActionBar {
    background-color: $surface;
    border: 1px solid $border;
    border-radius: 10px;
}

QPushButton {
    background-color: $surface_alt;
    color: $text;
    border: 1px solid $border;
    border-radius: 8px;
    padding: 7px 13px;
}
QPushButton:hover { background-color: $hover; }
QPushButton:pressed { background-color: $border; }
QPushButton:disabled {
    color: $text_muted;
    background-color: transparent;
    border-color: $border;
}

QPushButton[variant="primary"] {
    background-color: $primary;
    color: $primary_text;
    border: 1px solid $primary;
    font-weight: 700;
}
QPushButton[variant="primary"]:hover {
    background-color: $primary_hover;
    border-color: $primary_hover;
}
QPushButton[variant="secondary"] { background-color: transparent; }
QPushButton[variant="danger"] {
    background-color: $danger;
    color: #ffffff;
    border: 1px solid $danger;
    font-weight: 700;
}
QPushButton[variant="danger"]:hover {
    background-color: $danger_hover;
    border-color: $danger_hover;
}
QPushButton[variant="ghost"] {
    background-color: transparent;
    border-color: transparent;
}
QPushButton[variant="ghost"]:hover {
    background-color: $hover;
    border-color: $border;
}

QPushButton[nav="true"] {
    text-align: left;
    padding: 9px 12px;
    background-color: transparent;
    border: 1px solid transparent;
    border-radius: 8px;
    color: $text_muted;
    font-weight: 600;
}
QPushButton[nav="true"]:hover { background-color: $hover; color: $text; }
QPushButton[nav="true"]:checked {
    background-color: $nav_active_bg;
    border-color: $nav_active_bg;
    color: $primary;
}

QLineEdit, QTextEdit, QComboBox {
    background-color: $input_bg;
    border: 1px solid $border;
    border-radius: 8px;
    padding: 6px 9px;
    selection-background-color: $primary;
    selection-color: $primary_text;
}
QLineEdit:focus, QTextEdit:focus, QComboBox:focus { border-color: $primary; }
QComboBox { padding-right: 24px; }
QComboBox QAbstractItemView {
    background-color: $surface;
    border: 1px solid $border;
    border-radius: 8px;
    padding: 4px;
    selection-background-color: $nav_active_bg;
    selection-color: $primary;
    outline: none;
}

QCheckBox { spacing: 8px; background: transparent; }
QCheckBox::indicator {
    width: 16px;
    height: 16px;
    border: 1px solid $border_strong;
    border-radius: 4px;
    background-color: $input_bg;
}
QCheckBox::indicator:hover { border-color: $primary; }
QCheckBox::indicator:checked {
    background-color: $primary;
    border-color: $primary;
}

QScrollArea { border: none; background: transparent; }
QWidget#GridContainer, QWidget#GridViewport { background: transparent; }

QScrollBar:vertical { background: transparent; width: 10px; margin: 2px; }
QScrollBar::handle:vertical {
    background: $scrollbar;
    min-height: 30px;
    border-radius: 5px;
}
QScrollBar::handle:vertical:hover { background: $scrollbar_hover; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }
QScrollBar:horizontal { background: transparent; height: 10px; margin: 2px; }
QScrollBar::handle:horizontal {
    background: $scrollbar;
    min-width: 30px;
    border-radius: 5px;
}
QScrollBar::handle:horizontal:hover { background: $scrollbar_hover; }
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; }
QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal { background: transparent; }

QFrame#MediaCard {
    background-color: $surface;
    border: 2px solid $border;
    border-radius: 12px;
}
QFrame#MediaCard:hover {
    background-color: $surface_alt;
    border-color: $border_strong;
}
QFrame#MediaCard[selected="true"] {
    background-color: $selection_bg;
    border-color: $primary;
}

QLabel#CardImage {
    background-color: $surface_alt;
    border-radius: 8px;
    color: $text_muted;
}
QLabel#CardTitle { background: transparent; font-weight: 700; }
QLabel#SelectionBadge {
    background-color: $primary;
    color: $primary_text;
    border-radius: 11px;
    font-weight: 700;
}
QLabel#ScoreBadge {
    border-radius: 9px;
    padding: 2px 8px;
    font-size: 11px;
    font-weight: 700;
}
QLabel#ScoreBadge[tier="high"] { background-color: $score_high; color: #ffffff; }
QLabel#ScoreBadge[tier="mid"] { background-color: $score_mid; color: #ffffff; }
QLabel#ScoreBadge[tier="low"] { background-color: $score_low; color: #ffffff; }
QLabel#ScoreBadge[tier="bad"] { background-color: $score_bad; color: #ffffff; }

QLabel#DialogImage {
    background-color: $surface_alt;
    border-radius: 10px;
    color: $text_muted;
}

QRubberBand {
    background-color: $selection_fill;
    border: 1px solid $primary;
}

QToolTip {
    background-color: $surface;
    color: $text;
    border: 1px solid $border;
    border-radius: 6px;
    padding: 5px 8px;
}

QMenu, QMessageBox { background-color: $surface; }
QMenu::item:selected { background-color: $nav_active_bg; color: $primary; }
"""
)


def build_stylesheet(name: str) -> str:
    """Return the QSS for the requested theme, falling back to dark."""
    colors = PALETTES.get(name, PALETTES["dark"])
    return _STYLESHEET.substitute(colors)


def build_qpalette(name: str) -> QPalette:
    """Return a QPalette for native dialogs and popups."""
    colors = PALETTES.get(name, PALETTES["dark"])
    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor(colors["bg"]))
    palette.setColor(QPalette.ColorRole.WindowText, QColor(colors["text"]))
    palette.setColor(QPalette.ColorRole.Base, QColor(colors["input_bg"]))
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor(colors["surface_alt"]))
    palette.setColor(QPalette.ColorRole.Text, QColor(colors["text"]))
    palette.setColor(QPalette.ColorRole.Button, QColor(colors["surface_alt"]))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor(colors["text"]))
    palette.setColor(QPalette.ColorRole.Highlight, QColor(colors["primary"]))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor(colors["primary_text"]))
    palette.setColor(QPalette.ColorRole.ToolTipBase, QColor(colors["surface"]))
    palette.setColor(QPalette.ColorRole.ToolTipText, QColor(colors["text"]))
    palette.setColor(QPalette.ColorRole.PlaceholderText, QColor(colors["text_muted"]))
    palette.setColor(QPalette.ColorRole.Link, QColor(colors["primary"]))
    palette.setColor(
        QPalette.ColorGroup.Disabled,
        QPalette.ColorRole.Text,
        QColor(colors["text_muted"]),
    )
    palette.setColor(
        QPalette.ColorGroup.Disabled,
        QPalette.ColorRole.ButtonText,
        QColor(colors["text_muted"]),
    )
    return palette


def repolish(widget: QWidget) -> None:
    """Force a restyle after a dynamic property (e.g. ``selected``) changed."""
    style = widget.style()
    style.unpolish(widget)
    style.polish(widget)
    widget.update()


class ThemeManager(QObject):
    """Manage the active theme and persist the user's choice."""

    theme_changed = pyqtSignal(str)

    def __init__(
        self, settings: QSettings | None = None, parent: QObject | None = None
    ) -> None:
        """Load the stored theme, defaulting to dark."""
        super().__init__(parent)
        self._settings = settings or QSettings(ORGANIZATION, APPLICATION)
        stored = str(self._settings.value(SETTINGS_KEY, "dark"))
        self._name = stored if stored in PALETTES else "dark"

    @property
    def name(self) -> str:
        """Name of the active theme ("dark" or "light")."""
        return self._name

    def palette(self) -> dict[str, str]:
        """Color palette of the active theme."""
        return PALETTES[self._name]

    def apply(self, app: QApplication, name: str | None = None) -> str:
        """Apply a theme to the application and persist the choice."""
        if name in PALETTES:
            self._name = name
        app.setPalette(build_qpalette(self._name))
        app.setStyleSheet(build_stylesheet(self._name))
        self._settings.setValue(SETTINGS_KEY, self._name)
        for widget in app.allWidgets():
            repolish(widget)
        self.theme_changed.emit(self._name)
        return self._name

    def toggle(self, app: QApplication) -> str:
        """Switch between dark and light and return the new theme name."""
        return self.apply(app, "light" if self._name == "dark" else "dark")
