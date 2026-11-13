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
