"""Application-wide paths, vault configs and logging setup.

A *config* (:class:`VaultConfig`) is one named collection: its own JSON
database, an optional media folder (local or on a USB stick) and the settings
of its import plugins. All configs plus the last used one are stored
in ``~/.mediavault/configs.json`` (:data:`CONFIGS_PATH`), written with ``0600``
permissions because plugin settings may hold API credentials.

Reading is forgiving: unknown or malformed values fall back to safe defaults,
so a damaged file never prevents the app from starting. :func:`locate`
resolves where a config's media currently lives, which for stick configs
depends on whether the stick is plugged in.
"""

import json
import logging
import os
import re
from collections.abc import Iterable, Mapping
from dataclasses import asdict, fields
from typing import Any

from mediavault import volumes
from mediavault.models import MODE_AI, MODE_NORMAL, LibraryRoot, VaultConfig

logger = logging.getLogger(__name__)

APP_DIR = os.path.join(os.path.expanduser("~"), ".mediavault")
DEFAULT_DB_PATH = os.path.join(APP_DIR, "media_data.json")
CONFIGS_PATH = os.path.join(APP_DIR, "configs.json")


def config_from_dict(data: Mapping[str, Any]) -> VaultConfig:
    """Build a config from stored data, falling back to safe defaults.

    Missing names become "Unbenannt", unknown modes become
    :data:`MODE_NORMAL` and a missing database path becomes
    :data:`DEFAULT_DB_PATH`. Unknown keys are kept in ``extra``.

    Args:
        data: One entry of the ``"configs"`` list in ``configs.json``.

    Returns:
        The validated config.
    """
    mode = data.get("mode", MODE_NORMAL)
    return VaultConfig(
        name=str(data.get("name") or "Unbenannt"),
        mode=mode if mode in (MODE_NORMAL, MODE_AI) else MODE_NORMAL,
        db_path=str(data.get("db_path") or DEFAULT_DB_PATH),
        folder=str(data.get("folder") or ""),
        folder_last_sync=str(data.get("folder_last_sync") or ""),
        volume_uuid=str(data.get("volume_uuid") or ""),
        volume_label=str(data.get("volume_label") or ""),
        folder_rel=str(data.get("folder_rel") or ""),
        plugins=_plugin_settings(data.get("plugins")),
        extra={key: value for key, value in data.items() if key not in _KNOWN_KEYS},
    )


_KNOWN_KEYS = frozenset(f.name for f in fields(VaultConfig))


def _plugin_settings(value: Any) -> dict[str, dict]:
    """Return only string keys with dict values from the stored ``plugins``."""
    if not isinstance(value, Mapping):
        return {}
    return {
        key: dict(item)
        for key, item in value.items()
        if isinstance(key, str) and isinstance(item, Mapping)
    }


def _stored(config: VaultConfig) -> dict[str, Any]:
    """Return the JSON form of a config; unknown keys go back to the top level."""
    known = asdict(config)
    known.pop("extra")
    return {**config.extra, **known}


def int_setting(value: Any, default: int, minimum: int, maximum: int) -> int:
    """Return an integer setting clamped to a valid range.

    Args:
        value: Raw stored value of any type.
        default: Returned when ``value`` is not convertible to ``int``.
        minimum: Lowest allowed result.
        maximum: Highest allowed result.

    Returns:
        ``int(value)`` clamped to ``[minimum, maximum]``, or ``default``.
    """
    try:
        number = int(value)
    except (TypeError, ValueError):
        return default
    return min(max(number, minimum), maximum)


def _default_config() -> VaultConfig:
    """Return the config that keeps the original single library at the default path."""
    return VaultConfig("Meine Mediathek", MODE_NORMAL, DEFAULT_DB_PATH)


def load_configs(path: str = CONFIGS_PATH) -> tuple[list[VaultConfig], str]:
    """Load all configs and the database path of the last used one.

    An unreadable or malformed file is logged and treated as empty; the file
    itself is left untouched. Without any configs a default config is returned,
    so callers always get at least one entry.

    Args:
        path: Location of ``configs.json``.

    Returns:
        ``(configs, last_db_path)``; ``last_db_path`` always matches one of the
        returned configs.
    """
    data: Any = {}
    if os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, ValueError):
            logger.warning("Configs konnten nicht gelesen werden: %s", path)

    items = data.get("configs", []) if isinstance(data, dict) else []
    if not isinstance(items, list) or not all(
        isinstance(item, dict) for item in items
    ):
        logger.warning("Configs haben ein unerwartetes Format: %s", path)
        items = []
    configs = [config_from_dict(item) for item in items]
    if not configs:
        config = _default_config()
        return [config], config.db_path
    last = data.get("last", "")
    if last not in {config.db_path for config in configs}:
        last = configs[0].db_path
    return configs, last


def save_configs(
    configs: Iterable[VaultConfig], last: str, path: str = CONFIGS_PATH
) -> None:
    """Persist configs and the last used database path atomically.

    Writes to a temporary file created with ``0600`` permissions and replaces
    the target in one step, so a crash never leaves a half-written file and the
    API credentials stay private to the user.

    Args:
        configs: All configs to store.
        last: ``db_path`` of the config to open on the next start.
        path: Location of ``configs.json``.

    Raises:
        OSError: When the file cannot be written.
    """
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    data = {"last": last, "configs": [_stored(config) for config in configs]}
    tmp_path = f"{path}.tmp"
    # The file holds API credentials: keep it private to the user.
    fd = os.open(tmp_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    try:
        os.chmod(tmp_path, 0o600)
    except OSError:
        logger.debug("Rechte nicht setzbar: %s", tmp_path, exc_info=True)
    os.replace(tmp_path, path)


def _slug(name: str) -> str:
    """Turn a display name into a lowercase, dash-separated file name."""
    slug = re.sub(r"[^a-z0-9]+", "-", name.casefold()).strip("-")
    return slug or "config"


def create_config(
    name: str,
    mode: str,
    folder: str = "",
    existing: Iterable[VaultConfig] = (),
    base_dir: str | None = None,
    volume_uuid: str = "",
    volume_label: str = "",
    folder_rel: str = "",
) -> VaultConfig:
    """Create a config with a unique database path, without saving it.

    The database file name is derived from ``name`` and gets a ``-2``, ``-3``
    … suffix while it collides with an existing config.

    Args:
        name: Display name; surrounding whitespace is stripped.
        mode: :data:`MODE_NORMAL` or :data:`MODE_AI`; anything else is normal.
        folder: Absolute media folder for local configs.
        existing: Current configs, used to avoid database path collisions.
        base_dir: Directory for the database; ``~/.mediavault/data`` by default.
        volume_uuid: Stick identity for stick configs.
        volume_label: Stick name for stick configs.
        folder_rel: Media folder relative to the stick root.

    Returns:
        The new config; the caller adds it to the list and saves it.
    """
    base_dir = base_dir or os.path.join(APP_DIR, "data")
    used = {config.db_path for config in existing}
    slug = candidate = _slug(name)
    index = 2
    while os.path.join(base_dir, f"{candidate}.json") in used:
        candidate = f"{slug}-{index}"
        index += 1
    return VaultConfig(
        name=name.strip(),
        mode=mode if mode in (MODE_NORMAL, MODE_AI) else MODE_NORMAL,
        db_path=os.path.join(base_dir, f"{candidate}.json"),
        folder=folder,
        volume_uuid=volume_uuid,
        volume_label=volume_label,
        folder_rel=folder_rel,
    )


def locate(config: VaultConfig) -> LibraryRoot:
    """Resolve a config's volume mount and media folder with a single probe.

    Local configs return their folder directly. Stick configs search the
    mounted volumes for the matching marker; while the stick is unplugged an
    empty :class:`LibraryRoot` is returned.

    Args:
        config: The config to resolve.

    Returns:
        The current location of the config's media.
    """
    if not config.volume_uuid:
        return LibraryRoot(folder=config.folder)
    root = volumes.find_volume(config.volume_uuid)
    if not root:
        return LibraryRoot()
    return LibraryRoot(volume=root, folder=volumes.folder_path(root, config.folder_rel))


def setup_logging() -> None:
    """Configure root logging at INFO level with timestamps and logger names."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
