"""Import flow for every plugin: settings, fetching posts, selection, queueing.

Steps driven by :class:`PluginImport`:

1. The plugin's own settings dialog (:func:`plugins.configure_plugin`); the
   changed settings are stored in the active config.
2. Posts and thumbnails are fetched in a background worker
   (:func:`plugins.run_fetch`); the sidebar shows a loading state meanwhile.
3. :class:`PreviewDialog` lets the user pick posts.
4. The picked posts are queued on the :class:`DownloadsPage`.

After a download job finished without failed files, :func:`apply_imported`
hands the job's plugin state back to the plugin (``on_imported``), e.g. so the
next run only offers newer posts.
"""

import logging

from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtWidgets import QMessageBox, QWidget

from mediavault import remote
from mediavault.config import save_configs
from mediavault.database import MediaDatabase
from mediavault.gui.downloads import DownloadJob, DownloadsPage, JobState
from mediavault.gui.preview_dialog import PreviewDialog
from mediavault.gui.worker import Worker
from mediavault.models import FetchResult, LibraryRoot, VaultConfig
from mediavault.plugins import (
    ImportPlugin,
    PluginError,
    configure_plugin,
    is_saveable,
    run_fetch,
)

logger = logging.getLogger(__name__)


class PluginImport(QObject):
    """Run one post fetch at a time and hand selected posts to the queue.

    Signals:
        loading_changed(str, bool): Plugin key and True while it fetches posts.
    """

    loading_changed = pyqtSignal(str, bool)

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
        key: str,
        plugin: ImportPlugin,
        config: VaultConfig,
        configs: list[VaultConfig],
        db: MediaDatabase,
        location: LibraryRoot,
    ) -> None:
        """Ask for settings, then fetch new posts in the background.

        Does nothing while a fetch is already running. The result is handled by
        :meth:`_select` on the GUI thread.

        Args:
            key: Plugin key (its folder name).
            plugin: The plugin.
            config: Active config; its settings for this plugin are updated.
            configs: All configs, needed to save the settings.
            db: Database the downloads will be imported into.
            location: Where the active config's media lives.
        """
        if self._fetch is not None:
            return
        try:
            proceed, settings = configure_plugin(
                plugin, self._parent, config.plugins.get(key, {})
            )
        except PluginError as exc:
            QMessageBox.warning(self._parent, plugin.name, str(exc))
            return
        config.plugins[key] = settings
        save_configs(configs, config.db_path)
        if not proceed:
            return
        self._abandoned = False
        worker = Worker(
            self._parent,
            run_fetch,
            plugin=plugin,
            settings=settings,
            default_preview=remote.fetch_preview,
        )
        self._fetch = worker
        self._set_loading(key, plugin, True)
        worker.finished.connect(
            lambda: self._select(worker, key, plugin, db, location)
        )
        worker.start()

    def abandon(self) -> None:
        """Drop the result of a running fetch, e.g. after a config switch.

        The fetch itself cannot be cancelled; its result is ignored when it
        arrives, so posts never land in the wrong library.
        """
        self._abandoned = self._fetch is not None

    def _set_loading(self, key: str, plugin: ImportPlugin, loading: bool) -> None:
        """Report the fetch state to the sidebar and the downloads page."""
        self._downloads.set_activity(
            f"🔎  Lade Posts von {plugin.name} …" if loading else ""
        )
        self.loading_changed.emit(key, loading)

    def _select(
        self,
        worker: Worker,
        key: str,
        plugin: ImportPlugin,
        db: MediaDatabase,
        location: LibraryRoot,
    ) -> None:
        """Let the user pick posts from the fetch result and queue them.

        Reports fetch errors, "no new posts" and an empty selection with a
        message box instead.
        """
        self._fetch = None
        self._set_loading(key, plugin, False)
        worker.deleteLater()
        if self._abandoned:
            return
        if worker.error is not None:
            # run_fetch only raises PluginError, whose text is safe to show.
            QMessageBox.warning(self._parent, plugin.name, str(worker.error))
            return
        result: FetchResult
        result, previews = worker.result
        if not result.posts:
            QMessageBox.information(self._parent, plugin.name, "Keine neuen Posts.")
            return
        dlg = PreviewDialog(self._parent, plugin.name, result.posts, previews)
        if not dlg.exec():
            return
        selected = dlg.selected_ids()
        if not selected:
            QMessageBox.information(
                self._parent, plugin.name, "Keine Posts ausgewählt."
            )
            return
        title = result.label or plugin.name
        self._downloads.enqueue(
            key=key,
            label=f"{title} · {len(selected)} Posts",
            db=db,
            folder=location.folder,
            posts=result.posts,
            selected_ids=selected,
            fallback_group=title,
            plugin_state=result.state,
            root=location.volume,
        )


def apply_imported(
    job: DownloadJob,
    plugins: dict[str, ImportPlugin],
    configs: list[VaultConfig],
    active_db_path: str,
) -> None:
    """Hand a cleanly finished job's plugin state back to its plugin.

    Jobs that failed or had failed files are skipped, so their posts are
    offered again. The returned settings go to the config that owns the job's
    database, even if the user switched configs in between, and the configs
    file is saved. A failing ``on_imported`` is logged and changes nothing.

    Args:
        job: The finished download job.
        plugins: Loaded plugins by key.
        configs: All configs.
        active_db_path: Database path of the active config, saved as "last".
    """
    if job.state is not JobState.DONE or job.failed:
        return
    hook = getattr(plugins.get(job.key), "on_imported", None)
    if not callable(hook):
        return
    config = next((c for c in configs if c.db_path == job.db.filepath), None)
    if config is None:
        return
    try:
        settings = hook(dict(config.plugins.get(job.key, {})), job.plugin_state)
    except Exception:  # noqa: BLE001 - a plugin bug must not break the queue
        logger.exception("on_imported of %s failed", job.key)
        return
    if not is_saveable(settings):
        logger.error("on_imported of %s returned invalid data", job.key)
        return
    config.plugins[job.key] = settings
    save_configs(configs, active_db_path)
