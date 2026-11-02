"""Manual folder sync: find new files, preview them and import on confirm."""

import os

from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtWidgets import QMessageBox, QWidget

from mediavault import library
from mediavault.config import LibraryRoot
from mediavault.gui.dialogs import FolderPreviewDialog
from mediavault.gui.worker import Worker, run_with_progress
from mediavault.models import MediaDatabase

_TITLE = "Ordner synchronisieren"


class FolderSync(QObject):
    """Scan the library folder on request and import what the user confirms.

    Files a sync could not import are remembered, so the next sync of the same
    library does not offer them again.
    """

    running_changed = pyqtSignal(bool)
    # Emitted after a completed sync; the flag says whether entries were added.
    synced = pyqtSignal(bool)

    def __init__(self, parent: QWidget) -> None:
        """Bind to the window used as dialog parent."""
        super().__init__(parent)
        self._parent = parent
        self._ignored: set[str] = set()

    def reset(self) -> None:
        """Forget the ignored files, for example after a library switch."""
        self._ignored.clear()

    def start(self, db: MediaDatabase, mode: str, location: LibraryRoot) -> None:
        """Search the library folder for new files in the background."""
        if not location.folder:
            QMessageBox.information(
                self._parent, _TITLE, "Für diese Config ist kein Ordner hinterlegt."
            )
            return
        if not os.path.isdir(location.folder):
            QMessageBox.warning(
                self._parent, _TITLE, "Der Ordner wurde nicht gefunden."
            )
            return
        self.running_changed.emit(True)
        run_with_progress(
            self._parent,
            "Durchsuche Ordner nach neuen Bildern …",
            library.find_unindexed,
            lambda worker: self._preview(worker, db, mode, location),
            db=db,
            mode=mode,
            location=location,
            ignored=set(self._ignored),
        )

    def _preview(
        self, worker: Worker, db: MediaDatabase, mode: str, location: LibraryRoot
    ) -> None:
        """Show the new files and import them after confirmation."""
        self.running_changed.emit(False)
        if worker.error is not None:
            QMessageBox.warning(self._parent, _TITLE, str(worker.error))
            return
        found = {
            media_type: [path for path in paths if os.path.isfile(path)]
            for media_type, paths in worker.result.items()
        }
        paths = [path for type_paths in found.values() for path in type_paths]
        if not paths:
            self.synced.emit(False)
            QMessageBox.information(
                self._parent, _TITLE, "Keine neuen Bilder gefunden."
            )
            return
        if not FolderPreviewDialog(self._parent, paths).exec():
            return
        run_with_progress(
            self._parent,
            f"Importiere {len(paths)} Bild(er) …",
            library.index_files,
            lambda importer: self._report(importer, db, paths, location),
            db=db,
            found=found,
            mode=mode,
            location=location,
        )

    def _report(
        self,
        worker: Worker,
        db: MediaDatabase,
        paths: list[str],
        location: LibraryRoot,
    ) -> None:
        """Remember rejected files and summarize the finished import."""
        if worker.error is not None:
            QMessageBox.warning(self._parent, _TITLE, str(worker.error))
            return
        result = worker.result
        self._ignored |= library.not_indexed(db, paths, location)
        self.synced.emit(result.added > 0)
        summary = f"{result.added} importiert, {result.duplicates} Duplikate"
        if result.skipped_no_ai:
            summary += f", {result.skipped_no_ai} ohne KI-Metadaten übersprungen"
        QMessageBox.information(self._parent, _TITLE, summary)
