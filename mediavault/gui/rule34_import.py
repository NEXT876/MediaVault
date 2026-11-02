"""rule34 import flow: settings, fetching posts, selection and queueing."""

from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtWidgets import QMessageBox, QWidget

from mediavault.config import LibraryRoot, VaultConfig, save_configs
from mediavault.gui.downloads import DownloadJob, DownloadsPage, JobState
from mediavault.gui.rule34_dialog import Rule34Dialog, Rule34PreviewDialog
from mediavault.gui.worker import Worker
from mediavault.models import MediaDatabase
from mediavault.rule34 import fetch_posts_with_previews

_TITLE = "rule34 Import"


class Rule34Import(QObject):
    """Run one post fetch at a time and hand selected posts to the queue."""

    loading_changed = pyqtSignal(bool)

    def __init__(self, parent: QWidget, downloads: DownloadsPage) -> None:
        """Bind to the window used as dialog parent and the download queue."""
        super().__init__(parent)
        self._parent = parent
        self._downloads = downloads
        self._fetch: Worker | None = None
        self._abandoned = False

    @property
    def is_busy(self) -> bool:
        """Return True while posts are being fetched."""
        return self._fetch is not None

    def start(
        self,
        config: VaultConfig,
        configs: list[VaultConfig],
        db: MediaDatabase,
        location: LibraryRoot,
    ) -> None:
        """Ask for settings, then fetch new posts in the background."""
        if self._fetch is not None:
            return
        dlg = Rule34Dialog(self._parent, config, configs)
        if not dlg.exec():
            return
        dlg.store_settings()
        self._abandoned = False
        settings = config.rule34
        worker = Worker(
            self._parent,
            fetch_posts_with_previews,
            api_key=settings.api_key,
            user_id=settings.user_id,
            tags=settings.tags,
            webm=settings.webm,
            limit=settings.count,
            last_ids=dlg.last_ids(),
        )
        self._fetch = worker
        self._set_loading(True)
        worker.finished.connect(lambda: self._select(worker, config, db, location))
        worker.start()

    def abandon(self) -> None:
        """Drop the result of a running fetch, for example after a vault switch."""
        self._abandoned = self._fetch is not None

    def _set_loading(self, loading: bool) -> None:
        """Report the fetch state to the window and the downloads page."""
        self._downloads.set_activity("🔎  Lade Posts von rule34 …" if loading else "")
        self.loading_changed.emit(loading)

    def _select(
        self,
        worker: Worker,
        config: VaultConfig,
        db: MediaDatabase,
        location: LibraryRoot,
    ) -> None:
        """Let the user pick posts from the fetch result and queue them."""
        self._fetch = None
        self._set_loading(False)
        worker.deleteLater()
        if self._abandoned:
            return
        if worker.error is not None:
            QMessageBox.warning(self._parent, _TITLE, str(worker.error))
            return
        posts, previews, newest_ids = worker.result
        if not posts:
            QMessageBox.information(self._parent, _TITLE, "Keine neuen Posts.")
            return
        dlg = Rule34PreviewDialog(self._parent, posts, previews)
        if not dlg.exec():
            return
        selected = dlg.selected_ids()
        if not selected:
            QMessageBox.information(self._parent, _TITLE, "Keine Posts ausgewählt.")
            return
        tags = config.rule34.tags
        self._downloads.enqueue(
            label=f"{tags or 'ohne Tags'} · {len(selected)} Posts",
            db=db,
            folder=location.folder,
            tags=tags,
            posts=posts,
            selected_ids=selected,
            newest_ids=newest_ids,
            root=location.volume,
        )


def remember_newest_ids(
    job: DownloadJob, configs: list[VaultConfig], active_db_path: str
) -> None:
    """Store the newest post IDs once every selected post reached the disk."""
    if job.state is not JobState.DONE or job.failed or not job.newest_ids:
        return
    config = next((c for c in configs if c.db_path == job.db.filepath), None)
    if config is not None:
        config.rule34.last_ids.update(job.newest_ids)
        save_configs(configs, active_db_path)
