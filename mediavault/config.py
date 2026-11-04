"""Application-wide paths, vault configs and logging setup.

A *config* (:class:`VaultConfig`) is one named collection: its own JSON
database, an optional media folder (local or on a USB stick) and the state of
the optional rule34 integration. All configs plus the last used one are stored
in ``~/.mediavault/configs.json`` (:data:`CONFIGS_PATH`), written with ``0600``
permissions because it holds API credentials.

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
from dataclasses import asdict, dataclass, field
from typing import Any

from mediavault import volumes

logger = logging.getLogger(__name__)

APP_DIR = os.path.join(os.path.expanduser("~"), ".mediavault")
DEFAULT_DB_PATH = os.path.join(APP_DIR, "media_data.json")
CONFIGS_PATH = os.path.join(APP_DIR, "configs.json")
MODE_NORMAL = "normal"
MODE_AI = "ai"


@dataclass
class Rule34Settings:
    """Credentials and search state of the optional rule34 integration.

    Attributes:
        api_key: rule34 API key, sent with every API request.
        user_id: rule34 user ID belonging to the API key.
        tags: Last entered tag query (one query per line).
        count: Number of new posts to fetch per query, 1-1000.
        webm: True to only fetch videos (``webm`` posts).
        last_ids: Newest post ID already downloaded per query signature, so
            the next run only fetches newer posts.
        saved_tags: Named tag presets, ``{name: tag query}``.
    """

    api_key: str = ""
    user_id: str = ""
    tags: str = ""
    count: int = 10
    webm: bool = False
    last_ids: dict[str, int] = field(default_factory=dict)
    saved_tags: dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any], prefix: str = "") -> "Rule34Settings":
        """Build settings from stored data, validating every field.

        Args:
            data: Stored mapping, either the nested ``"rule34"`` object or a whole
                config dict from older files.
            prefix: Key prefix to read; ``"rule34_"`` reads the old flat keys.

        Returns:
            Settings with invalid values replaced by defaults.
        """

        def get(key: str) -> Any:
            """Read one setting, honoring the key prefix."""
            return data.get(prefix + key)

        return cls(
            api_key=str(get("api_key") or ""),
            user_id=str(get("user_id") or ""),
            tags=str(get("tags") or ""),
            count=int_setting(get("count"), 10, 1, 1000),
            webm=_bool_setting(get("webm")),
            last_ids=_last_ids(get("last_ids")),
            saved_tags=_saved_tags(get("saved_tags")),
        )


@dataclass
class VaultConfig:
    """A named collection with its own database and optional media folder.

    Attributes:
        name: Display name shown in the config switcher.
        mode: :data:`MODE_NORMAL` for any images and videos, :data:`MODE_AI`
            for AI-generated PNGs that carry generation metadata.
        db_path: Path of the JSON database (:class:`MediaDatabase`).
        folder: Absolute media folder for local configs; empty otherwise.
        folder_last_sync: Human-readable time of the last folder sync.
        volume_uuid: Identity of the stick the media lives on (from its
            ``.mediavault-vault`` marker); empty for local configs.
        volume_label: Stick name shown to the user while it is unplugged.
        folder_rel: Media folder relative to the stick root.
        rule34: Settings of the rule34 integration.
    """

    name: str
    mode: str = MODE_NORMAL
    db_path: str = ""
    folder: str = ""
    folder_last_sync: str = ""
    # Set for configs whose media lives on a removable volume; folder_rel is
    # then the location inside that volume, not an absolute path.
    volume_uuid: str = ""
    volume_label: str = ""
    folder_rel: str = ""
    rule34: Rule34Settings = field(default_factory=Rule34Settings)

    @property
    def is_ai(self) -> bool:
        """Return True for configs that only hold AI images with metadata."""
        return self.mode == MODE_AI

    @property
    def has_folder(self) -> bool:
        """Return True when the config manages a media folder, local or on a stick."""
        return bool(self.folder.strip() or self.volume_uuid)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "VaultConfig":
        """Build a config from stored data, falling back to safe defaults.

        Missing names become "Unbenannt", unknown modes become
        :data:`MODE_NORMAL` and a missing database path becomes
        :data:`DEFAULT_DB_PATH`. Files written before :class:`Rule34Settings`
        existed keep the rule34 values as flat ``rule34_*`` keys; they are still read.

        Args:
            data: One entry of the ``"configs"`` list in ``configs.json``.

        Returns:
            The validated config.
        """
        mode = data.get("mode", MODE_NORMAL)
        nested = data.get("rule34")
        rule34 = (
            Rule34Settings.from_dict(nested)
            if isinstance(nested, Mapping)
            else Rule34Settings.from_dict(data, prefix="rule34_")
        )
        return cls(
            name=str(data.get("name") or "Unbenannt"),
            mode=mode if mode in (MODE_NORMAL, MODE_AI) else MODE_NORMAL,
            db_path=str(data.get("db_path") or DEFAULT_DB_PATH),
            folder=str(data.get("folder") or ""),
            folder_last_sync=str(data.get("folder_last_sync") or ""),
            volume_uuid=str(data.get("volume_uuid") or ""),
            volume_label=str(data.get("volume_label") or ""),
            folder_rel=str(data.get("folder_rel") or ""),
            rule34=rule34,
        )


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


def _bool_setting(value: Any) -> bool:
    """Return a boolean setting; accepts JSON booleans, 1 and "true"/"yes"."""
    if isinstance(value, str):
        return value.strip().casefold() in {"1", "true", "yes"}
    if isinstance(value, bool):
        return value
    return isinstance(value, (int, float)) and value == 1


def _last_ids(value: Any) -> dict[str, int]:
    """Return only string keys with positive integer IDs from a stored mapping."""
    if not isinstance(value, Mapping):
        return {}
    result: dict[str, int] = {}
    for key, raw in value.items():
        if not isinstance(key, str):
            continue
        try:
            number = int(raw)
        except (TypeError, ValueError):
            continue
        if number > 0:
            result[key] = number
    return result


def _saved_tags(value: Any) -> dict[str, str]:
    """Return only named, non-empty tag presets from stored data."""
    if not isinstance(value, Mapping):
        return {}
    return {
        name: tags
        for name, tags in value.items()
        if isinstance(name, str)
        and name.strip()
        and isinstance(tags, str)
        and tags.strip()
    }


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
    configs = [VaultConfig.from_dict(item) for item in items]
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
    data = {"last": last, "configs": [asdict(config) for config in configs]}
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


@dataclass(frozen=True)
class LibraryRoot:
    """Where a config's media lives right now.

    Attributes:
        volume: Mount point that stored paths are relative to; empty for
            local configs, whose paths are absolute.
        folder: Directory to scan for media; empty while a stick is unplugged
            or when the config has no folder.
    """

    volume: str = ""
    folder: str = ""

    @property
    def available(self) -> bool:
        """Return True when the media folder can be read right now."""
        return bool(self.folder)


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
