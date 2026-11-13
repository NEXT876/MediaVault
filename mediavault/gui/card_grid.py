"""Scrollable card grid: layout, selection and background preview loading.

:class:`CardGrid` is the central view of the images and videos pages. It
shows one :class:`MediaCard` per entry in a responsive grid (the column count
follows the viewport width), owns the multi-selection (click toggles,
Shift+click selects a range, dragging draws a rubber band via
:class:`RubberBandSelector`) and loads previews in a background
:class:`Worker` so scrolling never waits for disk or video decoding.
"""

import logging
from collections.abc import Iterable

from PyQt6.QtCore import QEvent, QObject, QPoint, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QPixmap, QResizeEvent
from PyQt6.QtWidgets import QGridLayout, QLabel, QScrollArea, QWidget

from mediavault.gui.selection import RubberBandSelector
from mediavault.gui.thumbnails import load_thumbnail, load_thumbnails
from mediavault.gui.widgets import CARD_WIDTH, MediaCard
from mediavault.gui.worker import Worker
from mediavault.models import MediaItem

logger = logging.getLogger(__name__)

_SPINNER_FRAMES = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"


class LoadingLabel(QLabel):
    """Animated "loading previews" hint.

    Shows a braille spinner next to "Lade Vorschauen …" while
    :meth:`set_running` is True.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        """Create the hidden label and its animation timer."""
        super().__init__(parent)
        self.setObjectName("HintLabel")
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.hide()
        self._frame = 0
        self._timer = QTimer(self)
        self._timer.setInterval(90)
        self._timer.timeout.connect(self._spin)

    def set_running(self, running: bool) -> None:
        """Show and animate the label, or hide it."""
        self.setVisible(running)
        if running:
            self._spin()
            self._timer.start()
        else:
            self._timer.stop()

    def _spin(self) -> None:
        """Advance the spinner animation by one frame."""
        self._frame = (self._frame + 1) % len(_SPINNER_FRAMES)
        self.setText(f"{_SPINNER_FRAMES[self._frame]}  Lade Vorschauen …")


class CardGrid(QScrollArea):
    """Show entries as cards and own their selection and preview cache.

    Previews are cached in memory by media path; ``None`` marks a preview that
    could not be built, so it is not retried until :meth:`forget_missing` is
    called. At most one preview worker runs at a time; entries added while it
    runs are loaded by a follow-up worker.

    Signals:
        selection_changed: The selection changed (action bar updates).
        open_requested(MediaItem): A card was double-clicked.
        loading_changed(bool): Preview loading started or finished.

    Attributes:
        cards: Card widgets in grid order.
        selected: Currently selected entries.
    """

    GRID_SPACING = 12
    SCROLLBAR_RESERVE = 12

    selection_changed = pyqtSignal()
    open_requested = pyqtSignal(object)
    loading_changed = pyqtSignal(bool)

    def __init__(self, parent: QWidget | None = None) -> None:
        """Build the empty grid and the rubber-band selector."""
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setObjectName("CardScroll")
        container = QWidget()
        container.setObjectName("GridContainer")
        self._layout = QGridLayout(container)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(self.GRID_SPACING)
        self._layout.setAlignment(
            Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft
        )
        self.setWidget(container)
        self.viewport().setObjectName("GridViewport")
        self.viewport().installEventFilter(self)

        self.cards: list[MediaCard] = []
        self.selected: set[MediaItem] = set()
        self._cols = 1
        self._anchor: MediaItem | None = None
        # Selection before the last press, so a double click or Esc can undo it.
        self._press_snapshot: set[MediaItem] = set()
        self._rubber = RubberBandSelector(self, lambda: self.cards, self.set_selection)

        self._pixmaps: dict[str, QPixmap | None] = {}
        self._thumb_worker: Worker | None = None
        # Library (root, scope) the running preview worker loads for.
        self._thumb_library = ("", "")
        self._root = ""
        self._scope = ""

    # --- Content ---
    @property
    def entries(self) -> list[MediaItem]:
        """Return the entries of the visible cards in grid order."""
        return [card.entry for card in self.cards]

    @property
    def is_loading(self) -> bool:
        """Return True while previews load in the background."""
        return self._thumb_worker is not None

    def show_entries(self, entries: Iterable[MediaItem], root: str, scope: str) -> None:
        """Replace the cards, keep the still visible selection and load previews.

        Args:
            entries: Entries to show, already filtered and sorted.
            root: Volume root to resolve relative paths.
            scope: Library identity for the disk cache (the config's volume UUID).
        """
        self.cancel_drag()
        self._root, self._scope = root, scope
        for card in self.cards:
            card.hide()
            card.setParent(None)
            card.deleteLater()
        self.cards = [self._make_card(entry) for entry in entries]

        visible = set(self.entries)
        if self._anchor not in visible:
            self._anchor = None
        self._update_columns(force=True)
        self.set_selection(self.selected & visible)
        self._start_thumbnail_load()

    def _make_card(self, entry: MediaItem) -> MediaCard:
        """Create one card with its cached preview, wired to the selection."""
        card = MediaCard(entry, self._pixmaps.get(entry.media_path))
        card.clicked.connect(self._on_card_clicked)
        card.double_clicked.connect(self._on_card_double_clicked)
        card.drag_pressed.connect(self._on_drag_pressed)
        card.drag_moved.connect(self._rubber.move)
        card.drag_finished.connect(self.cancel_drag)
        return card

    # --- Layout ---
    def resizeEvent(self, event: QResizeEvent) -> None:
        """Recalculate the column count when the grid is resized."""
        super().resizeEvent(event)
        self._update_columns()

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:
        """Recalculate the column count when the scroll viewport changes width."""
        if obj is self.viewport() and event.type() == QEvent.Type.Resize:
            self._update_columns()
        return super().eventFilter(obj, event)

    def _update_columns(self, force: bool = False) -> None:
        """Compute the column count from the viewport width and re-lay the cards.

        Cards are only moved when the count changed, unless ``force`` is set.
        """
        available = self.viewport().width() - self.SCROLLBAR_RESERVE
        cols = max(
            1, (available + self.GRID_SPACING) // (CARD_WIDTH + self.GRID_SPACING)
        )
        if cols == self._cols and not force:
            return
        self._cols = cols
        while self._layout.count():
            self._layout.takeAt(0)
        for index, card in enumerate(self.cards):
            row, col = divmod(index, cols)
            self._layout.addWidget(card, row, col)

    # --- Selection ---
    def set_selection(self, entries: Iterable[MediaItem]) -> None:
        """Replace the selection, update the highlights, emit ``selection_changed``."""
        self.selected = set(entries)
        for card in self.cards:
            card.set_selected(card.entry in self.selected)
        self.selection_changed.emit()

    def select_all(self) -> None:
        """Select every visible card."""
        self.set_selection(self.entries)

    def clear_selection(self) -> None:
        """Cancel a drag and clear the selection."""
        self.cancel_drag()
        self.set_selection(set())

    def reset_selection(self) -> None:
        """Clear the selection and forget the Shift+click anchor."""
        self.clear_selection()
        self._anchor = None

    def escape(self) -> None:
        """Abort a drag and restore the previous selection, else clear it."""
        if self._rubber.active:
            self.cancel_drag()
            self.set_selection(self._press_snapshot)
        else:
            self.clear_selection()

    def cancel_drag(self) -> None:
        """Hide the selection rectangle and stop auto-scrolling."""
        self._rubber.cancel()

    def _on_card_clicked(
        self, entry: MediaItem, modifiers: Qt.KeyboardModifier
    ) -> None:
        """Toggle a card, or select a range from the last clicked card with Shift.

        Remembers the selection before the click, so a following double click can
        fully undo the toggle caused by its first click.
        """
        # Snapshot before changing anything: a following double click can then
        # fully undo the toggle caused by the first click.
        self._press_snapshot = set(self.selected)
        entries = self.entries
        shift = modifiers & Qt.KeyboardModifier.ShiftModifier
        if shift and self._anchor in entries and entry in entries:
            lo, hi = sorted((entries.index(self._anchor), entries.index(entry)))
            self.set_selection(self.selected | set(entries[lo : hi + 1]))
            return
        self.set_selection(self.selected ^ {entry})
        self._anchor = entry

    def _on_card_double_clicked(self, entry: MediaItem) -> None:
        """Undo the first click's toggle and ask to open the entry."""
        self.cancel_drag()
        self.set_selection(self._press_snapshot)
        self.open_requested.emit(entry)

    def _on_drag_pressed(self, _entry: MediaItem, global_pos: QPoint) -> None:
        """Remember the selection and start a rubber-band drag on top of it."""
        self._press_snapshot = set(self.selected)
        self._rubber.press(global_pos, self.selected)

    # --- Previews ---
    def pixmap(self, entry: MediaItem) -> QPixmap | None:
        """Return an entry's preview, loading it synchronously if needed.

        Used by the detail dialog, which needs the preview right away.

        Returns:
            The preview, or None if it cannot be built.
        """
        key = entry.media_path
        if key not in self._pixmaps:
            image = load_thumbnail(entry, self._root, self._scope)
            self._pixmaps[key] = QPixmap.fromImage(image) if image is not None else None
        return self._pixmaps[key]

    def forget(self, entries: Iterable[MediaItem]) -> None:
        """Drop the cached previews of entries whose files changed."""
        for entry in entries:
            self._pixmaps.pop(entry.media_path, None)

    def forget_all(self) -> None:
        """Drop every cached preview, for example after a library switch."""
        self._pixmaps.clear()

    def forget_missing(self) -> None:
        """Retry previews that failed, for example after a volume came back."""
        self._pixmaps = {k: v for k, v in self._pixmaps.items() if v is not None}

    def wait_for_previews(self, msecs: int) -> bool:
        """Wait up to ``msecs`` for the preview worker, e.g. before closing.

        Returns:
            True when no worker is running anymore.
        """
        worker = self._thumb_worker
        if worker is not None and not worker.wait(msecs):
            return False
        self._thumb_worker = None
        return True

    def _start_thumbnail_load(self) -> None:
        """Load missing previews of the visible cards in a background worker."""
        if self._thumb_worker is not None:
            return
        missing = [e for e in self.entries if e.media_path not in self._pixmaps]
        if not missing:
            return
        worker = Worker(
            self, load_thumbnails, entries=missing, root=self._root, scope=self._scope
        )
        self._thumb_library = (self._root, self._scope)
        worker.finished.connect(self._finish_thumbnail_load)
        self._thumb_worker = worker
        self.loading_changed.emit(True)
        worker.start()

    def _finish_thumbnail_load(self) -> None:
        """Publish the loaded previews to the cards and load what is still missing.

        Results are discarded when the library changed while the worker ran,
        because the same relative path then names another file.
        """
        worker = self._thumb_worker
        self._thumb_worker = None
        if worker is None:
            return
        worker.deleteLater()
        if worker.error is not None:
            logger.debug("Previews not loaded", exc_info=worker.error)
        elif self._thumb_library != (self._root, self._scope):
            # Loaded for another library: the same relative path is another file.
            self._start_thumbnail_load()
        else:
            for path, image in worker.result.items():
                self._pixmaps[path] = (
                    QPixmap.fromImage(image) if image is not None else None
                )
            for card in self.cards:
                pixmap = self._pixmaps.get(card.entry.media_path)
                if pixmap is not None:
                    card.set_pixmap(pixmap)
            # A refresh during loading may have added entries the worker missed.
            self._start_thumbnail_load()
        self.loading_changed.emit(self.is_loading)
