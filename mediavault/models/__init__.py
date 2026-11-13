"""Plain data classes of MediaVault, free of any program logic.

Everything in this folder only describes the shape of the data: entries,
configs, volumes, the results of import, copy and download runs, and the
posts that import plugins offer. The modules import nothing from the rest of
the package; loading, saving, validation and every other behavior live in the
logic modules (:mod:`mediavault.database`, :mod:`mediavault.config`,
:mod:`mediavault.importer` …).

- :mod:`.media`: media entries (:class:`MediaItem`, :class:`MediaType`).
- :mod:`.vault`: configs, where their media lives, and stick identities.
- :mod:`.results`: counts of import, copy and download runs.
- :mod:`.posts`: posts offered by import plugins.

Import the classes from this package (``from mediavault.models import
MediaItem``); the submodules are only an internal grouping.
"""

from mediavault.models.media import MediaItem, MediaType
from mediavault.models.posts import FetchResult, RemotePost
from mediavault.models.results import CopyResult, DownloadResult, ImportResult
from mediavault.models.vault import (
    MODE_AI,
    MODE_NORMAL,
    LibraryRoot,
    VaultConfig,
    VolumeInfo,
)

__all__ = [
    "MODE_AI",
    "MODE_NORMAL",
    "CopyResult",
    "DownloadResult",
    "FetchResult",
    "ImportResult",
    "LibraryRoot",
    "MediaItem",
    "MediaType",
    "RemotePost",
    "VaultConfig",
    "VolumeInfo",
]
