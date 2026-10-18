import json

from mediavault.config import (
    DEFAULT_DB_PATH,
    MODE_AI,
    MODE_NORMAL,
    VaultConfig,
    create_config,
    find_new_images,
    load_configs,
    save_configs,
)


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


def test_find_new_images_recurses_and_skips_known(tmp_path):
    known = tmp_path / "a.png"
    new_nested = tmp_path / "sub" / "b.JPG"
    ignored = tmp_path / "c.txt"
    _touch(known)
    _touch(new_nested)
    _touch(ignored)

    found = find_new_images(str(tmp_path), [str(known)])

    assert found == [str(new_nested)]


def test_find_new_images_can_limit_to_png(tmp_path):
    _touch(tmp_path / "a.png")
    _touch(tmp_path / "b.jpg")

    found = find_new_images(str(tmp_path), [], {".png"})

    assert found == [str(tmp_path / "a.png")]


def test_find_new_images_missing_folder_returns_empty(tmp_path):
    assert find_new_images(str(tmp_path / "nope"), []) == []
