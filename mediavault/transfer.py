"""Copy newly added media into a config's media folder.

When a config has a media folder, manually imported files are copied there
so the library is self-contained (e.g. on a stick). Content that is already
stored (same :func:`importer.content_hash`) is skipped, and name collisions
get a numeric suffix instead of overwriting.

Kept free of Qt so the same code can serve the GUI and a future CLI importer.
"""

import logging
import os
import shutil
from collections.abc import Iterable

from mediavault.importer import content_hash
from mediavault.models import CopyResult
from mediavault.volumes import is_inside

logger = logging.getLogger(__name__)


def unique_destination(folder: str, name: str) -> str:
    """Return a free path in ``folder``, adding -2, -3, ... on name collisions."""
    candidate = os.path.join(folder, name)
    stem, extension = os.path.splitext(name)
    index = 2
    while os.path.exists(candidate):
        candidate = os.path.join(folder, f"{stem}-{index}{extension}")
        index += 1
    return candidate


def copy_into_folder(
    paths: Iterable[str],
    folder: str,
    known_hashes: Iterable[str] = (),
) -> CopyResult:
    """Copy files into ``folder``, skipping content that is already stored.

    Files that already sit inside the folder are kept where they are, so a
    re-import never duplicates a library onto itself. ``shutil.copy2`` keeps
    file timestamps. If the folder cannot be created, every path fails.

    Args:
        paths: Source files.
        folder: Target media folder; created if missing.
        known_hashes: Content hashes already in the database.

    Returns:
        The copied paths, the number of skipped duplicates and the failures.
    """
    result = CopyResult()
    known = {value for value in known_hashes if value}
    try:
        os.makedirs(folder, exist_ok=True)
    except OSError:
        logger.warning("Could not create target folder: %s", folder, exc_info=True)
        result.failed.extend(paths)
        return result

    for path in paths:
        if is_inside(path, folder):
            result.copied.append(path)
            continue
        try:
            digest = content_hash(path)
        except OSError:
            result.failed.append(path)
            continue
        if digest in known:
            result.skipped += 1
            continue
        destination = unique_destination(folder, os.path.basename(path))
        try:
            shutil.copy2(path, destination)
        except OSError:
            logger.warning("Copy failed: %s", path, exc_info=True)
            result.failed.append(path)
            continue
        known.add(digest)
        result.copied.append(destination)
    return result
