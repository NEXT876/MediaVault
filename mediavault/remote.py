"""Download plugin posts and import them into a library.

The core half of every import plugin: plugins only say *what* to download
(:class:`~mediavault.plugins.RemotePost`); this module checks URLs and IDs,
streams the files to disk and hands them to :func:`importer.import_paths`,
which skips duplicates. Qt-free; runs in the download queue's worker thread.
"""

import contextlib
import http.client
import os
import re
import urllib.parse
import urllib.request
from collections.abc import Callable
from typing import Any

from mediavault.config import APP_DIR
from mediavault.database import MediaDatabase
from mediavault.importer import import_paths
from mediavault.models import MODE_NORMAL, DownloadResult, MediaType, RemotePost
from mediavault.plugins import PluginError
from mediavault.scanner import is_video

USER_AGENT = "MediaVault/1.0"
_CHUNK = 1024 * 1024
_NET_ERRORS = (OSError, ValueError, http.client.HTTPException)
_SAFE_ID = re.compile(r"[A-Za-z0-9_-]{1,64}")


def _request(url: str) -> urllib.request.Request:
    """Return a request for ``url`` that identifies MediaVault as user agent."""
    return urllib.request.Request(url, headers={"User-Agent": USER_AGENT})


def _is_http(url: str) -> bool:
    return urllib.parse.urlsplit(url).scheme in ("http", "https")


def download_dir(config_folder: str, key: str) -> str:
    """Return ``<config folder>/<key>``, or ``~/.mediavault/downloads`` without folder."""
    if config_folder.strip():
        return os.path.join(config_folder, key)
    return os.path.join(APP_DIR, "downloads")


def _target_path(post: RemotePost, folder: str, key: str) -> str:
    """Return ``<key>_<id><ext>`` in ``folder``; odd extensions are dropped."""
    extension = os.path.splitext(urllib.parse.urlsplit(post.file_url).path)[1]
    extension = extension.casefold()
    if not re.fullmatch(r"\.[a-z0-9]{1,5}", extension):
        extension = ""
    return os.path.join(folder, f"{key}_{post.id}{extension}")


def download_post(
    post: RemotePost,
    folder: str,
    key: str,
    *,
    opener: Callable[..., Any] = urllib.request.urlopen,
) -> str:
    """Download one post to ``folder`` and return the local path.

    An existing non-empty file is reused. The download streams into a
    ``.part`` file that only replaces the target when complete, so an aborted
    download never looks finished.

    Raises:
        PluginError: When the post has an unsafe ID or no HTTP(S) file URL.
        OSError: On network or disk errors (the ``.part`` file is removed).
    """
    # The ID becomes part of a file name and comes from plugin code.
    if not isinstance(post.id, str) or not _SAFE_ID.fullmatch(post.id):
        raise PluginError("Post hat eine ungültige ID.")
    if not _is_http(post.file_url):
        raise PluginError(f"Post {post.id} hat keine gültige Datei-URL.")

    os.makedirs(folder, exist_ok=True)
    destination = _target_path(post, folder, key)
    if os.path.isfile(destination) and os.path.getsize(destination) > 0:
        return destination

    part_path = destination + ".part"
    try:
        with (
            opener(_request(post.file_url), timeout=30) as response,
            open(part_path, "wb") as out,
        ):
            while chunk := response.read(_CHUNK):
                out.write(chunk)
        os.replace(part_path, destination)
    except Exception:
        with contextlib.suppress(OSError):
            os.remove(part_path)
        raise
    return destination


def fetch_preview(
    url: str, *, opener: Callable[..., Any] = urllib.request.urlopen
) -> bytes | None:
    """Return thumbnail bytes, or None for non-HTTP URLs and network errors."""
    if not _is_http(url):
        return None
    try:
        with opener(_request(url), timeout=30) as response:
            return response.read()
    except _NET_ERRORS:
        return None


def download_and_import(
    db: MediaDatabase,
    posts: list[RemotePost],
    *,
    key: str,
    folder: str,
    selected_ids: set[str],
    fallback_group: str,
    root: str = "",
    opener: Callable[..., Any] = urllib.request.urlopen,
    progress: Callable[[int, int], None] | None = None,
) -> DownloadResult:
    """Download the selected posts and import them into ``db``.

    Files are grouped by ``post.group or fallback_group`` and media type and
    imported with :func:`importer.import_paths`, so duplicates are skipped
    there. A failed download is recorded and the run continues.

    Args:
        db: Database of the config the job belongs to.
        posts: All posts of the fetch.
        key: Plugin key; download subfolder and file name prefix.
        folder: Media folder of the config (see :func:`download_dir`).
        selected_ids: Post IDs the user picked.
        fallback_group: Group for posts without their own.
        root: Volume root of a stick library, so stored paths stay relative.
        opener: URL opener, replaceable in tests.
        progress: Called with ``(finished, total)`` after each file.
    """
    result = DownloadResult()
    destination = download_dir(folder, key)
    paths: dict[tuple[str, str], list[str]] = {}
    targets = [post for post in posts if post.id in selected_ids]
    for number, post in enumerate(targets, 1):
        try:
            path = download_post(post, destination, key, opener=opener)
        except (*_NET_ERRORS, PluginError) as exc:
            # One broken download must not abort the rest of the run.
            detail = str(exc) if isinstance(exc, PluginError) else type(exc).__name__
            result.failed.append(f"Post {post.id}: {detail}")
        else:
            media_type = MediaType.VIDEO if is_video(path) else MediaType.IMAGE
            paths.setdefault((post.group or fallback_group, media_type), []).append(
                path
            )
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
