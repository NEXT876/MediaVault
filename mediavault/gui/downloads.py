"""Background download queue page and its job cards.

Each confirmed rule34 import becomes a :class:`DownloadJob`. The
:class:`DownloadsPage` runs one job at a time in a :class:`Worker` thread
(:func:`rule34.download_and_import`), so the library stays usable while files
download, and shows every job as a :class:`DownloadRow` with live progress.
The worker reports progress through a Qt signal, which Qt delivers on the GUI
thread. When a job finishes without failed files, the window stores its
newest post IDs (:func:`rule34_import.remember_newest_ids`), so the next run
only fetches newer posts.
"""

from dataclasses import dataclass
from enum import Enum

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from mediavault.gui.widgets import button, hint_label
from mediavault.gui.worker import Worker
from mediavault.models import MediaDatabase
from mediavault.rule34 import Post, download_and_import


class JobState(str, Enum):
    """Lifecycle state of one queued download: waiting, running, done or error."""

    WAITING = "waiting"
    RUNNING = "running"
    DONE = "done"
    ERROR = "error"


OPEN_STATES = (JobState.WAITING, JobState.RUNNING)

_JOB_ICONS = {
    JobState.WAITING: "⏳",
    JobState.RUNNING: "⬇️",
    JobState.DONE: "✅",
    JobState.ERROR: "⚠️",
}


@dataclass
class DownloadJob:
    """One rule34 import waiting in or running through the download queue.

    Attributes:
        number: Running number shown as ``#n``.
        label: Title of the job (the tag search).
        db: Database the files are imported into; the config active when the
            job was queued, even if the user switched since.
        folder: Media folder of that config.
        tags: Tag text, the fallback group.
        posts: All fetched posts.
        selected_ids: Post IDs the user chose to download.
        newest_ids: Newest post ID per search signature, stored on success.
        root: Volume root of a stick library; stored paths stay relative to it.
        state: Current :class:`JobState`.
        done: Finished files so far.
        total: Files to download.
        imported: Entries added (when done).
        duplicates: Files already in the database (when done).
        failed: Files that failed to download (when done).
        detail: Error text or one line per failed file.
    """

    number: int
    label: str
    db: MediaDatabase
    folder: str
    tags: str
    posts: list[Post]
    selected_ids: set[int]
    newest_ids: dict[str, int]
    # Volume root of a stick library; stored paths stay relative to it.
    root: str = ""
    state: JobState = JobState.WAITING
    done: int = 0
    total: int = 0
    imported: int = 0
    duplicates: int = 0
    failed: int = 0
    detail: str = ""


def download_status_text(job: DownloadJob) -> str:
    """Return the short status line shown under a job's title.

    E.g. "Lädt Datei 3 von 10" while running, or "8 importiert, 2 Duplikate"
    when done.
    """
    if job.state is JobState.WAITING:
        return "Wartet in der Warteschlange"
    if job.state is JobState.RUNNING:
        if job.total:
            # ``done`` counts finished files; the next one is in progress.
            return f"Lädt Datei {min(job.done + 1, job.total)} von {job.total}"
        return "Startet …"
    if job.state is JobState.ERROR:
        return "Fehlgeschlagen"
    parts = [f"{job.imported} importiert", f"{job.duplicates} Duplikate"]
    if job.failed:
        parts.append(f"{job.failed} fehlgeschlagen")
    return ", ".join(parts)


class DownloadRow(QFrame):
    """Card on the downloads page showing one job's icon, title, status and progress."""

    def __init__(self, job: DownloadJob) -> None:
        """Build the card and fill it with the job's current state."""
        super().__init__()
        self.setObjectName("DownloadRow")
        self.lbl_icon = QLabel()
        self.lbl_icon.setObjectName("DownloadIcon")
        self.lbl_icon.setFixedWidth(26)
        self.lbl_title = QLabel()
        self.lbl_title.setObjectName("DownloadTitle")
        self.lbl_status = QLabel()
        self.lbl_status.setObjectName("MutedLabel")
        self.bar = QProgressBar()
        self.bar.setTextVisible(False)
        self.bar.setFixedHeight(6)
        self.lbl_detail = hint_label()

        text_layout = QVBoxLayout()
        text_layout.setSpacing(2)
        text_layout.addWidget(self.lbl_title)
        text_layout.addWidget(self.lbl_status)
        text_layout.addWidget(self.bar)
        text_layout.addWidget(self.lbl_detail)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(10)
        layout.addWidget(self.lbl_icon, 0, Qt.AlignmentFlag.AlignTop)
        layout.addLayout(text_layout, 1)
        self.set_job(job)

    def set_job(self, job: DownloadJob) -> None:
        """Update icon, title, status, progress bar and error detail from the job."""
        done_with_errors = job.state is JobState.DONE and job.failed > 0
        self.lbl_icon.setText("⚠️" if done_with_errors else _JOB_ICONS[job.state])
        self.lbl_title.setText(f"#{job.number}  {job.label}")
        self.lbl_status.setText(download_status_text(job))
        self.bar.setVisible(job.state is JobState.RUNNING)
        self.bar.setRange(0, max(job.total, 1))
        self.bar.setValue(job.done)
        self.lbl_detail.setText(job.detail)
        self.lbl_detail.setVisible(bool(job.detail))
        self.setToolTip(job.detail)


class DownloadsPage(QWidget):
    """Owns the download queue and runs one import at a time in the background.

    Signals:
        progress(int, int): ``(done, total)`` from the worker thread; connected
            to :meth:`_on_progress` so the update happens on the GUI thread.
        queue_changed: The job list or a job's state changed (sidebar badge).
        job_finished(DownloadJob): A job reached DONE or ERROR.
        reveal_requested: A download is still running 1.5 s after queuing; the
            window may switch to this page.
        emptied: :meth:`clear_finished` removed the last job.
    """

    progress = pyqtSignal(int, int)
    queue_changed = pyqtSignal()
    job_finished = pyqtSignal(object)
    reveal_requested = pyqtSignal()
    emptied = pyqtSignal()

    def __init__(self, parent: QWidget | None = None) -> None:
        """Build the page and wire the progress signal to the GUI thread."""
        super().__init__(parent)
        self._jobs: list[DownloadJob] = []
        self._rows: dict[int, DownloadRow] = {}
        self._active: DownloadJob | None = None
        self._worker: Worker | None = None
        self._sequence = 0
        self._activity = ""
        self._build_ui()
        self.progress.connect(self._on_progress)
        self._reveal_timer = QTimer(self)
        self._reveal_timer.setSingleShot(True)
        self._reveal_timer.setInterval(1500)
        self._reveal_timer.timeout.connect(self._request_reveal)
        self._render()

    @property
    def is_busy(self) -> bool:
        """Return True while a download worker is running."""
        return self._active is not None

    @property
    def has_jobs(self) -> bool:
        """Return True when the queue holds at least one job."""
        return bool(self._jobs)

    @property
    def open_count(self) -> int:
        """Return the number of waiting or running jobs."""
        return sum(1 for job in self._jobs if job.state in OPEN_STATES)

    def enqueue(
        self,
        *,
        label: str,
        db: MediaDatabase,
        folder: str,
        tags: str,
        posts: list[Post],
        selected_ids: set[int],
        newest_ids: dict[str, int],
        root: str = "",
    ) -> None:
        """Append a job and start it unless another download is running.

        Args:
            label: Job title.
            db: Target database.
            folder: Media folder of the target config.
            tags: Tag text, the fallback group.
            posts: All fetched posts.
            selected_ids: Post IDs to download.
            newest_ids: Newest post ID per search signature.
            root: Volume root of a stick library.
        """
        self._sequence += 1
        self._jobs.append(
            DownloadJob(
                number=self._sequence,
                label=label,
                db=db,
                folder=folder,
                tags=tags,
                posts=posts,
                selected_ids=selected_ids,
                newest_ids=newest_ids,
                root=root,
            )
        )
        self._render()
        if self._active is None:
            self._start_next()
        self._reveal_timer.start()

    def set_activity(self, text: str) -> None:
        """Show an extra status line, for example while posts are loading."""
        self._activity = text
        self.lbl_activity.setText(text)
        self.lbl_activity.setVisible(bool(text))
        self._render()

    def clear_finished(self) -> None:
        """Drop finished jobs and report when the page became empty."""
        self._jobs = [job for job in self._jobs if job.state in OPEN_STATES]
        self._render()
        if not self._jobs:
            self.emptied.emit()

    def _build_ui(self) -> None:
        """Build the hint, summary header, scroll area and empty state."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        hint = hint_label(
            "Downloads laufen im Hintergrund weiter. Du kannst die Bibliothek "
            "benutzen und weitere Importe einreihen."
        )
        layout.addWidget(hint)

        header = QHBoxLayout()
        header.setSpacing(8)
        self.lbl_summary = QLabel()
        self.lbl_summary.setObjectName("SectionLabel")
        self.btn_clear = button("Fertige entfernen", "ghost", self.clear_finished)
        header.addWidget(self.lbl_summary)
        header.addStretch(1)
        header.addWidget(self.btn_clear)
        layout.addLayout(header)

        self.lbl_activity = hint_label()
        self.lbl_activity.hide()
        layout.addWidget(self.lbl_activity)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setObjectName("CardScroll")
        container = QWidget()
        container.setObjectName("GridContainer")
        self._rows_layout = QVBoxLayout(container)
        self._rows_layout.setContentsMargins(0, 0, 0, 0)
        self._rows_layout.setSpacing(8)
        self._rows_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.scroll.setWidget(container)
        layout.addWidget(self.scroll, 1)

        self.lbl_empty = QLabel("Keine Downloads.")
        self.lbl_empty.setObjectName("MutedLabel")
        self.lbl_empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.lbl_empty)

    def _render(self) -> None:
        """Sync job cards, summary, clear button and empty state with the jobs."""
        current = {job.number for job in self._jobs}
        for number in [number for number in self._rows if number not in current]:
            row = self._rows.pop(number)
            self._rows_layout.removeWidget(row)
            row.hide()
            row.deleteLater()
        for job in self._jobs:
            row = self._rows.get(job.number)
            if row is None:
                row = DownloadRow(job)
                self._rows[job.number] = row
                self._rows_layout.addWidget(row)
            else:
                row.set_job(job)

        open_jobs = self.open_count
        finished = len(self._jobs) - open_jobs
        has_jobs = bool(self._jobs)
        self.lbl_empty.setVisible(not has_jobs and not self._activity)
        self.scroll.setVisible(has_jobs)
        self.lbl_summary.setVisible(has_jobs)
        self.lbl_summary.setText(f"{open_jobs} offen · {finished} abgeschlossen")
        self.btn_clear.setVisible(finished > 0)
        self.queue_changed.emit()

    def _start_next(self) -> None:
        """Start the first waiting job; only one download runs at a time."""
        job = next(
            (job for job in self._jobs if job.state is JobState.WAITING), None
        )
        if job is None:
            return
        self._active = job
        job.state = JobState.RUNNING
        job.done = 0
        job.total = len(job.selected_ids)
        self._render()
        worker = Worker(
            self,
            download_and_import,
            db=job.db,
            posts=job.posts,
            folder=job.folder,
            tags=job.tags,
            selected_ids=job.selected_ids,
            root=job.root,
            progress=self.progress.emit,
        )
        self._worker = worker
        worker.finished.connect(self._finish)
        worker.start()

    def _on_progress(self, done: int, total: int) -> None:
        """Update the running job's progress bar after each file."""
        job = self._active
        if job is None or job.state is not JobState.RUNNING:
            return
        job.done = done
        job.total = total
        self._render()

    def _finish(self) -> None:
        """Record the worker's outcome, update the job and start the next one.

        An exception from the worker marks the job as ERROR with its message;
        per-file failures leave it DONE with the failures as detail.
        """
        worker = self._worker
        job = self._active
        self._worker = None
        self._active = None
        if worker is None or job is None:
            return
        worker.deleteLater()
        if worker.error is not None:
            job.state = JobState.ERROR
            job.detail = str(worker.error)
        elif worker.result is not None:
            job.state = JobState.DONE
            job.imported = worker.result.imported
            job.duplicates = worker.result.duplicates
            job.failed = len(worker.result.failed)
            job.detail = "\n".join(worker.result.failed)
        else:
            job.state = JobState.ERROR
            job.detail = "Download wurde ohne Ergebnis beendet."
        self._render()
        self.job_finished.emit(job)
        self._start_next()

    def _request_reveal(self) -> None:
        """Ask the window to show this page if the download still runs."""
        if self._active is not None:
            self.reveal_requested.emit()
