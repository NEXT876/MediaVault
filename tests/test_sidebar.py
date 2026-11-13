"""Tests for the sidebar's page highlight and mode-dependent sections."""

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QSettings  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402

from mediavault.gui.sidebar import DOWNLOADS, WHEEL, Sidebar  # noqa: E402
from mediavault.models import MediaType  # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def sidebar(app, tmp_path, monkeypatch):
    # Keep the collapsible section's state out of the real user settings.
    path = str(tmp_path / "settings.ini")
    monkeypatch.setattr(
        "mediavault.gui.collapsible.QSettings",
        lambda *_args: QSettings(path, QSettings.Format.IniFormat),
    )
    return Sidebar()


def _checked(sidebar):
    return {
        "image": sidebar._view_buttons[MediaType.IMAGE].isChecked(),
        "video": sidebar._view_buttons[MediaType.VIDEO].isChecked(),
        "downloads": sidebar._btn_downloads.isChecked(),
        "wheel": sidebar._btn_wheel.isChecked(),
    }


@pytest.mark.parametrize(
    ("page", "expected"),
    [
        (MediaType.IMAGE, "image"),
        (MediaType.VIDEO, "video"),
        (DOWNLOADS, "downloads"),
        (WHEEL, "wheel"),
    ],
)
def test_set_page_checks_exactly_one_button(sidebar, page, expected):
    sidebar.set_page(page)
    checked = _checked(sidebar)
    assert checked.pop(expected)
    assert not any(checked.values())


def test_online_section_only_outside_ai_mode(sidebar):
    sidebar.set_plugins([("a", "A")])
    sidebar.set_mode(ai=False, has_folder=False)
    assert not sidebar._online_section.isHidden()
    sidebar.set_mode(ai=True, has_folder=False)
    assert sidebar._online_section.isHidden()


def test_wheel_button_emits_request(sidebar):
    calls = []
    sidebar.wheel_requested.connect(lambda: calls.append(True))
    sidebar._btn_wheel.click()
    assert calls == [True]


def test_online_section_hidden_without_plugins(sidebar):
    sidebar.set_plugins([])
    assert not sidebar._online_section.isVisibleTo(sidebar)


def test_one_button_per_plugin(sidebar):
    sidebar.set_plugins([("a", "A"), ("b", "B")])
    assert sidebar._online_section.isVisibleTo(sidebar)
    assert [btn.text() for btn in sidebar._plugin_buttons.values()] == [
        "⬇️  A",
        "⬇️  B",
    ]
    clicked = []
    sidebar.plugin_requested.connect(clicked.append)
    sidebar._plugin_buttons["b"].click()
    assert clicked == ["b"]


def test_set_plugins_replaces_old_buttons(sidebar):
    sidebar.set_plugins([("a", "A")])
    sidebar.set_plugins([("b", "B")])
    assert list(sidebar._plugin_buttons) == ["b"]


def test_plugin_loading_text(sidebar):
    sidebar.set_plugins([("a", "A")])
    sidebar.set_plugin_loading("a", True)
    button = sidebar._plugin_buttons["a"]
    assert (button.text(), button.isEnabled()) == ("⬇️  Lade Posts …", False)
    sidebar.set_plugin_loading("a", False)
    assert (button.text(), button.isEnabled()) == ("⬇️  A", True)
    sidebar.set_plugin_loading("unknown", True)  # no error for stale keys


def test_online_section_stays_hidden_without_plugins_in_normal_mode(sidebar):
    sidebar.set_plugins([])
    sidebar.set_mode(ai=False, has_folder=False)
    assert sidebar._online_section.isHidden()


def test_set_plugins_keeps_section_hidden_in_ai_mode(sidebar):
    sidebar.set_mode(ai=True, has_folder=False)
    sidebar.set_plugins([("a", "A")])
    assert sidebar._online_section.isHidden()
