"""Configs, where their media lives, and stick identities."""

from dataclasses import dataclass, field
from typing import Any

MODE_NORMAL = "normal"
MODE_AI = "ai"


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
        plugins: Settings per import plugin, keyed by plugin folder name.
        extra: Stored keys this version does not know; written back unchanged,
            so settings of removed plugins and old keys are never lost.
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
    plugins: dict[str, dict] = field(default_factory=dict)
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def is_ai(self) -> bool:
        """Return True for configs that only hold AI images with metadata."""
        return self.mode == MODE_AI

    @property
    def has_folder(self) -> bool:
        """Return True when the config manages a media folder, local or on a stick."""
        return bool(self.folder.strip() or self.volume_uuid)


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


@dataclass(frozen=True)
class VolumeInfo:
    """Identity and display label of one marked volume.

    Attributes:
        uuid: Stable identifier stored in the marker file.
        label: Name shown to the user, e.g. while the stick is unplugged.
    """

    uuid: str
    label: str = ""
