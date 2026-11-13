"""Posts that import plugins offer for download."""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class RemotePost:
    """One downloadable file offered by a plugin.

    Attributes:
        id: Unique within the plugin; ``[A-Za-z0-9_-]{1,64}``, checked by the
            core before it becomes part of a file name.
        file_url: URL of the full file; must be http(s).
        preview_url: URL of a small thumbnail, may be empty.
        group: Entry group in the library; empty falls back to the fetch label
            or the plugin name.
        title: Tooltip in the preview dialog.
    """

    id: str
    file_url: str
    preview_url: str = ""
    group: str = ""
    title: str = ""


@dataclass
class FetchResult:
    """What :meth:`ImportPlugin.fetch` returns.

    Attributes:
        posts: Posts to offer, newest first.
        state: Opaque data handed back to ``on_imported`` once the download job
            built from this result finished without failed files.
        label: Job title in the download queue, e.g. the search.
    """

    posts: list[RemotePost]
    state: dict = field(default_factory=dict)
    label: str = ""
