"""Tests for removable volume identity and path helpers."""

import json
import os

from mediavault import volumes


def _make_volume(base, name, uuid_value="", label=""):
    """Create a directory that looks like a marked vault volume."""
    root = base / name
    root.mkdir(parents=True)
    info = volumes.write_marker(str(root), uuid_value, label)
    return root, info


def test_marker_round_trip(tmp_path):
    info = volumes.write_marker(str(tmp_path), label="SanDisk")

    assert info.uuid
    assert info.label == "SanDisk"
    assert volumes.read_marker(str(tmp_path)) == info


def test_missing_or_broken_marker_reads_as_none(tmp_path):
    assert volumes.read_marker(str(tmp_path)) is None

    (tmp_path / volumes.MARKER_NAME).write_text("{not json", encoding="utf-8")
    assert volumes.read_marker(str(tmp_path)) is None

    (tmp_path / volumes.MARKER_NAME).write_text(
        json.dumps({"uuid": ""}), encoding="utf-8"
    )
    assert volumes.read_marker(str(tmp_path)) is None


def test_vaults_lists_only_marked_volumes(tmp_path):
    marked, info = _make_volume(tmp_path, "marked")
    unmarked = tmp_path / "unmarked"
    unmarked.mkdir()

    found = volumes.vaults([str(marked), str(unmarked)])

    assert found == [(str(marked), info)]


def test_find_volume_matches_uuid_only(tmp_path):
    other, _ = _make_volume(tmp_path, "other")
    stick, info = _make_volume(tmp_path, "stick", label="Stick")
    roots = [str(other), str(stick)]

    assert volumes.find_volume(info.uuid, roots) == str(stick)
    assert volumes.find_volume("missing", roots) == ""
    assert volumes.find_volume("", roots) == ""


def test_volume_for_path_picks_the_deepest_mount(tmp_path):
    outer, _ = _make_volume(tmp_path, "outer")
    inner, info = _make_volume(outer, "inner")
    roots = [str(outer), str(inner)]

    found_root, found_info = volumes.volume_for_path(str(inner / "media"), roots)

    assert found_root == str(inner)
    assert found_info == info


def test_volume_for_path_outside_any_root(tmp_path):
    assert volumes.volume_for_path(str(tmp_path / "loose"), []) == ("", None)


def test_relative_and_absolute_paths_round_trip(tmp_path):
    root = str(tmp_path)
    target = str(tmp_path / "Bilder" / "sub" / "a.png")

    stored = volumes.stored_path(target, root)

    assert stored == "Bilder/sub/a.png"
    assert volumes.absolute_path(stored, root) == target


def test_stored_path_keeps_paths_outside_the_volume(tmp_path):
    inside = str(tmp_path / "vol")
    os.makedirs(inside)
    outside = str(tmp_path / "elsewhere" / "a.png")

    assert volumes.stored_path(outside, inside) == outside
    assert volumes.stored_path(outside, "") == outside


def test_folder_path_treats_empty_as_the_root(tmp_path):
    assert volumes.folder_path(str(tmp_path), "") == str(tmp_path)
    assert volumes.folder_path(str(tmp_path), "Media") == str(tmp_path / "Media")
    assert volumes.folder_path("", "Media") == ""


def test_absolute_path_never_returns_the_root(tmp_path):
    assert volumes.absolute_path("", str(tmp_path)) == ""
    assert volumes.absolute_path(".", str(tmp_path)) == ""


def test_paths_cannot_escape_the_volume(tmp_path):
    assert volumes.folder_path(str(tmp_path), "../etc") == ""
    assert volumes.absolute_path("../etc/passwd", str(tmp_path)) == ""
    assert volumes.absolute_path("a.png", "") == ""


def test_path_key_matches_absolute_and_relative(tmp_path):
    root = str(tmp_path)
    absolute = str(tmp_path / "a" / "b.png")

    assert volumes.path_key(absolute, root) == volumes.path_key("a/b.png", root)
    assert volumes.path_key("", root) == ""
    # Without a root an absolute path stays absolute, so nothing matches falsely.
    assert volumes.path_key(absolute) != volumes.path_key("a/b.png", root)


def test_relativize_converts_only_entries_inside_root(tmp_path):
    from mediavault.database import MediaDatabase
    from mediavault.models import MediaItem

    root = tmp_path / "stick"
    (root / "m").mkdir(parents=True)
    db = MediaDatabase(str(tmp_path / "db.json"))
    db.entries = [
        MediaItem(title="in", image_path=str(root / "m" / "a.png")),
        MediaItem(title="out", image_path=str(tmp_path / "b.png")),
        MediaItem(title="vid", entry_type="Videos", video_link=str(root / "v.mp4")),
    ]

    assert db.relativize(str(root)) == 2
    assert db.entries[0].image_path == "m/a.png"
    assert db.entries[1].image_path == str(tmp_path / "b.png")
    assert db.entries[2].video_link == "v.mp4"
    assert db.relativize(str(root)) == 0
