import http.client
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
    collect_new_posts_multi,
    download_and_import,
    download_post,
    fetch_and_import,
    fetch_posts,
    fetch_preview,
    fetch_tag_suggestions,
    parse_posts,
    query_signature,
    select_new_posts,
    split_queries,
    tag_at,
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


def test_split_queries_returns_one_normalized_query_per_line():
    text = "  Cat   Dog \n\n cat dog\nfoo\n  \n"

    assert split_queries(text) == ["Cat Dog", "foo"]


def test_tag_at_returns_word_around_cursor():
    text = "cat dog\nfox"

    assert tag_at(text, 5) == ("dog", 4, 7)
    assert tag_at(text, 4) == ("dog", 4, 7)
    assert tag_at(text, 3) == ("cat", 0, 3)
    assert tag_at(text, 99) == ("fox", 8, 11)


def test_fetch_tag_suggestions_queries_autocomplete_without_credentials():
    calls = []
    payload = [
        {"label": "cat_ears (207855)", "value": "cat_ears"},
        {"label": "catalogue (12)", "value": "catalogue"},
        {"label": "broken"},
        {"label": "duplicate", "value": "cat_ears"},
        "junk",
    ]

    names = fetch_tag_suggestions("cat", opener=_json_opener(payload, calls))

    assert names == ["cat_ears", "catalogue"]
    url = urllib.parse.urlsplit(calls[0])
    assert url.path == "/autocomplete.php"
    query = urllib.parse.parse_qs(url.query)
    assert query == {"q": ["cat"]}


def test_fetch_tag_suggestions_respects_limit():
    payload = [{"value": f"tag{i}"} for i in range(20)]

    names = fetch_tag_suggestions("ta", limit=3, opener=_json_opener(payload))

    assert names == ["tag0", "tag1", "tag2"]


def test_fetch_tag_suggestions_skips_short_or_namespaced_prefix():
    def unused(request, timeout=None):
        raise AssertionError("no request expected")

    assert fetch_tag_suggestions("c", opener=unused) == []
    assert fetch_tag_suggestions("cat:xyz", opener=unused) == []


def test_fetch_tag_suggestions_returns_empty_on_errors():
    def failing(request, timeout=None):
        raise OSError("no network")

    assert fetch_tag_suggestions("cat", opener=failing) == []
    assert fetch_tag_suggestions("cat", opener=_bytes_opener(b"not json")) == []
    assert fetch_tag_suggestions("cat", opener=_json_opener({"bad": "shape"})) == []


def test_collect_new_posts_multi_uses_each_line_last_id(monkeypatch):
    requested = []

    def fake_fetch(api_key, user_id, tags, webm, limit, *, opener=None):
        requested.append((tags, limit))
        if tags == "cat":
            return [Post(10, "https://x/cat.png"), Post(4, "https://x/old.png")]
        return [Post(20, "https://x/dog.png")]

    monkeypatch.setattr(rule34, "fetch_posts", fake_fetch)
    last_ids = {
        query_signature("cat", False): 5,
        query_signature("dog", False): 15,
    }

    posts, newest_ids = collect_new_posts_multi(
        "key", "42", "cat\ndog", False, 3, last_ids
    )

    assert requested == [("cat", 3), ("dog", 3)]
    assert [(post.id, post.group) for post in posts] == [(20, "dog"), (10, "cat")]
    assert newest_ids == {
        query_signature("cat", False): 10,
        query_signature("dog", False): 20,
    }


def test_collect_new_posts_multi_advances_lines_before_dedupe(monkeypatch):
    def fake_fetch(api_key, user_id, tags, webm, limit, *, opener=None):
        if tags == "cat":
            return [Post(12, "https://x/shared.png")]
        return [Post(12, "https://x/shared.png"), Post(11, "https://x/b.png")]

    monkeypatch.setattr(rule34, "fetch_posts", fake_fetch)

    posts, newest_ids = collect_new_posts_multi(
        "key", "42", "cat\ndog", False, 10, {}
    )

    # The first line owns a post that both lines returned.
    assert [(post.id, post.group) for post in posts] == [(12, "cat"), (11, "dog")]
    assert newest_ids[query_signature("cat", False)] == 12
    assert newest_ids[query_signature("dog", False)] == 12


def test_collect_new_posts_multi_fetches_equivalent_lines_once(monkeypatch):
    requested = []

    def fake_fetch(api_key, user_id, tags, webm, limit, *, opener=None):
        requested.append(tags)
        return [Post(5, "https://x/a.png")]

    monkeypatch.setattr(rule34, "fetch_posts", fake_fetch)

    posts, newest_ids = collect_new_posts_multi(
        "key", "42", "cat dog\ndog cat", False, 10, {}
    )

    assert requested == ["cat dog"]
    assert [(post.id, post.group) for post in posts] == [(5, "cat dog")]
    assert newest_ids == {query_signature("cat dog", False): 5}


def test_query_signature_ignores_order_and_spacing():
    assert query_signature("Cat   Dog", False) == query_signature("dog cat", False)
    assert query_signature("cat sort:score:desc", False) == query_signature(
        "cat", False
    )
    assert query_signature("cat", True) != query_signature("cat", False)


def test_select_new_posts_filters_sorts_and_limits():
    posts = [Post(5, "a"), Post(10, "b"), Post(7, "c"), Post(3, "d")]

    selected = select_new_posts(posts, 5, 10)
    assert [post.id for post in selected] == [10, 7]

    assert [post.id for post in select_new_posts(posts, 0, 2)] == [10, 7]


def test_parse_posts_skips_broken_entries():
    payload = [
        {
            "id": "7",
            "file_url": "https://example.test/a.png",
            "preview_url": "https://example.test/a.jpg",
        },
        {"id": "bad", "file_url": "https://example.test/b.png"},
        {"id": 8, "file_url": ""},
        "not a post",
    ]

    posts = parse_posts(payload)

    assert [(post.id, post.file_url, post.preview_url) for post in posts] == [
        (7, "https://example.test/a.png", "https://example.test/a.jpg")
    ]


def test_parse_posts_rejects_error_response():
    with pytest.raises(Rule34Error):
        parse_posts({"success": False, "message": "API error"})


def test_parse_posts_surfaces_string_message():
    with pytest.raises(Rule34Error, match="Missing authentication"):
        parse_posts("Missing authentication.")


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


def test_fetch_posts_requires_api_key():
    def unused(request, timeout=None):
        raise AssertionError("no request without an API key")

    with pytest.raises(Rule34Error):
        fetch_posts("", "42", "cat", False, 5, opener=unused)


def test_fetch_preview_returns_bytes():
    data = fetch_preview(
        "https://example.test/thumb.jpg", opener=_bytes_opener(b"thumb")
    )

    assert data == b"thumb"


def test_fetch_preview_returns_none_on_error_or_bad_scheme():
    def failing(request, timeout=None):
        raise OSError("no network")

    def unused(request, timeout=None):
        raise AssertionError("non-http URLs must not be opened")

    assert fetch_preview("https://example.test/thumb.jpg", opener=failing) is None
    assert fetch_preview("file:///etc/passwd", opener=unused) is None
    assert fetch_preview("ftp://example.test/a.jpg", opener=unused) is None


def test_fetch_posts_wraps_truncated_response():
    def failing(request, timeout=None):
        raise http.client.IncompleteRead(b"partial")

    with pytest.raises(Rule34Error):
        fetch_posts("secret-key", "42", "cat", False, 5, opener=failing)


def test_download_post_writes_file_and_leaves_no_part_file(tmp_path):
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


def test_download_and_import_only_downloads_selected(tmp_path, monkeypatch):
    db = MediaDatabase(str(tmp_path / "db.json"))
    posts = [
        Post(5, "https://example.test/a.png"),
        Post(4, "https://example.test/b.png"),
    ]
    downloaded = []

    def fake_download(post, folder, **kwargs):
        downloaded.append(post.id)
        os.makedirs(folder, exist_ok=True)
        path = os.path.join(folder, f"rule34_{post.id}.png")
        with open(path, "wb") as f:
            f.write(b"image")
        return path

    monkeypatch.setattr(rule34, "download_post", fake_download)

    result = download_and_import(
        db, posts, folder=str(tmp_path), tags="cat", selected_ids={4}
    )

    assert downloaded == [4]
    assert result.imported == 1
    # Deselected posts are still marked as seen.
    assert result.newest_id == 5


def test_download_and_import_reports_progress_after_each_file(tmp_path, monkeypatch):
    db = MediaDatabase(str(tmp_path / "db.json"))
    posts = [
        Post(2, "https://example.test/a.png"),
        Post(1, "https://example.test/b.png"),
    ]
    events = []

    def fake_download(post, folder, **kwargs):
        events.append(f"file{post.id}")
        os.makedirs(folder, exist_ok=True)
        path = os.path.join(folder, f"rule34_{post.id}.png")
        with open(path, "wb") as f:
            f.write(b"image")
        return path

    monkeypatch.setattr(rule34, "download_post", fake_download)

    download_and_import(
        db,
        posts,
        folder=str(tmp_path),
        tags="cat",
        selected_ids={1, 2},
        progress=lambda done, total: events.append(f"done{done}of{total}"),
    )

    assert events == ["file2", "done1of2", "file1", "done2of2"]


def test_download_and_import_groups_per_source_query(tmp_path, monkeypatch):
    db = MediaDatabase(str(tmp_path / "db.json"))
    posts = [
        Post(3, "https://example.test/a.png", group="cat"),
        Post(2, "https://example.test/b.png", group="dog"),
        Post(1, "https://example.test/c.png"),
    ]

    def fake_download(post, folder, **kwargs):
        os.makedirs(folder, exist_ok=True)
        path = os.path.join(folder, f"rule34_{post.id}.png")
        with open(path, "wb") as f:
            f.write(f"image{post.id}".encode())
        return path

    monkeypatch.setattr(rule34, "download_post", fake_download)

    result = download_and_import(
        db, posts, folder=str(tmp_path), tags="cat\n  dog  "
    )

    assert result.imported == 3
    assert {entry.group for entry in db.entries} == {"cat", "dog", "cat dog"}


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


def test_download_and_import_stores_stick_paths_relative(tmp_path):
    stick = tmp_path / "stick"
    db = MediaDatabase(str(tmp_path / "db.json"))

    result = download_and_import(
        db,
        [Post(7, "https://x/seven.png")],
        folder=str(stick / "media"),
        tags="cat",
        root=str(stick),
        opener=_bytes_opener(b"png-bytes"),
    )

    assert result.imported == 1
    assert db.entries[0].image_path == "media/rule34/rule34_7.png"


def test_fetch_posts_with_previews_keeps_only_loaded_thumbnails(monkeypatch):
    posts = [Post(2, "https://x/a.png"), Post(1, "https://x/b.png")]
    posts[0].preview_url = "https://x/a_thumb.jpg"
    monkeypatch.setattr(
        rule34, "collect_new_posts_multi", lambda *args, **kwargs: (posts, {"cat": 2})
    )
    monkeypatch.setattr(
        rule34,
        "fetch_preview",
        lambda url, **kwargs: b"thumb" if url.endswith("a_thumb.jpg") else None,
    )

    found, previews, newest = rule34.fetch_posts_with_previews(
        "key", "1", "cat", False, 5, {}
    )

    assert found == posts
    assert previews == {2: b"thumb"}
    assert newest == {"cat": 2}
