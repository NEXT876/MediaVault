"""Shared pytest fixtures."""

import pytest

from mediavault.gui import thumbnails


@pytest.fixture(autouse=True)
def isolated_thumb_cache(tmp_path, monkeypatch):
    """Keep the preview cache out of the developer's home directory."""
    monkeypatch.setattr(thumbnails, "CACHE_DIR", str(tmp_path / "thumbs"))
