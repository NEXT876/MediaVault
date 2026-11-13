"""Crash-safe JSON writing shared by every file MediaVault stores."""

import json
import os
from contextlib import suppress
from typing import Any


def write_json_atomic(
    path: str, data: Any, *, indent: int = 2, private: bool = False
) -> None:
    """Write ``data`` as JSON so ``path`` is always either the old or the new file.

    The data goes to ``<path>.tmp``, is flushed to the disk with ``fsync`` and
    then replaces ``path`` in one step. Without the ``fsync`` a pulled stick or
    a power cut right after the replace can leave an empty file.

    Args:
        path: Target file; its folder must exist.
        data: JSON-serializable value.
        indent: Indentation of the written JSON.
        private: Create the file with ``0600`` permissions (API credentials).

    Raises:
        OSError: When the file cannot be written.
    """
    tmp_path = f"{path}.tmp"
    fd = os.open(
        tmp_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600 if private else 0o666
    )
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=indent)
        f.flush()
        os.fsync(f.fileno())
    if private:
        # O_CREAT keeps the mode of an existing leftover temp file.
        with suppress(OSError):
            os.chmod(tmp_path, 0o600)
    os.replace(tmp_path, path)
