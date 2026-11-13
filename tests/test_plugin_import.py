"""Tests for storing plugin state after a finished download job."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402

from mediavault.database import MediaDatabase  # noqa: E402
from mediavault.gui import plugin_import  # noqa: E402
from mediavault.gui.downloads import DownloadJob, JobState  # noqa: E402
from mediavault.gui.plugin_import import apply_imported  # noqa: E402
from mediavault.models import VaultConfig  # noqa: E402


class _Plugin:
    name = "Quelle"

    def __init__(self, fail=False):
        self.fail = fail
        self.calls = []

    def configure(self, parent, settings):
        return True

    def fetch(self, settings):
        return None

    def on_imported(self, settings, state):
        self.calls.append((dict(settings), state))
        if self.fail:
            raise RuntimeError("broken")
        return {**settings, "seen": state["n"]}


@pytest.fixture
def saved(monkeypatch):
    calls = []
    monkeypatch.setattr(
        plugin_import, "save_configs", lambda configs, last: calls.append(last)
    )
    return calls


def _job(tmp_path, **changes):
    job = DownloadJob(
        number=1,
        label="x",
        db=MediaDatabase(str(tmp_path / "b.json")),
        folder="",
        key="src",
        posts=[],
        selected_ids=set(),
        fallback_group="g",
        plugin_state={"n": 7},
        state=JobState.DONE,
    )
    for name, value in changes.items():
        setattr(job, name, value)
    return job


def _configs(tmp_path):
    return [
        VaultConfig(name="A", db_path=str(tmp_path / "a.json")),
        VaultConfig(
            name="B", db_path=str(tmp_path / "b.json"), plugins={"src": {"k": 1}}
        ),
    ]


def test_apply_imported_stores_state_in_owning_config(tmp_path, saved):
    configs = _configs(tmp_path)
    plugin = _Plugin()
    apply_imported(_job(tmp_path), {"src": plugin}, configs, "active.json")
    assert configs[1].plugins["src"] == {"k": 1, "seen": 7}
    assert configs[0].plugins == {}
    assert plugin.calls == [({"k": 1}, {"n": 7})]
    assert saved == ["active.json"]


@pytest.mark.parametrize(
    "changes", [{"failed": 1}, {"state": JobState.ERROR}]
)
def test_apply_imported_skips_unclean_jobs(tmp_path, saved, changes):
    plugin = _Plugin()
    apply_imported(_job(tmp_path, **changes), {"src": plugin}, _configs(tmp_path), "x")
    assert plugin.calls == []
    assert saved == []


def test_apply_imported_survives_plugin_error(tmp_path, saved):
    configs = _configs(tmp_path)
    apply_imported(_job(tmp_path), {"src": _Plugin(fail=True)}, configs, "x")
    assert configs[1].plugins["src"] == {"k": 1}
    assert saved == []


def test_apply_imported_without_plugin_or_hook(tmp_path, saved):
    configs = _configs(tmp_path)
    apply_imported(_job(tmp_path), {}, configs, "x")
    apply_imported(_job(tmp_path), {"src": object()}, configs, "x")
    assert saved == []


def test_apply_imported_rejects_unsaveable_settings(tmp_path, saved):
    configs = _configs(tmp_path)
    plugin = _Plugin()
    plugin.on_imported = lambda settings, state: {"bad": object()}
    apply_imported(_job(tmp_path), {"src": plugin}, configs, "x")
    assert configs[1].plugins["src"] == {"k": 1}
    assert saved == []
