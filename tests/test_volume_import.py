"""Relative-path storage for volume configs."""

from mediavault import volumes
from mediavault.config import MODE_NORMAL
from mediavault.importer import import_paths
from mediavault.models import MediaDatabase


def _write(path, payload=b"x"):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    return str(path)


def test_import_stores_paths_relative_to_the_volume(tmp_path):
    root = tmp_path / "stick"
    image = _write(root / "Bilder" / "a.png")
    db = MediaDatabase(str(tmp_path / "db.json"))

    result = import_paths(
        db, [image], type_str="Bilder", group="", mode=MODE_NORMAL, root=str(root)
    )

    assert result.added == 1
    assert db.entries[0].image_path == "Bilder/a.png"


def test_import_skips_a_file_that_is_already_stored(tmp_path):
    root = tmp_path / "stick"
    image = _write(root / "a.png")
    db = MediaDatabase(str(tmp_path / "db.json"))
    import_paths(
        db, [image], type_str="Bilder", group="", mode=MODE_NORMAL, root=str(root)
    )

    again = import_paths(
        db, [image], type_str="Bilder", group="", mode=MODE_NORMAL, root=str(root)
    )

    assert again.added == 0
    assert again.duplicates == 1


def test_import_without_root_keeps_absolute_paths(tmp_path):
    image = _write(tmp_path / "a.png")
    db = MediaDatabase(str(tmp_path / "db.json"))

    import_paths(db, [image], type_str="Bilder", group="", mode=MODE_NORMAL)

    assert db.entries[0].image_path == image


def test_entry_resolves_back_to_the_original_file(tmp_path):
    root = tmp_path / "stick"
    image = _write(root / "a.png")
    db = MediaDatabase(str(tmp_path / "db.json"))
    import_paths(
        db, [image], type_str="Bilder", group="", mode=MODE_NORMAL, root=str(root)
    )

    entry = db.entries[0]

    assert volumes.absolute_path(entry.image_path, str(root)) == image
