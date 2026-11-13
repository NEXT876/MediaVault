"""Tests for downloading and importing plugin posts (mediavault.remote)."""

import os

import pytest

from mediavault import remote
from mediavault.config import APP_DIR
from mediavault.database import MediaDatabase
from mediavault.models import FetchResult, RemotePost
from mediavault.plugins import run_fetch
from mediavault.remote import (
    download_and_import,
    download_dir,
    download_post,
    fetch_preview,
)


class _Response:
    """Minimal urlopen response with context-manager and read support."""

    def __init__(self, data: bytes) -> None:
        self._data = data

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self, size: int = -1) -> bytes:
        if size < 0:
            data, self._data = self._data, b""
            return data
        chunk, self._data = self._data[:size], self._data[size:]
        return chunk


def _opener(contents, calls=None):
    """Serve ``contents[url]``; record every opened URL in ``calls``."""

    def opener(request, timeout=None):
        if calls is not None:
            calls.append(request.full_url)
        if request.full_url not in contents:
            raise OSError("not found")
        return _Response(contents[request.full_url])

    return opener


def _never(request, timeout=None):
    raise AssertionError("must not be opened")


def _post(post_id, url=None, group=""):
    return RemotePost(post_id, url or f"https://h/{post_id}.png", group=group)


def test_download_dir():
    assert download_dir("/m", "src") == os.path.join("/m", "src")
    assert download_dir("  ", "src") == os.path.join(APP_DIR, "downloads")


def test_file_name_uses_key_and_id(tmp_path):
    post = RemotePost("42", "https://h/files/a.JPG")
    path = download_post(
        post, str(tmp_path), "src", opener=_opener({post.file_url: b"x"})
    )
    assert path == str(tmp_path / "src_42.jpg")


def test_download_post_writes_file_and_leaves_no_part_file(tmp_path):
    post = _post("7")
    path = download_post(
        post, str(tmp_path), "src", opener=_opener({post.file_url: b"image"})
    )
    with open(path, "rb") as f:
        assert f.read() == b"image"
    assert not os.path.exists(path + ".part")


def test_download_post_removes_part_file_on_error(tmp_path):
    def failing(request, timeout=None):
        raise OSError("down")

    with pytest.raises(OSError):
        download_post(_post("7"), str(tmp_path), "src", opener=failing)
    assert os.listdir(tmp_path) == []


def test_download_post_keeps_existing_file(tmp_path):
    destination = tmp_path / "src_7.png"
    destination.write_bytes(b"old")
    path = download_post(_post("7"), str(tmp_path), "src", opener=_never)
    assert path == str(destination)
    assert destination.read_bytes() == b"old"


@pytest.mark.parametrize("url", ["ftp://h/a.png", "file:///etc/passwd", "a.png"])
def test_rejects_non_http_urls(tmp_path, url):
    db = MediaDatabase(str(tmp_path / "db.json"))
    result = download_and_import(
        db,
        [_post("1", url)],
        key="src",
        folder=str(tmp_path),
        selected_ids={"1"},
        fallback_group="g",
        opener=_never,
    )
    assert len(result.failed) == 1
    assert result.imported == 0


@pytest.mark.parametrize("post_id", ["../x", "", "a/b", "x" * 65, "a\\b", "a.b"])
def test_rejects_unsafe_ids(tmp_path, post_id):
    db = MediaDatabase(str(tmp_path / "db.json"))
    media = tmp_path / "media"
    result = download_and_import(
        db,
        [_post(post_id, "https://h/a.png")],
        key="src",
        folder=str(media),
        selected_ids={post_id},
        fallback_group="g",
        opener=_never,
    )
    assert len(result.failed) == 1
    written = [name for _, _, names in os.walk(tmp_path) for name in names]
    assert written in ([], ["db.json"])


def test_download_and_import_only_downloads_selected(tmp_path):
    db = MediaDatabase(str(tmp_path / "db.json"))
    posts = [_post("5"), _post("4")]
    calls = []
    contents = {p.file_url: p.id.encode() for p in posts}
    result = download_and_import(
        db,
        posts,
        key="src",
        folder=str(tmp_path),
        selected_ids={"4"},
        fallback_group="g",
        opener=_opener(contents, calls),
    )
    assert calls == ["https://h/4.png"]
    assert result.imported == 1


def test_download_and_import_groups_and_media_types(tmp_path):
    db = MediaDatabase(str(tmp_path / "db.json"))
    posts = [
        _post("3", "https://h/a.webm", group="cat"),
        _post("2", "https://h/b.png", group="dog"),
        _post("1", "https://h/c.png"),
    ]
    contents = {p.file_url: p.id.encode() for p in posts}
    result = download_and_import(
        db,
        posts,
        key="src",
        folder=str(tmp_path),
        selected_ids={"1", "2", "3"},
        fallback_group="search",
        opener=_opener(contents),
    )
    assert result.imported == 3
    groups = {(entry.group, entry.entry_type) for entry in db.entries}
    assert groups == {("cat", "Videos"), ("dog", "Bilder"), ("search", "Bilder")}


def test_download_and_import_reports_progress_and_keeps_going(tmp_path):
    db = MediaDatabase(str(tmp_path / "db.json"))
    posts = [_post("2"), _post("1")]
    events = []
    result = download_and_import(
        db,
        posts,
        key="src",
        folder=str(tmp_path),
        selected_ids={"1", "2"},
        fallback_group="g",
        opener=_opener({"https://h/1.png": b"one"}),
        progress=lambda done, total: events.append((done, total)),
    )
    assert events == [(1, 2), (2, 2)]
    assert result.imported == 1
    assert result.failed == ["Post 2: OSError"]


def test_fetch_preview_returns_bytes_or_none():
    def failing(request, timeout=None):
        raise OSError("no network")

    assert (
        fetch_preview("https://h/t.jpg", opener=_opener({"https://h/t.jpg": b"t"}))
        == b"t"
    )
    assert fetch_preview("https://h/t.jpg", opener=failing) is None
    assert fetch_preview("file:///etc/passwd", opener=_never) is None
    assert fetch_preview("", opener=_never) is None


class _Source:
    name = "Quelle"

    def configure(self, parent, settings):
        return True

    def fetch(self, settings):
        return FetchResult(posts=[_post("1"), _post("2")], label="suche")


def test_end_to_end_with_dummy_plugin_detects_duplicates(tmp_path):
    db = MediaDatabase(str(tmp_path / "db.json"))
    contents = {"https://h/1.png": b"one", "https://h/2.png": b"two"}
    result, _previews = run_fetch(_Source(), {}, lambda url: None)

    def run():
        return download_and_import(
            db,
            result.posts,
            key="quelle",
            folder=str(tmp_path / "media"),
            selected_ids={p.id for p in result.posts},
            fallback_group=result.label,
            opener=_opener(contents),
        )

    first = run()
    second = run()
    assert (first.imported, first.duplicates) == (2, 0)
    assert (second.imported, second.duplicates) == (0, 2)
    assert {entry.group for entry in db.entries} == {"suche"}
    assert remote.USER_AGENT == "MediaVault/1.0"


def test_download_and_import_stores_stick_paths_relative(tmp_path):
    stick = tmp_path / "stick"
    db = MediaDatabase(str(tmp_path / "db.json"))
    result = download_and_import(
        db,
        [_post("7", "https://x/seven.png")],
        key="src",
        folder=str(stick / "media"),
        selected_ids={"7"},
        fallback_group="g",
        root=str(stick),
        opener=_opener({"https://x/seven.png": b"png-bytes"}),
    )
    assert result.imported == 1
    assert db.entries[0].image_path == "media/src/src_7.png"


def test_non_string_id_only_fails_that_post(tmp_path):
    db = MediaDatabase(str(tmp_path / "db.json"))
    posts = [RemotePost(5, "https://h/5.png"), _post("6")]
    result = download_and_import(
        db,
        posts,
        key="src",
        folder=str(tmp_path),
        selected_ids={5, "6"},
        fallback_group="g",
        opener=_opener({"https://h/6.png": b"six"}),
    )
    assert result.imported == 1
    assert len(result.failed) == 1
