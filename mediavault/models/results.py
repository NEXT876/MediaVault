"""Counts returned by import, copy and download runs."""

from dataclasses import dataclass, field


@dataclass
class ImportResult:
    """Counts from one import run.

    Attributes:
        added: Entries that were added to the database.
        duplicates: Files skipped because path, content or AI generation was
            already stored.
        skipped_no_ai: Files skipped in AI configs because they carry no AI
            metadata.
        failed: Files that passed every check but could not be copied into the
            library folder.
    """

    added: int = 0
    duplicates: int = 0
    skipped_no_ai: int = 0
    failed: int = 0


@dataclass
class CopyResult:
    """Outcome of one copy run.

    Attributes:
        copied: Paths of the stored files in order: the new copy, or the
            original path for files already inside the folder.
        skipped: Number of files whose content was already known.
        failed: Source paths that could not be read or copied.
    """

    copied: list[str] = field(default_factory=list)
    skipped: int = 0
    failed: list[str] = field(default_factory=list)


@dataclass
class DownloadResult:
    """Counts of one download job.

    Attributes:
        imported: Entries added to the database.
        duplicates: Downloaded files that were already in the database.
        failed: One message per post that could not be downloaded.
    """

    imported: int = 0
    duplicates: int = 0
    failed: list[str] = field(default_factory=list)
