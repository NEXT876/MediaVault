"""Application-wide paths, vault configs and logging setup."""

import json
import logging
import os
import re
from collections.abc import Iterable, Mapping
from dataclasses import asdict, dataclass
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_DB_PATH = os.path.join(
    os.path.expanduser("~"), ".mediavault", "media_data.json"
)
CONFIGS_PATH = os.path.join(os.path.expanduser("~"), ".mediavault", "configs.json")
MODE_NORMAL = "normal"
MODE_AI = "ai"
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".bmp", ".webp"}


@dataclass
class VaultConfig:
    """A named collection with its own database and optional scan folder."""

    name: str
    mode: str = MODE_NORMAL
    db_path: str = ""
    folder: str = ""

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "VaultConfig":
        """Build a config from stored data, falling back to safe defaults."""
        mode = data.get("mode", MODE_NORMAL)
        return cls(
            name=str(data.get("name") or "Unbenannt"),
            mode=mode if mode in (MODE_NORMAL, MODE_AI) else MODE_NORMAL,
            db_path=str(data.get("db_path") or DEFAULT_DB_PATH),
            folder=str(data.get("folder") or ""),
        )


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

    configs = [VaultConfig.from_dict(item) for item in data.get("configs", [])]
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
    )


def find_new_images(
    folder: str,
    known_paths: Iterable[str],
    extensions: Iterable[str] = IMAGE_EXTS,
) -> list[str]:
    """Return image paths in ``folder`` that are not yet known."""
    if not os.path.isdir(folder):
        logger.warning("Ordner nicht gefunden: %s", folder)
        return []
    known = {os.path.normcase(os.path.abspath(path)) for path in known_paths}
    allowed = {extension.casefold() for extension in extensions}
    found: list[str] = []
    for root, _dirs, files in os.walk(folder):
        for name in files:
            if os.path.splitext(name)[1].casefold() not in allowed:
                continue
            path = os.path.join(root, name)
            if os.path.normcase(os.path.abspath(path)) not in known:
                found.append(path)
    return sorted(found)


def setup_logging() -> None:
    """Configure root logging once with timestamps and level."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
