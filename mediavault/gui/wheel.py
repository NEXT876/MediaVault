"""Wheel of fortune page: animated wheel plus a panel with entries and result.

:class:`WheelWidget` paints the wheel and runs the spin animation; the
winner is chosen up front and the end angle is computed so that slice lands
under the top pointer (:func:`target_angle`). :class:`WheelPage` adds the
editor (one entry per line), saved entry lists (:mod:`mediavault.wheel_configs`),
buttons to put the library's groups on the wheel, and the result card.
The page has nothing to do with media entries except reading group names.
"""

import math
import random
from collections.abc import Callable

from PyQt6.QtCore import (
    QEasingCurve,
    QLineF,
    QPointF,
    QPropertyAnimation,
    QRectF,
    QSize,
    Qt,
    QTimer,
    pyqtProperty,
    pyqtSignal,
)
from PyQt6.QtGui import (
    QColor,
    QFont,
    QFontMetricsF,
    QKeySequence,
    QMouseEvent,
    QPainter,
    QPainterPath,
    QPaintEvent,
    QPen,
    QPolygonF,
    QRadialGradient,
    QResizeEvent,
    QShortcut,
    QTransform,
)
from PyQt6.QtWidgets import (
    QComboBox,
    QFrame,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from mediavault.gui.dialogs import GroupPickDialog
from mediavault.gui.theme import WHEEL_SLICE_COLORS
from mediavault.gui.widgets import button
from mediavault.wheel_configs import (
    WHEEL_CONFIGS_PATH,
    load_wheel_configs,
    matching_config,
    save_wheel_configs,
)

DEMO_ENTRIES = ("Pizza", "Sushi", "Burger", "Pasta", "Salat", "Döner", "Ramen", "Curry")

_MARGIN = 26.0  # Platz für Zeiger und Schatten


def parse_entries(text: str) -> list[str]:
    """Return one stripped entry per non-empty line."""
    return [line.strip() for line in text.splitlines() if line.strip()]


def target_angle(current: float, index: int, count: int, turns: float) -> float:
    """Return the end angle that puts slice ``index`` under the top pointer.

    The wheel turns at least ``turns`` full rotations (but never fewer than
    3.2) past ``current`` so every spin feels like a real spin.

    Args:
        current: Current wheel angle in degrees.
        index: Index of the winning slice.
        count: Number of slices.
        turns: Desired number of full rotations.
    """
    slice_deg = 360.0 / count
    target_mod = (-(index * slice_deg + slice_deg / 2.0)) % 360.0
    target = current + turns * 360.0
    target += (target_mod - target) % 360.0
    if target - current < 3.2 * 360.0:
        target += 360.0
    return target


def _contrast_color(color: QColor) -> QColor:
    """Return near-black or white, whichever is readable on the given background."""
    luminance = 0.2126 * color.redF() + 0.7152 * color.greenF() + 0.0722 * color.blueF()
    return QColor("#11141c") if luminance > 0.52 else QColor("#ffffff")


def _alpha(color: str, alpha: int) -> QColor:
    """Return ``color`` with the given alpha channel."""
    result = QColor(color)
    result.setAlpha(alpha)
    return result


class WheelWidget(QWidget):
    """A wheel of fortune that fits its slices to the given entries.

    Slices and labels are cached as painter paths and only rotated through
    the painter transform while spinning, so the animation stays smooth. The
    cache is rebuilt when the size or the entries change. Long labels are
    elided; the font shrinks as the number of slices grows.

    Signals:
        spinRequested: The wheel was clicked; the page decides whether to spin.
        spinStarted: A spin animation started.
        spinFinished(str): The animation ended; carries the winning entry.
    """

    spinRequested = pyqtSignal()
    spinStarted = pyqtSignal()
    spinFinished = pyqtSignal(str)

    def __init__(self, colors: dict[str, str], parent: QWidget | None = None) -> None:
        """Create an empty wheel painted with the given theme palette.

        Args:
            colors: Theme palette from :meth:`ThemeManager.palette`.
            parent: Parent widget.
        """
        super().__init__(parent)
        self._colors = colors
        self._entries: list[str] = []
        self._fills: list[QColor] = []
        self._text_colors: list[QColor] = []
        self._slice_paths: list[QPainterPath] = []
        self._text_paths: list[QPainterPath] = []
        self._separators: list[QLineF] = []
        self._radius = 0.0

        self._angle = 0.0
        self._winning: int | None = None
        self._spinning = False
        self._pending_index: int | None = None
        self._pending_entries: list[str] | None = None
        self._cache_key: tuple[int, int, tuple[str, ...]] | None = None

        self._animation = QPropertyAnimation(self, b"wheelAngle", self)
        self._animation.setEasingCurve(QEasingCurve.Type.OutQuart)
        self._animation.finished.connect(self._on_spin_finished)

        self.setMinimumSize(360, 360)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    # --- API ---
    @property
    def entries(self) -> list[str]:
        """Return a copy of the entries currently shown on the wheel."""
        return list(self._entries)

    @property
    def is_spinning(self) -> bool:
        """Return True while a spin animation is running."""
        return self._spinning

    def set_colors(self, colors: dict[str, str]) -> None:
        """Repaint the wheel with a new theme palette."""
        self._colors = colors
        self.update()

    def set_entries(self, entries: list[str]) -> None:
        """Show new entries; during a spin they apply once it has finished.

        Blank entries are dropped. Deferring the change keeps the result consistent
        with the slices it was drawn on.
        """
        cleaned = [entry for entry in (str(e).strip() for e in entries) if entry]
        if cleaned == self._entries and self._pending_entries is None:
            return
        # Keep the running result consistent with the slices it was drawn on.
        if self._spinning:
            self._pending_entries = cleaned
            return
        self._entries = cleaned
        self._winning = None
        self._cache_key = None
        self.update()

    def spin(self) -> None:
        """Start a spin towards a random entry.

        Picks the winner uniformly, then animates to its angle for 3.9-5.3 s with
        an ease-out curve. Does nothing while spinning or without entries.
        """
        if self._spinning or not self._entries:
            return
        index = random.randrange(len(self._entries))
        current = self._angle
        target = target_angle(
            current, index, len(self._entries), random.uniform(4.2, 6.8)
        )

        self._pending_index = index
        self._winning = None
        self._spinning = True
        self.update()

        self._animation.stop()
        self._animation.setStartValue(current)
        self._animation.setEndValue(target)
        self._animation.setDuration(random.randint(3900, 5300))
        self._animation.start()
        self.spinStarted.emit()

    # --- Qt property driven by the animation ---
    def _get_angle(self) -> float:
        """Return the current rotation in degrees (``wheelAngle`` getter)."""
        return self._angle

    def _set_angle(self, value: float) -> None:
        """Set the rotation and repaint (``wheelAngle`` setter for the animation)."""
        self._angle = float(value)
        self.update()

    wheelAngle = pyqtProperty(float, fget=_get_angle, fset=_set_angle)

    # --- Events ---
    def sizeHint(self) -> QSize:
        """Prefer a roomy square."""
        return QSize(600, 600)

    def resizeEvent(self, event: QResizeEvent) -> None:
        """Rebuild the cached paths for the new size on the next paint."""
        self._cache_key = None
        super().resizeEvent(event)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        """Emit ``spinRequested`` on a left click when the wheel has entries."""
        if event.button() == Qt.MouseButton.LeftButton and self._entries:
            self.spinRequested.emit()
        super().mousePressEvent(event)

    def _on_spin_finished(self) -> None:
        """Finish a spin: report the winner, highlight it and apply deferred entries.

        When entries changed during the spin, the new entries replace the wheel
        and no slice is highlighted.
        """
        index = self._pending_index
        winner = ""
        if index is not None and 0 <= index < len(self._entries):
            winner = self._entries[index]

        # Keep the angle small; visually identical.
        self._angle %= 360.0
        self._spinning = False
        self._pending_index = None

        if self._pending_entries is not None:
            self._entries = self._pending_entries
            self._pending_entries = None
            self._winning = None
            self._cache_key = None
        else:
            self._winning = index

        self.update()
        self.spinFinished.emit(winner)

    # --- Painting ---
    def paintEvent(self, event: QPaintEvent) -> None:
        """Paint the wheel at its current angle, or the empty-state hint.

        Layers from bottom to top: shadow, slices, separators, depth shading, the
        winner highlight, labels, rim, hub and pointer.
        """
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)

        if not self._entries:
            self._paint_empty(painter)
            return

        key = (self.width(), self.height(), tuple(self._entries))
        if key != self._cache_key:
            self._build_cache()
            self._cache_key = key

        center = QPointF(self.width() / 2.0, self.height() / 2.0)
        radius = self._radius

        self._paint_shadow(painter, center, radius)

        painter.save()
        painter.translate(center)
        painter.rotate(self._angle)

        painter.setPen(Qt.PenStyle.NoPen)
        for path, color in zip(self._slice_paths, self._fills, strict=True):
            painter.setBrush(color)
            painter.drawPath(path)

        pen = QPen(_alpha(self._colors["bg"], 90), 1.4)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        for line in self._separators:
            painter.drawLine(line)

        # Subtle depth: slightly darker towards the rim.
        depth = QRadialGradient(QPointF(0.0, 0.0), radius)
        depth.setColorAt(0.0, QColor(255, 255, 255, 22))
        depth.setColorAt(0.50, QColor(255, 255, 255, 0))
        depth.setColorAt(0.86, QColor(5, 7, 12, 0))
        depth.setColorAt(1.0, QColor(5, 7, 12, 60))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(depth)
        painter.drawEllipse(QPointF(0.0, 0.0), radius, radius)

        if self._winning is not None and self._winning < len(self._slice_paths):
            painter.setBrush(QColor(255, 255, 255, 42))
            highlight = QPen(QColor(255, 255, 255, 220), 2.4)
            highlight.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            painter.setPen(highlight)
            painter.drawPath(self._slice_paths[self._winning])

        painter.setPen(Qt.PenStyle.NoPen)
        for text_path, color in zip(self._text_paths, self._text_colors, strict=True):
            painter.setBrush(color)
            painter.drawPath(text_path)

        painter.restore()

        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(QColor(self._colors["border_strong"]), 2.0))
        painter.drawEllipse(center, radius + 1.0, radius + 1.0)

        self._paint_hub(painter, center, radius)
        self._paint_pointer(painter, center, radius)

    def _paint_shadow(self, painter: QPainter, center: QPointF, radius: float) -> None:
        """Paint a soft ring shadow around the wheel, stronger on dark themes."""
        glow_radius = radius * 1.18
        strength = 90 if QColor(self._colors["bg"]).lightness() < 128 else 22
        glow = QRadialGradient(center, glow_radius)
        glow.setColorAt(0.0, QColor(0, 0, 0, 0))
        glow.setColorAt(0.76, QColor(0, 0, 0, 0))
        glow.setColorAt(0.84, QColor(0, 0, 0, strength))
        glow.setColorAt(1.0, QColor(0, 0, 0, 0))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(glow)
        painter.drawEllipse(center, glow_radius, glow_radius)

    def _paint_hub(self, painter: QPainter, center: QPointF, radius: float) -> None:
        """Paint the center hub with its accent ring and the "SPIN" label."""
        hub_radius = self._hub_radius(radius)
        colors = self._colors

        painter.setBrush(QColor(colors["surface"]))
        painter.setPen(QPen(QColor(colors["border_strong"]), 1.4))
        painter.drawEllipse(center, hub_radius, hub_radius)

        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(QColor(colors["primary"]), 2.0))
        painter.drawEllipse(center, hub_radius + 5.0, hub_radius + 5.0)

        font = QFont(self.font())
        font.setPixelSize(max(8, int(hub_radius * 0.32)))
        font.setWeight(QFont.Weight.Bold)
        painter.setFont(font)
        painter.setPen(QColor(colors["text_muted"]))
        painter.drawText(
            QRectF(
                center.x() - hub_radius,
                center.y() - hub_radius,
                hub_radius * 2,
                hub_radius * 2,
            ),
            Qt.AlignmentFlag.AlignCenter,
            "SPIN",
        )

    def _paint_pointer(self, painter: QPainter, center: QPointF, radius: float) -> None:
        """Paint the triangular pointer at the top that marks the winner."""
        half_width = max(9.0, radius * 0.045)
        base_y = center.y() - radius - 18.0
        tip_y = center.y() - radius + 10.0
        polygon = QPolygonF(
            [
                QPointF(center.x(), tip_y),
                QPointF(center.x() - half_width, base_y),
                QPointF(center.x() + half_width, base_y),
            ]
        )
        pen = QPen(QColor(self._colors["surface"]), 1.6)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)
        painter.setBrush(QColor(self._colors["text"]))
        painter.drawPolygon(polygon)

    def _paint_empty(self, painter: QPainter) -> None:
        """Paint a dashed placeholder circle with a hint when there are no entries."""
        colors = self._colors
        center_x = self.width() / 2.0
        center_y = self.height() / 2.0
        radius = max(40.0, min(self.width(), self.height()) / 2.0 - _MARGIN)

        painter.setBrush(QColor(colors["surface"]))
        painter.setPen(QPen(QColor(colors["border_strong"]), 2.0, Qt.PenStyle.DashLine))
        painter.drawEllipse(QPointF(center_x, center_y), radius, radius)

        title_font = QFont(self.font())
        title_font.setPixelSize(18)
        title_font.setWeight(QFont.Weight.DemiBold)
        painter.setFont(title_font)
        painter.setPen(QColor(colors["text"]))
        painter.drawText(
            QRectF(center_x - radius, center_y - 28, radius * 2, 24),
            Qt.AlignmentFlag.AlignCenter,
            "Noch keine Einträge",
        )

        hint_font = QFont(self.font())
        hint_font.setPixelSize(12)
        painter.setFont(hint_font)
        painter.setPen(QColor(colors["text_muted"]))
        painter.drawText(
            QRectF(center_x - radius, center_y + 2, radius * 2, 22),
            Qt.AlignmentFlag.AlignCenter,
            "Rechts einen Eintrag pro Zeile schreiben",
        )

    # --- Geometry ---
    @staticmethod
    def _hub_radius(radius: float) -> float:
        """Return the hub radius for a wheel radius (15 %, at least 26 px)."""
        return max(26.0, radius * 0.15)

    @staticmethod
    def _font_pixel_size(count: int, radius: float) -> int:
        """Return the label font size: smaller for many slices, scaled by radius."""
        for limit, size in ((6, 18.0), (10, 16.0), (16, 14.0), (24, 12.0), (36, 10.5)):
            if count <= limit:
                base = size
                break
        else:
            base = 9.0
        scale = min(1.5, max(0.86, radius / 300.0))
        return max(8, round(base * scale))

    def _build_cache(self) -> None:
        """Rebuild slice and label paths for the current size.

        Slices start at 12 o'clock and go clockwise. Neighboring slices never share
        a color, also across the seam. Labels run radially from the rim inwards and
        are mirrored on the left half so none is upside down.
        """
        count = len(self._entries)
        radius = max(40.0, min(self.width(), self.height()) / 2.0 - _MARGIN)
        self._radius = radius

        slice_deg = 360.0 / count
        circle_rect = QRectF(-radius, -radius, radius * 2.0, radius * 2.0)

        font = QFont(self.font())
        font.setPixelSize(self._font_pixel_size(count, radius))
        font.setWeight(QFont.Weight.DemiBold)
        metrics = QFontMetricsF(font)

        # Labels use the full radial width from the hub outwards.
        text_start = self._hub_radius(radius) + 16.0
        max_text_width = max(20.0, radius - 18.0 - text_start)
        baseline_shift = (metrics.ascent() - metrics.descent()) / 2.0

        self._slice_paths = []
        self._text_paths = []
        self._fills = []
        self._text_colors = []
        self._separators = []

        for index, entry in enumerate(self._entries):
            wedge = QPainterPath()
            wedge.moveTo(0.0, 0.0)
            # Qt angles: 0° is 3 o'clock, positive is counter-clockwise.
            wedge.arcTo(circle_rect, 90.0 - index * slice_deg, -slice_deg)
            wedge.closeSubpath()
            self._slice_paths.append(wedge)

            color_index = index % len(WHEEL_SLICE_COLORS)
            # Avoid two neighbouring slices with the same color at the seam.
            if index == count - 1 and color_index == 0 and count > 1:
                color_index = 1
            fill = QColor(WHEEL_SLICE_COLORS[color_index])
            self._fills.append(fill)
            self._text_colors.append(_contrast_color(fill))

            label = metrics.elidedText(
                entry, Qt.TextElideMode.ElideRight, max_text_width
            )
            text_width = metrics.horizontalAdvance(label)
            text_path = QPainterPath()
            text_path.addText(0.0, 0.0, font, label)

            # Radial labels; mirrored on the left half so none are upside down.
            mid_angle = (index + 0.5) * slice_deg
            transform = QTransform()
            if 90.0 < mid_angle <= 270.0:
                transform.rotate(mid_angle + 90.0)
                transform.translate(-(radius - 18.0), baseline_shift)
            else:
                transform.rotate(mid_angle - 90.0)
                transform.translate(radius - 18.0 - text_width, baseline_shift)
            self._text_paths.append(transform.map(text_path))

            angle = math.radians(index * slice_deg)
            self._separators.append(
                QLineF(0.0, 0.0, radius * math.sin(angle), -radius * math.cos(angle))
            )


class WheelPage(QWidget):
    """Wheel on the left, entry editor and result card on the right.

    Typing in the editor updates the wheel after a 120 ms debounce. While the
    wheel spins, every control that could replace the entries is locked.
    Before entries are replaced (applying a config, loading groups), unsaved
    entries trigger a warning with the option to save them first.
    """

    def __init__(
        self,
        colors: dict[str, str],
        group_provider: Callable[[], list[str]],
        configs_path: str = WHEEL_CONFIGS_PATH,
        parent: QWidget | None = None,
    ) -> None:
        """Build the page and fill the wheel with demo entries.

        Args:
            colors: Theme palette for the wheel.
            group_provider: Returns the group names of the active library; it is
                called on every use so a switched library is picked up.
            configs_path: File for saved entry lists (tests pass their own).
            parent: Parent widget.
        """
        super().__init__(parent)
        self._group_provider = group_provider
        self._configs_path = configs_path
        self._configs = load_wheel_configs(configs_path)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 4, 0, 0)
        layout.setSpacing(24)

        self.wheel = WheelWidget(colors)
        layout.addWidget(self.wheel, 1)
        layout.addWidget(self._build_panel(), 0)

        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(120)
        self._debounce.timeout.connect(self._apply_entries)

        self.editor.textChanged.connect(self._debounce.start)
        self.clear_button.clicked.connect(self.editor.clear)
        self.apply_button.clicked.connect(self.apply_config)
        self.save_button.clicked.connect(self.save_config)
        self.delete_button.clicked.connect(self.delete_config)
        self.all_groups_button.clicked.connect(self.load_all_groups)
        self.pick_groups_button.clicked.connect(self.pick_groups)
        self.spin_button.clicked.connect(self.spin)
        self.wheel.spinRequested.connect(self.spin)
        self.wheel.spinStarted.connect(self._on_spin_started)
        self.wheel.spinFinished.connect(self._on_spin_finished)
        self._refresh_config_combo()
        shortcut = QShortcut(QKeySequence("Ctrl+Return"), self)
        shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        shortcut.activated.connect(self.spin)

        self.editor.setPlainText("\n".join(DEMO_ENTRIES))
        self._apply_entries()

    def _build_panel(self) -> QFrame:
        """Build the right-hand panel.

        Contains the config row, the group buttons, the editor, the result card
        and the spin button.
        """
        panel = QFrame()
        panel.setObjectName("WheelPanel")
        panel.setFixedWidth(340)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(0)

        header = QHBoxLayout()
        header.setSpacing(8)
        section = QLabel("EINTRÄGE")
        section.setObjectName("FieldLabel")
        header.addWidget(section)
        header.addStretch(1)
        self.clear_button = button(
            "Leeren",
            "ghost",
            tooltip="Alle Einträge entfernen",
            cursor=True,
        )
        header.addWidget(self.clear_button)
        layout.addLayout(header)
        layout.addSpacing(8)

        self.combo_config = QComboBox()
        layout.addWidget(self.combo_config)
        layout.addSpacing(6)
        config_row = QHBoxLayout()
        config_row.setSpacing(6)
        self.apply_button = self._small_button("Anwenden", "Gewählte Config laden")
        self.save_button = self._small_button(
            "Speichern", "Aktuelle Einträge als Config speichern"
        )
        self.delete_button = self._small_button("Löschen", "Gewählte Config löschen")
        for btn in (self.apply_button, self.save_button, self.delete_button):
            config_row.addWidget(btn)
        layout.addLayout(config_row)
        layout.addSpacing(6)
        group_row = QHBoxLayout()
        group_row.setSpacing(6)
        self.all_groups_button = self._small_button(
            "Alle Gruppen", "Alle Gruppen der Bibliothek aufs Rad legen"
        )
        self.pick_groups_button = self._small_button(
            "Gruppen wählen …", "Ausgewählte Gruppen aufs Rad legen"
        )
        group_row.addWidget(self.all_groups_button)
        group_row.addWidget(self.pick_groups_button)
        layout.addLayout(group_row)
        layout.addSpacing(10)

        self.editor = QPlainTextEdit()
        self.editor.setPlaceholderText("Ein Eintrag pro Zeile …")
        self.editor.setTabChangesFocus(True)
        self.editor.setMinimumHeight(180)
        layout.addWidget(self.editor, 1)
        layout.addSpacing(8)

        info_row = QHBoxLayout()
        self.count_label = QLabel()
        self.count_label.setObjectName("HintLabel")
        info_row.addWidget(self.count_label)
        info_row.addStretch(1)
        hint = QLabel("Strg + Enter zum Drehen")
        hint.setObjectName("HintLabel")
        info_row.addWidget(hint)
        layout.addLayout(info_row)
        layout.addSpacing(16)

        result_card = QFrame()
        result_card.setObjectName("WheelResult")
        result_layout = QVBoxLayout(result_card)
        result_layout.setContentsMargins(16, 14, 16, 16)
        result_layout.setSpacing(6)
        caption = QLabel("ERGEBNIS")
        caption.setObjectName("FieldLabel")
        caption.setAlignment(Qt.AlignmentFlag.AlignCenter)
        result_layout.addWidget(caption)

        self.winner_label = QLabel("Bereit zum Drehen")
        self.winner_label.setObjectName("WheelWinner")
        self.winner_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.winner_label.setWordWrap(True)
        self.winner_label.setMinimumHeight(30)
        result_layout.addWidget(self.winner_label)

        self._winner_effect = QGraphicsOpacityEffect(self.winner_label)
        self._winner_effect.setOpacity(1.0)
        self.winner_label.setGraphicsEffect(self._winner_effect)
        self._winner_fade = QPropertyAnimation(self._winner_effect, b"opacity", self)
        self._winner_fade.setDuration(420)
        self._winner_fade.setEasingCurve(QEasingCurve.Type.OutCubic)

        layout.addWidget(result_card)
        layout.addSpacing(14)

        self.spin_button = button("Drehen", "primary", cursor=True)
        self.spin_button.setFixedHeight(44)
        layout.addWidget(self.spin_button)
        return panel

    @staticmethod
    def _small_button(text: str, tooltip: str) -> QPushButton:
        """Create a secondary button with a tooltip for the config and group rows."""
        return button(text, "secondary", tooltip=tooltip, cursor=True)

    # --- Configs ---
    def _current_entries(self) -> list[str]:
        """Return the entries currently typed in the editor."""
        return parse_entries(self.editor.toPlainText())

    def _refresh_config_combo(self, select: str | None = None) -> None:
        """Fill the combo from the saved configs and select ``select``.

        Without saved configs, apply/delete are disabled and a placeholder is shown.
        """
        self.combo_config.clear()
        for name in sorted(self._configs, key=str.casefold):
            self.combo_config.addItem(name, name)
        if select is not None:
            self.combo_config.setCurrentIndex(
                max(0, self.combo_config.findData(select))
            )
        has_configs = bool(self._configs)
        self.apply_button.setEnabled(has_configs)
        self.delete_button.setEnabled(has_configs)
        self.combo_config.setEnabled(has_configs)
        if not has_configs:
            self.combo_config.addItem("– keine Configs gespeichert –")

    def _persist_configs(self) -> bool:
        """Write the configs to disk; show a warning and return False on failure."""
        try:
            save_wheel_configs(self._configs, self._configs_path)
        except OSError as error:
            QMessageBox.warning(self, "Speichern fehlgeschlagen", str(error))
            return False
        return True

    def save_config(self) -> bool:
        """Ask for a name and store the current entries.

        Suggests the name of an identical saved config or the selected one, and
        asks before overwriting a config with different entries.

        Returns:
            True when the entries were saved.
        """
        entries = self._current_entries()
        if not entries:
            QMessageBox.information(
                self, "Hinweis", "Es sind keine Einträge vorhanden."
            )
            return False
        suggestion = matching_config(self._configs, entries) or str(
            self.combo_config.currentData() or ""
        )
        name, ok = QInputDialog.getText(
            self, "Config speichern", "Name der Config:", text=suggestion
        )
        name = name.strip()
        if not ok or not name:
            return False
        if name in self._configs and self._configs[name] != entries:
            answer = QMessageBox.question(
                self,
                "Config überschreiben?",
                f"Die Config „{name}“ existiert bereits und wird überschrieben.",
            )
            if answer != QMessageBox.StandardButton.Yes:
                return False
        self._configs[name] = entries
        if not self._persist_configs():
            return False
        self._refresh_config_combo(select=name)
        return True

    def apply_config(self) -> None:
        """Load the selected config into the editor after :meth:`confirm_overwrite`."""
        name = self.combo_config.currentData()
        if name in self._configs and self.confirm_overwrite():
            self.editor.setPlainText("\n".join(self._configs[name]))

    def delete_config(self) -> None:
        """Delete the selected config after asking."""
        name = self.combo_config.currentData()
        if name not in self._configs:
            return
        answer = QMessageBox.question(
            self, "Config löschen?", f"Die Config „{name}“ wirklich löschen?"
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        del self._configs[name]
        if self._persist_configs():
            self._refresh_config_combo()

    def confirm_overwrite(self) -> bool:
        """Return True when the current entries may be replaced.

        Entries that match a saved config (or an empty list) are replaced
        without asking; otherwise the user may overwrite, save first or abort.
        """
        entries = self._current_entries()
        if not entries or matching_config(self._configs, entries) is not None:
            return True
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Warning)
        box.setWindowTitle("Nicht gespeicherte Einträge")
        box.setText(
            f"Die aktuellen {len(entries)} Einträge sind nicht als Config "
            "gespeichert und gehen beim Überschreiben verloren."
        )
        overwrite = box.addButton(
            "Überschreiben", QMessageBox.ButtonRole.DestructiveRole
        )
        save_first = box.addButton(
            "Erst speichern …", QMessageBox.ButtonRole.AcceptRole
        )
        box.addButton("Abbrechen", QMessageBox.ButtonRole.RejectRole)
        box.exec()
        clicked = box.clickedButton()
        if clicked is overwrite:
            return True
        return clicked is save_first and self.save_config()

    # --- Groups ---
    def load_all_groups(self) -> None:
        """Put every group of the active library on the wheel."""
        self._load_groups(list(self._group_provider()))

    def pick_groups(self) -> None:
        """Let the user choose groups in a dialog and put them on the wheel."""
        groups = list(self._group_provider())
        if not groups:
            return self._load_groups(groups)
        dialog = GroupPickDialog(self, groups)
        if dialog.exec():
            self._load_groups(dialog.selected_groups)

    def _load_groups(self, groups: list[str]) -> None:
        """Put groups on the wheel after confirmation; say so when there are none."""
        if not groups:
            QMessageBox.information(
                self, "Hinweis", "In dieser Bibliothek gibt es keine Gruppen."
            )
            return
        if self.confirm_overwrite():
            self.editor.setPlainText("\n".join(groups))

    def apply_theme(self, colors: dict[str, str]) -> None:
        """Repaint the wheel after the global theme changed."""
        self.wheel.set_colors(colors)

    def spin(self) -> None:
        """Spin the wheel unless it is empty or already spinning.

        Text typed within the debounce delay is applied to the wheel first.
        """
        # Text typed within the debounce delay must be on the wheel first.
        if self._debounce.isActive():
            self._debounce.stop()
            self._apply_entries()
        self.wheel.spin()

    def _apply_entries(self) -> None:
        """Push the editor's entries to the wheel; update count and spin button."""
        entries = parse_entries(self.editor.toPlainText())
        self.wheel.set_entries(entries)
        count = len(entries)
        self.count_label.setText("1 Eintrag" if count == 1 else f"{count} Einträge")
        self.spin_button.setEnabled(count > 0 and not self.wheel.is_spinning)

    def _on_spin_started(self) -> None:
        """Lock editing and show the spinning state in the button and result card."""
        self._set_editing_enabled(False)
        self.spin_button.setEnabled(False)
        self.spin_button.setText("Dreht …")
        self.winner_label.setText("…")
        self._winner_effect.setOpacity(1.0)

    def _set_editing_enabled(self, enabled: bool) -> None:
        """Lock the controls that replace entries while the wheel turns."""
        for btn in (
            self.apply_button,
            self.save_button,
            self.delete_button,
            self.all_groups_button,
            self.pick_groups_button,
            self.clear_button,
        ):
            btn.setEnabled(enabled)
        self.editor.setReadOnly(not enabled)
        if enabled:
            self._refresh_config_combo(select=self.combo_config.currentData())

    def _on_spin_finished(self, winner: str) -> None:
        """Unlock editing and fade in the winner in the result card."""
        self._set_editing_enabled(True)
        self.spin_button.setText("Drehen")
        self.spin_button.setEnabled(bool(self.wheel.entries))
        self.winner_label.setText(winner or "Kein Ergebnis")
        self._winner_fade.stop()
        self._winner_fade.setStartValue(0.0)
        self._winner_fade.setEndValue(1.0)
        self._winner_fade.start()
