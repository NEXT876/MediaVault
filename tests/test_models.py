import random

import pytest

from mediavault import database
from mediavault.database import MediaDatabase
from mediavault.models import MediaItem


def test_round_trip_preserves_all_fields(tmp_path):
    path = tmp_path / "m.json"
    entry = MediaItem(
        title="Titel",
        image_path="bild.png",
        score=77,
        description="Beschreibung",
        entry_type="Videos",
        video_link="video.mp4",
        watched_counter=3,
        last_watched=123.5,
        rating_count=2,
        group="Gruppe",
        ai_meta={"seed": 1},
        content_hash="abc",
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


@pytest.mark.parametrize("content", ["{not json", "{}", '[{"title": "A"}, 5]'])
def test_corrupt_json_is_backed_up(tmp_path, content):
    path = tmp_path / "m.json"
    path.write_text(content, encoding="utf-8")

    db = MediaDatabase(str(path))
    db.load()

    assert db.entries == []
    backups = list(tmp_path.glob("m.json.corrupt.*"))
    assert len(backups) == 1
    assert backups[0].read_text(encoding="utf-8") == content


def _smart_weights(monkeypatch, entries, now):
    """Return the weights get_random(smart=True) hands to random.choices."""
    captured = {}

    def fake_choices(population, weights, k):
        captured.update(zip((entry.title for entry in population), weights, strict=True))
        return [population[0]]

    monkeypatch.setattr(random, "choices", fake_choices)
    monkeypatch.setattr(database.time, "time", lambda: now)
    MediaDatabase("unused.json").get_random(entries, smart=True)
    return captured


def test_smart_weights_prefer_high_scores_and_unwatched(monkeypatch):
    now = 1_000_000.0
    weights = _smart_weights(
        monkeypatch,
        [
            MediaItem("high", score=90),
            MediaItem("low", score=10),
            MediaItem("watched_often", score=90, watched_counter=10),
            MediaItem("just_watched", score=90, last_watched=now - 3600),
            MediaItem("watched_days_ago", score=90, last_watched=now - 3 * 86400),
            MediaItem("watched_long_ago", score=90, last_watched=now - 30 * 86400),
            MediaItem("worthless", score=0, watched_counter=500),
        ],
        now,
    )

    assert weights["high"] > weights["low"]
    assert weights["high"] > weights["watched_often"]
    assert weights["just_watched"] < weights["watched_days_ago"]
    assert weights["watched_days_ago"] < weights["watched_long_ago"]
    assert weights["watched_long_ago"] == pytest.approx(weights["high"])
    # Every entry keeps a chance to be picked.
    assert weights["worthless"] > 0


def test_recent_picks_are_excluded_unless_whole_pool(monkeypatch):
    db = MediaDatabase("unused.json")
    first, second = MediaItem("A"), MediaItem("B")
    monkeypatch.setattr(random, "choice", lambda population: population[0])

    assert db.get_random([first, second], recent_picks=[first]) is second
    assert db.get_random([first], recent_picks=[first]) is first
    assert db.get_random([]) is None


def test_media_type_is_stored_as_plain_value(tmp_path):
    from mediavault.database import MediaDatabase
    from mediavault.models import MediaType

    path = tmp_path / "m.json"
    db = MediaDatabase(str(path))
    db.entries = [MediaItem("v", entry_type=MediaType.VIDEO, video_link="v.mp4")]
    db.save()

    assert '"entry_type": "Videos"' in path.read_text(encoding="utf-8")
    loaded = MediaDatabase(str(path))
    loaded.load()
    assert loaded.entries[0].entry_type == MediaType.VIDEO
    assert loaded.get_by_type(MediaType.VIDEO) == loaded.entries
    assert str(MediaType.IMAGE) == "Bilder" and f"{MediaType.VIDEO}" == "Videos"


def test_file_path_prefers_video_over_preview_image():
    from mediavault.models import MediaType

    entry = MediaItem(
        "v", image_path="p.png", entry_type=MediaType.VIDEO, video_link="v.mp4"
    )

    assert entry.file_path == "v.mp4"
    assert entry.media_path == "p.png"
