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
    assert _titles(visible_entries(entries, "", "", "last_watched")) == [
        "Gamma",
        "Beta",
        "alpha",
    ]


def test_input_order_is_not_mutated():
    entries = _entries()
    visible_entries(entries, "", "", "score_desc")
    assert _titles(entries) == ["Beta", "alpha", "Gamma"]
