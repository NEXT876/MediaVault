"""Named entry lists ("configs") of the wheel of fortune, stored as JSON."""

import json
import logging
import os
from collections.abc import Mapping
from typing import Any

logger = logging.getLogger(__name__)

WHEEL_CONFIGS_PATH = os.path.join(
    os.path.expanduser("~"), ".mediavault", "wheel_configs.json"
)


def _clean(data: Any) -> dict[str, list[str]]:
    """Keep only named configs whose entries are non-empty strings."""
    if not isinstance(data, Mapping):
        return {}
    result: dict[str, list[str]] = {}
    for name, entries in data.items():
        if not isinstance(name, str) or not name.strip():
            continue
        if not isinstance(entries, list):
            continue
        cleaned = [e.strip() for e in entries if isinstance(e, str) and e.strip()]
        if cleaned:
            result[name.strip()] = cleaned
    return result


def load_wheel_configs(path: str = WHEEL_CONFIGS_PATH) -> dict[str, list[str]]:
    """Load the saved configs; a missing or unreadable file yields none."""
    try:
        with open(path, encoding="utf-8") as f:
            return _clean(json.load(f))
    except FileNotFoundError:
        return {}
    except (OSError, ValueError):
        logger.warning("Glücksrad-Configs konnten nicht gelesen werden: %s", path)
        return {}


def save_wheel_configs(
    configs: Mapping[str, list[str]], path: str = WHEEL_CONFIGS_PATH
) -> None:
    """Persist the configs atomically.

    A file that cannot be parsed is moved to ``<path>.corrupt`` first instead
    of being silently overwritten.
    """
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    if os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as f:
                json.load(f)
        except (OSError, ValueError):
            os.replace(path, f"{path}.corrupt")
    tmp_path = f"{path}.tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(_clean(configs), f, ensure_ascii=False, indent=2)
    os.replace(tmp_path, path)


def matching_config(configs: Mapping[str, list[str]], entries: list[str]) -> str | None:
    """Return the name of a config with exactly these entries, if any."""
    for name, saved in configs.items():
        if saved == entries:
            return name
    return None
