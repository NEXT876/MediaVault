"""Tests for the rubber-band selection helper."""

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QPoint  # noqa: E402
from PyQt6.QtWidgets import QApplication, QScrollArea, QWidget  # noqa: E402

from mediavault.gui.selection import RubberBandSelector  # noqa: E402
from mediavault.models import MediaItem  # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


class _Card(QWidget):
    def __init__(self, parent, entry, x, y):
        super().__init__(parent)
        self.entry = entry
        self.setGeometry(x, y, 50, 50)


def _grid(app):
    area = QScrollArea()
    area.resize(400, 400)
    content = QWidget()
    content.resize(380, 380)
    area.setWidget(content)
    first, second = MediaItem("a"), MediaItem("b")
    cards = [_Card(content, first, 10, 10), _Card(content, second, 200, 200)]
    area.show()
    app.processEvents()
    return area, cards, first, second


def test_drag_selects_touched_cards_on_top_of_base(app):
    area, cards, first, second = _grid(app)
    applied = []
    selector = RubberBandSelector(area, lambda: cards, applied.append)
    viewport = area.viewport()
    keep = MediaItem("kept")

    selector.press(viewport.mapToGlobal(QPoint(0, 0)), {keep})
    selector.move(viewport.mapToGlobal(QPoint(80, 80)))

    assert selector.active
    assert applied[-1] == {keep, first}

    selector.move(viewport.mapToGlobal(QPoint(260, 260)))
    assert applied[-1] == {keep, first, second}

    selector.cancel()
    assert not selector.active


def test_move_without_press_does_nothing(app):
    area, cards, _first, _second = _grid(app)
    applied = []
    selector = RubberBandSelector(area, lambda: cards, applied.append)

    selector.move(area.viewport().mapToGlobal(QPoint(80, 80)))

    assert applied == []
