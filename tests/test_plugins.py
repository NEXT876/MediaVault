"""Tests for the plugin interface, folder discovery and the safe plugin calls."""

import logging
import textwrap

import pytest

from mediavault.models import FetchResult, RemotePost, VaultConfig
from mediavault.plugins import (
    PLUGIN_ROOT,
    PluginError,
    configure_plugin,
    discover_plugins,
    migrate_settings,
    run_fetch,
)

GOOD = """
class Plugin:
    name = {name!r}

    def configure(self, parent, settings):
        return True

    def fetch(self, settings):
        return None

PLUGIN = Plugin
"""


def write_plugin(folder, body=None, name=None, extra_files=None):
    folder.mkdir(parents=True)
    source = body if body is not None else GOOD.format(name=name or folder.name)
    (folder / "__init__.py").write_text(textwrap.dedent(source), encoding="utf-8")
    for file_name, text in (extra_files or {}).items():
        (folder / file_name).write_text(textwrap.dedent(text), encoding="utf-8")


class Dummy:
    """In-memory plugin for the run_fetch / configure_plugin tests."""

    name = "Dummy"

    def __init__(self, result=None, error=None):
        self.result = result
        self.error = error

    def configure(self, parent, settings):
        return True

    def fetch(self, settings):
        if self.error is not None:
            raise self.error
        return self.result


def post(post_id, preview=""):
    return RemotePost(
        id=post_id, file_url=f"https://h/{post_id}.jpg", preview_url=preview
    )


# --- discovery ---


def test_discovers_public_and_private(tmp_path):
    write_plugin(tmp_path / "a")
    write_plugin(tmp_path / "private" / "b")
    assert set(discover_plugins(tmp_path)) == {"a", "b"}


def test_missing_root_returns_empty(tmp_path):
    assert discover_plugins(tmp_path / "nope") == {}


def test_private_folder_itself_is_not_a_plugin(tmp_path):
    write_plugin(tmp_path / "private", name="P")
    assert "private" not in discover_plugins(tmp_path)


def test_broken_plugins_are_skipped(tmp_path, caplog):
    write_plugin(tmp_path / "syntax", body="def broken(:\n")
    write_plugin(tmp_path / "noplugin", body="X = 1\n")
    write_plugin(
        tmp_path / "raises",
        body="def PLUGIN():\n    raise RuntimeError('boom')\n",
    )
    write_plugin(
        tmp_path / "nofetch",
        body="class P:\n    name = 'N'\n    def configure(self, p, s):\n"
        "        return True\nPLUGIN = P\n",
    )
    write_plugin(tmp_path / "good")
    with caplog.at_level(logging.WARNING):
        found = discover_plugins(tmp_path)
    assert list(found) == ["good"]
    warned = " ".join(record.getMessage() for record in caplog.records)
    for name in ("syntax", "noplugin", "raises", "nofetch"):
        assert name in warned


def test_duplicate_name_first_wins(tmp_path):
    write_plugin(tmp_path / "a", name="X")
    write_plugin(tmp_path / "b", name="X")
    assert list(discover_plugins(tmp_path)) == ["a"]


def test_same_folder_public_and_private_loads_public(tmp_path):
    write_plugin(tmp_path / "a", name="Public")
    write_plugin(tmp_path / "private" / "a", name="Private")
    found = discover_plugins(tmp_path)
    assert list(found) == ["a"]
    assert found["a"].name == "Public"


def test_relative_import_and_hyphen_folder(tmp_path):
    body = GOOD.format(name="Hyphen") + "from .api import VALUE\n"
    write_plugin(
        tmp_path / "my-plugin", body=body, extra_files={"api.py": "VALUE = 1\n"}
    )
    assert list(discover_plugins(tmp_path)) == ["my-plugin"]


# --- run_fetch ---


def no_preview(url):
    return None


@pytest.mark.parametrize(
    ("result", "type_name"), [(None, "NoneType"), ([post("1")], "list")]
)
def test_run_fetch_rejects_wrong_return_type(result, type_name):
    with pytest.raises(PluginError) as info:
        run_fetch(Dummy(result=result), {}, no_preview)
    assert str(info.value).startswith("Dummy")
    assert type_name in str(info.value)


def test_run_fetch_rejects_posts_of_wrong_type():
    result = FetchResult(posts=[{"id": "1"}])
    with pytest.raises(PluginError, match="Dummy"):
        run_fetch(Dummy(result=result), {}, no_preview)


def test_run_fetch_wraps_bug_without_its_message():
    with pytest.raises(PluginError) as info:
        run_fetch(Dummy(error=ValueError("secret-key")), {}, no_preview)
    assert "ValueError" in str(info.value)
    assert "secret-key" not in str(info.value)


def test_run_fetch_passes_plugin_error():
    with pytest.raises(PluginError, match="^Offline$"):
        run_fetch(Dummy(error=PluginError("Offline")), {}, no_preview)


def test_run_fetch_drops_duplicate_ids():
    result = FetchResult(posts=[post("1"), post("1"), post("2")])
    fetched, _ = run_fetch(Dummy(result=result), {}, no_preview)
    assert [p.id for p in fetched.posts] == ["1", "2"]


def test_run_fetch_uses_plugin_preview():
    plugin = Dummy(result=FetchResult(posts=[post("1"), post("2")]))
    plugin.fetch_preview = lambda p: b"x" if p.id == "1" else None
    _, previews = run_fetch(plugin, {}, no_preview)
    assert previews == {"1": b"x"}


def test_run_fetch_uses_default_preview_and_survives_its_errors():
    def default(url):
        if url.endswith("bad"):
            raise OSError("down")
        return url.encode()

    result = FetchResult(posts=[post("1", "https://p/ok"), post("2", "https://p/bad")])
    _, previews = run_fetch(Dummy(result=result), {}, default)
    assert previews == {"1": b"https://p/ok"}


# --- configure_plugin ---


class Configuring(Dummy):
    def __init__(self, proceed=True, fail=False):
        super().__init__()
        self.proceed = proceed
        self.fail = fail

    def configure(self, parent, settings):
        settings["k"] = 2
        if self.fail:
            raise RuntimeError("dialog crashed")
        return self.proceed


def test_configure_plugin_keeps_settings_on_error():
    settings = {"k": 1}
    with pytest.raises(PluginError, match="Dummy.*RuntimeError"):
        configure_plugin(Configuring(fail=True), None, settings)
    assert settings == {"k": 1}


def test_configure_plugin_returns_changed_copy():
    settings = {"k": 1}
    assert configure_plugin(Configuring(proceed=False), None, settings) == (
        False,
        {"k": 2},
    )
    assert settings == {"k": 1}


# --- migrate_settings ---


class Migrating(Dummy):
    def __init__(self, fail=False):
        super().__init__()
        self.calls = 0
        self.fail = fail

    def migrate(self, extra):
        self.calls += 1
        old = extra.pop("old")
        if self.fail:
            raise RuntimeError("broken")
        return {"v": old}


def test_migrate_called_only_without_settings():
    plugin = Migrating()
    fresh = VaultConfig(name="A", extra={"old": 1, "keep": 2})
    done = VaultConfig(name="B", plugins={"p": {"v": 9}}, extra={"old": 5})
    assert migrate_settings({"p": plugin}, [fresh, done]) is True
    assert fresh.plugins == {"p": {"v": 1}}
    assert fresh.extra == {"keep": 2}
    assert done.extra == {"old": 5}
    assert plugin.calls == 1


def test_migrate_error_leaves_extra(caplog):
    config = VaultConfig(name="A", extra={"old": 1})
    with caplog.at_level(logging.WARNING):
        assert migrate_settings({"p": Migrating(fail=True)}, [config]) is False
    assert config.extra == {"old": 1}
    assert config.plugins == {}
    assert caplog.records


def test_plugin_without_migrate_is_left_alone():
    config = VaultConfig(name="A", extra={"old": 1})
    assert migrate_settings({"p": Dummy()}, [config]) is False
    assert config.plugins == {}


# --- documentation ---


def test_readme_example_loads(tmp_path):
    readme = (PLUGIN_ROOT / "README.md").read_text(encoding="utf-8")
    example = readme.split("```python\n", 1)[1].split("```", 1)[0]
    write_plugin(tmp_path / "example", body=example)
    plugin = discover_plugins(tmp_path)["example"]
    proceed, settings = configure_plugin(plugin, None, {})
    assert proceed is True
    result, _previews = run_fetch(plugin, settings, no_preview)
    assert result.posts and all(isinstance(p, RemotePost) for p in result.posts)


@pytest.mark.parametrize(
    "result",
    [
        FetchResult(posts=None),
        FetchResult(posts=[RemotePost(123, "https://h/1.png")]),
        FetchResult(posts=[RemotePost("1", None)]),
        FetchResult(posts=[RemotePost("1", "https://h/1.png", group=5)]),
        FetchResult(posts=[RemotePost(["x"], "https://h/1.png")]),
        FetchResult(posts=[], label=3),
        FetchResult(posts=[], state=None),
    ],
)
def test_run_fetch_rejects_wrong_field_types(result):
    with pytest.raises(PluginError, match="^Dummy hat ein ungültiges Ergebnis"):
        run_fetch(Dummy(result=result), {}, no_preview)


class _Unsaveable(Dummy):
    def configure(self, parent, settings):
        settings["bad"] = {1, 2}
        return True

    def migrate(self, extra):
        extra.pop("old")
        return {"bad": b"bytes"}


def test_configure_plugin_rejects_unsaveable_settings():
    with pytest.raises(PluginError, match="^Dummy ist fehlgeschlagen"):
        configure_plugin(_Unsaveable(), None, {})


def test_migrate_rejects_unsaveable_settings():
    config = VaultConfig(name="A", extra={"old": 1})
    assert migrate_settings({"p": _Unsaveable()}, [config]) is False
    assert config.plugins == {}
    assert config.extra == {"old": 1}
