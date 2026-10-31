"""Application-wide paths, vault configs and logging setup."""

import json
import logging
import os
import re
from collections.abc import Iterable, Mapping
from dataclasses import asdict, dataclass, field
from typing import Any

from mediavault import volumes

logger = logging.getLogger(__name__)

DEFAULT_DB_PATH = os.path.join(
    os.path.expanduser("~"), ".mediavault", "media_data.json"
)
CONFIGS_PATH = os.path.join(os.path.expanduser("~"), ".mediavault", "configs.json")
MODE_NORMAL = "normal"
MODE_AI = "ai"
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".bmp", ".webp"}
VIDEO_EXTS = {".mp4", ".mkv", ".avi", ".mov", ".webm", ".m4v", ".wmv"}


@dataclass
class VaultConfig:
    """A named collection with its own database and optional scan folder."""

    name: str
    mode: str = MODE_NORMAL
    db_path: str = ""
    folder: str = ""
    rule34_api_key: str = ""
    rule34_user_id: str = ""
    rule34_tags: str = ""
    rule34_count: int = 10
    rule34_webm: bool = False
    rule34_last_ids: dict[str, int] = field(default_factory=dict)
    # Appended last so existing positional construction keeps working.
    folder_last_sync: str = ""
    rule34_saved_tags: dict[str, str] = field(default_factory=dict)
    # Set for configs whose media lives on a removable volume; folder_rel is
    # then the location inside that volume, not an absolute path.
    volume_uuid: str = ""
    volume_label: str = ""
    folder_rel: str = ""

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "VaultConfig":
        """Build a config from stored data, falling back to safe defaults."""
        mode = data.get("mode", MODE_NORMAL)
        return cls(
            name=str(data.get("name") or "Unbenannt"),
            mode=mode if mode in (MODE_NORMAL, MODE_AI) else MODE_NORMAL,
            db_path=str(data.get("db_path") or DEFAULT_DB_PATH),
            folder=str(data.get("folder") or ""),
            rule34_api_key=str(data.get("rule34_api_key") or ""),
            rule34_user_id=str(data.get("rule34_user_id") or ""),
            rule34_tags=str(data.get("rule34_tags") or ""),
            rule34_count=_int_setting(data.get("rule34_count"), 10, 1, 1000),
            rule34_webm=_bool_setting(data.get("rule34_webm")),
            rule34_last_ids=_last_ids(data.get("rule34_last_ids")),
            folder_last_sync=str(data.get("folder_last_sync") or ""),
            rule34_saved_tags=_saved_tags(data.get("rule34_saved_tags")),
            volume_uuid=str(data.get("volume_uuid") or ""),
            volume_label=str(data.get("volume_label") or ""),
            folder_rel=str(data.get("folder_rel") or ""),
        )


def _int_setting(value: Any, default: int, minimum: int, maximum: int) -> int:
    """Return an integer setting clamped to a valid range."""
    try:
        number = int(value)
    except (TypeError, ValueError):
        return default
    return min(max(number, minimum), maximum)


def _bool_setting(value: Any) -> bool:
    """Return a boolean setting, accepting common JSON and string forms."""
    if isinstance(value, str):
        return value.strip().casefold() in {"1", "true", "yes"}
    if isinstance(value, bool):
        return value
    return isinstance(value, (int, float)) and value == 1


def _last_ids(value: Any) -> dict[str, int]:
    """Return only positive integer IDs from a stored mapping."""
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
    """Return the config that keeps the existing library available."""
    return VaultConfig("Meine Mediathek", MODE_NORMAL, DEFAULT_DB_PATH)


def load_configs(path: str = CONFIGS_PATH) -> tuple[list[VaultConfig], str]:
    """Load configs and the db_path of the last used one."""
    if not os.path.exists(path):
        config = _default_config()
        return [config], config.db_path
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        logger.warning("Configs konnten nicht gelesen werden: %s", path)
        config = _default_config()
        return [config], config.db_path

    items = data.get("configs", []) if isinstance(data, dict) else []
    if not isinstance(items, list) or not all(
        isinstance(item, dict) for item in items
    ):
        logger.warning("Configs haben ein unerwartetes Format: %s", path)
        config = _default_config()
        return [config], config.db_path
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
    """Persist configs and the last used db_path atomically."""
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    data = {"last": last, "configs": [asdict(config) for config in configs]}
    tmp_path = f"{path}.tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp_path, path)


def _slug(name: str) -> str:
    """Turn a display name into a lowercase file name."""
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
    """Create a config with a unique database path, without saving it."""
    base_dir = base_dir or os.path.join(os.path.expanduser("~"), ".mediavault", "data")
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


def is_volume_config(config: VaultConfig) -> bool:
    """Return True if the config's media lives on a removable volume."""
    return bool(config.volume_uuid)


def storage_root(config: VaultConfig) -> str:
    """Return the root stored paths are relative to, or '' when unplugged."""
    if not config.volume_uuid:
        return ""
    return volumes.find_volume(config.volume_uuid)


def resolve_folder(config: VaultConfig) -> str:
    """Return the config's media folder, or '' when its volume is unplugged."""
    if config.volume_uuid:
        root = storage_root(config)
        if not root:
            return ""
        return volumes.resolve(root, config.folder_rel) if config.folder_rel else root
    return config.folder


def find_new_media(
    folder: str,
    known_paths: Iterable[str],
    *,
    image_exts: Iterable[str] = IMAGE_EXTS,
    video_exts: Iterable[str] = VIDEO_EXTS,
    root: str = "",
) -> tuple[list[str], list[str]]:
    """Return the images and videos in folder that are not yet known.

    Known paths are compared through volumes.path_key, so entries stored
    relative to a volume still match the absolute paths found on disk.
    """
    if not os.path.isdir(folder):
        logger.warning("Ordner nicht gefunden: %s", folder)
        return [], []
    known = {volumes.path_key(path, root) for path in known_paths if path}
    images_ext = {extension.casefold() for extension in image_exts}
    videos_ext = {extension.casefold() for extension in video_exts}
    images: list[str] = []
    videos: list[str] = []
    for current, _dirs, files in os.walk(folder):
        for name in files:
            extension = os.path.splitext(name)[1].casefold()
            if extension in images_ext:
                bucket = images
            elif extension in videos_ext:
                bucket = videos
            else:
                continue
            path = os.path.join(current, name)
            if volumes.path_key(path, root) not in known:
                bucket.append(path)
    return sorted(images), sorted(videos)


def find_new_images(
    folder: str,
    known_paths: Iterable[str],
    extensions: Iterable[str] = IMAGE_EXTS,
) -> list[str]:
    """Return image paths in ``folder`` that are not yet known."""
    images, _videos = find_new_media(
        folder,
        known_paths,
        image_exts=extensions,
        video_exts=(),
    )
    return images


def setup_logging() -> None:
    """Configure root logging once with timestamps and level."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
