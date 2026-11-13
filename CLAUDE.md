# Hinweise für Claude

## Autorschaft (gilt immer)

- **Commits:** Author ist Ben Waibel, Claude ist Co-Author.
  - Committen mit `--author "Ben Waibel <103282803+NEXT876@users.noreply.github.com>"`.
  - Die Commit-Message endet mit dem `Co-Authored-By: Claude …`-Trailer.
  - Keinen `Claude-Session: …`-Trailer in Commits.
- **Pull Requests:** Gleiche Regel. Die PR-Beschreibung endet mit
  `Co-Authored-By: Claude <noreply@anthropic.com>`, damit Claude als
  Co-Author sichtbar ist. Ben Waibel (NEXT876) ist der Autor.

## Git-Workflow (gilt immer)

- Neue Features bekommen einen eigenen Branch von `develop`, benannt nach dem
  Feature (kurz, englisch, mit Bindestrichen), und gehen per PR nach `develop`.
- Jeder Branch außer `main` und `develop` beginnt mit seiner Art:
  `feature/`, `fix/`, `refactor/`, `docs/`, `test/`, `chore/`
  (z. B. `feature/plugin-system`, `fix/empty-library-crash`,
  `refactor/split-models`).
- PRs nach `develop`: Vorlage `.github/pull_request_template.md` nutzen.
  Der Titel nennt den Typ, Format `<Typ>: <was sich ändert>` auf Englisch,
  Typen: `Feature`, `Fix`, `Refactor`, `Docs`, `Test`, `Chore`
  (z. B. `Feature: Duel mode with Elo ratings`). GitHub squasht automatisch
  und nimmt den PR-Titel als Commit-Message, der Titel ist also die spätere
  Commit-Message.
- Nach dem Merge nach `develop` löscht GitHub den Branch automatisch
  („Automatically delete head branches“ ist an). Den lokalen Branch selbst
  löschen.
- Bugfixes (z. B. wenn der Release-PR nach `main` scheitert) direkt auf
  `develop` committen und pushen, ohne eigenen Branch und ohne PR.
- Auch Commits direkt auf `develop` beginnen mit dem Typ, genau wie PR-Titel:
  `<Typ>: <was sich ändert>` mit `Feature`, `Fix`, `Refactor`, `Docs`, `Test`
  oder `Chore` (z. B. `Fix: Crash on empty library`). Das gilt für jeden
  Commit, nicht nur den ersten.
- Nie direkt nach `main` pushen; der einzige PR nach `main` ist der Release-PR.
- Release (`develop` → `main`, Reset von `develop`, Tag, GitHub-Release): nur
  über den Skill `ship-develop`, nur auf Bens Bitte und erst nach Nachfrage.
  Was genau passiert, steht im Skill.

## Codegraph mit graphify (gilt immer)

- `graphify-out/` enthält einen Wissensgraphen des Codes (`GRAPH_REPORT.md`,
  `graph.json`, `graph.html`) und wird mit committet.
- **Vor** Arbeit am Code zuerst den Graphen nutzen, statt das Repo neu zu
  durchsuchen: `graphify-out/GRAPH_REPORT.md` lesen und gezielt
  `graphify query "<Frage>"`, `graphify explain "<Symbol>"`,
  `graphify affected "<Symbol>"` (wen eine Änderung trifft) oder
  `graphify path "A" "B"` aufrufen.
- **Nach** jeder fertig umgesetzten Änderung `graphify update .` ausführen und
  `graphify-out/` im selben Branch mit committen und pushen.
- Fehlt das Tool: `pip install graphifyy`. Nur `--code-only` bzw. `update`
  nutzen (lokal, ohne LLM); keinen Code an externe LLM-Backends schicken.

## Gedächtnis (dauerhafte Notizen)

- Sprache: Antworten auf Deutsch. GitHub-Issues und PRs (Titel und Text) auf Englisch.
- Tech-Debt-Backlog (Audit 2026-11-10), nach Priorität:
  1. CI-Matrix (Python 3.10/3.13, Windows)
  2. Atomares JSON-Speichern 4× dupliziert, ohne fsync (Datenverlust-Risiko auf Stick/rclone)
  3. Obergrenzen für PyQt6/opencv
  4. GUI-Riesendateien (dialogs.py, wheel.py, main_window.py)
  5. GUI-Tests fehlen
  6. MediaDatabase schreibt bei jeder Änderung alles neu (erst bei großen Bibliotheken relevant)
- Offene Feature-Ideen: Duell-Modus (Elo), fehlende Dateien finden, Diashow mit
  Schnellbewertung, Backups von media_data.json, Tags statt Gruppen.
- Specs und Pläne (`docs/superpowers/specs/`, `docs/superpowers/plans/`) löschen,
  sobald sie fertig umgesetzt sind, im selben Branch wie die Umsetzung.
- Neue Notizen hier eintragen, wenn Ben sagt „merk dir …".
- Modelle und Subagents: Planung, Architektur und Reviews selbst machen (Opus).
  Routinearbeit nach einem fertigen Plan nur dann an Subagents mit
  `model: sonnet` geben, wenn es sich lohnt: mehrere unabhängige, klar
  umrissene Aufgaben oder viel mechanische Arbeit. Kleine Aufgaben und alles,
  was Gesprächskontext braucht, ohne Subagents direkt erledigen.
