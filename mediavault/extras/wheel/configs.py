"""Named entry lists ("configs") of the wheel of fortune, stored as JSON.

The file ``~/.mediavault/wheel_configs.json`` maps a config name to its list
of wheel entries. Reading drops anything malformed; saving is atomic and
moves an unparsable file aside instead of overwriting it.
"""

import json
import logging
import os
from collections.abc import Mapping
from typing import Any

from mediavault.config import APP_DIR
from mediavault.jsonio import write_json_atomic

logger = logging.getLogger(__name__)

WHEEL_CONFIGS_PATH = os.path.join(APP_DIR, "wheel_configs.json")


def _clean(data: Any) -> dict[str, list[str]]:
    """Keep only named configs whose entries are non-empty strings, all stripped."""
    if not isinstance(data, Mapping):
        return {}
    result: dict[str, list[str]] = {}
    for name, entries in data.items():
        valid = isinstance(name, str) and name.strip() and isinstance(entries, list)
        if not valid:
            continue
        cleaned = [e.strip() for e in entries if isinstance(e, str) and e.strip()]
        if cleaned:
            result[name.strip()] = cleaned
    return result


def load_wheel_configs(path: str = WHEEL_CONFIGS_PATH) -> dict[str, list[str]]:
    """Load the saved configs.

    Returns:
        ``{name: entries}``; empty when the file is missing or unreadable.
    """
    try:
        with open(path, encoding="utf-8") as f:
            return _clean(json.load(f))
    except FileNotFoundError:
        return {}
    except (OSError, ValueError):
        logger.warning("Could not read wheel configs: %s", path)
        return {}


def save_wheel_configs(
    configs: Mapping[str, list[str]], path: str = WHEEL_CONFIGS_PATH
) -> None:
    """Persist the configs atomically.

    A file that cannot be parsed is moved to ``<path>.corrupt`` first instead
    of being silently overwritten.

    Raises:
        OSError: When the file cannot be written.
    """
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    if os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as f:
                json.load(f)
        except (OSError, ValueError):
            os.replace(path, f"{path}.corrupt")
    write_json_atomic(path, _clean(configs))


def matching_config(configs: Mapping[str, list[str]], entries: list[str]) -> str | None:
    """Return the name of a config with exactly these entries in this order, if any."""
    return next((name for name, saved in configs.items() if saved == entries), None)
