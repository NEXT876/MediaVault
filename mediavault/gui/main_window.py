"""Main window of MediaVault."""

import logging
from collections.abc import Callable, Iterable
from typing import Any

from PyQt6.QtCore import QEvent, QObject, QPoint, QRect, Qt, QThread, QTimer
from PyQt6.QtGui import QKeyEvent, QKeySequence, QPixmap, QResizeEvent
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
    QRubberBand,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from mediavault.ai_meta import extract_ai_metadata
from mediavault.config import (
    IMAGE_EXTS,
    MODE_AI,
    find_new_images,
    load_configs,
    save_configs,
)
from mediavault.gui.dialogs import (
    AnalysisDialog,
    ConfigDialog,
    DetailDialog,
    EditDialog,
    GroupRandomDialog,
    Rule34Dialog,
    Rule34PreviewDialog,
)
from mediavault.gui.theme import ThemeManager
from mediavault.gui.widgets import CARD_WIDTH, MediaCard
from mediavault.importer import find_duplicate, import_paths
from mediavault.models import MediaDatabase, MediaItem
from mediavault.rule34 import (
    Post,
    collect_new_posts,
    download_and_import,
    fetch_preview,
    query_signature,
)
from mediavault.utils import OSHelper

logger = logging.getLogger(__name__)

ALL_GROUPS = "Alle Gruppen"


class _Rule34Worker(QThread):
    """Run one blocking rule34 step outside the GUI thread."""

    def __init__(
        self, parent: QWidget, fn: Callable[..., Any], **kwargs: Any
    ) -> None:
        super().__init__(parent)
        self._fn = fn
        self._kwargs = kwargs
        self.result: Any = None
        self.error: Exception | None = None

    def run(self) -> None:
        """Run the step and store its outcome for the GUI thread."""
        try:
            self.result = self._fn(**self._kwargs)
        except Exception as exc:  # noqa: BLE001 - reported in the GUI thread
            self.error = exc


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


class MainWindow(QMainWindow):
    """Main window with sidebar, filter bar, card grid and batch actions."""

    GRID_SPACING = 12
    SCROLLBAR_RESERVE = 12
    AUTOSCROLL_MARGIN = 24
    AUTOSCROLL_STEP = 28

    def __init__(self, theme_manager: ThemeManager | None = None) -> None:
        """Initialize the database, view state and the full user interface."""
        super().__init__()
        self.setWindowTitle("MediaVault")
        self.resize(1180, 820)

        self.configs, last = load_configs()
        self.config = next(
            (config for config in self.configs if config.db_path == last),
            self.configs[0],
        )

        self.db = MediaDatabase(self.config.db_path)
        self.db.load()

        self.theme = theme_manager or ThemeManager()
        self.current_view: str = "Bilder"
        self.selected_entries: set[MediaItem] = set()
        self.recent_picks: list[MediaItem] = []
        self.thumbnail_cache: dict[str, QPixmap | None] = {}
        self.cards: list[MediaCard] = []
        self.current_cols = 1

        self._anchor_entry: MediaItem | None = None
        self._press_snapshot: set[MediaItem] = set()
        self._drag_base: set[MediaItem] = set()
        self._drag_origin_global: QPoint | None = None
        self._last_drag_global: QPoint | None = None
        self._rubber_band: QRubberBand | None = None
        self._autoscroll_direction = 0

        self._autoscroll_timer = QTimer(self)
        self._autoscroll_timer.setInterval(40)
        self._autoscroll_timer.timeout.connect(self._autoscroll_step)

        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(200)
        self._search_timer.timeout.connect(self.refresh_data)

        self._setup_ui()
        self._sync_theme_button()
        self._apply_config_ui()
        self.refresh_data()

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
            "🖼️  Bilder", lambda: self.switch_view("Bilder"), checkable=True
        )
        self.btn_videos = self._create_side_btn(
            "🎬  Videos", lambda: self.switch_view("Videos"), checkable=True
        )
        self.btn_bilder.setChecked(True)
        side_layout.addWidget(self.btn_bilder)
        side_layout.addWidget(self.btn_videos)

        self.lbl_analysis_section = self._create_section_label("KI-ANALYSE")
        side_layout.addWidget(self.lbl_analysis_section)
        self.btn_analysis = self._create_side_btn("📊  Analyse", self._open_analysis)
        side_layout.addWidget(self.btn_analysis)

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

        lbl_group = QLabel("Gruppe")
        lbl_group.setObjectName("MutedLabel")
        top_bar.addWidget(lbl_group)
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
        content_layout.addWidget(self.scroll_area, 1)

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
        self.btn_bilder.setChecked(view == "Bilder")
        self.btn_videos.setChecked(view == "Videos")
        self.lbl_view_title.setText("🖼️ Bilder" if view == "Bilder" else "🎬 Videos")
        self._cancel_drag()
        self._apply_selection(set())
        self._anchor_entry = None
        self.refresh_data()

    def _apply_config_ui(self) -> None:
        """Show only the controls that fit the active config's mode."""
        ai = self.config.mode == MODE_AI
        self.btn_videos.setVisible(not ai)
        self.lbl_analysis_section.setVisible(ai)
        self.btn_analysis.setVisible(ai)
        self.lbl_rule34_section.setVisible(not ai)
        self.btn_rule34.setVisible(not ai)
        self.current_view = "Bilder"
        self.btn_bilder.setChecked(True)
        self.lbl_view_title.setText("🖼️ Bilder")
        self.inp_search.setPlaceholderText(
            "Titel, Beschreibung, Prompt suchen…"
            if ai
            else "Titel, Beschreibung, Gruppe suchen…"
        )
        suffix = " · KI" if ai else ""
        self.setWindowTitle(f"MediaVault – {self.config.name}{suffix}")

    def scan_folder(self) -> None:
        """Import images from the config's folder, using the DB as the cache."""
        if not self.config.folder:
            return
        ai = self.config.mode == MODE_AI
        known = [entry.image_path for entry in self.db.get_by_type("Bilder")]
        paths = find_new_images(
            self.config.folder, known, {".png"} if ai else IMAGE_EXTS
        )
        import_paths(
            self.db, paths, type_str="Bilder", group="", mode=self.config.mode
        )

    def _fetch_rule34(self) -> None:
        """Fetch new rule34 posts and show them for selection."""
        if self.config.mode == MODE_AI:
            return
        dlg = Rule34Dialog(self, self.config)
        if not dlg.exec():
            return
        for key, value in dlg.settings().items():
            setattr(self.config, key, value)
        save_configs(self.configs, self.config.db_path)

        signature = query_signature(
            self.config.rule34_tags, self.config.rule34_webm
        )
        # The reset option ignores the stored ID; the import still skips
        # files that are already stored locally.
        last_id = (
            0
            if dlg.chk_reset.isChecked()
            else self.config.rule34_last_ids.get(signature, 0)
        )
        worker = _Rule34Worker(
            self,
            self._load_rule34_preview,
            api_key=self.config.rule34_api_key,
            user_id=self.config.rule34_user_id,
            tags=self.config.rule34_tags,
            webm=self.config.rule34_webm,
            limit=self.config.rule34_count,
            last_id=last_id,
        )
        progress = self._rule34_progress("Lade Posts von rule34 …")
        worker.finished.connect(
            lambda: self._show_rule34_preview(worker, signature, progress)
        )
        worker.start()
        progress.show()

    def _load_rule34_preview(
        self,
        *,
        api_key: str,
        user_id: str,
        tags: str,
        webm: bool,
        limit: int,
        last_id: int,
    ) -> tuple[list[Post], dict[int, bytes]]:
        """Fetch new posts and their thumbnails for the selection dialog."""
        posts = collect_new_posts(api_key, user_id, tags, webm, limit, last_id)
        previews: dict[int, bytes] = {}
        for post in posts:
            data = fetch_preview(post.preview_url)
            if data:
                previews[post.id] = data
        return posts, previews

    def _rule34_progress(self, text: str) -> QProgressDialog:
        """Create a modal busy dialog for one rule34 step."""
        progress = QProgressDialog(text, "", 0, 0, self)
        progress.setCancelButton(None)
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.setMinimumDuration(0)
        return progress

    def _show_rule34_preview(
        self, worker: _Rule34Worker, signature: str, progress: QProgressDialog
    ) -> None:
        """Open the selection dialog for the fetched posts."""
        progress.close()
        progress.deleteLater()
        worker.deleteLater()
        if worker.error is not None:
            QMessageBox.warning(self, "rule34 Import", str(worker.error))
            return
        posts, previews = worker.result
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
        importer = _Rule34Worker(
            self,
            download_and_import,
            db=self.db,
            posts=posts,
            folder=self.config.folder,
            tags=self.config.rule34_tags,
            selected_ids=selected,
        )
        progress = self._rule34_progress("Lade ausgewählte Posts …")
        importer.finished.connect(
            lambda: self._apply_rule34_result(importer, signature, progress)
        )
        importer.start()
        progress.show()

    def _apply_rule34_result(
        self, worker: _Rule34Worker, signature: str, progress: QProgressDialog
    ) -> None:
        """Report a finished rule34 import and store the newest post ID."""
        progress.close()
        progress.deleteLater()
        worker.deleteLater()
        if worker.error is not None:
            QMessageBox.warning(self, "rule34 Import", str(worker.error))
            return
        result = worker.result
        if result is None:
            return
        if result.imported:
            self.refresh_data()
        summary = f"{result.imported} importiert, {result.duplicates} Duplikate"
        if result.failed:
            QMessageBox.warning(
                self,
                "rule34 Import",
                summary + "\n\nFehlgeschlagen:\n" + "\n".join(result.failed),
            )
            return
        if result.newest_id:
            self.config.rule34_last_ids[signature] = result.newest_id
            save_configs(self.configs, self.config.db_path)
        QMessageBox.information(self, "rule34 Import", summary)

    def _get_pixmap(self, entry: MediaItem) -> QPixmap | None:
        """Return an entry's preview pixmap, cached by its media path."""
        key = entry.media_path
        if key not in self.thumbnail_cache:
            pixmap = None
            if entry.image_path:
                try:
                    pixmap = QPixmap(entry.image_path)
                except (OSError, TypeError, ValueError):
                    logger.debug(
                        "Bild konnte nicht geladen werden: %s",
                        entry.image_path,
                        exc_info=True,
                    )
            elif entry.entry_type == "Videos":
                pixmap = OSHelper.get_video_frame_pixmap(entry.video_link)
                if not pixmap:
                    os_thumb = OSHelper.get_os_thumbnail(entry.video_link)
                    if os_thumb:
                        pixmap = QPixmap(os_thumb)
            if pixmap:
                # Cards are ~176 px wide; keep the cache small.
                pixmap = pixmap.scaled(
                    512,
                    512,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            self.thumbnail_cache[key] = pixmap
        return self.thumbnail_cache[key]

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
            card = MediaCard(entry, self._get_pixmap(entry))
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

        self.lbl_empty.setVisible(not self.cards)
        self._update_columns()
        self._reflow_grid()
        self._update_action_bar()

    # --- Grid ---
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
    def _ensure_rubber_band(self) -> QRubberBand:
        """Create the selection rectangle on first use."""
        if self._rubber_band is None:
            self._rubber_band = QRubberBand(
                QRubberBand.Shape.Rectangle, self.scroll_area.viewport()
            )
            self._rubber_band.setAttribute(
                Qt.WidgetAttribute.WA_TransparentForMouseEvents, True
            )
        return self._rubber_band

    def _on_drag_pressed(self, entry: MediaItem, global_pos: QPoint) -> None:
        """Capture the starting selection before the first click."""
        self._press_snapshot = set(self.selected_entries)
        self._drag_base = set(self.selected_entries)
        self._drag_origin_global = global_pos
        self._last_drag_global = global_pos

    def _on_drag_moved(self, global_pos: QPoint) -> None:
        """Draw the selection rectangle and select the cards it touches."""
        if self._drag_origin_global is None:
            return
        self._last_drag_global = global_pos
        viewport = self.scroll_area.viewport()
        origin = viewport.mapFromGlobal(self._drag_origin_global)
        current = viewport.mapFromGlobal(global_pos)
        rect = QRect(origin, current).normalized().intersected(viewport.rect())

        band = self._ensure_rubber_band()
        band.setGeometry(rect)
        if not band.isVisible():
            band.show()
        band.raise_()

        self._apply_selection(self._drag_base | self._cards_intersecting(rect))
        self._update_autoscroll(current)

    def _on_drag_finished(self) -> None:
        """Finish the rubber-band selection."""
        self._cancel_drag()

    def _cancel_drag(self) -> None:
        """Hide the selection rectangle and stop auto-scrolling."""
        self._autoscroll_timer.stop()
        self._autoscroll_direction = 0
        self._drag_origin_global = None
        self._last_drag_global = None
        self._drag_base = set()
        if self._rubber_band is not None:
            self._rubber_band.hide()
            self._rubber_band.setGeometry(QRect())

    def _cards_intersecting(self, rect: QRect) -> set[MediaItem]:
        """Return all cards intersecting ``rect`` in viewport coordinates."""
        viewport = self.scroll_area.viewport()
        hits = set()
        for card in self.cards:
            top_left = card.mapTo(viewport, QPoint(0, 0))
            if rect.intersects(QRect(top_left, card.size())):
                hits.add(card.entry)
        return hits

    def _update_autoscroll(self, pos_in_viewport: QPoint) -> None:
        """Start or stop scrolling at the top or bottom edge."""
        viewport = self.scroll_area.viewport()
        direction = 0
        if pos_in_viewport.y() < self.AUTOSCROLL_MARGIN:
            direction = -1
        elif pos_in_viewport.y() > viewport.height() - self.AUTOSCROLL_MARGIN:
            direction = 1
        self._autoscroll_direction = direction
        if direction and not self._autoscroll_timer.isActive():
            self._autoscroll_timer.start()
        elif not direction:
            self._autoscroll_timer.stop()

    def _autoscroll_step(self) -> None:
        """Advance the scroll position while a rubber-band selection is active."""
        if not self._autoscroll_direction or self._last_drag_global is None:
            self._autoscroll_timer.stop()
            return
        bar = self.scroll_area.verticalScrollBar()
        before = bar.value()
        bar.setValue(before + self._autoscroll_direction * self.AUTOSCROLL_STEP)
        if bar.value() == before:
            self._autoscroll_timer.stop()
            return
        self._on_drag_moved(self._last_drag_global)

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
            if self._drag_origin_global is not None:
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
        if not dlg.exec() or dlg.selected_config is None:
            return

        self.configs, last = load_configs()
        self.config = next(
            (config for config in self.configs if config.db_path == last),
            dlg.selected_config,
        )
        self.db = MediaDatabase(self.config.db_path)
        self.db.load()

        self.thumbnail_cache.clear()
        self.recent_picks = []
        self.inp_search.blockSignals(True)
        self.inp_search.clear()
        self.inp_search.blockSignals(False)
        self._apply_selection(set())
        self._anchor_entry = None
        self._apply_config_ui()
        self.scan_folder()
        self.refresh_data()

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

        dlg = DetailDialog(self, entry, self.db, self._get_pixmap)
        dlg.exec()
        if dlg.edit_requested:
            self._open_edit(entry)
        else:
            self.refresh_data()

    def _open_edit(self, entry: MediaItem) -> None:
        """Open the edit dialog and reload the view after saving."""
        dlg = EditDialog(self, self.db, entry.entry_type, entry)
        if dlg.exec():
            self.db.save()
            self.thumbnail_cache.pop(entry.media_path, None)
            self.refresh_data()

    def _create_new(self) -> None:
        """Show a menu to choose between single and batch creation."""
        options: list[tuple[str, Callable[[], None]]] = [
            ("Bild einzeln", lambda: self._create_single("Bilder")),
            ("Video einzeln", lambda: self._create_single("Videos")),
            ("Bilder Massenimport", lambda: self._batch_import("Bilder")),
            ("Videos Massenimport", lambda: self._batch_import("Videos")),
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
        if type_str == "Bilder":
            file_filter = "Bilder (*.png *.jpg *.jpeg *.bmp *.webp);;Alle Dateien (*.*)"
        else:
            file_filter = "Videos (*.mp4 *.mkv *.avi *.mov *.webm);;Alle Dateien (*.*)"

        path, _ = OSHelper.pick_file(self, "Datei auswählen", file_filter)
        if not path:
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

        if find_duplicate(self.db, path, type_str, meta):
            QMessageBox.information(
                self,
                "Bereits vorhanden",
                "Dieses Medium ist bereits in der Sammlung.",
            )
            return

        dlg = EditDialog(self, self.db, type_str, ai_meta=meta)
        if type_str == "Bilder":
            dlg.inp_img.setText(path)
        else:
            dlg.inp_video.setText(path)

        if dlg.exec():
            self.refresh_data()

    def _batch_import(self, type_str: str) -> None:
        """Import several files as entries, skipping duplicates."""
        exts = (
            "*.png *.jpg *.jpeg *.bmp *.webp"
            if type_str == "Bilder"
            else "*.mp4 *.mkv *.avi *.mov *.webm"
        )
        paths, _ = OSHelper.pick_files(
            self, "Importieren", f"Media ({exts});;Alle (*.*)"
        )
        if not paths:
            return

        group = (
            self.combo_group.currentText()
            if self.combo_group.currentText() != ALL_GROUPS
            else ""
        )
        result = import_paths(
            self.db, paths, type_str=type_str, group=group, mode=self.config.mode
        )
        if result.added:
            self.refresh_data()
        if result.duplicates or result.skipped_no_ai:
            summary = [f"{result.added} importiert", f"{result.duplicates} Duplikate"]
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

    def _do_random(self, smart: bool, global_pool: bool) -> None:
        """Pick a random entry (local or global) and open it."""
        pool = (
            self.db.entries if global_pool else self.db.get_by_type(self.current_view)
        )
        chosen = self.db.get_random(pool, smart, self.recent_picks)
        if chosen:
            self._open_detail(chosen)

    def _open_group_random(self) -> None:
        """Open the group random dialog and show the chosen entry."""
        dlg = GroupRandomDialog(self, self.db)
        if dlg.exec() and dlg.result_pool:
            chosen = self.db.get_random(dlg.result_pool, dlg.smart, self.recent_picks)
            if chosen:
                self._open_detail(chosen)
