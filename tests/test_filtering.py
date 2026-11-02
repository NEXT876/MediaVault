from mediavault.gui.main_window import ALL_GROUPS, visible_entries
from mediavault.models import MediaItem


def _titles(entries):
    return [entry.title for entry in entries]


def _entries():
    return [
        MediaItem("Beta", score=50, group="G1", description="Zweiter"),
        MediaItem("alpha", score=90, group="G2", description="Erster"),
        MediaItem("Gamma", score=90, group="G1", last_watched=10),
    ]


def test_group_filter():
    entries = _entries()
    assert _titles(visible_entries(entries, "G1", "", "title")) == ["Beta", "Gamma"]
    assert _titles(visible_entries(entries, ALL_GROUPS, "", "title")) == [
        "alpha",
        "Beta",
        "Gamma",
    ]
    assert _titles(visible_entries(entries, "", "", "title")) == [
        "alpha",
        "Beta",
        "Gamma",
    ]


def test_search_is_case_insensitive_across_fields():
    entries = _entries()
    assert _titles(visible_entries(entries, "", "ERSTER", "title")) == ["alpha"]
    assert _titles(visible_entries(entries, "", "g2", "title")) == ["alpha"]
    assert _titles(visible_entries(entries, "", "beta", "title")) == ["Beta"]
    assert visible_entries(entries, "", "nichts", "title") == []


def test_search_finds_ai_prompts():
    entries = [
        MediaItem(
            "A",
            ai_meta={"prompt": "castle at dawn", "negative_prompt": "blurry"},
        ),
        MediaItem("B"),
    ]

    assert _titles(visible_entries(entries, "", "CASTLE", "title")) == ["A"]
    assert _titles(visible_entries(entries, "", "blurry", "title")) == ["A"]


def test_sort_modes():
    entries = _entries()
    assert _titles(visible_entries(entries, "", "", "title")) == [
        "alpha",
        "Beta",
        "Gamma",
    ]
    assert _titles(visible_entries(entries, "", "", "score_desc")) == [
        "alpha",
        "Gamma",
        "Beta",
    ]
    assert _titles(visible_entries(entries, "", "", "score_asc")) == [
        "Beta",
        "alpha",
        "Gamma",
    ]
    assert _titles(visible_entries(entries, "", "", "last_watched"))[0] == "Gamma"


def test_score_ties_are_broken_by_title_not_input_order():
    entries = [
        MediaItem("b", score=50),
        MediaItem("C", score=50),
        MediaItem("a", score=50),
    ]

    assert _titles(visible_entries(entries, "", "", "score_desc")) == ["a", "b", "C"]
    assert _titles(visible_entries(entries, "", "", "score_asc")) == ["a", "b", "C"]


def test_last_watched_puts_unwatched_entries_last():
    entries = [
        MediaItem("never"),
        MediaItem("old", last_watched=5),
        MediaItem("new", last_watched=50),
    ]

    assert _titles(visible_entries(entries, "", "", "last_watched")) == [
        "new",
        "old",
        "never",
    ]


def test_input_order_is_not_mutated():
    entries = _entries()
    visible_entries(entries, "", "", "score_desc")
    assert _titles(entries) == ["Beta", "alpha", "Gamma"]
