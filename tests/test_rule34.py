import json
import os
import urllib.parse

import pytest

from mediavault import rule34
from mediavault.models import MediaDatabase
from mediavault.rule34 import (
    Post,
    Rule34Error,
    build_query,
    download_post,
    fetch_and_import,
    fetch_posts,
    parse_posts,
    query_signature,
    select_new_posts,
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


def _json_opener(payload, calls=None):
    def opener(request, timeout=None):
        if calls is not None:
            calls.append(request.full_url)
        return _Response(json.dumps(payload).encode())

    return opener


def _bytes_opener(data):
    def opener(request, timeout=None):
        return _Response(data)

    return opener


def test_build_query_adds_webm_and_newest_sort():
    assert build_query("  cat   dog ", False) == "cat dog sort:id:desc"
    assert build_query("cat", True) == "cat webm sort:id:desc"


def test_build_query_drops_user_sort_tokens():
    assert build_query("cat sort:score:desc", False) == "cat sort:id:desc"


def test_query_signature_ignores_order_and_spacing():
    assert query_signature("Cat   Dog", False) == query_signature("cat dog", False)
    assert query_signature("cat", True) != query_signature("cat", False)


def test_select_new_posts_filters_sorts_and_limits():
    posts = [Post(5, "a"), Post(10, "b"), Post(7, "c"), Post(3, "d")]

    selected = select_new_posts(posts, 5, 10)
    assert [post.id for post in selected] == [10, 7]

    assert [post.id for post in select_new_posts(posts, 0, 2)] == [10, 7]


def test_parse_posts_skips_broken_entries():
    payload = [
        {"id": "7", "file_url": "https://example.test/a.png", "tags": "cat"},
        {"id": "bad", "file_url": "https://example.test/b.png"},
        {"id": 8, "file_url": ""},
        "not a post",
    ]

    posts = parse_posts(payload)

    assert [(post.id, post.file_url) for post in posts] == [
        (7, "https://example.test/a.png")
    ]


def test_parse_posts_rejects_error_response():
    with pytest.raises(Rule34Error):
        parse_posts({"success": False, "message": "API error"})


def test_fetch_posts_sends_credentials_and_search():
    calls = []
    payload = [{"id": 9, "file_url": "https://example.test/a.webm"}]

    posts = fetch_posts(
        "secret-key", "42", "cat dog", True, 5, opener=_json_opener(payload, calls)
    )

    assert [post.id for post in posts] == [9]
    query = urllib.parse.parse_qs(urllib.parse.urlsplit(calls[0]).query)
    assert query["api_key"] == ["secret-key"]
    assert query["user_id"] == ["42"]
    assert query["json"] == ["1"]
    assert query["limit"] == ["5"]
    assert query["pid"] == ["0"]
    assert query["tags"] == ["cat dog webm sort:id:desc"]


def test_fetch_posts_error_does_not_leak_key():
    def failing(request, timeout=None):
        raise OSError("connection failed")

    with pytest.raises(Rule34Error) as error:
        fetch_posts("secret-key", "42", "cat", False, 5, opener=failing)

    assert "secret-key" not in str(error.value)


def test_download_post_writes_file_atomically(tmp_path):
    post = Post(7, "https://example.test/files/abc.PNG")

    path = download_post(post, str(tmp_path), opener=_bytes_opener(b"image"))

    assert path == str(tmp_path / "rule34_7.png")
    with open(path, "rb") as f:
        assert f.read() == b"image"
    assert not os.path.exists(path + ".part")


def test_download_post_keeps_existing_file(tmp_path):
    destination = tmp_path / "rule34_7.png"
    destination.write_bytes(b"old")

    def failing(request, timeout=None):
        raise AssertionError("existing file must not be downloaded again")

    post = Post(7, "https://example.test/files/abc.png")
    path = download_post(post, str(tmp_path), opener=failing)

    assert path == str(destination)
    assert destination.read_bytes() == b"old"


def test_fetch_and_import_adds_both_media_types(tmp_path, monkeypatch):
    db = MediaDatabase(str(tmp_path / "db.json"))
    posts = [
        Post(2, "https://example.test/newest.webm"),
        Post(1, "https://example.test/image.png"),
    ]
    contents = {
        "https://example.test/newest.webm": b"video",
        "https://example.test/image.png": b"image",
    }
    monkeypatch.setattr(rule34, "fetch_posts", lambda *args, **kwargs: posts)

    def fake_download(post, folder, **kwargs):
        os.makedirs(folder, exist_ok=True)
        path = os.path.join(folder, os.path.basename(post.file_url))
        with open(path, "wb") as f:
            f.write(contents[post.file_url])
        return path

    monkeypatch.setattr(rule34, "download_post", fake_download)

    result = fetch_and_import(
        db,
        folder=str(tmp_path),
        tags="cat",
        api_key="key",
        user_id="42",
        last_id=0,
        limit=10,
        webm=False,
    )

    assert result.imported == 2
    assert result.failed == []
    assert result.newest_id == 2
    types = {entry.entry_type for entry in db.entries}
    assert types == {"Bilder", "Videos"}
    assert {entry.group for entry in db.entries} == {"cat"}


def test_fetch_and_import_records_failed_downloads(tmp_path, monkeypatch):
    db = MediaDatabase(str(tmp_path / "db.json"))
    posts = [Post(3, "https://example.test/broken.png"), Post(2, "https://x/ok.png")]
    monkeypatch.setattr(rule34, "fetch_posts", lambda *args, **kwargs: posts)

    def fake_download(post, folder, **kwargs):
        if post.id == 3:
            raise OSError("disk full")
        os.makedirs(folder, exist_ok=True)
        path = os.path.join(folder, "rule34_2.png")
        with open(path, "wb") as f:
            f.write(b"image")
        return path

    monkeypatch.setattr(rule34, "download_post", fake_download)

    result = fetch_and_import(
        db,
        folder=str(tmp_path),
        tags="cat",
        api_key="key",
        user_id="42",
        last_id=0,
        limit=10,
        webm=False,
    )

    assert result.imported == 1
    assert result.newest_id == 3
    assert len(result.failed) == 1
    assert "Post 3" in result.failed[0]


def test_fetch_and_import_returns_empty_below_last_id(tmp_path, monkeypatch):
    db = MediaDatabase(str(tmp_path / "db.json"))
    monkeypatch.setattr(
        rule34, "fetch_posts", lambda *args, **kwargs: [Post(5, "https://x/a.png")]
    )

    result = fetch_and_import(
        db,
        folder=str(tmp_path),
        tags="cat",
        api_key="key",
        user_id="42",
        last_id=5,
        limit=10,
        webm=False,
    )

    assert result.imported == 0
    assert result.newest_id == 0
    assert db.entries == []
