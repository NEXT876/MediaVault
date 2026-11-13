"""Import plugins: interface, discovery and safe calls into plugin code.

A plugin is a folder in ``plugins/`` (shared) or ``plugins/private/``
(gitignored, local only) whose ``__init__.py`` exposes ``PLUGIN``, a
zero-argument factory returning an :class:`ImportPlugin`. The folder name is
the plugin's key in the settings. See ``plugins/README.md``.

Plugin code is untrusted in the sense that it may be buggy: every call goes
through :func:`configure_plugin` or :func:`run_fetch`, which turn any failure
into a :class:`PluginError` with a message that is safe to show. Qt-free.
"""

import copy
import importlib.util
import json
import logging
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any, Protocol

import mediavault
from mediavault.models import FetchResult, RemotePost, VaultConfig

logger = logging.getLogger(__name__)

PLUGIN_ROOT = Path(mediavault.__file__).resolve().parent.parent / "plugins"
PRIVATE = "private"


class PluginError(Exception):
    """Expected plugin failure; the message is German and shown to the user."""


class ImportPlugin(Protocol):
    """Interface of an import plugin. Optional hooks are listed in the README."""

    name: str

    def configure(self, parent: Any, settings: dict) -> bool:
        """Show the settings dialog (GUI thread); False means "do not fetch"."""
        ...

    def fetch(self, settings: dict) -> FetchResult:
        """Return the posts to offer (worker thread, no Qt calls)."""
        ...


def _load(folder: Path) -> Any:
    """Import one plugin folder as a package and return its plugin object."""
    module_name = f"mediavault_plugin_{folder.name}"
    spec = importlib.util.spec_from_file_location(
        module_name, folder / "__init__.py", submodule_search_locations=[str(folder)]
    )
    if spec is None or spec.loader is None:
        raise ImportError("kein ladbares Paket")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
        factory = getattr(module, "PLUGIN", None)
        if factory is None:
            raise AttributeError("PLUGIN fehlt")
        plugin = factory()
    except BaseException:
        sys.modules.pop(module_name, None)
        raise
    name = getattr(plugin, "name", None)
    if not isinstance(name, str) or not name.strip():
        raise TypeError("name fehlt")
    for method in ("configure", "fetch"):
        if not callable(getattr(plugin, method, None)):
            raise TypeError(f"{method} fehlt")
    return plugin


def _candidates(root: Path) -> list[Path]:
    """Plugin folders in root and root/private, each sorted by name."""
    folders: list[Path] = []
    for base in (root, root / PRIVATE):
        if not base.is_dir():
            continue
        folders.extend(
            path
            for path in sorted(base.iterdir())
            if path.is_dir()
            and (path / "__init__.py").is_file()
            and not (base == root and path.name == PRIVATE)
        )
    return folders


def discover_plugins(root: Path = PLUGIN_ROOT) -> dict[str, ImportPlugin]:
    """Load all plugin folders in ``root`` and ``root/private``.

    Broken plugins are skipped with a warning, so the app always starts. A
    folder name or plugin name that was already loaded is skipped as well;
    public plugins come before private ones.

    Returns:
        Plugins by folder name, in load order.
    """
    plugins: dict[str, ImportPlugin] = {}
    names: set[str] = set()
    for folder in _candidates(root):
        if folder.name in plugins:
            logger.warning("Plugin-Ordner doppelt, übersprungen: %s", folder)
            continue
        try:
            plugin = _load(folder)
        except Exception as exc:  # noqa: BLE001 - any plugin bug must not stop the app
            logger.warning(
                "Plugin %s übersprungen: %s: %s", folder, type(exc).__name__, exc
            )
            continue
        if plugin.name in names:
            logger.warning(
                "Plugin-Name %r doppelt, übersprungen: %s", plugin.name, folder
            )
            continue
        names.add(plugin.name)
        plugins[folder.name] = plugin
    return plugins


def is_saveable(settings: Any) -> bool:
    """Return True for a dict that ``configs.json`` can store (JSON-serializable)."""
    if not isinstance(settings, dict):
        return False
    try:
        json.dumps(settings)
    except (TypeError, ValueError):
        return False
    return True


def migrate_settings(
    plugins: dict[str, ImportPlugin], configs: list[VaultConfig]
) -> bool:
    """Let each plugin adopt its old keys once per config.

    ``migrate(extra)`` is only called for configs without settings for that
    plugin. It works on a copy of ``extra``; the copy replaces ``extra`` only
    when it returned a dict, so a failing migration loses nothing.

    Returns:
        True when any config changed and should be saved.
    """
    changed = False
    for key, plugin in plugins.items():
        migrate = getattr(plugin, "migrate", None)
        if not callable(migrate):
            continue
        for config in configs:
            if key in config.plugins:
                continue
            extra = copy.deepcopy(config.extra)
            try:
                settings = migrate(extra)
            except Exception:  # noqa: BLE001 - a broken migration must not stop the app
                logger.warning(
                    "Migration von %s fehlgeschlagen", plugin.name, exc_info=True
                )
                continue
            if settings is not None and not is_saveable(settings):
                logger.warning("Migration von %s lieferte ungültige Daten", plugin.name)
                continue
            if settings is not None:
                config.plugins[key] = settings
                config.extra = extra
                changed = True
    return changed


def _bug(plugin: ImportPlugin, exc: BaseException) -> PluginError:
    """Turn an unexpected exception into a message without its text (may hold keys)."""
    logger.error("Plugin %s fehlgeschlagen", plugin.name, exc_info=exc)
    return PluginError(f"{plugin.name} ist fehlgeschlagen: {type(exc).__name__}")


def _invalid(plugin: ImportPlugin, value: Any) -> PluginError:
    """Report a fetch result of the wrong type, naming only the type."""
    name = type(value).__name__
    logger.error(
        "Plugin %s lieferte %s statt FetchResult/RemotePost", plugin.name, name
    )
    return PluginError(f"{plugin.name} hat ein ungültiges Ergebnis geliefert: {name}")


def configure_plugin(
    plugin: ImportPlugin, parent: Any, settings: dict
) -> tuple[bool, dict]:
    """Run the plugin's settings dialog on a copy of ``settings``.

    Returns:
        ``(proceed, changed_copy)``; the caller stores the copy either way.

    Raises:
        PluginError: When the dialog raised; ``settings`` is untouched.
    """
    changed = copy.deepcopy(settings)
    try:
        proceed = plugin.configure(parent, changed)
    except PluginError:
        raise
    except Exception as exc:
        raise _bug(plugin, exc) from None
    if not is_saveable(changed):
        raise _bug(plugin, TypeError("settings not JSON-serializable"))
    return bool(proceed), changed


def run_fetch(
    plugin: ImportPlugin,
    settings: dict,
    default_preview: Callable[[str], bytes | None],
) -> tuple[FetchResult, dict[str, bytes]]:
    """Fetch posts and their previews; meant to run in a worker thread.

    Validates the result, drops duplicate post IDs (the first one stays) and
    loads previews with the plugin's ``fetch_preview`` or ``default_preview``.
    A failing preview only leaves that preview out.

    Raises:
        PluginError: The plugin's own error, or a safe message for a bug.
    """
    try:
        result = plugin.fetch(settings)
    except PluginError:
        raise
    except Exception as exc:
        raise _bug(plugin, exc) from None
    if not isinstance(result, FetchResult):
        raise _invalid(plugin, result)
    if not isinstance(result.posts, list):
        raise _invalid(plugin, result.posts)
    if not isinstance(result.label, str):
        raise _invalid(plugin, result.label)
    if not isinstance(result.state, dict):
        raise _invalid(plugin, result.state)
    seen: set[str] = set()
    posts: list[RemotePost] = []
    for item in result.posts:
        if not isinstance(item, RemotePost):
            raise _invalid(plugin, item)
        for value in (item.id, item.file_url, item.preview_url, item.group, item.title):
            if not isinstance(value, str):
                raise _invalid(plugin, value)
        if item.id not in seen:
            seen.add(item.id)
            posts.append(item)
    result.posts = posts

    custom = getattr(plugin, "fetch_preview", None)
    previews: dict[str, bytes] = {}
    for item in posts:
        try:
            data = (
                custom(item) if callable(custom) else default_preview(item.preview_url)
            )
        except Exception:  # noqa: BLE001 - a missing thumbnail is not worth failing for
            logger.warning("Vorschau von %s fehlgeschlagen", plugin.name, exc_info=True)
            continue
        if data:
            previews[item.id] = data
    return result, previews
