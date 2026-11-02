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
