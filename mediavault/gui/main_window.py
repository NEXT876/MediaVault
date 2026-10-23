"""Main window of MediaVault."""

import logging
import os
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from PyQt6.QtCore import (
    QEvent,
    QObject,
    QPoint,
    QRect,
    Qt,
    QTimer,
    pyqtSignal,
)
from PyQt6.QtGui import (
    QCloseEvent,
    QImage,
    QKeyEvent,
    QKeySequence,
    QPixmap,
    QResizeEvent,
)
from PyQt6.QtWidgets import (
    QApplication,
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QProgressDialog,
    QPushButton,
    QRubberBand,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
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
    FolderPreviewDialog,
    GroupRandomDialog,
    Rule34Dialog,
    Rule34PreviewDialog,
    Worker,
)
from mediavault.gui.theme import ThemeManager
from mediavault.gui.widgets import CARD_WIDTH, MediaCard
from mediavault.importer import find_duplicate, import_paths, norm_path
from mediavault.models import MediaDatabase, MediaItem
from mediavault.rule34 import (
    Post,
    collect_new_posts_multi,
    download_and_import,
    fetch_preview,
)
from mediavault.utils import OSHelper

logger = logging.getLogger(__name__)

_SPINNER_FRAMES = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"


def load_thumbnail(entry: MediaItem) -> QImage | None:
    """Load and scale one preview image; safe outside the GUI thread."""
    image: QImage | None = None
    if entry.image_path:
        image = QImage(entry.image_path)
        if image.isNull():
            logger.debug("Bild konnte nicht geladen werden: %s", entry.image_path)
            image = None
    elif entry.entry_type == "Videos":
        image = OSHelper.get_video_frame_image(entry.video_link)
        if image is None:
            os_thumb = OSHelper.get_os_thumbnail(entry.video_link)
            if os_thumb:
                image = QImage(os_thumb)
    if image is None or image.isNull():
        return None
    # Cards are ~176 px wide; keep the cache small.
    return image.scaled(
        512,
        512,
        Qt.AspectRatioMode.KeepAspectRatio,
        Qt.TransformationMode.SmoothTransformation,
    )


def load_thumbnails(entries: list[MediaItem]) -> dict[str, QImage | None]:
    """Load previews for several entries, keyed by media path.

    One broken file must not discard the previews of the whole batch.
    """
    previews: dict[str, QImage | None] = {}
    for entry in entries:
        try:
            previews[entry.media_path] = load_thumbnail(entry)
        except Exception:  # One bad file must not stop the batch.
            logger.debug(
                "Vorschau fehlgeschlagen: %s", entry.media_path, exc_info=True
            )
            previews[entry.media_path] = None
    return previews


ALL_GROUPS = "Alle Gruppen"


@dataclass
class DownloadJob:
    """One rule34 import waiting in or running through the download queue."""

    number: int
    label: str
    db: MediaDatabase
    folder: str
    tags: str
    posts: list[Post]
    selected_ids: set[int]
    newest_ids: dict[str, int]
    state: str = "waiting"
    done: int = 0
    total: int = 0
    imported: int = 0
    duplicates: int = 0
    failed: int = 0
    detail: str = ""


_JOB_ICONS = {"waiting": "⏳", "running": "⬇️", "done": "✅", "error": "⚠️"}


def download_status_text(job: DownloadJob) -> str:
    """Return the short status line shown under a job's title."""
    if job.state == "waiting":
        return "Wartet in der Warteschlange"
    if job.state == "running":
        if job.total:
            # ``done`` counts finished files; the next one is in progress.
            return f"Lädt Datei {min(job.done + 1, job.total)} von {job.total}"
        return "Startet …"
    if job.state == "error":
        return "Fehlgeschlagen"
    parts = [f"{job.imported} importiert", f"{job.duplicates} Duplikate"]
    if job.failed:
        parts.append(f"{job.failed} fehlgeschlagen")
    return ", ".join(parts)


class _ProgressBridge(QObject):
    """Deliver download progress from the worker thread to the GUI thread."""

    progress = pyqtSignal(int, int)

    def __init__(
        self, callback: Callable[[int, int], None], parent: QObject | None = None
    ) -> None:
        super().__init__(parent)
        self._callback = callback
        self.progress.connect(self._deliver)

    def _deliver(self, done: int, total: int) -> None:
        """Forward one progress report to the GUI callback."""
        self._callback(done, total)


class DownloadRow(QFrame):
    """Card on the downloads page showing one job's state and progress."""

    def __init__(self, job: DownloadJob) -> None:
        """Build the card and fill it with the job's current state."""
        super().__init__()
        self.setObjectName("DownloadRow")
        self.lbl_icon = QLabel()
        self.lbl_icon.setObjectName("DownloadIcon")
        self.lbl_icon.setFixedWidth(26)
        self.lbl_title = QLabel()
        self.lbl_title.setObjectName("DownloadTitle")
        self.lbl_status = QLabel()
        self.lbl_status.setObjectName("MutedLabel")
        self.bar = QProgressBar()
        self.bar.setTextVisible(False)
        self.bar.setFixedHeight(6)
        self.lbl_detail = QLabel()
        self.lbl_detail.setObjectName("HintLabel")
        self.lbl_detail.setWordWrap(True)

        text_layout = QVBoxLayout()
        text_layout.setSpacing(2)
        text_layout.addWidget(self.lbl_title)
        text_layout.addWidget(self.lbl_status)
        text_layout.addWidget(self.bar)
        text_layout.addWidget(self.lbl_detail)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(10)
        layout.addWidget(self.lbl_icon, 0, Qt.AlignmentFlag.AlignTop)
        layout.addLayout(text_layout, 1)
        self.set_job(job)

    def set_job(self, job: DownloadJob) -> None:
        """Update icon, title, status, progress bar and error detail."""
        done_with_errors = job.state == "done" and job.failed > 0
        self.lbl_icon.setText("⚠️" if done_with_errors else _JOB_ICONS[job.state])
        self.lbl_title.setText(f"#{job.number}  {job.label}")
        self.lbl_status.setText(download_status_text(job))
        self.bar.setVisible(job.state == "running")
        self.bar.setRange(0, max(job.total, 1))
        self.bar.setValue(job.done)
        self.lbl_detail.setText(job.detail)
        self.lbl_detail.setVisible(bool(job.detail))
        self.setToolTip(job.detail)


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
        # Keyed by db_path, so switching back reuses the object a background
        # download is writing to instead of overwriting its entries.
        self._databases: dict[str, MediaDatabase] = {self.config.db_path: self.db}

        self.theme = theme_manager or ThemeManager()
        self.current_view: str = "Bilder"
        self.selected_entries: set[MediaItem] = set()
        self.recent_picks: list[MediaItem] = []
        self.thumbnail_cache: dict[str, QPixmap | None] = {}
        # Loads missing previews in the background so the grid stays usable.
        self._thumb_worker: Worker | None = None
        self.cards: list[MediaCard] = []
        self.current_cols = 1

        self._anchor_entry: MediaItem | None = None
        self._press_snapshot: set[MediaItem] = set()
        self._drag_base: set[MediaItem] = set()
        self._drag_origin_global: QPoint | None = None
        self._last_drag_global: QPoint | None = None
        self._rubber_band: QRubberBand | None = None
        self._autoscroll_direction = 0
        # Paths the last folder sync could not import; hidden from later syncs.
        self._sync_ignored: set[str] = set()

        # rule34 imports run one at a time in the background, so the window
        # stays usable and further imports wait in the queue.
        self._download_jobs: list[DownloadJob] = []
        self._download_rows: dict[int, DownloadRow] = {}
        self._download_active: DownloadJob | None = None
        self._download_seq = 0
        # The worker that fetches rule34 posts before the preview opens.
        self._rule34_fetch: Worker | None = None

        self._autoscroll_timer = QTimer(self)
        self._autoscroll_timer.setInterval(40)
        self._autoscroll_timer.timeout.connect(self._autoscroll_step)

        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(200)
        self._search_timer.timeout.connect(self.refresh_data)

        # Reveal the queue page only when a download takes noticeably long.
        self._download_timer = QTimer(self)
        self._download_timer.setSingleShot(True)
        self._download_timer.setInterval(1500)
        self._download_timer.timeout.connect(self._reveal_downloads)

        self._spinner_frame = 0
        self._spinner_timer = QTimer(self)
        self._spinner_timer.setInterval(90)
        self._spinner_timer.timeout.connect(self._spin)

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

        self.downloads_page = QWidget()
        downloads_layout = QVBoxLayout(self.downloads_page)
        downloads_layout.setContentsMargins(0, 0, 0, 0)
        downloads_layout.setSpacing(8)
        lbl_downloads_hint = QLabel(
            "Downloads laufen im Hintergrund weiter. Du kannst die Bibliothek "
            "benutzen und weitere Importe einreihen."
        )
        lbl_downloads_hint.setObjectName("HintLabel")
        lbl_downloads_hint.setWordWrap(True)
        downloads_layout.addWidget(lbl_downloads_hint)

        header = QHBoxLayout()
        header.setSpacing(8)
        self.lbl_downloads_summary = QLabel()
        self.lbl_downloads_summary.setObjectName("SectionLabel")
        self.btn_clear_downloads = QPushButton("Fertige entfernen")
        self.btn_clear_downloads.setProperty("variant", "ghost")
        self.btn_clear_downloads.clicked.connect(self._clear_finished_downloads)
        header.addWidget(self.lbl_downloads_summary)
        header.addStretch(1)
        header.addWidget(self.btn_clear_downloads)
        downloads_layout.addLayout(header)

        self.lbl_downloads_activity = QLabel()
        self.lbl_downloads_activity.setObjectName("HintLabel")
        self.lbl_downloads_activity.setWordWrap(True)
        downloads_layout.addWidget(self.lbl_downloads_activity)

        self.downloads_scroll = QScrollArea()
        self.downloads_scroll.setWidgetResizable(True)
        self.downloads_scroll.setObjectName("CardScroll")
        downloads_container = QWidget()
        downloads_container.setObjectName("GridContainer")
        self.downloads_layout = QVBoxLayout(downloads_container)
        self.downloads_layout.setContentsMargins(0, 0, 0, 0)
        self.downloads_layout.setSpacing(8)
        self.downloads_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.downloads_scroll.setWidget(downloads_container)
        downloads_layout.addWidget(self.downloads_scroll, 1)

        self.lbl_downloads_empty = QLabel("Keine Downloads.")
        self.lbl_downloads_empty.setObjectName("MutedLabel")
        self.lbl_downloads_empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        downloads_layout.addWidget(self.lbl_downloads_empty)

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
        self.btn_bilder.setChecked(view == "Bilder")
        self.btn_videos.setChecked(view == "Videos")
        self.btn_downloads.setChecked(False)
        self.lbl_view_title.setText("🖼️ Bilder" if view == "Bilder" else "🎬 Videos")
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
        self._render_downloads()

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
        self.current_view = "Bilder"
        self.btn_bilder.setChecked(True)
        self.btn_downloads.setChecked(False)
        self.pages.setCurrentWidget(self.scroll_area)
        self._set_library_controls_visible(True)
        self.action_bar.show()
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

    def auto_scan_folder(self) -> None:
        """Scan the folder on startup unless the config is in AI mode.

        AI mode extracts metadata from every file, so it only syncs when the
        user asks for it.
        """
        if self.config.mode != MODE_AI:
            self.scan_folder()

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
        folder = self.config.folder.strip()
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
        known = [entry.image_path for entry in self.db.get_by_type("Bilder")]
        known.extend(self._sync_ignored)
        self.btn_sync_folder.setEnabled(False)
        worker = Worker(
            self,
            find_new_images,
            folder=folder,
            known_paths=known,
            extensions={".png"},
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
        paths = [path for path in worker.result if os.path.isfile(path)]
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
            type_str="Bilder",
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
            norm_path(entry.image_path) for entry in self.db.get_by_type("Bilder")
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
        self.config.folder_last_sync = datetime.now().strftime("%d.%m.%Y %H:%M")
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
            setattr(self.config, key, value)
        save_configs(self.configs, self.config.db_path)

        # The reset option ignores the stored IDs; the import still skips
        # files that are already stored locally.
        last_ids: dict[str, int] = (
            {} if dlg.chk_reset.isChecked() else self.config.rule34_last_ids
        )
        db = self.db
        worker = Worker(
            self,
            self._load_rule34_preview,
            api_key=self.config.rule34_api_key,
            user_id=self.config.rule34_user_id,
            tags=self.config.rule34_tags,
            webm=self.config.rule34_webm,
            limit=self.config.rule34_count,
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
        self.lbl_downloads_activity.setText(
            "🔎  Lade Posts von rule34 …" if loading else ""
        )
        self.lbl_downloads_activity.setVisible(loading)
        self._render_downloads()

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
        """Add a rule34 import to the queue and start it when nothing runs."""
        self._download_seq += 1
        self._download_jobs.append(
            DownloadJob(
                number=self._download_seq,
                label=(
                    f"{self.config.rule34_tags or 'ohne Tags'} · "
                    f"{len(selected_ids)} Posts"
                ),
                db=db,
                folder=self.config.folder,
                tags=self.config.rule34_tags,
                posts=posts,
                selected_ids=selected_ids,
                newest_ids=newest_ids,
            )
        )
        self._render_downloads()
        if self._download_active is None:
            self._start_next_download()
        self._download_timer.start()

    def _start_next_download(self) -> None:
        """Start the first waiting job; only one download runs at a time."""
        job = next(
            (job for job in self._download_jobs if job.state == "waiting"), None
        )
        self._download_active = job
        if job is None:
            return
        job.state = "running"
        job.done = 0
        job.total = len(job.selected_ids)
        self._render_downloads()
        # The bridge turns the worker-thread callback into a GUI-thread signal.
        bridge = _ProgressBridge(
            lambda done, total: self._on_download_progress(job, done, total)
        )
        worker = Worker(
            self,
            download_and_import,
            db=job.db,
            posts=job.posts,
            folder=job.folder,
            tags=job.tags,
            selected_ids=job.selected_ids,
            progress=bridge.progress.emit,
        )
        bridge.setParent(worker)
        worker.finished.connect(lambda: self._finish_download(worker, job))
        worker.start()

    def _on_download_progress(self, job: DownloadJob, done: int, total: int) -> None:
        """Update one job's progress bar while its files download."""
        if job.state != "running":
            return
        job.done = done
        job.total = total
        row = self._download_rows.get(job.number)
        if row is not None:
            row.set_job(job)

    def _finish_download(self, worker: Worker, job: DownloadJob) -> None:
        """Record a finished job, store its post IDs and start the next one."""
        self._download_active = None
        error = worker.error
        result = worker.result
        worker.deleteLater()
        if error is not None:
            job.state = "error"
            job.detail = str(error)
        elif result is not None:
            job.state = "done"
            job.imported = result.imported
            job.duplicates = result.duplicates
            job.failed = len(result.failed)
            job.detail = "\n".join(result.failed)
            if not result.failed:
                # Same rule as before: keep the IDs only when every selected
                # post reached the disk.
                config = next(
                    (
                        config
                        for config in self.configs
                        if config.db_path == job.db.filepath
                    ),
                    None,
                )
                if config is not None and job.newest_ids:
                    config.rule34_last_ids.update(job.newest_ids)
                    save_configs(self.configs, self.config.db_path)
            if result.imported and job.db is self.db:
                self.refresh_data()
        self._render_downloads()
        self._start_next_download()

    def _reveal_downloads(self) -> None:
        """Switch to the queue page when a download still runs after a while."""
        if self._download_active is not None and (
            self.pages.currentWidget() is self.scroll_area
        ):
            self._show_downloads()

    def _render_downloads(self) -> None:
        """Redraw the job cards, the summary line and the sidebar button."""
        while self.downloads_layout.count():
            item = self.downloads_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.hide()
                widget.setParent(None)
                widget.deleteLater()
        self._download_rows = {}
        for job in self._download_jobs:
            row = DownloadRow(job)
            self._download_rows[job.number] = row
            self.downloads_layout.addWidget(row)

        open_jobs = sum(
            1 for job in self._download_jobs if job.state in ("waiting", "running")
        )
        finished = len(self._download_jobs) - open_jobs
        has_jobs = bool(self._download_jobs)
        loading = self._rule34_fetch is not None
        self.lbl_downloads_empty.setVisible(not has_jobs and not loading)
        self.downloads_scroll.setVisible(has_jobs)
        self.lbl_downloads_summary.setVisible(has_jobs)
        self.lbl_downloads_summary.setText(
            f"{open_jobs} offen · {finished} abgeschlossen"
        )
        self.btn_clear_downloads.setVisible(finished > 0)
        self.btn_downloads.setText(
            f"⬇️  Downloads ({open_jobs})" if open_jobs else "⬇️  Downloads"
        )
        self.btn_downloads.setVisible(has_jobs)

    def _clear_finished_downloads(self) -> None:
        """Drop finished jobs from the queue view."""
        self._download_jobs = [
            job
            for job in self._download_jobs
            if job.state in ("waiting", "running")
        ]
        self._render_downloads()
        on_downloads = self.pages.currentWidget() is self.downloads_page
        if not self._download_jobs and on_downloads:
            # The sidebar button is gone now, so leave the empty page.
            self.switch_view("Bilder")

    def _get_pixmap(self, entry: MediaItem) -> QPixmap | None:
        """Return an entry's preview pixmap, cached by its media path.

        Synchronous variant for the detail dialog; the grid loads previews in
        the background through ``_start_thumbnail_load``.
        """
        key = entry.media_path
        if key not in self.thumbnail_cache:
            image = load_thumbnail(entry)
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
        worker = Worker(self, load_thumbnails, entries=missing)
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
        if self._download_active is not None or self._rule34_fetch is not None:
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
        # Reuse the object a background download may still be writing to.
        self.db = self._databases.get(self.config.db_path)
        if self.db is None:
            self.db = MediaDatabase(self.config.db_path)
            self.db.load()
            self._databases[self.config.db_path] = self.db

        self.thumbnail_cache.clear()
        self.recent_picks = []
        self._sync_ignored.clear()
        self.inp_search.blockSignals(True)
        self.inp_search.clear()
        self.inp_search.blockSignals(False)
        self._apply_selection(set())
        self._anchor_entry = None
        self._apply_config_ui()
        self.auto_scan_folder()
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
