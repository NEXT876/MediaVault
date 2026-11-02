"""Sidebar with views, storage, random picks, online import, extras and settings."""

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QLabel, QPushButton, QVBoxLayout, QWidget

from mediavault.gui.collapsible import CollapsibleSection
from mediavault.gui.widgets import button, hint_label
from mediavault.models import MediaType

# Pages besides the library views; MediaType values name the library views.
DOWNLOADS = "downloads"
WHEEL = "wheel"
ONLINE_SECTION_KEY = "sidebar/online_expanded"


def _section_label(text: str) -> QLabel:
    """Create a muted section heading."""
    label = QLabel(text)
    label.setObjectName("SectionLabel")
    label.setContentsMargins(4, 10, 0, 2)
    return label


def _hint_label() -> QLabel:
    """Create a small wrapped status line under a button."""
    label = hint_label()
    label.setContentsMargins(4, 0, 0, 0)
    return label


def _nav_button(text: str, checkable: bool = False) -> QPushButton:
    """Create a left-aligned navigation btn."""
    btn = QPushButton(text)
    btn.setProperty("nav", True)
    btn.setCursor(Qt.CursorShape.PointingHandCursor)
    if checkable:
        btn.setCheckable(True)
        btn.setAutoExclusive(True)
    return btn


class Sidebar(QWidget):
    """Left navigation column; it only reports clicks and shows state."""

    view_requested = pyqtSignal(object)
    downloads_requested = pyqtSignal()
    random_requested = pyqtSignal(bool, bool)  # smart, global pool
    group_random_requested = pyqtSignal()
    stick_requested = pyqtSignal()
    analysis_requested = pyqtSignal()
    sync_requested = pyqtSignal()
    rule34_requested = pyqtSignal()
    wheel_requested = pyqtSignal()
    config_requested = pyqtSignal()
    theme_requested = pyqtSignal()
    new_requested = pyqtSignal()

    def __init__(self, parent: QWidget | None = None) -> None:
        """Build all sections; mode-specific ones start visible."""
        super().__init__(parent)
        self.setObjectName("Sidebar")
        self.setFixedWidth(250)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 22, 16, 22)
        layout.setSpacing(6)

        title = QLabel("MediaVault")
        title.setObjectName("AppTitle")
        subtitle = QLabel("Deine Medienbibliothek")
        subtitle.setObjectName("AppSubtitle")
        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addSpacing(12)

        layout.addWidget(_section_label("ANSICHTEN"))
        self._view_buttons = {
            MediaType.IMAGE: _nav_button("🖼️  Bilder", checkable=True),
            MediaType.VIDEO: _nav_button("🎬  Videos", checkable=True),
        }
        for view, btn in self._view_buttons.items():
            btn.clicked.connect(lambda _=False, v=view: self.view_requested.emit(v))
            layout.addWidget(btn)

        layout.addWidget(_section_label("SPEICHER"))
        btn_stick = self._add(layout, "🔌  Stick einrichten", self.stick_requested)
        btn_stick.setToolTip(
            "Ordner auf einem USB-Stick als Mediathek einrichten oder zuweisen"
        )
        self._lbl_stick = _hint_label()
        layout.addWidget(self._lbl_stick)

        self._ai_widgets: list[QWidget] = [_section_label("KI-ANALYSE")]
        layout.addWidget(self._ai_widgets[0])
        self._ai_widgets.append(
            self._add(layout, "📊  Analyse", self.analysis_requested)
        )
        self._btn_sync = self._add(
            layout, "🔄  Ordner synchronisieren", self.sync_requested
        )
        self._btn_sync.setToolTip("Ordner jetzt nach neuen Bildern durchsuchen")
        self._lbl_last_sync = _hint_label()
        layout.addWidget(self._lbl_last_sync)

        layout.addWidget(_section_label("ZUFALL (LOKAL)"))
        self._add_random(layout, "🎲  Normal", smart=False, global_pool=False)
        self._add_random(layout, "⚖️  Smart", smart=True, global_pool=False)
        layout.addWidget(_section_label("ZUFALL (GLOBAL)"))
        self._add_random(layout, "🌍  Alles", smart=False, global_pool=True)
        self._add_random(layout, "⚖️🌍  Alles Smart", smart=True, global_pool=True)
        self._add(layout, "📂  Aus Gruppen", self.group_random_requested)

        # Collapsed by default; the open/closed state is remembered.
        self._online_section = CollapsibleSection(
            "IMPORT FROM WEB", ONLINE_SECTION_KEY, expanded=False
        )
        self._btn_rule34 = _nav_button("")
        self._btn_rule34.clicked.connect(lambda _=False: self.rule34_requested.emit())
        self._online_section.add_widget(self._btn_rule34)
        layout.addWidget(self._online_section)
        self.set_rule34_loading(False)
        self._btn_downloads = _nav_button("⬇️  Downloads", checkable=True)
        self._btn_downloads.clicked.connect(self.downloads_requested)
        self._btn_downloads.setVisible(False)
        layout.addWidget(self._btn_downloads)

        layout.addWidget(_section_label("EXTRAS"))
        self._btn_wheel = _nav_button("🎡  Glücksrad", checkable=True)
        self._btn_wheel.clicked.connect(lambda _=False: self.wheel_requested.emit())
        layout.addWidget(self._btn_wheel)

        layout.addStretch()
        self._add(layout, "⚙️  Config wechseln", self.config_requested)
        self._btn_theme = self._add(layout, "", self.theme_requested)

        btn_new = button(
            "+  Neuer Eintrag", "primary", self.new_requested.emit, cursor=True
        )
        btn_new.setFixedHeight(40)
        layout.addWidget(btn_new)

    def _add(self, layout: QVBoxLayout, text: str, signal: pyqtSignal) -> QPushButton:
        """Add a navigation btn that emits ``signal`` when clicked."""
        btn = _nav_button(text)
        btn.clicked.connect(lambda _=False: signal.emit())
        layout.addWidget(btn)
        return btn

    def _add_random(
        self, layout: QVBoxLayout, text: str, smart: bool, global_pool: bool
    ) -> None:
        """Add a btn that asks for a random pick."""
        btn = _nav_button(text)
        btn.clicked.connect(
            lambda _=False: self.random_requested.emit(smart, global_pool)
        )
        layout.addWidget(btn)

    # --- State ---
    def set_mode(self, ai: bool, has_folder: bool) -> None:
        """Show only the sections that fit the active config's mode."""
        self._view_buttons[MediaType.VIDEO].setVisible(not ai)
        for widget in self._ai_widgets:
            widget.setVisible(ai)
        self._btn_sync.setVisible(ai and has_folder)
        self._lbl_last_sync.setVisible(ai and has_folder)
        self._online_section.setVisible(not ai)

    def set_page(self, page: MediaType | str) -> None:
        """Check the button of a library view, DOWNLOADS or WHEEL."""
        for media_type, btn in self._view_buttons.items():
            btn.setChecked(media_type == page)
        self._btn_downloads.setChecked(page == DOWNLOADS)
        self._btn_wheel.setChecked(page == WHEEL)

    def set_stick_status(self, text: str) -> None:
        """Show the connection state of the config's stick."""
        self._lbl_stick.setText(text)

    def set_last_sync(self, stamp: str) -> None:
        """Show when the config's folder was last synchronized."""
        self._lbl_last_sync.setText(
            f"Zuletzt synchronisiert: {stamp}" if stamp else "Noch nicht synchronisiert"
        )

    def set_sync_running(self, running: bool) -> None:
        """Disable the sync button while a folder sync runs."""
        self._btn_sync.setEnabled(not running)

    def set_rule34_loading(self, loading: bool) -> None:
        """Show that posts are being fetched."""
        self._btn_rule34.setEnabled(not loading)
        self._btn_rule34.setText("⬇️  Lade Posts …" if loading else "⬇️  rule34 Import")

    def set_downloads(self, open_jobs: int, has_jobs: bool) -> None:
        """Mirror the download queue on its button."""
        self._btn_downloads.setText(
            f"⬇️  Downloads ({open_jobs})" if open_jobs else "⬇️  Downloads"
        )
        self._btn_downloads.setVisible(has_jobs)

    def set_theme(self, dark: bool) -> None:
        """Label the theme toggle with the theme it switches to."""
        self._btn_theme.setText("☀️  Helles Theme" if dark else "🌙  Dunkles Theme")
        self._btn_theme.setToolTip(
            "Zu hellem Theme wechseln" if dark else "Zu dunklem Theme wechseln"
        )
