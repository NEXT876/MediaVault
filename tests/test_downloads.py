"""Tests for the download queue's job state and status line."""

from mediavault.database import MediaDatabase
from mediavault.gui.downloads import DownloadJob, JobState, download_status_text


def _job(tmp_path, **changes) -> DownloadJob:
    """Build a job with two selected posts and apply the given overrides."""
    job = DownloadJob(
        number=1,
        label="test",
        db=MediaDatabase(str(tmp_path / "db.json")),
        folder=str(tmp_path),
        key="src",
        posts=[],
        selected_ids={"1", "2"},
        fallback_group="cat",
        plugin_state={},
    )
    for name, value in changes.items():
        setattr(job, name, value)
    return job


def test_status_text_covers_every_state(tmp_path):
    assert download_status_text(_job(tmp_path)) == "Wartet in der Warteschlange"

    assert (
        download_status_text(_job(tmp_path, state=JobState.RUNNING))
        == "Startet …"
    )

    running = _job(tmp_path, state=JobState.RUNNING, done=1, total=2)
    assert download_status_text(running) == "Lädt Datei 2 von 2"

    done = _job(
        tmp_path, state=JobState.DONE, imported=3, duplicates=1, failed=0
    )
    assert download_status_text(done) == "3 importiert, 1 Duplikate"

    failed = _job(
        tmp_path, state=JobState.DONE, imported=3, duplicates=1, failed=2
    )
    assert download_status_text(failed) == "3 importiert, 1 Duplikate, 2 fehlgeschlagen"

    assert download_status_text(_job(tmp_path, state=JobState.ERROR)) == "Fehlgeschlagen"


def test_status_text_never_claims_a_file_past_the_total(tmp_path):
    # After the last progress callback ``done`` equals ``total``; the label must
    # not jump to "Datei 3 von 2" while the worker finishes.
    job = _job(tmp_path, state=JobState.RUNNING, done=2, total=2)

    assert download_status_text(job) == "Lädt Datei 2 von 2"
