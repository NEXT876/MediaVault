"""Tests for copying new media into a config folder."""

import os

from mediavault.importer import content_hash
from mediavault.transfer import copy_into_folder, is_inside, unique_destination


def _write(path, payload=b"data"):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    return str(path)


def test_copies_a_file_into_the_folder(tmp_path):
    source = _write(tmp_path / "inbox" / "a.png")
    target = tmp_path / "library"

    result = copy_into_folder([source], str(target))

    assert result.skipped == 0
    assert result.copied == [str(target / "a.png")]
    assert os.path.isfile(result.copied[0])
    # The source is left alone.
    assert os.path.isfile(source)


def test_skips_content_that_is_already_known(tmp_path):
    source = _write(tmp_path / "inbox" / "a.png", b"same")
    target = tmp_path / "library"

    result = copy_into_folder([source], str(target), {content_hash(source)})

    assert result.skipped == 1
    assert result.copied == []
    assert not (target / "a.png").exists()


def test_second_copy_of_the_same_run_is_skipped(tmp_path):
    first = _write(tmp_path / "inbox" / "a.png", b"same")
    second = _write(tmp_path / "inbox" / "b.png", b"same")
    target = tmp_path / "library"

    result = copy_into_folder([first, second], str(target))

    assert len(result.copied) == 1
    assert result.skipped == 1


def test_name_collision_gets_a_suffix(tmp_path):
    target = tmp_path / "library"
    _write(target / "a.png", b"old")
    source = _write(tmp_path / "inbox" / "a.png", b"new")

    result = copy_into_folder([source], str(target))

    assert result.copied == [str(target / "a-2.png")]
    assert (target / "a.png").read_bytes() == b"old"
    assert (target / "a-2.png").read_bytes() == b"new"


def test_file_already_inside_the_folder_is_kept(tmp_path):
    target = tmp_path / "library"
    inside = _write(target / "a.png", b"x")

    result = copy_into_folder([inside], str(target))

    assert result.copied == [inside]
    assert os.listdir(target) == ["a.png"]


def test_missing_source_is_reported_as_failure(tmp_path):
    result = copy_into_folder([str(tmp_path / "nope.png")], str(tmp_path / "lib"))

    assert result.copied == []
    assert len(result.failed) == 1
    assert "nope.png" in str(result.failed[0])


def test_unique_destination_counts_up(tmp_path):
    _write(tmp_path / "a.png", b"1")
    _write(tmp_path / "a-2.png", b"2")

    assert unique_destination(str(tmp_path), "a.png") == str(tmp_path / "a-3.png")


def test_is_inside_handles_prefix_lookalikes(tmp_path):
    folder = tmp_path / "lib"
    inside = _write(folder / "a.png")
    outside = _write(tmp_path / "lib2" / "a.png")

    assert is_inside(inside, str(folder))
    assert not is_inside(outside, str(folder))
    assert not is_inside(inside, "")
