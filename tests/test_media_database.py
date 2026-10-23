import json
import threading

from mediavault.models import MediaDatabase, MediaItem


def test_random_smart_only_from_pool(tmp_path):
    db = MediaDatabase(str(tmp_path / "m.json"))
    db.load()
    db.entries = [MediaItem("A", score=1), MediaItem("B", score=99)]
    chosen = db.get_random(db.entries, smart=True)
    assert chosen in db.entries


def test_save_is_atomic(tmp_path):
    path = tmp_path / "m.json"
    db = MediaDatabase(str(path))
    db.load()
    db.entries = [MediaItem("A")]
    db.save()
    assert path.exists()
    assert not (tmp_path / "m.json.tmp").exists()


def test_concurrent_adds_keep_every_entry(tmp_path):
    path = tmp_path / "m.json"
    db = MediaDatabase(str(path))
    db.load()
    threads = [
        threading.Thread(target=db.add, args=(MediaItem(f"T{index}"),))
        for index in range(8)
    ]

    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    stored = json.loads(path.read_text(encoding="utf-8"))
    assert len(db.entries) == 8
    assert len(stored) == 8
