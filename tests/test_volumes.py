"""Tests for removable volume identity and path helpers."""

import json
import os

from mediavault import volumes
from mediavault.config import (
    VaultConfig,
    find_new_media,
    resolve_folder,
    storage_root,
)


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

    (tmp_path / volumes.MARKER_NAME).write_text(json.dumps({"uuid": ""}), encoding="utf-8")
    assert volumes.read_marker(str(tmp_path)) is None


def test_find_volume_matches_uuid_only(tmp_path):
    other, stick = _make_volume(tmp_path, "other"), _make_volume(tmp_path, "stick", label="Stick")
    roots = [str(other[0]), str(stick[0])]

    assert volumes.find_volume(stick[1].uuid, roots) == str(stick[0])
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


def test_resolve_refuses_to_escape_the_volume(tmp_path):
    assert volumes.resolve(str(tmp_path), "../etc/passwd") == ""
    assert volumes.resolve(str(tmp_path), "") == ""
    assert volumes.resolve("", "a.png") == ""


def test_path_key_matches_absolute_and_relative(tmp_path):
    root = str(tmp_path)
    absolute = str(tmp_path / "a" / "b.png")

    assert volumes.path_key(absolute, root) == volumes.path_key("a/b.png", root)
    assert volumes.path_key("", root) == ""
    # Without a root an absolute path stays absolute, so nothing matches falsely.
    assert volumes.path_key(absolute) != volumes.path_key("a/b.png", root)


def test_resolve_folder_reports_an_unplugged_volume(monkeypatch, tmp_path):
    root, info = _make_volume(tmp_path, "stick", label="Stick")
    config = VaultConfig(
        name="Stick",
        db_path="s.json",
        volume_uuid=info.uuid,
        volume_label=info.label,
        folder_rel="Media",
    )

    monkeypatch.setattr(volumes, "mounted_roots", list)
    assert resolve_folder(config) == ""

    monkeypatch.setattr(volumes, "mounted_roots", lambda: [str(root)])
    assert resolve_folder(config) == str(root / "Media")


def test_storage_root_is_the_volume_root(monkeypatch, tmp_path):
    root, info = _make_volume(tmp_path, "stick")
    config = VaultConfig(
        name="S", db_path="s.json", volume_uuid=info.uuid, folder_rel="Media"
    )

    monkeypatch.setattr(volumes, "mounted_roots", lambda: [str(root)])

    assert storage_root(config) == str(root)


def test_storage_root_is_empty_without_a_volume(tmp_path):
    config = VaultConfig(name="L", db_path="l.json", folder=str(tmp_path))

    assert storage_root(config) == ""


def test_resolve_folder_falls_back_to_plain_folder(tmp_path):
    config = VaultConfig(name="Lokal", db_path="l.json", folder=str(tmp_path))

    assert resolve_folder(config) == str(tmp_path)


def test_find_new_media_splits_images_and_videos(tmp_path):
    (tmp_path / "a.png").write_bytes(b"x")
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "b.mp4").write_bytes(b"x")
    (tmp_path / "notes.txt").write_text("x", encoding="utf-8")

    images, videos = find_new_media(str(tmp_path), [])

    assert [os.path.basename(path) for path in images] == ["a.png"]
    assert [os.path.basename(path) for path in videos] == ["b.mp4"]


def test_find_new_media_skips_known_relative_paths(tmp_path):
    target = tmp_path / "a.png"
    target.write_bytes(b"x")

    images, videos = find_new_media(str(tmp_path), ["a.png"], root=str(tmp_path))

    assert images == []
    assert videos == []
