"""rule34.xxx API client, downloader and importer (without Qt)."""

import http.client
import json
import os
import re
import urllib.parse
import urllib.request
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

from mediavault.config import MODE_NORMAL
from mediavault.importer import import_paths
from mediavault.models import MediaDatabase, MediaType
from mediavault.scanner import is_video

API_URL = "https://api.rule34.xxx/index.php"
AUTOCOMPLETE_URL = "https://api.rule34.xxx/autocomplete.php"
USER_AGENT = "MediaVault/1.0"
_MAX_LIMIT = 1000
_CHUNK = 1024 * 1024
_SUGGESTION_TIMEOUT = 5


class Rule34Error(Exception):
    """A request or response that rule34 could not satisfy."""


@dataclass
class Post:
    """One rule34 post with the fields needed for downloading."""

    id: int
    file_url: str
    preview_url: str = ""
    group: str = ""


@dataclass
class Rule34Result:
    """Counts and state from one fetch-and-import run."""

    imported: int = 0
    duplicates: int = 0
    failed: list[str] = field(default_factory=list)
    newest_id: int = 0


def _normalized_tags(tags: str) -> str:
    """Collapse whitespace in a tag string."""
    return " ".join(tags.split())


def _clamp_limit(limit: int) -> int:
    """Clamp a post count to the range the API accepts."""
    try:
        number = int(limit)
    except (TypeError, ValueError):
        number = 10
    return min(max(number, 1), _MAX_LIMIT)


def split_queries(text: str) -> list[str]:
    """Return one normalized query per non-empty, unique line."""
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
    """Return the whitespace-delimited tag around a cursor position."""
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
    Failures are silent because suggestions are optional.
    """
    prefix = prefix.strip()
    if len(prefix) < 2 or ":" in prefix:
        return []
    params = urllib.parse.urlencode({"q": prefix})
    request = urllib.request.Request(
        f"{AUTOCOMPLETE_URL}?{params}",
        headers={"User-Agent": USER_AGENT},
    )
    try:
        with opener(request, timeout=_SUGGESTION_TIMEOUT) as response:
            payload = json.load(response)
    except (OSError, ValueError, http.client.HTTPException):
        return []
    if not isinstance(payload, list):
        return []

    names: list[str] = []
    for item in payload:
        if not isinstance(item, Mapping):
            continue
        name = str(item.get("value") or "").strip()
        if name and name not in names:
            names.append(name)
    return names[: _clamp_limit(limit)]


def query_signature(tags: str, webm: bool) -> str:
    """Return a key for the actual search, independent of tag order."""
    tokens = build_query(tags, webm).split(" ")
    return "|".join(
        sorted(token.casefold() for token in tokens if token != "sort:id:desc")
    )


def build_query(tags: str, webm: bool) -> str:
    """Build the tags value for a newest-first rule34 request."""
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
    """Turn an API response into posts, rejecting error responses."""
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
    """Request the newest posts for a tag search."""
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
    request = urllib.request.Request(
        f"{API_URL}?{urllib.parse.urlencode(params)}",
        headers={"User-Agent": USER_AGENT},
    )
    try:
        with opener(request, timeout=30) as response:
            payload = json.load(response)
    except (OSError, ValueError, http.client.HTTPException):
        # Never surface the request URL, which contains the API key.
        raise Rule34Error("rule34 ist nicht erreichbar.") from None
    return parse_posts(payload)


def select_new_posts(posts: list[Post], last_id: int, limit: int) -> list[Post]:
    """Return the newest posts above ``last_id``, capped at ``limit``."""
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
    """Return the newest posts the search has not imported yet."""
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

    Returns the posts (deduplicated across lines, newest first) and the newest
    post ID per line signature. IDs are recorded before deduplication so every
    line advances even when another line already supplied the same post.
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
    """Return the thumbnail bytes for one post, or None if unavailable."""
    if urllib.parse.urlsplit(url).scheme not in ("http", "https"):
        return None
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with opener(request, timeout=30) as response:
            return response.read()
    except (OSError, ValueError, http.client.HTTPException):
        return None


def download_dir(config_folder: str) -> str:
    """Return the download folder for a config."""
    if config_folder.strip():
        return os.path.join(config_folder, "rule34")
    return os.path.join(os.path.expanduser("~"), ".mediavault", "downloads")


def _target_path(post: Post, folder: str) -> str:
    """Return the destination file name for a post."""
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
    """Download one post to ``folder`` and return the local path."""
    scheme = urllib.parse.urlsplit(post.file_url).scheme
    if scheme not in ("http", "https"):
        raise Rule34Error(f"Post {post.id} hat keine gültige Datei-URL.")

    os.makedirs(folder, exist_ok=True)
    destination = _target_path(post, folder)
    if os.path.isfile(destination) and os.path.getsize(destination) > 0:
        return destination

    request = urllib.request.Request(
        post.file_url, headers={"User-Agent": USER_AGENT}
    )
    part_path = destination + ".part"
    try:
        with opener(request, timeout=30) as response, open(part_path, "wb") as out:
            while chunk := response.read(_CHUNK):
                out.write(chunk)
        os.replace(part_path, destination)
    except Exception:
        try:
            os.remove(part_path)
        except OSError:
            pass
        raise
    return destination


def download_and_import(
    db: MediaDatabase,
    posts: list[Post],
    *,
    folder: str,
    tags: str,
    selected_ids: set[int] | None = None,
    opener: Callable[..., Any] = urllib.request.urlopen,
    progress: Callable[[int, int], None] | None = None,
) -> Rule34Result:
    """Download and import ``posts``, optionally only those in ``selected_ids``.

    ``newest_id`` covers all fetched posts, so deselected posts are not shown
    again on the next run. ``progress`` is called with the number of finished
    files and the total after each file, successful or not.
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
        except (OSError, ValueError, http.client.HTTPException, Rule34Error) as exc:
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
    """Fetch the newest posts, download them and add them to the database.

    Download failures are collected in ``failed``; callers must not advance
    their stored ID in that case.
    """
    posts = collect_new_posts(
        api_key, user_id, tags, webm, limit, last_id, opener=opener
    )
    return download_and_import(db, posts, folder=folder, tags=tags, opener=opener)
