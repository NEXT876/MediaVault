"""rule34.xxx API client, downloader and importer (without Qt).

Flow of one import run, driven by the GUI (:mod:`mediavault.gui.rule34_dialog`
and :mod:`mediavault.gui.downloads`):

1. The tag field holds one search per line (:func:`split_queries`). For each
   line the newest posts are requested (:func:`fetch_posts`) and only those
   newer than the last imported post ID of that search are kept
   (:func:`collect_new_posts_multi`). Searches are identified by
   :func:`query_signature`, so tag order does not matter.
2. Optionally the thumbnails are fetched for a selection dialog
   (:func:`fetch_posts_with_previews`).
3. The chosen posts are downloaded into the config's ``rule34`` folder and
   imported with the search line as group (:func:`download_and_import`).

All network functions take an ``opener`` (default ``urllib.request.urlopen``)
so tests can inject fake responses. Network errors become
:class:`Rule34Error` with a German message; the request URL is never shown
because it contains the API key.
"""

import contextlib
import http.client
import json
import os
import re
import urllib.parse
import urllib.request
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

from mediavault.config import APP_DIR, MODE_NORMAL, int_setting
from mediavault.importer import import_paths
from mediavault.models import MediaDatabase, MediaType
from mediavault.scanner import is_video

API_URL = "https://api.rule34.xxx/index.php"
AUTOCOMPLETE_URL = "https://api.rule34.xxx/autocomplete.php"
USER_AGENT = "MediaVault/1.0"
_MAX_LIMIT = 1000
_CHUNK = 1024 * 1024
_SUGGESTION_TIMEOUT = 5
_NET_ERRORS = (OSError, ValueError, http.client.HTTPException)


class Rule34Error(Exception):
    """A request or response that rule34 could not satisfy; the message is user-facing.
    """


@dataclass
class Post:
    """One rule34 post with the fields needed for downloading.

    Attributes:
        id: Post ID; higher IDs are newer.
        file_url: URL of the full image or video.
        preview_url: URL of the small thumbnail.
        group: Search line the post was found with; becomes the entry group.
    """

    id: int
    file_url: str
    preview_url: str = ""
    group: str = ""


@dataclass
class Rule34Result:
    """Counts and state from one fetch-and-import run.

    Attributes:
        imported: Entries added to the database.
        duplicates: Downloaded files that were already in the database.
        failed: One message per post that could not be downloaded.
        newest_id: Highest post ID seen in this run; store it so the next run
            only fetches newer posts.
    """

    imported: int = 0
    duplicates: int = 0
    failed: list[str] = field(default_factory=list)
    newest_id: int = 0


def _normalized_tags(tags: str) -> str:
    """Collapse runs of whitespace in a tag string to single spaces."""
    return " ".join(tags.split())


def _clamp_limit(limit: int) -> int:
    """Clamp a post count to the range the API accepts (1-1000, default 10)."""
    return int_setting(limit, 10, 1, _MAX_LIMIT)


def _request(url: str) -> urllib.request.Request:
    """Return a request for ``url`` that identifies MediaVault as user agent."""
    return urllib.request.Request(url, headers={"User-Agent": USER_AGENT})


def split_queries(text: str) -> list[str]:
    """Return one normalized query per non-empty, unique line.

    Duplicate lines are compared case-insensitively; the first spelling wins.
    """
    queries: list[str] = []
    seen: set[str] = set()
    for line in text.splitlines():
        query = _normalized_tags(line)
        key = query.casefold()
        if query and key not in seen:
            seen.add(key)
            queries.append(query)
    return queries


def tag_at(text: str, position: int) -> tuple[str, int, int]:
    """Return the whitespace-delimited tag around a cursor position.

    Used by the tag autocompletion to know which word to complete.

    Returns:
        ``(tag, start, end)`` with the tag's slice bounds in ``text``.
    """
    position = min(max(position, 0), len(text))
    start = position
    while start > 0 and not text[start - 1].isspace():
        start -= 1
    end = position
    while end < len(text) and not text[end].isspace():
        end += 1
    return text[start:end], start, end


def fetch_tag_suggestions(
    prefix: str,
    *,
    limit: int = 10,
    opener: Callable[..., Any] = urllib.request.urlopen,
) -> list[str]:
    """Return existing tag names that start with ``prefix``.

    Uses the public autocomplete endpoint, so no credentials are needed.
    Prefixes shorter than two characters and meta tags containing ``:`` are not
    looked up. Failures are silent because suggestions are optional.

    Returns:
        Up to ``limit`` unique tag names.
    """
    prefix = prefix.strip()
    if len(prefix) < 2 or ":" in prefix:
        return []
    params = urllib.parse.urlencode({"q": prefix})
    request = _request(f"{AUTOCOMPLETE_URL}?{params}")
    try:
        with opener(request, timeout=_SUGGESTION_TIMEOUT) as response:
            payload = json.load(response)
    except _NET_ERRORS:
        return []
    if not isinstance(payload, list):
        return []
    names = (
        str(item.get("value") or "").strip()
        for item in payload
        if isinstance(item, Mapping)
    )
    return list(dict.fromkeys(name for name in names if name))[: _clamp_limit(limit)]


def query_signature(tags: str, webm: bool) -> str:
    """Return a key for the actual search, independent of tag order and case."""
    tokens = build_query(tags, webm).split(" ")
    return "|".join(
        sorted(token.casefold() for token in tokens if token != "sort:id:desc")
    )


def build_query(tags: str, webm: bool) -> str:
    """Build the ``tags`` value for a newest-first rule34 request.

    User ``sort:`` tokens are dropped and ``sort:id:desc`` is appended, so the
    "newer than last ID" logic always sees the newest posts. With ``webm`` only
    videos are requested.
    """
    tokens = [
        token
        for token in _normalized_tags(tags).split(" ")
        if token and not token.casefold().startswith("sort:")
    ]
    if webm:
        tokens.append("webm")
    tokens.append("sort:id:desc")
    return " ".join(tokens)


def parse_posts(payload: Any) -> list[Post]:
    """Turn an API response into posts, rejecting error responses.

    Items without a positive ID or a file URL are skipped.

    Raises:
        Rule34Error: When the API answered with an error string, an error
            object or anything that is not a list.
    """
    if isinstance(payload, str):
        # Rejected credentials arrive as a bare JSON string.
        raise Rule34Error(payload.strip() or "rule34 hat die Anfrage abgelehnt.")
    if isinstance(payload, Mapping):
        message = payload.get("message") or "rule34 hat die Anfrage abgelehnt."
        raise Rule34Error(str(message))
    if not isinstance(payload, list):
        raise Rule34Error("Unerwartete Antwort von rule34.")

    posts: list[Post] = []
    for item in payload:
        if not isinstance(item, Mapping):
            continue
        try:
            post_id = int(item.get("id"))
        except (TypeError, ValueError):
            continue
        file_url = str(item.get("file_url") or "").strip()
        if post_id <= 0 or not file_url:
            continue
        preview_url = str(item.get("preview_url") or "").strip()
        posts.append(Post(post_id, file_url, preview_url))
    return posts


def fetch_posts(
    api_key: str,
    user_id: str,
    tags: str,
    webm: bool,
    limit: int,
    *,
    opener: Callable[..., Any] = urllib.request.urlopen,
) -> list[Post]:
    """Request the newest posts for one tag search.

    Args:
        api_key: rule34 API key.
        user_id: rule34 user ID.
        tags: Space-separated tags of one search.
        webm: True to request videos only.
        limit: Number of posts to request (clamped to 1-1000).
        opener: URL opener, replaceable in tests.

    Returns:
        The parsed posts, newest first as returned by the API.

    Raises:
        Rule34Error: When credentials or tags are missing, the API is not
            reachable or it rejects the request.
    """
    api_key = api_key.strip()
    user_id = str(user_id).strip()
    if not api_key or not user_id or not _normalized_tags(tags):
        raise Rule34Error("API-Key, User-ID und Tags sind erforderlich.")

    params = {
        "page": "dapi",
        "s": "post",
        "q": "index",
        "json": "1",
        "tags": build_query(tags, webm),
        "pid": "0",
        "limit": str(_clamp_limit(limit)),
        "api_key": api_key,
        "user_id": user_id,
    }
    request = _request(f"{API_URL}?{urllib.parse.urlencode(params)}")
    try:
        with opener(request, timeout=30) as response:
            payload = json.load(response)
    except _NET_ERRORS:
        # Never surface the request URL, which contains the API key.
        raise Rule34Error("rule34 ist nicht erreichbar.") from None
    return parse_posts(payload)


def select_new_posts(posts: list[Post], last_id: int, limit: int) -> list[Post]:
    """Return the newest posts above ``last_id``, newest first, capped at ``limit``."""
    limit = _clamp_limit(limit)
    fresh = sorted(
        (post for post in posts if post.id > last_id),
        key=lambda post: post.id,
        reverse=True,
    )
    return fresh[:limit]


def collect_new_posts(
    api_key: str,
    user_id: str,
    tags: str,
    webm: bool,
    limit: int,
    last_id: int,
    *,
    opener: Callable[..., Any] = urllib.request.urlopen,
) -> list[Post]:
    """Fetch one search and return the posts it has not imported yet."""
    return select_new_posts(
        fetch_posts(api_key, user_id, tags, webm, limit, opener=opener),
        last_id,
        limit,
    )


def collect_new_posts_multi(
    api_key: str,
    user_id: str,
    tags: str,
    webm: bool,
    limit: int,
    last_ids: Mapping[str, int],
    *,
    opener: Callable[..., Any] = urllib.request.urlopen,
) -> tuple[list[Post], dict[str, int]]:
    """Fetch new posts for every query line.

    Lines with the same :func:`query_signature` are only fetched once. Each post
    gets the line it was found with as ``group``; a post found by several lines
    keeps the first.

    Args:
        last_ids: Newest imported post ID per query signature.
        (other args as in :func:`fetch_posts`)

    Returns:
        The posts (deduplicated across lines, newest first) and the newest post
        ID per line signature. IDs are recorded before deduplication so every
        line advances even when another line already supplied the same post.

    Raises:
        Rule34Error: As :func:`fetch_posts`; one failing line aborts the run.
    """
    posts: dict[int, Post] = {}
    newest_ids: dict[str, int] = {}
    seen: set[str] = set()
    for query in split_queries(tags):
        signature = query_signature(query, webm)
        # Tag order and sort tokens do not change the search.
        if signature in seen:
            continue
        seen.add(signature)
        fresh = collect_new_posts(
            api_key,
            user_id,
            query,
            webm,
            limit,
            last_ids.get(signature, 0),
            opener=opener,
        )
        if fresh:
            newest_ids[signature] = max(post.id for post in fresh)
        for post in fresh:
            post.group = query
            posts.setdefault(post.id, post)
    return sorted(posts.values(), key=lambda post: post.id, reverse=True), newest_ids


def fetch_preview(
    url: str, *, opener: Callable[..., Any] = urllib.request.urlopen
) -> bytes | None:
    """Return the thumbnail bytes for one post.

    Returns:
        The image bytes, or None for non-HTTP URLs and network errors.
    """
    if urllib.parse.urlsplit(url).scheme not in ("http", "https"):
        return None
    try:
        with opener(_request(url), timeout=30) as response:
            return response.read()
    except _NET_ERRORS:
        return None


def fetch_posts_with_previews(
    api_key: str,
    user_id: str,
    tags: str,
    webm: bool,
    limit: int,
    last_ids: Mapping[str, int],
    *,
    opener: Callable[..., Any] = urllib.request.urlopen,
) -> tuple[list[Post], dict[int, bytes], dict[str, int]]:
    """Fetch new posts plus their thumbnails for the selection dialog.

    Returns:
        ``(posts, previews by post ID, newest IDs by signature)``; posts without
        a loadable thumbnail are missing from the previews.
    """
    posts, newest_ids = collect_new_posts_multi(
        api_key, user_id, tags, webm, limit, last_ids, opener=opener
    )
    previews: dict[int, bytes] = {}
    for post in posts:
        data = fetch_preview(post.preview_url, opener=opener)
        if data:
            previews[post.id] = data
    return posts, previews, newest_ids


def download_dir(config_folder: str) -> str:
    """Return the download folder for a config.

    ``<config folder>/rule34`` for configs with a folder, else
    ``~/.mediavault/downloads``.
    """
    if config_folder.strip():
        return os.path.join(config_folder, "rule34")
    return os.path.join(APP_DIR, "downloads")


def _target_path(post: Post, folder: str) -> str:
    """Return the destination ``rule34_<id><ext>``; odd extensions are dropped."""
    extension = os.path.splitext(urllib.parse.urlsplit(post.file_url).path)[1]
    extension = extension.casefold()
    if not re.fullmatch(r"\.[a-z0-9]{1,5}", extension):
        extension = ""
    return os.path.join(folder, f"rule34_{post.id}{extension}")


def download_post(
    post: Post,
    folder: str,
    *,
    opener: Callable[..., Any] = urllib.request.urlopen,
) -> str:
    """Download one post to ``folder`` and return the local path.

    An existing non-empty file is reused. The download streams into a
    ``.part`` file that only replaces the target when complete, so an aborted
    download never looks finished.

    Raises:
        Rule34Error: When the post has no HTTP(S) file URL.
        OSError: On network or disk errors (the ``.part`` file is removed).
    """
    scheme = urllib.parse.urlsplit(post.file_url).scheme
    if scheme not in ("http", "https"):
        raise Rule34Error(f"Post {post.id} hat keine gültige Datei-URL.")

    os.makedirs(folder, exist_ok=True)
    destination = _target_path(post, folder)
    if os.path.isfile(destination) and os.path.getsize(destination) > 0:
        return destination

    request = _request(post.file_url)
    part_path = destination + ".part"
    try:
        with opener(request, timeout=30) as response, open(part_path, "wb") as out:
            while chunk := response.read(_CHUNK):
                out.write(chunk)
        os.replace(part_path, destination)
    except Exception:
        with contextlib.suppress(OSError):
            os.remove(part_path)
        raise
    return destination


def download_and_import(
    db: MediaDatabase,
    posts: list[Post],
    *,
    folder: str,
    tags: str,
    selected_ids: set[int] | None = None,
    root: str = "",
    opener: Callable[..., Any] = urllib.request.urlopen,
    progress: Callable[[int, int], None] | None = None,
) -> Rule34Result:
    """Download and import ``posts``, optionally only those in ``selected_ids``.

    Files are grouped by search line and media type and imported with
    :func:`importer.import_paths`, so duplicates are skipped there. A failed
    download is recorded and the run continues with the next post.

    Args:
        db: Database of the active config.
        posts: Posts from :func:`collect_new_posts_multi`.
        folder: Media folder of the config (see :func:`download_dir`).
        tags: Tag text; used as group for posts without their own.
        selected_ids: Post IDs the user picked; None downloads all.
        root: Volume root of a stick library, so stored paths stay relative.
        opener: URL opener, replaceable in tests.
        progress: Called with ``(finished, total)`` after each file,
            successful or not.

    Returns:
        Counts and failures; ``newest_id`` covers all fetched posts, so
        deselected posts are not offered again on the next run.
    """
    result = Rule34Result()
    if not posts:
        return result

    result.newest_id = max(post.id for post in posts)
    destination = download_dir(folder)
    fallback_group = _normalized_tags(tags)
    paths: dict[tuple[str, str], list[str]] = {}
    targets = [
        post
        for post in posts
        if selected_ids is None or post.id in selected_ids
    ]
    for number, post in enumerate(targets, 1):
        try:
            path = download_post(post, destination, opener=opener)
        except (*_NET_ERRORS, Rule34Error) as exc:
            # One broken download must not abort the rest of the run.
            detail = str(exc) if isinstance(exc, Rule34Error) else type(exc).__name__
            result.failed.append(f"Post {post.id}: {detail}")
        else:
            media_type = MediaType.VIDEO if is_video(path) else MediaType.IMAGE
            key = (post.group or fallback_group, media_type)
            paths.setdefault(key, []).append(path)
        if progress is not None:
            progress(number, len(targets))

    for (group, media_type), type_paths in paths.items():
        imported = import_paths(
            db,
            type_paths,
            type_str=media_type,
            group=group,
            mode=MODE_NORMAL,
            root=root,
        )
        result.imported += imported.added
        result.duplicates += imported.duplicates
    return result


def fetch_and_import(
    db: MediaDatabase,
    *,
    folder: str,
    tags: str,
    api_key: str,
    user_id: str,
    last_id: int,
    limit: int,
    webm: bool,
    opener: Callable[..., Any] = urllib.request.urlopen,
) -> Rule34Result:
    """Fetch the newest posts of one search, download them and add them to the db.

    Download failures are collected in ``failed``; callers must not advance
    their stored ID in that case.

    Raises:
        Rule34Error: When the search request fails.
    """
    posts = collect_new_posts(
        api_key, user_id, tags, webm, limit, last_id, opener=opener
    )
    return download_and_import(db, posts, folder=folder, tags=tags, opener=opener)
