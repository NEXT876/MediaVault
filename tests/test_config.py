import json
import os

import pytest

from mediavault import volumes
from mediavault.config import (
    DEFAULT_DB_PATH,
    config_from_dict,
    create_config,
    load_configs,
    locate,
    save_configs,
)
from mediavault.models import MODE_AI, MODE_NORMAL, LibraryRoot, VaultConfig
from mediavault.scanner import find_new_media


def _touch(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"")


def test_missing_file_migrates_to_default_config(tmp_path):
    path = tmp_path / "configs.json"

    configs, last = load_configs(str(path))

    assert [(config.name, config.mode, config.db_path) for config in configs] == [
        ("Meine Mediathek", MODE_NORMAL, DEFAULT_DB_PATH)
    ]
    assert last == DEFAULT_DB_PATH
    assert not path.exists()


def test_corrupt_file_is_not_overwritten(tmp_path):
    path = tmp_path / "configs.json"
    path.write_text("{not json", encoding="utf-8")

    configs, last = load_configs(str(path))

    assert len(configs) == 1
    assert last == DEFAULT_DB_PATH
    assert path.read_text(encoding="utf-8") == "{not json"


@pytest.mark.parametrize("content", ["[]", "null", '{"configs": "nope"}'])
def test_wrong_shape_falls_back_to_default(tmp_path, content):
    path = tmp_path / "configs.json"
    path.write_text(content, encoding="utf-8")

    configs, last = load_configs(str(path))

    assert [(config.name, config.mode, config.db_path) for config in configs] == [
        ("Meine Mediathek", MODE_NORMAL, DEFAULT_DB_PATH)
    ]
    assert last == DEFAULT_DB_PATH


def test_save_and_load_last_config(tmp_path):
    path = tmp_path / "configs.json"
    configs = [
        VaultConfig("A", MODE_NORMAL, str(tmp_path / "a.json")),
        VaultConfig("B", MODE_AI, str(tmp_path / "b.json"), str(tmp_path)),
    ]

    save_configs(configs, configs[1].db_path, str(path))
    loaded, last = load_configs(str(path))

    assert loaded == configs
    assert last == configs[1].db_path


def test_unknown_last_and_mode_fall_back(tmp_path):
    path = tmp_path / "configs.json"
    path.write_text(
        json.dumps(
            {
                "last": "missing.json",
                "configs": [
                    {"name": "A", "mode": "weird", "db_path": "a.json"},
                    {"name": "B", "mode": MODE_AI, "db_path": "b.json"},
                ],
            }
        ),
        encoding="utf-8",
    )

    configs, last = load_configs(str(path))

    assert [config.mode for config in configs] == [MODE_NORMAL, MODE_AI]
    assert last == "a.json"


def test_create_config_makes_unique_paths(tmp_path):
    first = create_config("Meine KI Bilder", MODE_AI, base_dir=str(tmp_path))
    second = create_config(
        "Meine KI Bilder", MODE_NORMAL, existing=[first], base_dir=str(tmp_path)
    )

    assert first.db_path == str(tmp_path / "meine-ki-bilder.json")
    assert second.db_path == str(tmp_path / "meine-ki-bilder-2.json")
    assert first.mode == MODE_AI


def test_find_new_media_recurses_and_skips_known(tmp_path):
    known = tmp_path / "a.png"
    new_nested = tmp_path / "sub" / "b.JPG"
    ignored = tmp_path / "c.txt"
    _touch(known)
    _touch(new_nested)
    _touch(ignored)

    images, videos = find_new_media(str(tmp_path), [str(known)])

    assert images == [str(new_nested)]
    assert videos == []


def test_find_new_media_splits_images_and_videos(tmp_path):
    _touch(tmp_path / "a.png")
    _touch(tmp_path / "sub" / "b.mp4")
    _touch(tmp_path / "notes.txt")

    images, videos = find_new_media(str(tmp_path), [])

    assert [os.path.basename(path) for path in images] == ["a.png"]
    assert [os.path.basename(path) for path in videos] == ["b.mp4"]


def test_find_new_media_can_limit_the_types(tmp_path):
    _touch(tmp_path / "a.png")
    _touch(tmp_path / "b.jpg")
    _touch(tmp_path / "c.mp4")

    images, videos = find_new_media(
        str(tmp_path), [], image_exts={".png"}, video_exts=()
    )

    assert images == [str(tmp_path / "a.png")]
    assert videos == []


def test_find_new_media_skips_known_relative_paths(tmp_path):
    _touch(tmp_path / "a.png")

    images, _videos = find_new_media(str(tmp_path), ["a.png"], root=str(tmp_path))

    assert images == []


def test_find_new_media_missing_folder_returns_empty(tmp_path):
    assert find_new_media(str(tmp_path / "nope"), []) == ([], [])


def _volume_config(tmp_path, folder_rel="Media"):
    """Create a config bound to a freshly marked volume."""
    root = tmp_path / "stick"
    root.mkdir()
    info = volumes.write_marker(str(root), label="Stick")
    config = VaultConfig(
        name="Stick",
        db_path="s.json",
        volume_uuid=info.uuid,
        volume_label=info.label,
        folder_rel=folder_rel,
    )
    return root, config


def test_locate_reports_an_unplugged_volume(monkeypatch, tmp_path):
    root, config = _volume_config(tmp_path)

    monkeypatch.setattr(volumes, "mounted_roots", list)
    assert locate(config) == LibraryRoot()
    assert not locate(config).available

    monkeypatch.setattr(volumes, "mounted_roots", lambda: [str(root)])
    location = locate(config)
    assert (location.volume, location.folder) == (str(root), str(root / "Media"))
    assert location.available


def test_locate_treats_an_empty_folder_as_the_volume_root(monkeypatch, tmp_path):
    root, config = _volume_config(tmp_path, folder_rel="")
    monkeypatch.setattr(volumes, "mounted_roots", lambda: [str(root)])

    location = locate(config)

    assert (location.volume, location.folder) == (str(root), str(root))


def test_locate_keeps_a_local_config_on_its_folder(tmp_path):
    config = VaultConfig(name="Lokal", db_path="l.json", folder=str(tmp_path))

    assert locate(config) == LibraryRoot(folder=str(tmp_path))


def test_folder_last_sync_defaults_and_round_trips(tmp_path):
    path = tmp_path / "configs.json"
    assert config_from_dict({"name": "Alt"}).folder_last_sync == ""

    config = VaultConfig(
        name="KI", mode=MODE_AI, db_path="ki.json", folder_last_sync="23.10.2026 14:05"
    )
    save_configs([config], config.db_path, str(path))
    loaded, _last = load_configs(str(path))

    assert loaded[0].folder_last_sync == "23.10.2026 14:05"


@pytest.mark.skipif(os.name != "posix", reason="POSIX-Dateirechte")
def test_configs_file_is_private(tmp_path):
    path = tmp_path / "configs.json"
    save_configs([VaultConfig("A", MODE_NORMAL, "a.json")], "a.json", str(path))

    assert (os.stat(path).st_mode & 0o777) == 0o600


def _round_trip(tmp_path, entry):
    path = tmp_path / "configs.json"
    path.write_text(
        json.dumps({"last": "a.json", "configs": [entry]}), encoding="utf-8"
    )
    loaded, _last = load_configs(str(path))
    save_configs(loaded, "a.json", str(path))
    stored = json.loads(path.read_text(encoding="utf-8"))["configs"][0]
    return loaded[0], stored


def test_unknown_keys_round_trip(tmp_path):
    config, stored = _round_trip(
        tmp_path, {"name": "A", "db_path": "a.json", "foo": {"x": 1}}
    )
    assert config.extra == {"foo": {"x": 1}}
    assert stored["foo"] == {"x": 1}
    assert "extra" not in stored


def test_plugins_round_trip(tmp_path):
    config, stored = _round_trip(
        tmp_path,
        {"name": "A", "db_path": "a.json", "plugins": {"p": {"a": 1}, "bad": 3}},
    )
    assert config.plugins == {"p": {"a": 1}}
    assert stored["plugins"] == {"p": {"a": 1}}
    assert config_from_dict({"name": "B", "plugins": []}).plugins == {}


def test_known_keys_win_over_extra(tmp_path):
    config = VaultConfig(name="A", db_path="a.json", extra={"name": "X"})
    path = tmp_path / "configs.json"
    save_configs([config], "a.json", str(path))
    stored = json.loads(path.read_text(encoding="utf-8"))["configs"][0]
    assert stored["name"] == "A"
