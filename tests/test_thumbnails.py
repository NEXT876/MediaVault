"""Tests for background preview loading."""

from pathlib import Path

from PyQt6.QtGui import QImage

from mediavault.gui import main_window
from mediavault.gui.main_window import load_thumbnail
from mediavault.models import MediaItem


def _write_image(path: Path, width: int, height: int) -> str:
    """Write a solid-color test image and return its path."""
    image = QImage(width, height, QImage.Format.Format_RGB32)
    image.fill(0xFF0000)
    assert image.save(str(path))
    return str(path)


def test_load_thumbnail_scales_to_cache_bounds(tmp_path):
    entry = MediaItem(title="a", image_path=_write_image(tmp_path / "a.png", 800, 400))

    image = load_thumbnail(entry)

    assert (image.width(), image.height()) == (512, 256)


def test_load_thumbnail_returns_none_for_missing_file(tmp_path):
    entry = MediaItem(title="a", image_path=str(tmp_path / "missing.png"))

    assert load_thumbnail(entry) is None


def test_load_thumbnails_keeps_other_previews_when_one_fails(tmp_path, monkeypatch):
    good = MediaItem(
        title="good", image_path=_write_image(tmp_path / "good.png", 20, 10)
    )
    bad = MediaItem(title="bad", image_path="broken")

    def fake_load(entry):
        if entry is bad:
            raise OSError("broken file")
        return load_thumbnail(entry)

    monkeypatch.setattr(main_window, "load_thumbnail", fake_load)

    previews = main_window.load_thumbnails([good, bad])

    assert previews[good.media_path] is not None
    assert previews[bad.media_path] is None
