import json
import os
import threading

import pytest

from mediavault.database import MediaDatabase
from mediavault.models import MediaItem


@pytest.mark.parametrize("smart", [False, True])
def test_random_picks_only_from_the_given_pool(tmp_path, smart):
    db = MediaDatabase(str(tmp_path / "m.json"))
    outside = MediaItem("outside", score=100)
    pool = [MediaItem("A", score=1), MediaItem("B", score=1)]
    db.entries = [outside, *pool]

    picks = {db.get_random(pool, smart=smart).title for _ in range(200)}

    assert picks == {"A", "B"}


def test_save_leaves_no_temp_file(tmp_path):
    path = tmp_path / "m.json"
    db = MediaDatabase(str(path))
    db.load()
    db.entries = [MediaItem("A")]
    db.save()
    assert json.loads(path.read_text(encoding="utf-8"))[0]["title"] == "A"
    assert not (tmp_path / "m.json.tmp").exists()


def test_concurrent_adds_keep_every_entry(tmp_path):
    # Smoke test only: it would not reliably catch a missing lock.
    path = tmp_path / "m.json"
    db = MediaDatabase(str(path))
    db.load()
    count = 8
    threads = [
        threading.Thread(target=db.add, args=(MediaItem(f"T{index}"),))
        for index in range(count)
    ]

    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    stored = json.loads(path.read_text(encoding="utf-8"))
    assert len(db.entries) == count
    assert {item["title"] for item in stored} == {f"T{i}" for i in range(count)}


def test_load_corrupt_file_reports_error_and_backup(tmp_path):
    path = tmp_path / "m.json"
    path.write_text("{kaputt", encoding="utf-8")
    db = MediaDatabase(str(path))

    db.load()

    assert db.entries == []
    assert db.load_error
    assert db.backup_path and os.path.exists(db.backup_path)
    assert not db.read_only


def test_unreadable_file_is_never_overwritten(tmp_path, monkeypatch):
    path = tmp_path / "m.json"
    path.write_text('[{"title": "A"}]', encoding="utf-8")
    db = MediaDatabase(str(path))
    real_open = open

    def failing_open(file, *args, **kwargs):
        if str(file) == str(path) and "r" in (args[0] if args else kwargs.get("mode", "r")):
            raise PermissionError("denied")
        return real_open(file, *args, **kwargs)

    monkeypatch.setattr("builtins.open", failing_open)
    db.load()
    monkeypatch.undo()

    assert db.read_only and db.load_error
    db.add(MediaItem("B"))
    assert json.loads(path.read_text(encoding="utf-8")) == [{"title": "A"}]


def test_entry_without_title_is_treated_as_corrupt(tmp_path):
    path = tmp_path / "m.json"
    path.write_text('[{"score": 5}]', encoding="utf-8")
    db = MediaDatabase(str(path))

    db.load()

    assert db.entries == []
    assert db.load_error
    assert db.backup_path and os.path.exists(db.backup_path)


def test_failed_backup_never_overwrites_corrupt_file(tmp_path, monkeypatch):
    path = tmp_path / "m.json"
    path.write_text("{kaputt", encoding="utf-8")
    db = MediaDatabase(str(path))

    def failing_copy(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr("mediavault.database.shutil.copy", failing_copy)
    db.load()

    assert db.read_only and not db.backup_path
    db.add(MediaItem("B"))
    assert path.read_text(encoding="utf-8") == "{kaputt"


def test_numbers_stored_as_text_are_converted(tmp_path):
    path = tmp_path / "m.json"
    path.write_text(
        '[{"title": "A", "score": "80", "last_watched": "1.5"}]', encoding="utf-8"
    )
    db = MediaDatabase(str(path))

    db.load()

    assert (db.entries[0].score, db.entries[0].last_watched) == (80, 1.5)
    assert db.get_random(db.entries, smart=True) is db.entries[0]
