"""Tests for the wheel of fortune's entry parsing and spin target."""

import pytest

from mediavault.gui.wheel import parse_entries, target_angle


def test_parse_entries_skips_blank_lines_and_strips():
    assert parse_entries("  Pizza \n\n\tSushi\n   \nRamen") == [
        "Pizza",
        "Sushi",
        "Ramen",
    ]
    assert parse_entries("") == []


@pytest.mark.parametrize("count", [1, 2, 3, 7, 12])
@pytest.mark.parametrize("current", [0.0, 123.4, 359.9])
def test_target_angle_puts_winner_under_pointer(count, current):
    slice_deg = 360.0 / count
    for index in range(count):
        target = target_angle(current, index, count, turns=4.5)
        # Rotating by ``target`` must move the slice's middle to 0° (the top).
        middle = (index + 0.5) * slice_deg
        assert (middle + target) % 360.0 == pytest.approx(0.0, abs=1e-6) or (
            (middle + target) % 360.0 == pytest.approx(360.0, abs=1e-6)
        )
        assert target - current >= 3.2 * 360.0


@pytest.fixture
def page(qtbot_free_app, tmp_path):
    from mediavault.gui.theme import PALETTES
    from mediavault.gui.wheel import WheelPage

    return WheelPage(
        PALETTES["dark"],
        lambda: ["Anime", "Filme"],
        str(tmp_path / "wheel.json"),
    )


@pytest.fixture(scope="module")
def qtbot_free_app():
    import os

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PyQt6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


def _answer(monkeypatch, label):
    """Make the overwrite warning "click" the button with this label."""
    from PyQt6.QtWidgets import QMessageBox

    calls = []

    def fake_exec(box):
        calls.append(box.text())
        box._chosen = next(b for b in box.buttons() if b.text() == label)
        return 0

    monkeypatch.setattr(QMessageBox, "exec", fake_exec)
    monkeypatch.setattr(QMessageBox, "clickedButton", lambda box: box._chosen)
    return calls


def test_all_groups_overwrite_warns_when_entries_are_unsaved(page, monkeypatch):
    calls = _answer(monkeypatch, "Abbrechen")

    page.load_all_groups()

    assert len(calls) == 1 and "nicht als Config" in calls[0]
    assert "Pizza" in page.editor.toPlainText()  # untouched


def test_all_groups_overwrite_confirmed(page, monkeypatch):
    _answer(monkeypatch, "Überschreiben")

    page.load_all_groups()

    assert page.editor.toPlainText() == "Anime\nFilme"


def test_saved_entries_are_replaced_without_warning(page, monkeypatch):
    from PyQt6.QtWidgets import QInputDialog

    monkeypatch.setattr(QInputDialog, "getText", lambda *a, **k: ("Essen", True))
    assert page.save_config() is True
    calls = _answer(monkeypatch, "Abbrechen")

    page.load_all_groups()

    assert calls == []
    assert page.editor.toPlainText() == "Anime\nFilme"
    # The group names are not saved, so applying the config now warns first.
    _answer(monkeypatch, "Überschreiben")
    page.apply_config()
    assert page.editor.toPlainText().splitlines()[0] == "Pizza"
    assert page.editor.toPlainText().splitlines()[-1] == "Curry"


def test_save_first_stores_config_then_overwrites(page, monkeypatch):
    from PyQt6.QtWidgets import QInputDialog

    monkeypatch.setattr(QInputDialog, "getText", lambda *a, **k: ("Backup", True))
    _answer(monkeypatch, "Erst speichern …")

    page.load_all_groups()

    assert page.editor.toPlainText() == "Anime\nFilme"
    assert "Backup" in page._configs
    assert "Pizza" in page._configs["Backup"]


def test_no_groups_shows_hint_and_keeps_entries(page, monkeypatch):
    from PyQt6.QtWidgets import QMessageBox

    page._group_provider = lambda: []
    shown = []
    monkeypatch.setattr(QMessageBox, "information", lambda *a: shown.append(a[2]))

    page.load_all_groups()

    assert shown and "keine Gruppen" in shown[0]
    assert "Pizza" in page.editor.toPlainText()


def test_spin_uses_text_typed_within_the_debounce_delay(page):
    page.editor.setPlainText("Nur Ich")
    page.spin()
    assert page.wheel.entries == ["Nur Ich"]
