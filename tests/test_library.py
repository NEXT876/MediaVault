"""Tests for indexing the library folder, including stick libraries."""

from mediavault import library
from mediavault.database import MediaDatabase
from mediavault.models import MODE_AI, MODE_NORMAL, LibraryRoot, MediaItem, MediaType


def _touch(path, data=b"x"):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return str(path)


def test_find_unindexed_matches_paths_stored_relative_to_the_stick(tmp_path):
    stick = tmp_path / "stick"
    known = _touch(stick / "media" / "a.png", b"a")
    new = _touch(stick / "media" / "b.png", b"b")
    db = MediaDatabase(str(tmp_path / "db.json"))
    db.entries.append(MediaItem("a", image_path="media/a.png"))
    location = LibraryRoot(volume=str(stick), folder=str(stick / "media"))

    found = library.find_unindexed(db, MODE_NORMAL, location)

    assert found[MediaType.IMAGE] == [new]
    assert known not in found[MediaType.IMAGE]


def test_find_unindexed_skips_ignored_files(tmp_path):
    ignored = _touch(tmp_path / "lib" / "x.png")
    db = MediaDatabase(str(tmp_path / "db.json"))

    found = library.find_unindexed(
        db, MODE_NORMAL, LibraryRoot(folder=str(tmp_path / "lib")), [ignored]
    )

    assert found[MediaType.IMAGE] == []


def test_ai_mode_only_indexes_png(tmp_path):
    exts = library.media_exts(MODE_AI)

    assert exts[MediaType.IMAGE] == {".png"}
    assert exts[MediaType.VIDEO] == set()


def test_scan_stores_stick_paths_relative(tmp_path):
    stick = tmp_path / "stick"
    _touch(stick / "media" / "a.png", b"a")
    _touch(stick / "media" / "clip.mp4", b"v")
    db = MediaDatabase(str(tmp_path / "db.json"))
    location = LibraryRoot(volume=str(stick), folder=str(stick / "media"))

    result = library.scan(db, MODE_NORMAL, location)

    assert result.added == 2
    assert sorted(entry.file_path for entry in db.entries) == [
        "media/a.png",
        "media/clip.mp4",
    ]
    assert library.scan(db, MODE_NORMAL, location).added == 0


def test_scan_does_nothing_while_the_stick_is_unplugged(tmp_path):
    db = MediaDatabase(str(tmp_path / "db.json"))

    assert library.scan(db, MODE_NORMAL, LibraryRoot()).added == 0
    assert db.entries == []


def test_not_indexed_reports_rejected_files(tmp_path):
    stick = tmp_path / "stick"
    kept = _touch(stick / "a.png", b"a")
    copy = _touch(stick / "copy.png", b"a")
    db = MediaDatabase(str(tmp_path / "db.json"))
    location = LibraryRoot(volume=str(stick), folder=str(stick))
    found = library.find_unindexed(db, MODE_NORMAL, location)

    library.index_files(db, found, MODE_NORMAL, location)

    # Same content under a second name is a duplicate and stays out.
    assert library.not_indexed(db, [kept, copy], location) == {copy}


def test_file_filter_lists_every_known_extension():
    image_filter = library.file_filter(MediaType.IMAGE)
    video_filter = library.file_filter(MediaType.VIDEO)

    assert image_filter.startswith("Bilder (") and "*.png" in image_filter
    assert video_filter.startswith("Videos (") and "*.m4v" in video_filter
