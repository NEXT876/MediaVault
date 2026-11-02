"""Rubber-band selection with edge auto-scrolling for the card grid."""

from collections.abc import Callable, Iterable

from PyQt6.QtCore import QObject, QPoint, QRect, Qt, QTimer
from PyQt6.QtWidgets import QRubberBand, QScrollArea, QWidget

from mediavault.models import MediaItem


class RubberBandSelector(QObject):
    """Track a drag over the grid and select the cards it touches.

    The window keeps ownership of the selection itself; this class only turns
    pointer positions into "base selection plus touched cards" and calls
    ``apply`` with the result.
    """

    AUTOSCROLL_MARGIN = 24
    AUTOSCROLL_STEP = 28

    def __init__(
        self,
        scroll_area: QScrollArea,
        cards: Callable[[], Iterable[QWidget]],
        apply: Callable[[set[MediaItem]], None],
    ) -> None:
        """Bind to the grid's scroll area, its cards and the selection setter."""
        super().__init__(scroll_area)
        self._scroll_area = scroll_area
        self._cards = cards
        self._apply = apply
        self._base: set[MediaItem] = set()
        self._origin: QPoint | None = None
        self._last: QPoint | None = None
        self._band: QRubberBand | None = None
        self._direction = 0
        self._timer = QTimer(self)
        self._timer.setInterval(40)
        self._timer.timeout.connect(self._autoscroll_step)

    @property
    def active(self) -> bool:
        """Return True while a drag is in progress."""
        return self._origin is not None

    def press(self, global_pos: QPoint, selected: Iterable[MediaItem]) -> None:
        """Start a drag on top of the current selection."""
        self._base = set(selected)
        self._origin = global_pos
        self._last = global_pos

    def move(self, global_pos: QPoint) -> None:
        """Draw the selection rectangle and select the cards it touches."""
        if self._origin is None:
            return
        self._last = global_pos
        viewport = self._scroll_area.viewport()
        origin = viewport.mapFromGlobal(self._origin)
        current = viewport.mapFromGlobal(global_pos)
        rect = QRect(origin, current).normalized().intersected(viewport.rect())

        band = self._ensure_band()
        band.setGeometry(rect)
        if not band.isVisible():
            band.show()
        band.raise_()

        self._apply(self._base | self.cards_intersecting(rect))
        self._update_autoscroll(current)

    def cancel(self) -> None:
        """Hide the selection rectangle and stop auto-scrolling."""
        self._timer.stop()
        self._direction = 0
        self._origin = None
        self._last = None
        self._base = set()
        if self._band is not None:
            self._band.hide()
            self._band.setGeometry(QRect())

    def cards_intersecting(self, rect: QRect) -> set[MediaItem]:
        """Return the entries of all cards intersecting rect (viewport coords)."""
        viewport = self._scroll_area.viewport()
        hits: set[MediaItem] = set()
        for card in self._cards():
            top_left = card.mapTo(viewport, QPoint(0, 0))
            if rect.intersects(QRect(top_left, card.size())):
                hits.add(card.entry)
        return hits

    def _ensure_band(self) -> QRubberBand:
        """Create the selection rectangle on first use."""
        if self._band is None:
            self._band = QRubberBand(
                QRubberBand.Shape.Rectangle, self._scroll_area.viewport()
            )
            self._band.setAttribute(
                Qt.WidgetAttribute.WA_TransparentForMouseEvents, True
            )
        return self._band

    def _update_autoscroll(self, pos_in_viewport: QPoint) -> None:
        """Start or stop scrolling at the top or bottom edge."""
        viewport = self._scroll_area.viewport()
        y, margin = pos_in_viewport.y(), self.AUTOSCROLL_MARGIN
        direction = -1 if y < margin else 1 if y > viewport.height() - margin else 0
        self._direction = direction
        if direction and not self._timer.isActive():
            self._timer.start()
        elif not direction:
            self._timer.stop()

    def _autoscroll_step(self) -> None:
        """Advance the scroll position while a drag is active."""
        if not self._direction or self._last is None:
            self._timer.stop()
            return
        bar = self._scroll_area.verticalScrollBar()
        before = bar.value()
        bar.setValue(before + self._direction * self.AUTOSCROLL_STEP)
        if bar.value() == before:
            self._timer.stop()
            return
        self.move(self._last)
