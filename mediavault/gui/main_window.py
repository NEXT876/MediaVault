"""Main window of MediaVault."""

import logging
import os
from collections.abc import Callable, Iterable
from datetime import datetime
from functools import partial
from typing import Any

from PyQt6.QtCore import (
    QEvent,
    QObject,
    QPoint,
    Qt,
    QTimer,
)
from PyQt6.QtGui import (
    QCloseEvent,
    QKeyEvent,
    QKeySequence,
    QPixmap,
    QResizeEvent,
)
from PyQt6.QtWidgets import (
    QApplication,
    QComboBox,
    QGridLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QProgressDialog,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from mediavault import transfer, volumes
from mediavault.ai_meta import extract_ai_metadata
from mediavault.config import (
    MODE_AI,
    LibraryRoot,
    load_configs,
    locate,
    save_configs,
)
from mediavault.gui import file_dialogs
from mediavault.gui.dialogs import (
    AnalysisDialog,
    ConfigDialog,
    DetailDialog,
    EditDialog,
    FolderPreviewDialog,
    GroupRandomDialog,
)
from mediavault.gui.downloads import DownloadJob, DownloadsPage, JobState
from mediavault.gui.rule34_dialog import Rule34Dialog, Rule34PreviewDialog
from mediavault.gui.selection import RubberBandSelector
from mediavault.gui.stick_banner import StickBanner
from mediavault.gui.stick_dialog import StickDialog
from mediavault.gui.theme import ThemeManager
from mediavault.gui.thumbnails import load_thumbnail, load_thumbnails
from mediavault.gui.widgets import CARD_WIDTH, MediaCard
from mediavault.gui.worker import Worker
from mediavault.importer import find_duplicate, import_paths, norm_path
from mediavault.models import MediaDatabase, MediaItem, MediaType
from mediavault.rule34 import Post, collect_new_posts_multi, fetch_preview
from mediavault.scanner import IMAGE_EXTS, VIDEO_EXTS, find_new_media
from mediavault.transfer import copy_into_folder

logger = logging.getLogger(__name__)

_SPINNER_FRAMES = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"


ALL_GROUPS = "Alle Gruppen"


def visible_entries(
    entries: Iterable[MediaItem],
    group_filter: str,
    query: str,
    sort_mode: str,
) -> list[MediaItem]:
    """Filter entries by group and text, then sort them for the card grid."""
    entries = list(entries)

    if group_filter and group_filter != ALL_GROUPS:
        entries = [entry for entry in entries if entry.group == group_filter]

    needle = query.strip().casefold()
    if needle:
        entries = [
            entry
            for entry in entries
            if needle in (entry.title or "").casefold()
            or needle in (entry.description or "").casefold()
            or needle in (entry.group or "").casefold()
            or needle in (entry.ai_meta.get("prompt") or "").casefold()
            or needle in (entry.ai_meta.get("negative_prompt") or "").casefold()
        ]

    if sort_mode == "score_desc":
        entries.sort(key=lambda entry: (-entry.score, entry.title.casefold()))
    elif sort_mode == "score_asc":
        entries.sort(key=lambda entry: (entry.score, entry.title.casefold()))
    elif sort_mode == "last_watched":
        entries.sort(
            key=lambda entry: (entry.last_watched > 0, entry.last_watched),
            reverse=True,
        )
    else:
        entries.sort(key=lambda entry: entry.title.casefold())
    return entries


# Display labels live in the GUI; MediaType values are storage keys.
VIEW_TITLES = {MediaType.IMAGE: "🖼️ Bilder", MediaType.VIDEO: "🎬 Videos"}


class MainWindow(QMainWindow):
    """Main window with sidebar, filter bar, card grid and batch actions."""

    GRID_SPACING = 12
    SCROLLBAR_RESERVE = 12

    def __init__(self, theme_manager: ThemeManager | None = None) -> None:
        """Initialize the database, view state and the full user interface."""
        super().__init__()
        self.setWindowTitle("MediaVault")
        self.resize(1180, 820)

        self.configs, _last = load_configs()
        self.config = next(
            (config for config in self.configs if config.db_path == _last),
            self.configs[0],
        )

        self.db = MediaDatabase(self.config.db_path)
        self.db.load()
        QTimer.singleShot(0, lambda: self._report_load_error(self.db))
        # Keyed by db_path, so switching back reuses the object a background
        # download is writing to instead of overwriting its entries.
        self._databases: dict[str, MediaDatabase] = {self.config.db_path: self.db}

        self.theme = theme_manager or ThemeManager()
        self.current_view: str = MediaType.IMAGE
        self.selected_entries: set[MediaItem] = set()
        self.recent_picks: list[MediaItem] = []
        self.thumbnail_cache: dict[str, QPixmap | None] = {}
        # Loads missing previews in the background so the grid stays usable.
        self._thumb_worker: Worker | None = None
        self.cards: list[MediaCard] = []
        self.current_cols = 1

        self._anchor_entry: MediaItem | None = None
        self._press_snapshot: set[MediaItem] = set()
        # Paths the last folder sync could not import; hidden from later syncs.
        self._sync_ignored: set[str] = set()
        # Last resolved media location, used to notice a plugged or pulled volume.
        self._location: LibraryRoot | None = None

        # The worker that fetches rule34 posts before the preview opens.
        self._rule34_fetch: Worker | None = None

        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(200)
        self._search_timer.timeout.connect(self.refresh_data)

        self._spinner_frame = 0
        self._spinner_timer = QTimer(self)
        self._spinner_timer.setInterval(90)
        self._spinner_timer.timeout.connect(self._spin)

        self._setup_ui()
        self._rubber = RubberBandSelector(
            self.scroll_area, lambda: self.cards, self._apply_selection
        )
        self._sync_theme_button()
        self._apply_config_ui()
        self.refresh_data()

        self._volume_timer = QTimer(self)
        self._volume_timer.setInterval(4000)
        self._volume_timer.timeout.connect(self._check_volumes)
        self._volume_timer.start()
        self._check_volumes()

    # --- UI construction ---
    def _setup_ui(self) -> None:
        """Build the sidebar, top bar, action bar and scrollable card grid."""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QHBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        sidebar = QWidget()
        sidebar.setObjectName("Sidebar")
        sidebar.setFixedWidth(250)
        side_layout = QVBoxLayout(sidebar)
        side_layout.setContentsMargins(16, 22, 16, 22)
        side_layout.setSpacing(6)

        lbl_title = QLabel("MediaVault")
        lbl_title.setObjectName("AppTitle")
        side_layout.addWidget(lbl_title)
        lbl_sub = QLabel("Deine Medienbibliothek")
        lbl_sub.setObjectName("AppSubtitle")
        side_layout.addWidget(lbl_sub)
        side_layout.addSpacing(12)

        side_layout.addWidget(self._create_section_label("ANSICHTEN"))
        self.btn_bilder = self._create_side_btn(
            "🖼️  Bilder", lambda: self.switch_view(MediaType.IMAGE), checkable=True
        )
        self.btn_videos = self._create_side_btn(
            "🎬  Videos", lambda: self.switch_view(MediaType.VIDEO), checkable=True
        )
        self.btn_bilder.setChecked(True)
        side_layout.addWidget(self.btn_bilder)
        side_layout.addWidget(self.btn_videos)

        side_layout.addWidget(self._create_section_label("SPEICHER"))
        self.btn_stick = self._create_side_btn(
            "🔌  Stick einrichten", self._open_stick
        )
        self.btn_stick.setToolTip(
            "Ordner auf einem USB-Stick als Mediathek einrichten oder zuweisen"
        )
        side_layout.addWidget(self.btn_stick)
        self.lbl_stick = QLabel("")
        self.lbl_stick.setObjectName("HintLabel")
        self.lbl_stick.setWordWrap(True)
        self.lbl_stick.setContentsMargins(4, 0, 0, 0)
        side_layout.addWidget(self.lbl_stick)

        self.lbl_analysis_section = self._create_section_label("KI-ANALYSE")
        side_layout.addWidget(self.lbl_analysis_section)
        self.btn_analysis = self._create_side_btn("📊  Analyse", self._open_analysis)
        side_layout.addWidget(self.btn_analysis)
        self.btn_sync_folder = self._create_side_btn(
            "🔄  Ordner synchronisieren", self._sync_folder
        )
        self.btn_sync_folder.setToolTip("Ordner jetzt nach neuen Bildern durchsuchen")
        side_layout.addWidget(self.btn_sync_folder)
        self.lbl_last_sync = QLabel("")
        self.lbl_last_sync.setObjectName("HintLabel")
        self.lbl_last_sync.setWordWrap(True)
        self.lbl_last_sync.setContentsMargins(4, 0, 0, 0)
        side_layout.addWidget(self.lbl_last_sync)

        side_layout.addWidget(self._create_section_label("ZUFALL (LOKAL)"))
        side_layout.addWidget(
            self._create_side_btn("🎲  Normal", lambda: self._do_random(False, False))
        )
        side_layout.addWidget(
            self._create_side_btn("⚖️  Smart", lambda: self._do_random(True, False))
        )

        side_layout.addWidget(self._create_section_label("ZUFALL (GLOBAL)"))
        side_layout.addWidget(
            self._create_side_btn("🌍  Alles", lambda: self._do_random(False, True))
        )
        side_layout.addWidget(
            self._create_side_btn(
                "⚖️🌍  Alles Smart", lambda: self._do_random(True, True)
            )
        )
        side_layout.addWidget(
            self._create_side_btn("📂  Aus Gruppen", self._open_group_random)
        )

        self.lbl_rule34_section = self._create_section_label("ONLINE")
        side_layout.addWidget(self.lbl_rule34_section)
        self.btn_rule34 = self._create_side_btn(
            "⬇️  rule34 Import", self._fetch_rule34
        )
        side_layout.addWidget(self.btn_rule34)
        self.btn_downloads = self._create_side_btn(
            "⬇️  Downloads", self._show_downloads, checkable=True
        )
        self.btn_downloads.setVisible(False)
        side_layout.addWidget(self.btn_downloads)

        side_layout.addStretch()

        side_layout.addWidget(
            self._create_side_btn("⚙️  Config wechseln", self._switch_config)
        )

        self.btn_theme = QPushButton()
        self.btn_theme.setProperty("nav", True)
        self.btn_theme.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_theme.clicked.connect(self._toggle_theme)
        side_layout.addWidget(self.btn_theme)

        btn_new = QPushButton("+  Neuer Eintrag")
        btn_new.setProperty("variant", "primary")
        btn_new.setFixedHeight(40)
        btn_new.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_new.clicked.connect(self._create_new)
        side_layout.addWidget(btn_new)

        main_layout.addWidget(sidebar)

        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(24, 20, 24, 20)
        content_layout.setSpacing(12)

        self.stick_banner = StickBanner()
        self.stick_banner.setup_requested.connect(self._open_stick)
        content_layout.addWidget(self.stick_banner)

        top_bar = QHBoxLayout()
        top_bar.setSpacing(10)
        self.lbl_view_title = QLabel("🖼️ Bilder")
        self.lbl_view_title.setObjectName("PageTitle")
        top_bar.addWidget(self.lbl_view_title)
        top_bar.addStretch()

        self.inp_search = QLineEdit()
        self.inp_search.setPlaceholderText("Titel, Beschreibung, Gruppe suchen…")
        self.inp_search.setClearButtonEnabled(True)
        self.inp_search.setFixedWidth(240)
        self.inp_search.textChanged.connect(self._schedule_search_refresh)
        self.inp_search.returnPressed.connect(self._flush_search)
        top_bar.addWidget(self.inp_search)

        self.lbl_group_filter = QLabel("Gruppe")
        self.lbl_group_filter.setObjectName("MutedLabel")
        top_bar.addWidget(self.lbl_group_filter)
        self.combo_group = QComboBox()
        self.combo_group.setMinimumWidth(140)
        self.combo_group.currentTextChanged.connect(self.refresh_data)
        top_bar.addWidget(self.combo_group)

        self.combo_sort = QComboBox()
        self.combo_sort.setMinimumWidth(160)
        for sort_key, sort_label in (
            ("title", "Titel A–Z"),
            ("score_desc", "Score ↓"),
            ("score_asc", "Score ↑"),
            ("last_watched", "Zuletzt gesehen"),
        ):
            self.combo_sort.addItem(sort_label, sort_key)
        self.combo_sort.currentIndexChanged.connect(self.refresh_data)
        top_bar.addWidget(self.combo_sort)

        content_layout.addLayout(top_bar)

        self.action_bar = QWidget()
        self.action_bar.setObjectName("ActionBar")
        ab_layout = QHBoxLayout(self.action_bar)
        ab_layout.setContentsMargins(12, 8, 12, 8)
        ab_layout.setSpacing(8)

        self.btn_sel_all = QPushButton("Alle")
        self.btn_sel_all.setProperty("variant", "ghost")
        self.btn_sel_all.clicked.connect(self._select_all)
        self.btn_sel_none = QPushButton("Keine")
        self.btn_sel_none.setProperty("variant", "ghost")
        self.btn_sel_none.clicked.connect(self._deselect_all)
        self.lbl_sel_count = QLabel("Keine Auswahl")
        self.lbl_sel_count.setObjectName("SelectionCount")
        self.lbl_hint = QLabel("Shift = Bereich · Ziehen = Rahmen")
        self.lbl_hint.setObjectName("HintLabel")
        self.lbl_hint.setToolTip(
            "Klick toggelt die Auswahl · Shift+Klick wählt einen Bereich · "
            "Ziehen markiert mehrere Kacheln"
        )
        self.lbl_hint.setSizePolicy(
            QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred
        )

        self.btn_batch_score = QPushButton("Score setzen")
        self.btn_batch_score.setProperty("variant", "secondary")
        self.btn_batch_score.clicked.connect(self._batch_score)
        self.btn_batch_group = QPushButton("Gruppe setzen")
        self.btn_batch_group.setProperty("variant", "secondary")
        self.btn_batch_group.clicked.connect(self._batch_group)
        self.btn_batch_del = QPushButton("Löschen")
        self.btn_batch_del.setProperty("variant", "danger")
        self.btn_batch_del.clicked.connect(self._batch_delete)

        ab_layout.addWidget(self.btn_sel_all)
        ab_layout.addWidget(self.btn_sel_none)
        ab_layout.addWidget(self.lbl_sel_count)
        ab_layout.addWidget(self.lbl_hint)
        ab_layout.addStretch()
        ab_layout.addWidget(self.btn_batch_score)
        ab_layout.addWidget(self.btn_batch_group)
        ab_layout.addWidget(self.btn_batch_del)
        content_layout.addWidget(self.action_bar)

        self.lbl_empty = QLabel("Keine Einträge gefunden.")
        self.lbl_empty.setObjectName("MutedLabel")
        self.lbl_empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_empty.hide()
        content_layout.addWidget(self.lbl_empty)

        self.lbl_loading = QLabel()
        self.lbl_loading.setObjectName("HintLabel")
        self.lbl_loading.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_loading.hide()
        content_layout.addWidget(self.lbl_loading)

        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setObjectName("CardScroll")
        self.grid_container = QWidget()
        self.grid_container.setObjectName("GridContainer")
        self.grid_layout = QGridLayout(self.grid_container)
        self.grid_layout.setContentsMargins(0, 0, 0, 0)
        self.grid_layout.setSpacing(self.GRID_SPACING)
        self.grid_layout.setAlignment(
            Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft
        )
        self.scroll_area.setWidget(self.grid_container)
        self.scroll_area.viewport().setObjectName("GridViewport")
        self.scroll_area.viewport().installEventFilter(self)

        self.downloads_page = DownloadsPage()
        self.downloads_page.job_finished.connect(self._on_download_finished)
        self.downloads_page.queue_changed.connect(self._sync_downloads_button)
        self.downloads_page.reveal_requested.connect(self._reveal_downloads)
        self.downloads_page.emptied.connect(self._leave_empty_downloads)

        self.pages = QStackedWidget()
        self.pages.addWidget(self.scroll_area)
        self.pages.addWidget(self.downloads_page)
        content_layout.addWidget(self.pages, 1)

        main_layout.addWidget(content, 1)

    def _create_section_label(self, text: str) -> QLabel:
        """Create a muted section label for the sidebar."""
        label = QLabel(text)
        label.setObjectName("SectionLabel")
        label.setContentsMargins(4, 10, 0, 2)
        return label

    def _create_side_btn(
        self, text: str, callback: Callable[[], None], checkable: bool = False
    ) -> QPushButton:
        """Create a left-aligned sidebar button wired to ``callback``."""
        btn = QPushButton(text)
        btn.setProperty("nav", True)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        if checkable:
            btn.setCheckable(True)
            btn.setAutoExclusive(True)
        btn.clicked.connect(callback)
        return btn

    # --- Data and view ---
    def switch_view(self, view: str) -> None:
        """Switch between the image and video views and reload the grid."""
        self.current_view = view
        self.btn_bilder.setChecked(view == MediaType.IMAGE)
        self.btn_videos.setChecked(view == MediaType.VIDEO)
        self.btn_downloads.setChecked(False)
        self.lbl_view_title.setText(VIEW_TITLES[view])
        self.pages.setCurrentWidget(self.scroll_area)
        self._set_library_controls_visible(True)
        self.action_bar.show()
        self._cancel_drag()
        self._apply_selection(set())
        self._anchor_entry = None
        self.refresh_data()

    def _show_downloads(self) -> None:
        """Show the background download queue without leaving the library."""
        self._cancel_drag()
        self._apply_selection(set())
        self.btn_downloads.setChecked(True)
        self.lbl_view_title.setText("⬇️ Downloads")
        self._set_library_controls_visible(False)
        self.action_bar.hide()
        self.lbl_empty.hide()
        self._set_loading(False)
        self.pages.setCurrentWidget(self.downloads_page)

    def _set_library_controls_visible(self, visible: bool) -> None:
        """Show or hide the filter widgets that only apply to the grid."""
        for widget in (
            self.inp_search,
            self.lbl_group_filter,
            self.combo_group,
            self.combo_sort,
        ):
            widget.setVisible(visible)

    def _apply_config_ui(self) -> None:
        """Show only the controls that fit the active config's mode."""
        ai = self.config.mode == MODE_AI
        self.btn_videos.setVisible(not ai)
        self.lbl_analysis_section.setVisible(ai)
        self.btn_analysis.setVisible(ai)
        show_sync = ai and bool(self.config.folder.strip())
        self.btn_sync_folder.setVisible(show_sync)
        self.lbl_last_sync.setVisible(show_sync)
        self._update_last_sync_label()
        self.lbl_rule34_section.setVisible(not ai)
        self.btn_rule34.setVisible(not ai)
        # Open on a view that actually has entries instead of an empty grid.
        has_images = bool(self.db.get_by_type(MediaType.IMAGE))
        has_videos = bool(self.db.get_by_type(MediaType.VIDEO))
        view = MediaType.VIDEO if has_videos and not has_images else MediaType.IMAGE
        self.current_view = view
        self.btn_bilder.setChecked(view == MediaType.IMAGE)
        self.btn_videos.setChecked(view == MediaType.VIDEO)
        self.btn_downloads.setChecked(False)
        self.pages.setCurrentWidget(self.scroll_area)
        self._set_library_controls_visible(True)
        self.action_bar.show()
        self.lbl_view_title.setText(VIEW_TITLES[view])
        self.inp_search.setPlaceholderText(
            "Titel, Beschreibung, Prompt suchen…"
            if ai
            else "Titel, Beschreibung, Gruppe suchen…"
        )
        self._check_volumes()

    @staticmethod
    def _entry_available(entry: MediaItem, root: str) -> bool:
        """Return True if an entry's file can be read right now."""
        path = entry.resolve(root)
        return bool(path) and os.path.isfile(path)

    def _library_ready(self) -> bool:
        """Return False and warn when the config's stick is not connected."""
        if self.config.volume_uuid and not locate(self.config).available:
            QMessageBox.warning(
                self,
                "Mediathek nicht verbunden",
                "Der Stick mit dieser Mediathek ist nicht verbunden.",
            )
            return False
        return True

    def _copy_into_library(self, path: str) -> str | None:
        """Copy one accepted file into the config folder; None on failure.

        Configs without a managed folder keep files where they are.
        """
        target = locate(self.config).folder
        if not target:
            return path
        known = {entry.content_hash for entry in self.db.entries if entry.content_hash}
        result = copy_into_folder([path], target, known)
        return result.copied[0] if result.copied else None

    def scan_folder(self) -> None:
        """Index the config folder into the DB, which acts as the reference cache.

        The DB keeps every reference, so random picking never touches the disk;
        only media paths and content hashes are written here.
        """
        location = locate(self.config)
        if not location.available or not os.path.isdir(location.folder):
            return
        ai = self.config.mode == MODE_AI
        known = [entry.file_path for entry in self.db.snapshot()]
        images, videos = find_new_media(
            location.folder,
            known,
            image_exts={".png"} if ai else IMAGE_EXTS,
            video_exts=set() if ai else VIDEO_EXTS,
            root=location.volume,
        )
        for paths, type_str in ((images, MediaType.IMAGE), (videos, MediaType.VIDEO)):
            if paths:
                import_paths(
                    self.db,
                    paths,
                    type_str=type_str,
                    group="",
                    mode=self.config.mode,
                    root=location.volume,
                )

    def auto_scan_folder(self) -> None:
        """Index the config folder on startup unless the config is in AI mode.

        AI mode extracts metadata from every file, so it only syncs when the
        user asks for it. An unplugged volume simply yields no new entries:
        the DB already holds the references from the first run.
        """
        if self.config.mode != MODE_AI:
            self.scan_folder()

    # --- Removable volumes ---
    def _open_stick(self) -> None:
        """Open the stick dialog and activate the config it produced."""
        self.db.save()
        dlg = StickDialog(self, self.configs, self.config)
        if dlg.exec() and dlg.target_db_path:
            if dlg.migrate_root:
                database = self._databases.get(dlg.target_db_path)
                if database is not None:
                    database.relativize(dlg.migrate_root)
            self._activate_config(dlg.target_db_path)

    def _report_load_error(self, database: MediaDatabase) -> None:
        """Tell the user once that a database could not be loaded."""
        if not database.load_error:
            return
        lines = [
            f"Die Mediathek „{database.filepath}“ konnte nicht geladen werden:",
            database.load_error,
        ]
        if database.backup_path:
            lines.append(f"Eine Sicherung liegt unter {database.backup_path}.")
        if database.read_only:
            lines.append(
                "Änderungen werden nicht gespeichert, bis die Datei lesbar ist."
            )
        QMessageBox.warning(self, "Mediathek nicht geladen", "\n\n".join(lines))
        database.load_error = ""

    def _activate_config(self, db_path: str) -> None:
        """Load a config by path, reuse its database and refresh the window."""
        self.configs, _last = load_configs()
        self.config = next(
            (config for config in self.configs if config.db_path == db_path),
            self.configs[0],
        )
        # Reuse the object a background download may still be writing to.
        self.db = self._databases.get(self.config.db_path)
        if self.db is None:
            self.db = MediaDatabase(self.config.db_path)
            self.db.load()
            self._databases[self.config.db_path] = self.db
            self._report_load_error(self.db)

        self.thumbnail_cache.clear()
        self.recent_picks = []
        self._sync_ignored.clear()
        self.inp_search.blockSignals(True)
        self.inp_search.clear()
        self.inp_search.blockSignals(False)
        self._apply_selection(set())
        self._anchor_entry = None
        self._location = locate(self.config)
        self._apply_config_ui()
        self.auto_scan_folder()
        self.refresh_data()

    def _check_volumes(self) -> None:
        """Keep location, window title, sidebar and stick banner in sync."""
        location = locate(self.config)
        previous = self._location
        changed = previous is not None and location.volume != previous.volume
        self._location = location
        self._sync_window_title(location)
        self.lbl_stick.setText(
            "Kein Stick zugeordnet"
            if not self.config.volume_uuid
            else f"🔌 {self.config.volume_label or 'Stick'} · "
            f"{'verbunden' if location.available else 'nicht verbunden'}"
        )
        used = {config.volume_uuid for config in self.configs if config.volume_uuid}
        self.stick_banner.offer(
            [(root, info) for root, info in volumes.vaults() if info.uuid not in used]
        )
        if changed:
            # Previews missed while unplugged must be retried, and files added
            # on another machine picked up.
            for key in [k for k, v in self.thumbnail_cache.items() if v is None]:
                del self.thumbnail_cache[key]
            if location.available:
                self.auto_scan_folder()
            self.refresh_data()

    def _sync_window_title(self, location: LibraryRoot) -> None:
        """Show config, mode and a missing volume in the window title."""
        suffix = " · KI" if self.config.mode == MODE_AI else ""
        if self.config.volume_uuid and not location.available:
            suffix += " · 🔌 Stick nicht verbunden"
        self.setWindowTitle(f"MediaVault – {self.config.name}{suffix}")

    def _update_last_sync_label(self) -> None:
        """Show when the config's folder was last synchronized."""
        stamp = self.config.folder_last_sync
        self.lbl_last_sync.setText(
            f"Zuletzt synchronisiert: {stamp}"
            if stamp
            else "Noch nicht synchronisiert"
        )

    def _sync_folder(self) -> None:
        """Scan the config folder in the background and preview new images."""
        folder = locate(self.config).folder
        if not folder:
            QMessageBox.information(
                self,
                "Ordner synchronisieren",
                "Für diese Config ist kein Ordner hinterlegt.",
            )
            return
        if not os.path.isdir(folder):
            QMessageBox.warning(
                self, "Ordner synchronisieren", "Der Ordner wurde nicht gefunden."
            )
            return
        known = [
            entry.image_path for entry in self.db.get_by_type(MediaType.IMAGE)
        ]
        known.extend(self._sync_ignored)
        self.btn_sync_folder.setEnabled(False)
        worker = Worker(
            self,
            partial(find_new_media, image_exts={".png"}, video_exts=()),
            folder=folder,
            known_paths=known,
        )
        progress = self._busy_progress("Durchsuche Ordner nach neuen Bildern …")
        worker.finished.connect(lambda: self._show_new_images(worker, progress))
        worker.start()
        progress.show()

    def _show_new_images(self, worker: Worker, progress: QProgressDialog) -> None:
        """Preview newly found images and import them after confirmation."""
        progress.close()
        progress.deleteLater()
        worker.deleteLater()
        self.btn_sync_folder.setEnabled(True)
        if worker.error is not None:
            QMessageBox.warning(self, "Ordner synchronisieren", str(worker.error))
            return
        paths = [path for path in worker.result[0] if os.path.isfile(path)]
        if not paths:
            self._mark_folder_synced()
            QMessageBox.information(
                self, "Ordner synchronisieren", "Keine neuen Bilder gefunden."
            )
            return
        if not FolderPreviewDialog(self, paths).exec():
            return
        importer = Worker(
            self,
            import_paths,
            db=self.db,
            paths=paths,
            type_str=MediaType.IMAGE,
            group="",
            mode=self.config.mode,
        )
        progress = self._busy_progress(f"Importiere {len(paths)} Bild(er) …")
        importer.finished.connect(
            lambda: self._apply_folder_sync(importer, progress, paths)
        )
        importer.start()
        progress.show()

    def _apply_folder_sync(
        self, worker: Worker, progress: QProgressDialog, paths: list[str]
    ) -> None:
        """Report the finished folder import and record the sync time."""
        progress.close()
        progress.deleteLater()
        worker.deleteLater()
        if worker.error is not None:
            QMessageBox.warning(self, "Ordner synchronisieren", str(worker.error))
            return
        result = worker.result
        if result is None:
            return
        stored = {
            norm_path(entry.image_path)
            for entry in self.db.get_by_type(MediaType.IMAGE)
        }
        self._sync_ignored.update(
            path for path in paths if norm_path(path) not in stored
        )
        self._mark_folder_synced()
        if result.added:
            self.refresh_data()
        summary = f"{result.added} importiert, {result.duplicates} Duplikate"
        if result.skipped_no_ai:
            summary += f", {result.skipped_no_ai} ohne KI-Metadaten übersprungen"
        QMessageBox.information(self, "Ordner synchronisieren", summary)

    def _mark_folder_synced(self) -> None:
        """Store and display the time of the last completed folder sync."""
        self.config.folder_last_sync = datetime.now().astimezone().strftime("%d.%m.%Y %H:%M")
        save_configs(self.configs, self.config.db_path)
        self._update_last_sync_label()

    def _fetch_rule34(self) -> None:
        """Fetch new rule34 posts in the background and show them for selection."""
        if self.config.mode == MODE_AI or self._rule34_fetch is not None:
            return
        dlg = Rule34Dialog(self, self.config, self.configs)
        if not dlg.exec():
            return
        for key, value in dlg.settings().items():
            setattr(self.config.rule34, key, value)
        save_configs(self.configs, self.config.db_path)

        # The reset option ignores the stored IDs; the import still skips
        # files that are already stored locally.
        last_ids: dict[str, int] = (
            {} if dlg.chk_reset.isChecked() else self.config.rule34.last_ids
        )
        db = self.db
        worker = Worker(
            self,
            self._load_rule34_preview,
            api_key=self.config.rule34.api_key,
            user_id=self.config.rule34.user_id,
            tags=self.config.rule34.tags,
            webm=self.config.rule34.webm,
            limit=self.config.rule34.count,
            last_ids=last_ids,
        )
        self._rule34_fetch = worker
        self._set_rule34_loading(True)
        worker.finished.connect(lambda: self._show_rule34_preview(worker, db))
        worker.start()

    def _set_rule34_loading(self, loading: bool) -> None:
        """Show the post-fetch state on the sidebar button and downloads page."""
        self.btn_rule34.setEnabled(not loading)
        self.btn_rule34.setText(
            "⬇️  Lade Posts …" if loading else "⬇️  rule34 Import"
        )
        self.downloads_page.set_activity(
            "🔎  Lade Posts von rule34 …" if loading else ""
        )

    def _load_rule34_preview(
        self,
        *,
        api_key: str,
        user_id: str,
        tags: str,
        webm: bool,
        limit: int,
        last_ids: dict[str, int],
    ) -> tuple[list[Post], dict[int, bytes], dict[str, int]]:
        """Fetch new posts and their thumbnails for the selection dialog."""
        posts, newest_ids = collect_new_posts_multi(
            api_key, user_id, tags, webm, limit, last_ids
        )
        previews: dict[int, bytes] = {}
        for post in posts:
            data = fetch_preview(post.preview_url)
            if data:
                previews[post.id] = data
        return posts, previews, newest_ids

    def _busy_progress(self, text: str) -> QProgressDialog:
        """Create a modal busy dialog for one background step."""
        progress = QProgressDialog(text, "", 0, 0, self)
        progress.setCancelButton(None)
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.setMinimumDuration(0)
        return progress

    def _show_rule34_preview(self, worker: Worker, db: MediaDatabase) -> None:
        """Open the selection dialog for the fetched posts."""
        self._rule34_fetch = None
        self._set_rule34_loading(False)
        error = worker.error
        result = worker.result
        worker.deleteLater()
        if db is not self.db:
            # The vault changed while the posts were loading; drop the result.
            return
        if error is not None:
            QMessageBox.warning(self, "rule34 Import", str(error))
            return
        posts, previews, newest_ids = result
        if not posts:
            QMessageBox.information(self, "rule34 Import", "Keine neuen Posts.")
            return
        dlg = Rule34PreviewDialog(self, posts, previews)
        if not dlg.exec():
            return
        selected = dlg.selected_ids()
        if not selected:
            QMessageBox.information(self, "rule34 Import", "Keine Posts ausgewählt.")
            return
        self._queue_rule34_download(db, posts, newest_ids, selected)

    # --- Download queue ---
    def _queue_rule34_download(
        self,
        db: MediaDatabase,
        posts: list[Post],
        newest_ids: dict[str, int],
        selected_ids: set[int],
    ) -> None:
        """Add a rule34 import to the background queue."""
        self.downloads_page.enqueue(
            label=(
                f"{self.config.rule34.tags or 'ohne Tags'} · "
                f"{len(selected_ids)} Posts"
            ),
            db=db,
            folder=self.config.folder,
            tags=self.config.rule34.tags,
            posts=posts,
            selected_ids=selected_ids,
            newest_ids=newest_ids,
        )

    def _on_download_finished(self, job: DownloadJob) -> None:
        """Store post IDs after a clean run and refresh the visible grid."""
        if job.state is JobState.DONE and not job.failed:
            # Keep the IDs only when every selected post reached the disk.
            config = next(
                (
                    config
                    for config in self.configs
                    if config.db_path == job.db.filepath
                ),
                None,
            )
            if config is not None and job.newest_ids:
                config.rule34.last_ids.update(job.newest_ids)
                save_configs(self.configs, self.config.db_path)
        if job.imported and job.db is self.db:
            self.refresh_data()

    def _sync_downloads_button(self) -> None:
        """Mirror the queue size on the sidebar button."""
        open_jobs = self.downloads_page.open_count
        self.btn_downloads.setText(
            f"⬇️  Downloads ({open_jobs})" if open_jobs else "⬇️  Downloads"
        )
        self.btn_downloads.setVisible(self.downloads_page.has_jobs)

    def _reveal_downloads(self) -> None:
        """Switch to the queue page when a download still runs after a while."""
        if self.pages.currentWidget() is self.scroll_area:
            self._show_downloads()

    def _leave_empty_downloads(self) -> None:
        """Leave the download page once the last job is cleared."""
        if self.pages.currentWidget() is self.downloads_page:
            self.switch_view(MediaType.IMAGE)

    def _get_pixmap(self, entry: MediaItem) -> QPixmap | None:
        """Return an entry's preview pixmap, cached by its media path.

        Synchronous variant for the detail dialog; the grid loads previews in
        the background through ``_start_thumbnail_load``.
        """
        key = entry.media_path
        if key not in self.thumbnail_cache:
            image = load_thumbnail(
                entry, locate(self.config).volume, self.config.volume_uuid
            )
            self.thumbnail_cache[key] = QPixmap.fromImage(image) if image else None
        return self.thumbnail_cache[key]

    def _start_thumbnail_load(self) -> None:
        """Load missing previews in the background and show the spinner."""
        if self._thumb_worker is not None:
            return
        missing = [
            entry
            for entry in self._visible_entries()
            if entry.media_path not in self.thumbnail_cache
        ]
        if not missing:
            return
        worker = Worker(
            self,
            load_thumbnails,
            entries=missing,
            root=locate(self.config).volume,
            scope=self.config.volume_uuid,
        )
        worker.finished.connect(self._finish_thumbnail_load)
        self._thumb_worker = worker
        self._set_loading(True)
        worker.start()

    def _finish_thumbnail_load(self) -> None:
        """Publish the loaded previews to the cards and update the spinner."""
        worker = self._thumb_worker
        self._thumb_worker = None
        self._set_loading(False)
        if worker is None:
            return
        worker.deleteLater()
        if worker.error is not None:
            logger.debug(
                "Vorschaubilder konnten nicht geladen werden", exc_info=worker.error
            )
            return
        if not isinstance(worker.result, dict):
            return
        for path, image in worker.result.items():
            self.thumbnail_cache[path] = (
                QPixmap.fromImage(image) if image is not None else None
            )
        for card in self.cards:
            pixmap = self.thumbnail_cache.get(card.entry.media_path)
            if pixmap is not None:
                card.set_pixmap(pixmap)
        # A refresh during loading may have added entries the worker missed.
        self._start_thumbnail_load()

    def _set_loading(self, loading: bool) -> None:
        """Show the spinner while previews are loading in the grid view."""
        visible = loading and self.pages.currentWidget() is self.scroll_area
        self.lbl_loading.setVisible(visible)
        if visible:
            self._spin()
            self._spinner_timer.start()
        else:
            self._spinner_timer.stop()

    def _spin(self) -> None:
        """Advance the loading spinner by one frame."""
        self._spinner_frame = (self._spinner_frame + 1) % len(_SPINNER_FRAMES)
        self.lbl_loading.setText(
            f"{_SPINNER_FRAMES[self._spinner_frame]}  Lade Vorschauen …"
        )

    def _visible_entries(self) -> list[MediaItem]:
        """Return the entries currently visible after filtering and sorting."""
        return visible_entries(
            self.db.get_by_type(self.current_view),
            self.combo_group.currentText(),
            self.inp_search.text(),
            self.combo_sort.currentData(),
        )

    def refresh_data(self, *_args: object) -> None:
        """Refresh the group filter, cards and grid for the current view."""
        self._cancel_drag()

        current_filter = self.combo_group.currentText()
        groups = self.db.get_all_groups()
        self.combo_group.blockSignals(True)
        self.combo_group.clear()
        self.combo_group.addItems([ALL_GROUPS] + groups)
        if current_filter in [ALL_GROUPS] + groups:
            self.combo_group.setCurrentText(current_filter)
        self.combo_group.blockSignals(False)

        while self.grid_layout.count():
            item = self.grid_layout.takeAt(0)
            widget = item.widget() if item else None
            if widget is not None:
                widget.hide()
                widget.setParent(None)
                widget.deleteLater()
        self.cards.clear()

        for entry in self._visible_entries():
            card = MediaCard(entry, self.thumbnail_cache.get(entry.media_path))
            card.clicked.connect(self._on_card_clicked)
            card.double_clicked.connect(self._on_card_double_clicked)
            card.drag_pressed.connect(self._on_drag_pressed)
            card.drag_moved.connect(self._on_drag_moved)
            card.drag_finished.connect(self._on_drag_finished)
            self.cards.append(card)

        visible = {card.entry for card in self.cards}
        self.selected_entries.intersection_update(visible)
        if self._anchor_entry not in visible:
            self._anchor_entry = None

        for card in self.cards:
            card.set_selected(card.entry in self.selected_entries)

        self.lbl_empty.setVisible(
            not self.cards and self.pages.currentWidget() is self.scroll_area
        )
        self._update_columns()
        self._reflow_grid()
        self._update_action_bar()
        self._start_thumbnail_load()
        self._set_loading(self._thumb_worker is not None)

    # --- Grid ---
    def closeEvent(self, event: QCloseEvent) -> None:
        """Keep the window open while a background download still runs."""
        if self.downloads_page.is_busy or self._rule34_fetch is not None:
            QMessageBox.information(
                self,
                "Download läuft",
                "Ein Download oder das Laden von Posts läuft noch. Bitte warte, "
                "bis er fertig ist, damit keine Datei halb geschrieben wird.",
            )
            event.ignore()
            return
        # A broken video can block OpenCV, so never wait for previews forever.
        if self._thumb_worker is not None and not self._thumb_worker.wait(3000):
            QMessageBox.information(
                self,
                "Vorschauen werden geladen",
                "Die Vorschaubilder werden noch geladen. Bitte schließe das "
                "Fenster gleich noch einmal.",
            )
            event.ignore()
            return
        self._thumb_worker = None
        super().closeEvent(event)

    def resizeEvent(self, event: QResizeEvent) -> None:
        """Recalculate the grid's column count when the window is resized."""
        super().resizeEvent(event)
        self._update_columns()

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:
        """React to width changes of the scroll viewport."""
        if (
            hasattr(self, "scroll_area")
            and obj is self.scroll_area.viewport()
            and event.type() == QEvent.Type.Resize
        ):
            self._update_columns()
        return super().eventFilter(obj, event)

    def changeEvent(self, event: QEvent) -> None:
        """Cancel an active rubber-band selection when the window deactivates."""
        if event.type() == QEvent.Type.WindowDeactivate:
            self._cancel_drag()
        super().changeEvent(event)

    def _update_columns(self) -> None:
        """Compute the number of columns from the viewport width."""
        if not hasattr(self, "scroll_area"):
            return
        available = self.scroll_area.viewport().width() - self.SCROLLBAR_RESERVE
        cols = max(
            1,
            (available + self.GRID_SPACING) // (CARD_WIDTH + self.GRID_SPACING),
        )
        if cols != self.current_cols:
            self.current_cols = cols
            self._reflow_grid()

    def _reflow_grid(self) -> None:
        """Reorder existing cards in the grid without recreating them."""
        while self.grid_layout.count():
            self.grid_layout.takeAt(0)

        for index, card in enumerate(self.cards):
            row, col = divmod(index, self.current_cols)
            self.grid_layout.addWidget(card, row, col)

    # --- Selection ---
    def _apply_selection(self, entries: Iterable[MediaItem]) -> None:
        """Synchronize the selection set and card appearance in one place."""
        self.selected_entries = set(entries)
        for card in self.cards:
            card.set_selected(card.entry in self.selected_entries)
        self._update_action_bar()

    def _on_card_clicked(
        self, entry: MediaItem, modifiers: Qt.KeyboardModifier
    ) -> None:
        """Toggle a card, or select a range when Shift is held."""
        # Snapshot before changing anything: a following double click can then
        # fully undo the toggle caused by the first click.
        self._press_snapshot = set(self.selected_entries)
        if (
            modifiers & Qt.KeyboardModifier.ShiftModifier
            and self._anchor_entry is not None
        ):
            entries = [card.entry for card in self.cards]
            if entry in entries and self._anchor_entry in entries:
                start = entries.index(self._anchor_entry)
                end = entries.index(entry)
                lo, hi = sorted((start, end))
                self._apply_selection(self.selected_entries | set(entries[lo : hi + 1]))
                return

        new_selection = set(self.selected_entries)
        if entry in new_selection:
            new_selection.discard(entry)
        else:
            new_selection.add(entry)
        self._apply_selection(new_selection)
        self._anchor_entry = entry

    def _on_card_double_clicked(self, entry: MediaItem) -> None:
        """Open details and undo the toggle performed by the first click."""
        self._cancel_drag()
        self._apply_selection(self._press_snapshot)
        self._open_detail(entry)

    def _select_all(self) -> None:
        """Mark all visible cards as selected."""
        self._apply_selection({card.entry for card in self.cards})

    def _deselect_all(self) -> None:
        """Clear the selection of all visible cards."""
        self._cancel_drag()
        self._apply_selection(set())

    def _update_action_bar(self) -> None:
        """Update the selection counter and batch button states."""
        count = len(self.selected_entries)
        self.lbl_sel_count.setText(f"{count} ausgewählt" if count else "Keine Auswahl")
        enabled = count > 0
        self.btn_batch_score.setEnabled(enabled)
        self.btn_batch_group.setEnabled(enabled)
        self.btn_batch_del.setEnabled(enabled)
        self.btn_sel_none.setEnabled(count > 0)
        self.btn_sel_all.setEnabled(bool(self.cards))
        self.lbl_hint.setVisible(count == 0)

    # --- Rubber-band selection ---
    def _on_drag_pressed(self, entry: MediaItem, global_pos: QPoint) -> None:
        """Capture the starting selection before the first click."""
        self._press_snapshot = set(self.selected_entries)
        self._rubber.press(global_pos, self.selected_entries)

    def _on_drag_moved(self, global_pos: QPoint) -> None:
        """Forward pointer movement to the rubber-band selector."""
        self._rubber.move(global_pos)

    def _on_drag_finished(self) -> None:
        """Finish the rubber-band selection."""
        self._cancel_drag()

    def _cancel_drag(self) -> None:
        """Hide the selection rectangle and stop auto-scrolling."""
        self._rubber.cancel()

    # --- Keyboard and search ---
    def keyPressEvent(self, event: QKeyEvent) -> None:
        """Handle keyboard shortcuts for selection, deletion and search."""
        if event.matches(QKeySequence.StandardKey.SelectAll):
            self._select_all()
            event.accept()
            return
        if event.matches(QKeySequence.StandardKey.Find):
            self.inp_search.setFocus()
            self.inp_search.selectAll()
            event.accept()
            return
        if event.key() == Qt.Key.Key_Escape:
            if self._rubber.active:
                self._cancel_drag()
                self._apply_selection(self._press_snapshot)
            else:
                self._deselect_all()
            event.accept()
            return
        if event.key() == Qt.Key.Key_Delete and self.selected_entries:
            self._batch_delete()
            event.accept()
            return
        super().keyPressEvent(event)

    def _schedule_search_refresh(self, _text: str | None = None) -> None:
        """Debounce the grid rebuild while the user is typing."""
        if not self.inp_search.text():
            self._search_timer.stop()
            self.refresh_data()
        else:
            self._search_timer.start()

    def _flush_search(self) -> None:
        """Refresh the search immediately (Enter)."""
        self._search_timer.stop()
        self.refresh_data()

    # --- Theme ---
    def _sync_theme_button(self) -> None:
        """Update the theme toggle's label and tooltip."""
        dark = self.theme.name == "dark"
        self.btn_theme.setText("☀️  Helles Theme" if dark else "🌙  Dunkles Theme")
        self.btn_theme.setToolTip(
            "Zu hellem Theme wechseln" if dark else "Zu dunklem Theme wechseln"
        )

    def _toggle_theme(self) -> None:
        """Switch between dark and light theme at runtime."""
        self.theme.toggle(QApplication.instance())
        self._sync_theme_button()

    def _switch_config(self) -> None:
        """Save the current database and open another vault config."""
        self.db.save()
        dlg = ConfigDialog(self, self.configs, self.config.db_path)
        if not dlg.exec():
            return
        if dlg.wants_stick_setup:
            self._open_stick()
            return
        if dlg.selected_config is not None:
            self._activate_config(dlg.selected_config.db_path)

    def _open_analysis(self) -> None:
        """Open the local prompt statistics for the current config."""
        AnalysisDialog(self, self.db).exec()

    # --- Actions ---
    def _open_detail(self, entry: MediaItem) -> None:
        """Open the detail dialog and remember the entry as a recent pick."""
        if entry in self.recent_picks:
            self.recent_picks.remove(entry)
        self.recent_picks.append(entry)
        if len(self.recent_picks) > 2:
            self.recent_picks.pop(0)

        dlg = DetailDialog(
            self, entry, self.db, self._get_pixmap, root=locate(self.config).volume
        )
        dlg.exec()
        if dlg.edit_requested:
            self._open_edit(entry)
        else:
            self.refresh_data()

    def _open_edit(self, entry: MediaItem) -> None:
        """Open the edit dialog and reload the view after saving."""
        dlg = EditDialog(
            self,
            self.db,
            entry.entry_type,
            entry,
            root=locate(self.config).volume,
        )
        if dlg.exec():
            self.db.save()
            self.thumbnail_cache.pop(entry.media_path, None)
            self.refresh_data()

    def _create_new(self) -> None:
        """Show a menu to choose between single and batch creation."""
        options: list[tuple[str, Callable[[], None]]] = [
            ("Bild einzeln", lambda: self._create_single(MediaType.IMAGE)),
            ("Video einzeln", lambda: self._create_single(MediaType.VIDEO)),
            ("Bilder Massenimport", lambda: self._batch_import(MediaType.IMAGE)),
            ("Videos Massenimport", lambda: self._batch_import(MediaType.VIDEO)),
        ]
        if self.config.mode == MODE_AI:
            options = [option for option in options if option[0].startswith("Bild")]
        labels = [label for label, _action in options]
        choice, ok = QInputDialog.getItem(
            self, "Neu", "Aktion wählen:", labels, 0, False
        )
        if not ok:
            return
        options[labels.index(choice)][1]()

    def _create_single(self, type_str: str) -> None:
        """Open the native file picker and then create a single entry."""
        if type_str == MediaType.IMAGE:
            file_filter = "Bilder (*.png *.jpg *.jpeg *.bmp *.webp);;Alle Dateien (*.*)"
        else:
            file_filter = "Videos (*.mp4 *.mkv *.avi *.mov *.webm);;Alle Dateien (*.*)"

        path, _ = file_dialogs.pick_file(self, "Datei auswählen", file_filter)
        if not path:
            return
        if not self._library_ready():
            return

        meta: dict[str, Any] = {}
        if self.config.mode == MODE_AI:
            meta = extract_ai_metadata(path) or {}
            if not meta:
                QMessageBox.warning(
                    self,
                    "Kein KI-Bild",
                    "In dieser Datei wurden keine KI-Metadaten gefunden.",
                )
                return

        root = locate(self.config).volume
        if find_duplicate(self.db, path, type_str, meta, root=root):
            QMessageBox.information(
                self,
                "Bereits vorhanden",
                "Dieses Medium ist bereits in der Sammlung.",
            )
            return

        # Only copy once every check passed; undo the copy if the user backs out.
        stored = self._copy_into_library(path)
        if stored is None:
            QMessageBox.warning(
                self,
                "Kopieren fehlgeschlagen",
                "Die Datei konnte nicht in den Ordner der Mediathek kopiert werden.",
            )
            return
        created = stored != path and not transfer.is_inside(path, locate(self.config).folder)
        path = stored

        dlg = EditDialog(
            self,
            self.db,
            type_str,
            ai_meta=meta,
            root=locate(self.config).volume,
        )
        if type_str == MediaType.IMAGE:
            dlg.inp_img.setText(path)
        else:
            dlg.inp_video.setText(path)

        if dlg.exec():
            self.refresh_data()
        elif created:
            try:
                os.remove(path)
            except OSError:
                logger.warning("Kopie nicht entfernbar: %s", path, exc_info=True)

    def _batch_import(self, type_str: str) -> None:
        """Import several files as entries, skipping duplicates."""
        exts = (
            "*.png *.jpg *.jpeg *.bmp *.webp"
            if type_str == MediaType.IMAGE
            else "*.mp4 *.mkv *.avi *.mov *.webm"
        )
        paths, _ = file_dialogs.pick_files(
            self, "Importieren", f"Media ({exts});;Alle (*.*)"
        )
        if not paths:
            return

        group = (
            self.combo_group.currentText()
            if self.combo_group.currentText() != ALL_GROUPS
            else ""
        )
        if not self._library_ready():
            return
        result = import_paths(
            self.db,
            paths,
            type_str=type_str,
            group=group,
            mode=self.config.mode,
            root=locate(self.config).volume,
            transfer=self._copy_into_library,
        )
        if result.added:
            self.refresh_data()
        if result.duplicates or result.skipped_no_ai or result.failed:
            summary = [f"{result.added} importiert", f"{result.duplicates} Duplikate"]
            if result.failed:
                summary.append(f"{result.failed} nicht kopierbar")
            if result.skipped_no_ai:
                summary.append(f"{result.skipped_no_ai} ohne KI-Metadaten")
            QMessageBox.information(
                self, "Import", ", ".join(summary) + " übersprungen."
            )

    def _batch_delete(self) -> None:
        """Delete all selected entries after confirmation."""
        if (
            QMessageBox.question(
                self, "Löschen", f"{len(self.selected_entries)} löschen?"
            )
            == QMessageBox.StandardButton.Yes
        ):
            for entry in self.selected_entries:
                self.thumbnail_cache.pop(entry.media_path, None)
            self.db.delete_multiple(self.selected_entries)
            self.recent_picks = [
                entry
                for entry in self.recent_picks
                if entry not in self.selected_entries
            ]
            self._deselect_all()
            self.refresh_data()

    def _batch_score(self) -> None:
        """Set the score of all selected entries to a new value."""
        score, ok = QInputDialog.getInt(
            self, "Score", "Neuer Score (1-100):", 50, 1, 100
        )
        if ok:
            for entry in self.selected_entries:
                entry.score = score
            self.db.save()
            self._deselect_all()
            self.refresh_data()

    def _batch_group(self) -> None:
        """Assign a new group to all selected entries."""
        grp, ok = QInputDialog.getItem(
            self,
            "Gruppe",
            "Neue Gruppe (oder neuen Namen tippen):",
            [""] + self.db.get_all_groups(),
            0,
            True,
        )
        if ok:
            for entry in self.selected_entries:
                entry.group = grp.strip()
            self.db.save()
            self._deselect_all()
            self.refresh_data()

    def _pick_available(
        self, pool: list[MediaItem], smart: bool, root: str
    ) -> MediaItem | None:
        """Pick a random entry, retrying while its file is unavailable."""
        for _attempt in range(5):
            chosen = self.db.get_random(pool, smart, self.recent_picks)
            if chosen is None:
                return None
            if self._entry_available(chosen, root):
                return chosen
        return None

    def _do_random(self, smart: bool, global_pool: bool) -> None:
        """Pick a random entry (local or global) and open it."""
        if not self._library_ready():
            return
        location = locate(self.config)
        pool = (
            self.db.entries if global_pool else self.db.get_by_type(self.current_view)
        )
        chosen = self._pick_available(pool, smart, location.volume)
        if chosen:
            self._open_detail(chosen)

    def _open_group_random(self) -> None:
        """Open the group random dialog and show the chosen entry."""
        dlg = GroupRandomDialog(self, self.db)
        if dlg.exec() and dlg.result_pool:
            chosen = self._pick_available(
                dlg.result_pool, dlg.smart, locate(self.config).volume
            )
            if chosen:
                self._open_detail(chosen)
