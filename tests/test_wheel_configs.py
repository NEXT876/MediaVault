"""Tests for storing and matching named wheel configs."""

import json

from mediavault.extras.wheel.configs import (
    load_wheel_configs,
    matching_config,
    save_wheel_configs,
)


def test_roundtrip_keeps_umlauts_and_order(tmp_path):
    path = str(tmp_path / "wheel.json")
    save_wheel_configs({"Essen": ["Döner", "Pizza", "Äpfel"]}, path)

    assert load_wheel_configs(path) == {"Essen": ["Döner", "Pizza", "Äpfel"]}
    assert "Döner" in (tmp_path / "wheel.json").read_text(encoding="utf-8")


def test_missing_file_gives_no_configs(tmp_path):
    assert load_wheel_configs(str(tmp_path / "nope.json")) == {}


def test_load_drops_malformed_data(tmp_path):
    path = tmp_path / "wheel.json"
    path.write_text(
        json.dumps({"ok": [" a ", "", 3], "empty": [], "bad": "x", " ": ["y"]}),
        encoding="utf-8",
    )

    assert load_wheel_configs(str(path)) == {"ok": ["a"]}


def test_corrupt_file_is_kept_aside_instead_of_overwritten(tmp_path):
    path = tmp_path / "wheel.json"
    path.write_text("{kaputt", encoding="utf-8")

    assert load_wheel_configs(str(path)) == {}
    save_wheel_configs({"neu": ["a"]}, str(path))

    assert (tmp_path / "wheel.json.corrupt").read_text(encoding="utf-8") == "{kaputt"
    assert load_wheel_configs(str(path)) == {"neu": ["a"]}


def test_matching_config_needs_identical_entries_in_order():
    configs = {"A": ["x", "y"], "B": ["z"]}

    assert matching_config(configs, ["x", "y"]) == "A"
    assert matching_config(configs, ["y", "x"]) is None
    assert matching_config(configs, []) is None
