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
