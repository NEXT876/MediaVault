import json
import struct
import zlib

from mediavault import volumes
from mediavault.database import MediaDatabase
from mediavault.importer import content_hash, find_duplicate, import_paths
from mediavault.models import MODE_AI, MODE_NORMAL, MediaItem


def _db(tmp_path):
    return MediaDatabase(str(tmp_path / "db.json"))


def test_content_hash_matches_identical_content(tmp_path):
    first = tmp_path / "a.bin"
    second = tmp_path / "b.bin"
    first.write_bytes(b"same bytes")
    second.write_bytes(b"same bytes")

    assert content_hash(str(first)) == content_hash(str(second))


def test_content_hash_differs_for_different_content(tmp_path):
    first = tmp_path / "a.bin"
    second = tmp_path / "b.bin"
    first.write_bytes(b"same bytes")
    second.write_bytes(b"other bytes")

    assert content_hash(str(first)) != content_hash(str(second))


def test_import_adds_entry_in_normal_mode(tmp_path):
    db = _db(tmp_path)
    path = tmp_path / "cat.png"
    path.write_bytes(b"cat")

    result = import_paths(
        db, [str(path)], type_str="Bilder", group="Tiere", mode=MODE_NORMAL
    )

    assert result.added == 1
    assert db.entries[0].title == "cat"
    assert db.entries[0].content_hash == content_hash(str(path))


def test_import_skips_same_content_under_new_name(tmp_path):
    db = _db(tmp_path)
    original = tmp_path / "original.png"
    original.write_bytes(b"identical image")
    import_paths(db, [str(original)], type_str="Bilder", group="", mode=MODE_NORMAL)

    renamed = tmp_path / "renamed.png"
    renamed.write_bytes(b"identical image")
    result = import_paths(
        db, [str(renamed)], type_str="Bilder", group="", mode=MODE_NORMAL
    )

    assert result.added == 0
    assert result.duplicates == 1
    assert len(db.entries) == 1


def test_import_skips_same_path_twice(tmp_path):
    db = _db(tmp_path)
    path = tmp_path / "cat.png"
    path.write_bytes(b"cat")

    result = import_paths(
        db, [str(path), str(path)], type_str="Bilder", group="", mode=MODE_NORMAL
    )

    assert (result.added, result.duplicates) == (1, 1)
    assert len(db.entries) == 1


def test_import_ai_mode_skips_file_without_metadata(tmp_path):
    db = _db(tmp_path)
    path = tmp_path / "plain.png"
    path.write_bytes(b"\x89PNG\r\n\x1a\n")

    result = import_paths(db, [str(path)], type_str="Bilder", group="", mode=MODE_AI)

    assert result.added == 0
    assert result.skipped_no_ai == 1
    assert db.entries == []


def test_import_backfills_legacy_content_hash(tmp_path):
    db = _db(tmp_path)
    legacy_path = tmp_path / "legacy.png"
    legacy_path.write_bytes(b"legacy")
    legacy = MediaItem("legacy", image_path=str(legacy_path), entry_type="Bilder")
    db.add_many([legacy])
    assert legacy.content_hash == ""

    other = tmp_path / "other.png"
    other.write_bytes(b"other")
    import_paths(db, [str(other)], type_str="Bilder", group="", mode=MODE_NORMAL)

    reloaded = MediaDatabase(str(tmp_path / "db.json"))
    reloaded.load()
    hashes = {entry.title: entry.content_hash for entry in reloaded.entries}
    assert hashes["legacy"] == content_hash(str(legacy_path))


def test_find_duplicate_detects_stored_content(tmp_path):
    db = _db(tmp_path)
    path = tmp_path / "cat.png"
    path.write_bytes(b"cat")
    import_paths(db, [str(path)], type_str="Bilder", group="", mode=MODE_NORMAL)

    renamed = tmp_path / "renamed.png"
    renamed.write_bytes(b"cat")

    assert find_duplicate(db, str(renamed), "Bilder", {})


def test_find_duplicate_rejects_unknown_content(tmp_path):
    db = _db(tmp_path)
    path = tmp_path / "cat.png"
    path.write_bytes(b"cat")
    import_paths(db, [str(path)], type_str="Bilder", group="", mode=MODE_NORMAL)

    other = tmp_path / "dog.png"
    other.write_bytes(b"dog")

    assert not find_duplicate(db, str(other), "Bilder", {})


def _ai_png(path, prompt="castle", seed=42, extra=b""):
    """Write a PNG carrying a ComfyUI workflow; ``extra`` changes the bytes."""
    graph = {
        "1": {"class_type": "KSampler", "inputs": {"seed": seed, "positive": ["2", 0]}},
        "2": {"class_type": "CLIPTextEncode", "inputs": {"text": prompt}},
        "3": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": "m"}},
    }
    chunk = b"tEXt", b"prompt\x00" + json.dumps(graph).encode()
    data = chunk[0] + chunk[1]
    body = struct.pack(">I", len(chunk[1])) + data + struct.pack(">I", zlib.crc32(data))
    ihdr = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)
    ihdr_data = b"IHDR" + ihdr
    iend = struct.pack(">I", 0) + b"IEND" + struct.pack(">I", zlib.crc32(b"IEND"))
    path.write_bytes(
        b"\x89PNG\r\n\x1a\n"
        + struct.pack(">I", len(ihdr))
        + ihdr_data
        + struct.pack(">I", zlib.crc32(ihdr_data))
        + body
        + iend
        + extra
    )
    return str(path)


def test_import_ai_mode_adds_file_with_metadata(tmp_path):
    db = _db(tmp_path)
    path = _ai_png(tmp_path / "castle.png")

    result = import_paths(db, [path], type_str="Bilder", group="", mode=MODE_AI)

    assert (result.added, result.skipped_no_ai) == (1, 0)
    assert db.entries[0].ai_meta["prompt"] == "castle"
    assert db.entries[0].ai_meta["seed"] == 42


def test_import_ai_mode_skips_same_generation_with_other_bytes(tmp_path):
    db = _db(tmp_path)
    first = _ai_png(tmp_path / "a.png")
    # Same prompt and seed, re-saved with different bytes and name.
    second = _ai_png(tmp_path / "b.png", extra=b"trailing")
    other_seed = _ai_png(tmp_path / "c.png", seed=43)

    result = import_paths(
        db, [first, second, other_seed], type_str="Bilder", group="", mode=MODE_AI
    )

    assert (result.added, result.duplicates) == (2, 1)
    assert {entry.title for entry in db.entries} == {"a", "c"}


def test_same_file_name_in_different_folders_is_not_a_duplicate(tmp_path):
    root = tmp_path / "stick"
    first = _write_media(root / "Urlaub" / "IMG_0001.jpg", b"beach")
    second = _write_media(root / "Geburtstag" / "IMG_0001.jpg", b"cake")
    db = _db(tmp_path)

    result = import_paths(
        db,
        [first, second],
        type_str="Bilder",
        group="",
        mode=MODE_NORMAL,
        root=str(root),
    )

    assert result.added == 2
    assert sorted(entry.image_path for entry in db.entries) == [
        "Geburtstag/IMG_0001.jpg",
        "Urlaub/IMG_0001.jpg",
    ]


def _write_media(path, payload=b"x"):
    """Create a small file and return its path."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    return str(path)


def test_import_stores_paths_relative_to_the_volume(tmp_path):
    root = tmp_path / "stick"
    image = _write_media(root / "Bilder" / "a.png")
    db = _db(tmp_path)

    result = import_paths(
        db, [image], type_str="Bilder", group="", mode=MODE_NORMAL, root=str(root)
    )

    assert result.added == 1
    assert db.entries[0].image_path == "Bilder/a.png"


def test_import_skips_a_file_that_is_already_stored(tmp_path):
    root = tmp_path / "stick"
    image = _write_media(root / "a.png")
    db = _db(tmp_path)
    import_paths(
        db, [image], type_str="Bilder", group="", mode=MODE_NORMAL, root=str(root)
    )

    again = import_paths(
        db, [image], type_str="Bilder", group="", mode=MODE_NORMAL, root=str(root)
    )

    assert again.added == 0
    assert again.duplicates == 1


def test_import_without_root_keeps_absolute_paths(tmp_path):
    image = _write_media(tmp_path / "a.png")
    db = _db(tmp_path)

    import_paths(db, [image], type_str="Bilder", group="", mode=MODE_NORMAL)

    assert db.entries[0].image_path == image


def test_entry_resolves_back_to_the_original_file(tmp_path):
    root = tmp_path / "stick"
    image = _write_media(root / "a.png")
    db = _db(tmp_path)
    import_paths(
        db, [image], type_str="Bilder", group="", mode=MODE_NORMAL, root=str(root)
    )

    assert volumes.absolute_path(db.entries[0].file_path, str(root)) == image


def test_transfer_runs_only_for_accepted_files(tmp_path):
    db = _db(tmp_path)
    kept = tmp_path / "kept.png"
    kept.write_bytes(b"one")
    twin = tmp_path / "twin.png"
    twin.write_bytes(b"one")
    seen = []

    def transfer(path):
        seen.append(path)
        return path

    result = import_paths(
        db,
        [str(kept), str(twin)],
        type_str="Bilder",
        group="",
        mode=MODE_NORMAL,
        transfer=transfer,
    )

    assert result.added == 1 and result.duplicates == 1
    assert seen == [str(kept)]


def test_transfer_skipped_for_files_without_ai_meta(tmp_path):
    db = _db(tmp_path)
    plain = tmp_path / "plain.png"
    plain.write_bytes(b"x")
    seen = []

    result = import_paths(
        db,
        [str(plain)],
        type_str="Bilder",
        group="",
        mode=MODE_AI,
        transfer=lambda path: seen.append(path) or path,
    )

    assert result.skipped_no_ai == 1 and not seen


def test_transfer_failure_is_counted_and_stores_new_path(tmp_path):
    db = _db(tmp_path)
    root = tmp_path / "stick"
    root.mkdir()
    ok = tmp_path / "ok.png"
    ok.write_bytes(b"ok")
    bad = tmp_path / "bad.png"
    bad.write_bytes(b"bad")

    def transfer(path):
        return str(root / "ok.png") if path == str(ok) else None

    result = import_paths(
        db,
        [str(ok), str(bad)],
        type_str="Bilder",
        group="",
        mode=MODE_NORMAL,
        root=str(root),
        transfer=transfer,
    )

    assert result.added == 1 and result.failed == 1
    assert db.entries[0].image_path == "ok.png"


def test_import_holds_lock_against_concurrent_add(tmp_path):
    import threading

    db = _db(tmp_path)
    first = tmp_path / "first.png"
    first.write_bytes(b"same")
    twin = tmp_path / "twin.png"
    twin.write_bytes(b"same")
    started = threading.Event()
    release = threading.Event()

    def slow_transfer(path):
        started.set()
        release.wait(2)
        return path

    def other_thread():
        started.wait(2)
        import_paths(db, [str(twin)], type_str="Bilder", group="", mode=MODE_NORMAL)

    worker = threading.Thread(target=other_thread)
    worker.start()
    timer = threading.Timer(0.2, release.set)
    timer.start()
    import_paths(
        db,
        [str(first)],
        type_str="Bilder",
        group="",
        mode=MODE_NORMAL,
        transfer=slow_transfer,
    )
    worker.join(3)

    assert len(db.entries) == 1
