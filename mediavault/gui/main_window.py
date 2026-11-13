"""Main window of MediaVault: wires sidebar, filter bar, grid, pages and dialogs.

:class:`MainWindow` owns the application state at runtime:

- the active config and its open :class:`MediaDatabase` (databases stay
  open per config, so a background download keeps writing to the same
  object after a config switch),
- the page stack: card grid (images/videos), downloads and wheel,
- helpers for the folder sync (:class:`FolderSync`) and the plugin imports
  (:class:`PluginImport`),
- a 4 s timer that notices when the config's stick is plugged in or pulled
  and refreshes the view.

User actions from the sidebar, the top bar, the action bar and keyboard
shortcuts end up in the methods below; they delegate the actual work to the
Qt-free core modules and the dialogs.
"""

import logging
import os
from collections.abc import Callable
from datetime import datetime
from functools import partial
from typing import Any

from PyQt6.QtCore import QEvent, Qt, QTimer
from PyQt6.QtGui import QCloseEvent, QKeyEvent, QKeySequence
from PyQt6.QtWidgets import (
    QApplication,
    QComboBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from mediavault import library, volumes
from mediavault.ai_meta import extract_ai_metadata
from mediavault.config import load_configs, locate, save_configs
from mediavault.database import MediaDatabase
from mediavault.extras.wheel import WheelPage
from mediavault.gui import file_dialogs
from mediavault.gui.card_grid import CardGrid, LoadingLabel
from mediavault.gui.dialogs import (
    AnalysisDialog,
    ConfigDialog,
    DetailDialog,
    EditDialog,
    GroupRandomDialog,
)
from mediavault.gui.downloads import DownloadJob, DownloadsPage
from mediavault.gui.folder_sync import FolderSync
from mediavault.gui.plugin_import import PluginImport, apply_imported
from mediavault.gui.sidebar import DOWNLOADS, WHEEL, Sidebar
from mediavault.gui.stick_banner import StickBanner
from mediavault.gui.stick_dialog import StickDialog
from mediavault.gui.theme import ThemeManager
from mediavault.gui.widgets import button
from mediavault.importer import find_duplicate, import_paths
from mediavault.library import ALL_GROUPS, SORT_MODES
from mediavault.models import LibraryRoot, MediaItem, MediaType
from mediavault.plugins import discover_plugins, migrate_settings
from mediavault.transfer import copy_into_folder

logger = logging.getLogger(__name__)

# Display labels live in the GUI; MediaType values are storage keys.
PAGE_TITLES = {
    MediaType.IMAGE: "🖼️ Bilder",
    MediaType.VIDEO: "🎬 Videos",
    DOWNLOADS: "⬇️ Downloads",
    WHEEL: "🎡 Glücksrad",
}
# Singular and plural for the "new entry" menu.
TYPE_NAMES = {MediaType.IMAGE: ("Bild", "Bilder"), MediaType.VIDEO: ("Video", "Videos")}
RECENT_PICKS = 2


class MainWindow(QMainWindow):
    """Main window with sidebar, filter bar, card grid and batch actions.

    Attributes:
        config: Active :class:`VaultConfig`.
        configs: All configs, reloaded from disk on every config switch.
        db: Database of the active config.
        current_view: Media type shown by the grid.
        recent_picks: Last random picks, excluded from the next pick so the
            same entries do not come up again and again.
    """

    def __init__(self, theme_manager: ThemeManager | None = None) -> None:
        """Load the last used config and build the user interface.

        Args:
            theme_manager: Shared theme manager; a new one when omitted (tests).
        """
        super().__init__()
        self.resize(1180, 820)
        self.theme = theme_manager or ThemeManager()
        self.current_view = MediaType.IMAGE
        self.recent_picks: list[MediaItem] = []
        # Keyed by db_path, so switching back reuses the object a background
        # download is writing to instead of overwriting its entries.
        self._databases: dict[str, MediaDatabase] = {}
        # Last resolved media location, used to notice a plugged or pulled volume.
        self._location = LibraryRoot()

        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(200)
        self._search_timer.timeout.connect(self.refresh_data)

        self._setup_ui()
        self.folder_sync = FolderSync(self)
        self.folder_sync.running_changed.connect(self.sidebar.set_sync_running)
        self.folder_sync.synced.connect(self._on_folder_synced)
        self.plugin_import = PluginImport(self, self.downloads_page)
        self.plugin_import.loading_changed.connect(self.sidebar.set_plugin_loading)
        self.plugins = discover_plugins()
        self.sidebar.set_plugins(
            [(key, plugin.name) for key, plugin in self.plugins.items()]
        )
        self.sidebar.set_theme(self.theme.name == "dark")

        self._load_config(load_configs()[1])
        self._apply_config_ui()
        self.refresh_data()

        self._volume_timer = QTimer(self)
        self._volume_timer.setInterval(4000)
        self._volume_timer.timeout.connect(self._check_volumes)
        self._volume_timer.start()

    # --- UI construction ---
    def _setup_ui(self) -> None:
        """Build the window layout and wire the signals of all child widgets.

        Sidebar on the left; stick banner, top bar, action bar and the page stack
        (grid, downloads, wheel) on the right.
        """
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QHBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        self.sidebar = Sidebar()
        self.sidebar.view_requested.connect(self._show_page)
        self.sidebar.downloads_requested.connect(lambda: self._show_page(DOWNLOADS))
        self.sidebar.random_requested.connect(self._do_random)
        self.sidebar.group_random_requested.connect(self._open_group_random)
        self.sidebar.stick_requested.connect(self._open_stick)
        self.sidebar.analysis_requested.connect(
            lambda: AnalysisDialog(self, self.db).exec()
        )
        self.sidebar.sync_requested.connect(
            lambda: self.folder_sync.start(self.db, self.config.mode, self._locate())
        )
        self.sidebar.plugin_requested.connect(self._start_plugin_import)
        self.sidebar.wheel_requested.connect(self._show_wheel)
        self.sidebar.config_requested.connect(self._switch_config)
        self.sidebar.theme_requested.connect(self._toggle_theme)
        self.sidebar.new_requested.connect(self._create_new)
        main_layout.addWidget(self.sidebar)

        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(24, 20, 24, 20)
        content_layout.setSpacing(12)

        self.stick_banner = StickBanner()
        self.stick_banner.setup_requested.connect(self._open_stick)
        content_layout.addWidget(self.stick_banner)
        content_layout.addLayout(self._build_top_bar())
        self.action_bar = self._build_action_bar()
        content_layout.addWidget(self.action_bar)

        self.lbl_empty = QLabel("Keine Einträge gefunden.")
        self.lbl_empty.setObjectName("MutedLabel")
        self.lbl_empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_empty.hide()
        content_layout.addWidget(self.lbl_empty)
        self.lbl_loading = LoadingLabel()
        content_layout.addWidget(self.lbl_loading)

        self.grid = CardGrid()
        self.grid.selection_changed.connect(self._update_action_bar)
        self.grid.open_requested.connect(self._open_detail)
        self.grid.loading_changed.connect(self._sync_loading)

        self.downloads_page = DownloadsPage()
        self.downloads_page.job_finished.connect(self._on_download_finished)
        self.downloads_page.queue_changed.connect(
            lambda: self.sidebar.set_downloads(
                self.downloads_page.open_count, self.downloads_page.has_jobs
            )
        )
        self.downloads_page.reveal_requested.connect(self._reveal_downloads)
        self.downloads_page.emptied.connect(self._leave_empty_downloads)

        self.wheel_page = WheelPage(
            self.theme.palette(), lambda: self.db.get_all_groups()
        )
        self.theme.theme_changed.connect(
            lambda _name: self.wheel_page.apply_theme(self.theme.palette())
        )

        self._side_pages = {DOWNLOADS: self.downloads_page, WHEEL: self.wheel_page}
        self.pages = QStackedWidget()
        self.pages.addWidget(self.grid)
        for page in self._side_pages.values():
            self.pages.addWidget(page)
        content_layout.addWidget(self.pages, 1)
        main_layout.addWidget(content, 1)

    def _build_top_bar(self) -> QHBoxLayout:
        """Build the page title, search field, group filter and sort order."""
        top_bar = QHBoxLayout()
        top_bar.setSpacing(10)
        self.lbl_view_title = QLabel(PAGE_TITLES[MediaType.IMAGE])
        self.lbl_view_title.setObjectName("PageTitle")
        top_bar.addWidget(self.lbl_view_title)
        top_bar.addStretch()

        self.inp_search = QLineEdit()
        self.inp_search.setClearButtonEnabled(True)
        self.inp_search.setFixedWidth(240)
        self.inp_search.textChanged.connect(self._schedule_search_refresh)
        self.inp_search.returnPressed.connect(self._flush_search)
        lbl_group = QLabel("Gruppe")
        lbl_group.setObjectName("MutedLabel")
        self.combo_group = QComboBox()
        self.combo_group.setMinimumWidth(140)
        self.combo_group.currentTextChanged.connect(self.refresh_data)
        self.combo_sort = QComboBox()
        self.combo_sort.setMinimumWidth(160)
        for sort_key, sort_label in SORT_MODES:
            self.combo_sort.addItem(sort_label, sort_key)
        self.combo_sort.currentIndexChanged.connect(self.refresh_data)

        # Only meaningful for the grid; hidden on the downloads page.
        self._library_controls = (
            self.inp_search,
            lbl_group,
            self.combo_group,
            self.combo_sort,
        )
        for widget in self._library_controls:
            top_bar.addWidget(widget)
        return top_bar

    def _build_action_bar(self) -> QWidget:
        """Build the selection counter, select all/none and the batch action buttons."""
        bar = QWidget()
        bar.setObjectName("ActionBar")
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(8)

        self.btn_sel_all = button("Alle", "ghost", lambda: self.grid.select_all())
        self.btn_sel_none = button(
            "Keine", "ghost", lambda: self.grid.clear_selection()
        )
        self.lbl_sel_count = QLabel()
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
        self._batch_buttons = (
            button("Score setzen", "secondary", self._batch_score),
            button("Gruppe setzen", "secondary", self._batch_group),
            button("Löschen", "danger", self._batch_delete),
        )

        for widget in (
            self.btn_sel_all,
            self.btn_sel_none,
            self.lbl_sel_count,
            self.lbl_hint,
        ):
            layout.addWidget(widget)
        layout.addStretch()
        for widget in self._batch_buttons:
            layout.addWidget(widget)
        return bar

    # --- Pages ---
    def _show_page(self, page: MediaType | str) -> None:
        """Show the grid for a media type, or the DOWNLOADS or WHEEL page.

        Search, filters and the action bar are only shown for the grid. Switching
        pages clears the grid selection.
        """
        library_page = isinstance(page, MediaType)
        self.grid.reset_selection()
        self.sidebar.set_page(page)
        self.lbl_view_title.setText(PAGE_TITLES[page])
        for widget in self._library_controls:
            widget.setVisible(library_page)
        self.action_bar.setVisible(library_page)
        self.pages.setCurrentWidget(
            self.grid if library_page else self._side_pages[page]
        )
        if library_page:
            self.current_view = page
            self.refresh_data()
        else:
            self.lbl_empty.hide()
            self._sync_loading()

    def _show_wheel(self) -> None:
        """Show the wheel of fortune page."""
        self._show_page(WHEEL)
        self.wheel_page.setFocus()

    def _on_grid_page(self) -> bool:
        """Return True while the card grid is the visible page."""
        return self.pages.currentWidget() is self.grid

    def _reveal_downloads(self) -> None:
        """Show the downloads page if a download still runs and the grid is shown."""
        if self._on_grid_page():
            self._show_page(DOWNLOADS)

    def _leave_empty_downloads(self) -> None:
        """Leave the download page once the last job is cleared."""
        if self.pages.currentWidget() is self.downloads_page:
            self._show_page(MediaType.IMAGE)

    def _sync_loading(self, *_args: object) -> None:
        """Show the preview spinner while the grid page loads previews."""
        self.lbl_loading.set_running(self.grid.is_loading and self._on_grid_page())

    def refresh_data(self, *_args: object) -> None:
        """Rebuild the group filter and the cards of the current view.

        Keeps the chosen group when it still exists. Connected to every filter
        change, so it accepts and ignores signal arguments.
        """
        current_filter = self.combo_group.currentText()
        groups = [ALL_GROUPS, *self.db.get_all_groups()]
        self.combo_group.blockSignals(True)
        self.combo_group.clear()
        self.combo_group.addItems(groups)
        if current_filter in groups:
            self.combo_group.setCurrentText(current_filter)
        self.combo_group.blockSignals(False)

        location = self._locate()
        self.grid.show_entries(
            library.visible_entries(
                self.db.get_by_type(self.current_view),
                self.combo_group.currentText(),
                self.inp_search.text(),
                self.combo_sort.currentData(),
            ),
            root=location.volume,
            scope=self.config.volume_uuid,
        )
        self.lbl_empty.setVisible(not self.grid.cards and self._on_grid_page())
        self._sync_loading()

    def _update_action_bar(self) -> None:
        """Update the selection counter and enable the batch buttons for a selection."""
        count = len(self.grid.selected)
        self.lbl_sel_count.setText(f"{count} ausgewählt" if count else "Keine Auswahl")
        for btn in (*self._batch_buttons, self.btn_sel_none):
            btn.setEnabled(count > 0)
        self.btn_sel_all.setEnabled(bool(self.grid.cards))
        self.lbl_hint.setVisible(count == 0)

    # --- Configs and volumes ---
    def _load_config(self, db_path: str) -> None:
        """Make the config with ``db_path`` active, reusing its open database.

        Configs are reloaded from disk; a database opened for the first time is
        loaded and load errors are reported once after the event loop runs.
        """
        self.configs = load_configs()[0]
        self.config = next(
            (config for config in self.configs if config.db_path == db_path),
            self.configs[0],
        )
        if migrate_settings(self.plugins, self.configs):
            try:
                save_configs(self.configs, self.config.db_path)
            except OSError:
                logger.warning("Migrated plugin settings not saved")
        db = self._databases.get(self.config.db_path)
        if db is None:
            db = MediaDatabase(self.config.db_path)
            db.load()
            self._databases[self.config.db_path] = db
            QTimer.singleShot(0, lambda: self._report_load_error(db))
        self.db = db
        self._location = locate(self.config)

    def _activate_config(self, db_path: str) -> None:
        """Switch to another config and reset all per-library state.

        Abandons a running plugin fetch for the old library, clears previews,
        random history, ignored sync files and the search, then scans the folder
        and shows the page that has entries.
        """
        previous = self.db
        self._load_config(db_path)
        if self.db is not previous:
            # Posts fetched for the old library must not land in the new one.
            self.plugin_import.abandon()
        self.grid.forget_all()
        self.recent_picks = []
        self.folder_sync.reset()
        self.inp_search.blockSignals(True)
        self.inp_search.clear()
        self.inp_search.blockSignals(False)
        self._apply_config_ui()
        self.auto_scan_folder()
        self.refresh_data()

    def _apply_config_ui(self) -> None:
        """Fit the controls to the config and open a page that has entries.

        Shows the videos page only when the library has videos but no images.
        """
        ai = self.config.is_ai
        self.sidebar.set_mode(ai, self.config.has_folder)
        self.sidebar.set_last_sync(self.config.folder_last_sync)
        self.inp_search.setPlaceholderText(
            "Titel, Beschreibung, Prompt suchen…"
            if ai
            else "Titel, Beschreibung, Gruppe suchen…"
        )
        has_images = bool(self.db.get_by_type(MediaType.IMAGE))
        has_videos = bool(self.db.get_by_type(MediaType.VIDEO))
        self._show_page(
            MediaType.VIDEO if has_videos and not has_images else MediaType.IMAGE
        )
        self._check_volumes()

    def _report_load_error(self, database: MediaDatabase) -> None:
        """Tell the user once that a database failed to load and where its backup is."""
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

    def _locate(self) -> LibraryRoot:
        """Resolve where the active config's media lives right now."""
        return locate(self.config)

    def _check_volumes(self) -> None:
        """Keep location, window title, sidebar and stick banner in sync.

        Runs every 4 s. When the config's stick was plugged in or pulled, failed
        previews are retried, the folder is scanned and the grid refreshed. Also
        offers unassigned vault sticks in the banner.
        """
        location = self._locate()
        changed = location.volume != self._location.volume
        self._location = location

        suffix = " · KI" if self.config.is_ai else ""
        if self.config.volume_uuid and not location.available:
            suffix += " · 🔌 Stick nicht verbunden"
        self.setWindowTitle(f"MediaVault – {self.config.name}{suffix}")
        self.sidebar.set_stick_status(
            f"🔌 {self.config.volume_label or 'Stick'} · "
            f"{'verbunden' if location.available else 'nicht verbunden'}"
            if self.config.volume_uuid
            else "Kein Stick zugeordnet"
        )
        used = {config.volume_uuid for config in self.configs if config.volume_uuid}
        self.stick_banner.offer(
            [(root, info) for root, info in volumes.vaults() if info.uuid not in used]
        )
        if changed:
            # Previews missed while unplugged must be retried, and files added
            # on another machine picked up.
            self.grid.forget_missing()
            self.auto_scan_folder()
            self.refresh_data()

    def _library_ready(self) -> bool:
        """Return False and warn when the config's stick is not connected."""
        if self.config.volume_uuid and not self._locate().available:
            QMessageBox.warning(
                self,
                "Mediathek nicht verbunden",
                "Der Stick mit dieser Mediathek ist nicht verbunden.",
            )
            return False
        return True

    def auto_scan_folder(self) -> None:
        """Index new files of the config folder, except in AI mode.

        AI mode extracts metadata from every file, so it only syncs when the
        user asks for it. An unplugged volume simply yields no new entries:
        the database already holds the references from the first run.
        """
        if not self.config.is_ai:
            library.scan(self.db, self.config.mode, self._locate())

    def _on_folder_synced(self, added: bool) -> None:
        """Record the time of a completed folder sync and show new entries."""
        self.config.folder_last_sync = (
            datetime.now().astimezone().strftime("%d.%m.%Y %H:%M")
        )
        save_configs(self.configs, self.config.db_path)
        self.sidebar.set_last_sync(self.config.folder_last_sync)
        if added:
            self.refresh_data()

    def _open_stick(self) -> None:
        """Open the stick dialog and activate the config it produced.

        When the active config was moved onto a stick, its stored paths are made
        relative to the stick first.
        """
        self.db.save()
        dlg = StickDialog(self, self.configs, self.config)
        if dlg.exec() and dlg.target_db_path:
            if dlg.migrate_root:
                database = self._databases.get(dlg.target_db_path)
                if database is not None:
                    database.relativize(dlg.migrate_root)
            self._activate_config(dlg.target_db_path)

    def _switch_config(self) -> None:
        """Save the current database and open the config dialog; activate its choice."""
        self.db.save()
        dlg = ConfigDialog(self, self.configs, self.config.db_path)
        if not dlg.exec():
            return
        if dlg.wants_stick_setup:
            self._open_stick()
        elif dlg.selected_config is not None:
            self._activate_config(dlg.selected_config.db_path)

    def _toggle_theme(self) -> None:
        """Switch between dark and light theme at runtime."""
        self.theme.toggle(QApplication.instance())
        self.sidebar.set_theme(self.theme.name == "dark")

    # --- Import plugins ---
    def _start_plugin_import(self, key: str) -> None:
        """Start a plugin import into the active library, if its stick is connected."""
        plugin = self.plugins.get(key)
        if plugin is not None and self._library_ready():
            self.plugin_import.start(
                key, plugin, self.config, self.configs, self.db, self._locate()
            )

    def _on_download_finished(self, job: DownloadJob) -> None:
        """Hand the plugin state back after a clean run and refresh the grid.

        The grid only refreshes when the job imported into the active library.
        """
        apply_imported(job, self.plugins, self.configs, self.config.db_path)
        if job.imported and job.db is self.db:
            self.refresh_data()

    # --- Window events ---
    def closeEvent(self, event: QCloseEvent) -> None:
        """Keep the window open while background work could lose data.

        Refuses to close during a download or post fetch, and when the preview
        worker does not finish within 3 s (a broken video can block OpenCV).
        """
        if self.downloads_page.is_busy or self.plugin_import.is_busy:
            QMessageBox.information(
                self,
                "Download läuft",
                "Ein Download oder das Laden von Posts läuft noch. Bitte warte, "
                "bis er fertig ist, damit keine Datei halb geschrieben wird.",
            )
            event.ignore()
            return
        # A broken video can block OpenCV, so never wait for previews forever.
        if not self.grid.wait_for_previews(3000):
            QMessageBox.information(
                self,
                "Vorschauen werden geladen",
                "Die Vorschaubilder werden noch geladen. Bitte schließe das "
                "Fenster gleich noch einmal.",
            )
            event.ignore()
            return
        super().closeEvent(event)

    def changeEvent(self, event: QEvent) -> None:
        """Cancel an active rubber-band selection when the window deactivates."""
        if event.type() == QEvent.Type.WindowDeactivate:
            self.grid.cancel_drag()
        super().changeEvent(event)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        """Handle grid shortcuts: Ctrl+A, Ctrl+F, Esc and Delete.

        Only active while the grid page is shown, so they never act on hidden
        cards behind another page.
        """
        # Grid shortcuts must not act on hidden cards behind another page.
        if not self._on_grid_page():
            super().keyPressEvent(event)
            return
        if event.matches(QKeySequence.StandardKey.SelectAll):
            self.grid.select_all()
        elif event.matches(QKeySequence.StandardKey.Find):
            self.inp_search.setFocus()
            self.inp_search.selectAll()
        elif event.key() == Qt.Key.Key_Escape:
            self.grid.escape()
        elif event.key() == Qt.Key.Key_Delete and self.grid.selected:
            self._batch_delete()
        else:
            super().keyPressEvent(event)
            return
        event.accept()

    def _schedule_search_refresh(self, _text: str | None = None) -> None:
        """Debounce the grid rebuild by 200 ms while the user types."""
        if self.inp_search.text():
            self._search_timer.start()
        else:
            self._flush_search()

    def _flush_search(self) -> None:
        """Refresh the search immediately (Enter or cleared field)."""
        self._search_timer.stop()
        self.refresh_data()

    # --- Entries ---
    def _open_detail(self, entry: MediaItem) -> None:
        """Open the detail dialog and remember the entry as a recent pick.

        Opens the edit dialog afterwards when the user asked for it.
        """
        self.recent_picks = [e for e in self.recent_picks if e is not entry]
        self.recent_picks = [*self.recent_picks, entry][-RECENT_PICKS:]
        dlg = DetailDialog(
            self, entry, self.db, self.grid.pixmap, root=self._locate().volume
        )
        dlg.exec()
        if dlg.edit_requested:
            self._open_edit(entry)
        else:
            self.refresh_data()

    def _open_edit(self, entry: MediaItem) -> None:
        """Open the edit dialog; on save, persist, drop the old preview and refresh."""
        dlg = EditDialog(
            self, self.db, entry.entry_type, entry, root=self._locate().volume
        )
        if dlg.exec():
            self.db.save()
            self.grid.forget([entry])
            self.refresh_data()

    def _create_new(self) -> None:
        """Ask what to create and run it.

        Offers single and batch creation per media type; AI configs only offer
        images.
        """
        types = (MediaType.IMAGE,) if self.config.is_ai else tuple(MediaType)
        options: dict[str, Callable[[], None]] = {}
        for media_type in types:
            options[f"{TYPE_NAMES[media_type][0]} einzeln"] = partial(
                self._create_single, media_type
            )
        for media_type in types:
            options[f"{TYPE_NAMES[media_type][1]} Massenimport"] = partial(
                self._batch_import, media_type
            )
        choice, ok = QInputDialog.getItem(
            self, "Neu", "Aktion wählen:", list(options), 0, False
        )
        if ok:
            options[choice]()

    def _copy_into_library(self, path: str) -> str | None:
        """Copy one accepted file into the config folder.

        Configs without a managed folder keep files where they are.

        Returns:
            The stored path (the copy, or the original path), or None when the
            copy failed or the same content is already in the database.
        """
        target = self._locate().folder
        if not target:
            return path
        known = {
            entry.content_hash for entry in self.db.snapshot() if entry.content_hash
        }
        result = copy_into_folder([path], target, known)
        return result.copied[0] if result.copied else None

    def _create_single(self, media_type: MediaType) -> None:
        """Pick a file, check it, copy it into the library and edit the new entry.

        AI configs require AI metadata; duplicates are rejected. The file is only
        copied once every check passed, and the copy is removed again if the user
        cancels the edit dialog.
        """
        path, _ = file_dialogs.pick_file(
            self, "Datei auswählen", library.file_filter(media_type)
        )
        if not path or not self._library_ready():
            return

        meta: dict[str, Any] = {}
        if self.config.is_ai:
            meta = extract_ai_metadata(path) or {}
            if not meta:
                QMessageBox.warning(
                    self,
                    "Kein KI-Bild",
                    "In dieser Datei wurden keine KI-Metadaten gefunden.",
                )
                return
        root = self._locate().volume
        if find_duplicate(self.db, path, media_type, meta, root=root):
            QMessageBox.information(
                self, "Bereits vorhanden", "Dieses Medium ist bereits in der Sammlung."
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

        dlg = EditDialog(self, self.db, media_type, ai_meta=meta, root=root)
        field = dlg.inp_img if media_type == MediaType.IMAGE else dlg.inp_video
        field.setText(stored)
        if dlg.exec():
            self.refresh_data()
        elif stored != path:
            try:
                os.remove(stored)
            except OSError:
                logger.warning("Could not remove copy: %s", stored, exc_info=True)

    def _batch_import(self, media_type: MediaType) -> None:
        """Import several files as entries, skipping duplicates.

        New entries get the group selected in the filter and are copied into the
        config folder. A summary is shown when files were skipped.
        """
        paths, _ = file_dialogs.pick_files(
            self, "Importieren", library.file_filter(media_type)
        )
        if not paths or not self._library_ready():
            return
        group = self.combo_group.currentText()
        result = import_paths(
            self.db,
            paths,
            type_str=media_type,
            group="" if group == ALL_GROUPS else group,
            mode=self.config.mode,
            root=self._locate().volume,
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
        """Delete all selected entries after confirmation.

        Only database entries are removed; the files stay on disk.
        """
        doomed = set(self.grid.selected)
        answer = QMessageBox.question(self, "Löschen", f"{len(doomed)} löschen?")
        if answer != QMessageBox.StandardButton.Yes:
            return
        self.grid.forget(doomed)
        self.db.delete_multiple(doomed)
        self.recent_picks = [
            entry for entry in self.recent_picks if entry not in doomed
        ]
        self._finish_batch()

    def _batch_score(self) -> None:
        """Set the score of all selected entries to a value the user enters."""
        score, ok = QInputDialog.getInt(
            self, "Score", "Neuer Score (1-100):", 50, 1, 100
        )
        if ok:
            for entry in self.grid.selected:
                entry.score = score
            self.db.save()
            self._finish_batch()

    def _batch_group(self) -> None:
        """Assign an existing or newly typed group to all selected entries."""
        group, ok = QInputDialog.getItem(
            self,
            "Gruppe",
            "Neue Gruppe (oder neuen Namen tippen):",
            ["", *self.db.get_all_groups()],
            0,
            True,
        )
        if ok:
            for entry in self.grid.selected:
                entry.group = group.strip()
            self.db.save()
            self._finish_batch()

    def _finish_batch(self) -> None:
        """Clear the selection and refresh the grid after a batch action."""
        self.grid.clear_selection()
        self.refresh_data()

    # --- Random picks ---
    def _pick_and_open(self, pool: list[MediaItem], smart: bool) -> None:
        """Open a random entry whose file is readable.

        Tries up to five picks, so a few missing files do not end in nothing; gives
        up silently after that.

        Args:
            pool: Candidate entries.
            smart: True for the weighted pick (:meth:`MediaDatabase.get_random`).
        """
        root = self._locate().volume
        for _attempt in range(5):
            chosen = self.db.get_random(pool, smart, self.recent_picks)
            if chosen is None:
                return
            path = volumes.absolute_path(chosen.file_path, root)
            if path and os.path.isfile(path):
                self._open_detail(chosen)
                return

    def _do_random(self, smart: bool, global_pool: bool) -> None:
        """Pick a random entry from the current view or the library and open it."""
        if self._library_ready():
            pool = (
                self.db.snapshot()
                if global_pool
                else self.db.get_by_type(self.current_view)
            )
            self._pick_and_open(pool, smart)

    def _open_group_random(self) -> None:
        """Let the user choose groups and types, then open a random entry from them."""
        dlg = GroupRandomDialog(self, self.db)
        if dlg.exec() and dlg.result_pool:
            self._pick_and_open(dlg.result_pool, dlg.smart)
