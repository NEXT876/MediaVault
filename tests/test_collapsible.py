"""Tests for the collapsible sidebar section."""

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QSettings  # noqa: E402
from PyQt6.QtWidgets import QApplication, QPushButton  # noqa: E402

from mediavault.gui.collapsible import CollapsibleSection  # noqa: E402

KEY = "sidebar/test_expanded"


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def settings(tmp_path):
    return QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)


def _section(settings, **kwargs):
    section = CollapsibleSection("IMPORT FROM WEB", KEY, settings=settings, **kwargs)
    button = QPushButton("Import")
    section.add_widget(button)
    return section, button


def test_collapsed_by_default(app, settings):
    section, button = _section(settings)
    section.show()

    assert not section.is_expanded()
    assert not button.isVisible()
    assert section.header.text().startswith("▸")


def test_clicking_the_header_toggles_and_persists(app, settings):
    section, button = _section(settings)
    section.show()

    section.header.click()

    assert section.is_expanded()
    assert button.isVisible()
    assert section.header.text().startswith("▾")
    assert settings.value(KEY) in (True, "true")

    section.header.click()
    assert not button.isVisible()
    assert settings.value(KEY) in (False, "false")


def test_restores_the_saved_state(app, settings):
    settings.setValue(KEY, True)

    section, _ = _section(settings)

    assert section.is_expanded()


def test_toggled_signal(app, settings):
    section, _ = _section(settings)
    seen = []
    section.toggled.connect(seen.append)

    section.set_expanded(True)

    assert seen == [True]
