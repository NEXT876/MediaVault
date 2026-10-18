import random

import pytest

from mediavault import models
from mediavault.models import MediaDatabase, MediaItem


def test_round_trip_preserves_all_fields(tmp_path):
    path = tmp_path / "m.json"
    entry = MediaItem(
        "Titel",
        "bild.png",
        77,
        "Beschreibung",
        "Videos",
        "video.mp4",
        3,
        123.5,
        2,
        "Gruppe",
    )
    db = MediaDatabase(str(path))
    db.add(entry)

    loaded = MediaDatabase(str(path))
    loaded.load()

    assert [item.to_dict() for item in loaded.entries] == [entry.to_dict()]


def test_ai_meta_round_trip(tmp_path):
    path = tmp_path / "m.json"
    db = MediaDatabase(str(path))
    db.add(MediaItem("Titel", ai_meta={"prompt": "castle", "steps": 20}))

    loaded = MediaDatabase(str(path))
    loaded.load()

    assert loaded.entries[0].ai_meta == {"prompt": "castle", "steps": 20}


def test_legacy_dict_gets_empty_ai_meta():
    entry = MediaItem.from_dict({"title": "A"})

    assert entry.ai_meta == {}


def test_from_dict_ignores_unknown_keys():
    entry = MediaItem.from_dict({"title": "A", "legacy_field": 42})
    assert entry.title == "A"
    assert not hasattr(entry, "legacy_field")


def test_to_dict_returns_detached_copy():
    entry = MediaItem("A")
    data = entry.to_dict()
    data["title"] = "B"
    assert entry.title == "A"


def test_add_many_saves_once(tmp_path, monkeypatch):
    db = MediaDatabase(str(tmp_path / "m.json"))
    saves = []
    monkeypatch.setattr(db, "save", lambda: saves.append(True))

    db.add_many([MediaItem("A"), MediaItem("B")])

    assert saves == [True]
    assert [entry.title for entry in db.entries] == ["A", "B"]


def test_add_saves(tmp_path, monkeypatch):
    db = MediaDatabase(str(tmp_path / "m.json"))
    saves = []
    monkeypatch.setattr(db, "save", lambda: saves.append(True))

    db.add(MediaItem("A"))

    assert saves == [True]
    assert [entry.title for entry in db.entries] == ["A"]


def test_corrupt_json_is_backed_up(tmp_path):
    path = tmp_path / "m.json"
    path.write_text("{not json", encoding="utf-8")

    db = MediaDatabase(str(path))
    db.load()

    assert db.entries == []
    backups = list(tmp_path.glob("m.json.corrupt.*"))
    assert len(backups) == 1
    assert backups[0].read_text(encoding="utf-8") == "{not json"


def test_smart_weights_follow_formula(monkeypatch):
    now = 1_000_000.0
    entries = [
        MediaItem("fresh", score=80),
        MediaItem("recent", score=50, watched_counter=2, last_watched=now - 3600),
        MediaItem("week", score=10, watched_counter=1, last_watched=now - 2 * 86400),
        MediaItem("low", score=1, watched_counter=100),
    ]
    captured = {}

    def fake_choices(population, weights, k):
        captured["weights"] = weights
        return [population[0]]

    monkeypatch.setattr(random, "choices", fake_choices)
    monkeypatch.setattr(models.time, "time", lambda: now)
    db = MediaDatabase("unused.json")
    db.entries = entries

    assert db.get_random(entries, smart=True) is entries[0]
    assert captured["weights"] == pytest.approx(
        [
            (80 + 20),
            (50 + 20) * 0.85**2 * 0.3,
            (10 + 20) * 0.85 * 0.6,
            1.0,
        ]
    )


def test_recent_picks_are_excluded_unless_whole_pool(monkeypatch):
    db = MediaDatabase("unused.json")
    first, second = MediaItem("A"), MediaItem("B")
    monkeypatch.setattr(random, "choice", lambda population: population[0])

    assert db.get_random([first, second], recent_picks=[first]) is second
    assert db.get_random([first], recent_picks=[first]) is first
    assert db.get_random([]) is None
