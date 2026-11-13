"""Tests for selection handling in the card grid."""

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import Qt  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402

from mediavault.gui.card_grid import CardGrid  # noqa: E402
from mediavault.models import MediaItem  # noqa: E402

NONE = Qt.KeyboardModifier.NoModifier
SHIFT = Qt.KeyboardModifier.ShiftModifier


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def grid(app):
    # Entries without files: preview loading finds nothing and stays harmless.
    grid = CardGrid()
    entries = [MediaItem(name) for name in "abcde"]
    grid.show_entries(entries, root="", scope="")
    yield grid, entries
    grid.wait_for_previews(2000)


def test_click_toggles_and_shift_click_selects_a_range(grid):
    grid, entries = grid
    grid._on_card_clicked(entries[1], NONE)
    grid._on_card_clicked(entries[3], SHIFT)
    assert grid.selected == set(entries[1:4])

    grid._on_card_clicked(entries[2], NONE)
    assert grid.selected == {entries[1], entries[3]}


def test_double_click_restores_selection_and_requests_open(grid):
    grid, entries = grid
    opened = []
    grid.open_requested.connect(opened.append)
    grid._on_card_clicked(entries[0], NONE)
    grid._on_card_double_clicked(entries[0])

    assert grid.selected == set()
    assert opened == [entries[0]]


def test_new_entries_keep_only_the_visible_part_of_the_selection(grid):
    grid, entries = grid
    grid.select_all()
    grid.show_entries(entries[:2], root="", scope="")

    assert grid.selected == set(entries[:2])
    assert grid.entries == entries[:2]


def test_escape_clears_the_selection(grid):
    grid, entries = grid
    changes = []
    grid.selection_changed.connect(lambda: changes.append(len(grid.selected)))
    grid.select_all()
    grid.escape()

    assert grid.selected == set()
    assert changes == [5, 0]


def test_previews_loaded_for_another_library_are_discarded(app, monkeypatch):
    import threading

    from PyQt6.QtGui import QColor, QImage

    release = threading.Event()

    def fake_load(entries, root="", scope=""):
        # The first library's worker is still running when the library switches.
        if scope == "stick-a":
            release.wait(2)
        image = QImage(4, 4, QImage.Format.Format_RGB32)
        image.fill(QColor("red" if scope == "stick-a" else "blue"))
        return {entry.media_path: image for entry in entries}

    monkeypatch.setattr("mediavault.gui.card_grid.load_thumbnails", fake_load)
    grid = CardGrid()
    same_path = [MediaItem("x", image_path="Bilder/1.png")]
    grid.show_entries(same_path, root="/media/a", scope="stick-a")
    grid.forget_all()
    grid.show_entries(
        [MediaItem("x", image_path="Bilder/1.png")], root="/media/b", scope="stick-b"
    )
    release.set()
    for _ in range(200):
        app.processEvents()
        if not grid.is_loading:
            break
        if grid._thumb_worker is not None:
            grid._thumb_worker.wait(20)
    assert not grid.is_loading
    pixmap = grid._pixmaps["Bilder/1.png"]
    assert pixmap.toImage().pixelColor(0, 0) == QColor("blue")
