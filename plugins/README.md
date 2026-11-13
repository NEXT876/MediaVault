# MediaVault plugins

Import sources for the "IMPORT FROM WEB" section of the sidebar. Every plugin
found here gets its own button there; without plugins the section is hidden.
MediaVault itself does the rest: the preview where you pick posts, the
download queue, and the import with duplicate detection.

## Folder layout

```
plugins/
  README.md        this file
  <name>/          a shared plugin (committed)
  private/         local-only plugins, ignored by git
    <name>/
      __init__.py  must define PLUGIN
      ...          any further modules, tests/
```

- A plugin is a folder with an `__init__.py` that defines `PLUGIN`, a
  callable without arguments that returns the plugin object (usually the
  class itself).
- The folder name is the plugin's **key**: its settings are stored under it,
  and downloads go to `<library folder>/<key>/<key>_<post id>.<ext>`.
- Install a plugin by copying its folder into `plugins/` or
  `plugins/private/`; remove it by deleting the folder. Restart MediaVault
  afterwards. Plugins are loaded from the folder next to the `mediavault`
  package, so start the app from the repository (`python -m mediavault`).
- The folder is loaded as a package, so relative imports work
  (`from .api import search`).
- Shared plugins win over private ones with the same folder name, and the
  first plugin with a given `name` wins. Broken plugins are skipped with a
  warning in the log; the app always starts.

## Interface

Everything a plugin uses comes from `mediavault.plugins`.

| Member | Required | Thread | Purpose |
|---|---|---|---|
| `name: str` | yes | – | Button text and dialog titles. |
| `configure(parent, settings) -> bool` | yes | GUI | Show your settings or search dialog (`parent` is the main window). Change `settings` in place; it is a copy. MediaVault stores it afterwards **whether you return True or False**. `False` means "do not fetch". |
| `fetch(settings) -> FetchResult` | yes | worker | Return the posts to offer. No Qt calls here. |
| `fetch_preview(post) -> bytes \| None` | no | worker | Thumbnail bytes. Default: download `post.preview_url`. |
| `on_imported(settings, state) -> dict` | no | GUI | Called after a download job finished **without failed files**, with the `state` of the `FetchResult` the job came from. Return the settings to store, e.g. with the newest post remembered. |
| `migrate(extra) -> dict \| None` | no | GUI | See below. |

`FetchResult(posts, state={}, label="")`:

- `posts`: a list of `RemotePost`. Duplicate IDs are dropped (the first one
  stays).
- `state`: any JSON-like data you want back in `on_imported`.
- `label`: job title in the download queue and group for posts without one,
  e.g. the search. Defaults to the plugin name.

`RemotePost(id, file_url, preview_url="", group="", title="")`:

- `id`: unique within your plugin; letters, digits, `_` and `-`, at most 64
  characters. Other IDs are rejected because the ID becomes a file name.
- `file_url`, `preview_url`: must be `http://` or `https://`.
- `group`: the library group of the entry.
- `title`: tooltip in the preview.

Minimal example (also loaded by `tests/test_plugins.py`, so it stays correct):

```python
from mediavault.plugins import FetchResult, PluginError, RemotePost


class ExamplePlugin:
    name = "Beispiel"

    def configure(self, parent, settings):
        # A real plugin shows a dialog here and writes the input to settings.
        settings.setdefault("count", 2)
        return True

    def fetch(self, settings):
        count = settings.get("count", 0)
        if count < 1:
            raise PluginError("Keine Anzahl eingestellt.")
        posts = [
            RemotePost(str(n), f"https://example.org/{n}.png", group="Beispiel")
            for n in range(1, count + 1)
        ]
        return FetchResult(posts=posts, label="Beispiel")


PLUGIN = ExamplePlugin
```

## Settings and `migrate`

- Settings are a plain dict per library (each config has its own), stored
  under `plugins.<key>` in `~/.mediavault/configs.json`. Values must be JSON
  serializable. Validate them yourself when reading; the file can be old or
  edited by hand.
- Keys of `configs.json` that MediaVault does not know are kept unchanged in
  `extra`. If your plugin used to store settings under other keys,
  implement `migrate(extra)`: it is called once per library while there are
  no settings for your plugin yet. Remove the keys you adopt from `extra`
  and return your settings, or return `None`. A failing `migrate` changes
  nothing.

## Errors and threads

- Raise `PluginError("…")` for expected problems (wrong credentials,
  offline, empty search). The message is shown to the user as is, so write
  it in German and never include secrets such as API keys or URLs that
  contain them.
- Any other exception counts as a bug: the user sees
  "`<name>` ist fehlgeschlagen: `<ExceptionType>`" (without the message) and
  the traceback goes to the log.
- `fetch` and `fetch_preview` run in a worker thread: no Qt calls there, and
  do not share mutable state with `configure` without care.
- A failed download is reported per post; the other posts still download.
  Jobs with failed files do not call `on_imported`, so the posts are offered
  again next time.

## Security

A plugin is ordinary Python code. It is imported when MediaVault starts and
runs with your user's rights; there is no sandbox. Only install plugins you
trust. Settings, including API keys, are stored in plain text in
`configs.json` (readable only by your user).
