# MediaVault

Ein Desktop-Tool zum Verwalten, Bewerten und Durchstöbern von Medien (Bilder und Videos) – mit Bewertungssystem, Zufallsauswahl und Batch-Funktionen.

## Überblick

MediaVault ("Media Score Tracker") ist eine PyQt6-basierte Desktop-Anwendung, mit der du deine Bilder- und Videosammlung organisierst, bewertest und per Zufall durchstöbern kannst. Alle Einträge werden in einer lokalen JSON-Datei (`~/.mediavault/media_data.json`) gespeichert. Die Oberfläche bietet ein modernes Dark- und Light-Theme.

## Features

- **Medienverwaltung**: Bilder und Videos als Kacheln (Grid) anzeigen, anlegen, bearbeiten und löschen
- **Mehrfachauswahl**: Klick toggelt eine Kachel, Shift+Klick wählt einen Bereich, Strg+A wählt alles, ein aufgezogenes Rechteck markiert mehrere Kacheln auf einmal; Esc hebt die Auswahl auf
- **Suche & Sortierung**: Volltextsuche über Titel, Beschreibung und Gruppe sowie Sortierung nach Titel, Score oder zuletzt angesehen
- **Bewertungssystem**: Medien mit einem Score (1–100) bewerten; Bewertungsanzahl und Zeitpunkt der letzten Bewertung werden erfasst
- **Detailansicht**: Vorschaubild, Statistiken, Beschreibung, direkte Wiedergabe/Öffnen sowie Schnellbewertung über die Buttons `1`–`5` (Doppelklick auf eine Kachel öffnet die Details)
- **Zufallsauswahl**: Lokaler und globaler Zufall, inkl. "Smart"-Modus (gewichtet nach Score, Aufrufen und letzter Wiedergabe) sowie Zufall innerhalb ausgewählter Gruppen
- **Batch-Aktionen**: Mehrfachauswahl zum gleichzeitigen Bewerten, Gruppieren und Löschen
- **Massenimport**: Mehrere Bilder oder Videos auf einmal importieren (Duplikate werden übersprungen)
- **Thumbnails**: Automatische Vorschaubilder über OS-Thumbnails (nur Linux) bzw. extrahierte Videoframes (via OpenCV); einmal erzeugte Vorschauen liegen als WebP in `~/.mediavault/thumbs` und sind auch ohne Stick da
- **Stick-Modus**: USB-Stick einstecken, `🔌 Stick einrichten` öffnen, Ordner wählen – entweder als neue Config anlegen oder die aktive Config darauf umstellen. Referenzen werden relativ zur Stick-Identität gespeichert (Marker-Datei `.mediavault-vault`), damit ein anderer Laufwerksbuchstabe nichts kaputt macht
- **Kopieren beim Hinzufügen**: Bilder und Videos, die von Hand importiert werden, kopiert die App in den Ordner der aktiven Config
- **Responsive Grid**: Die Kachelansicht passt die Spaltenanzahl automatisch an die Fenstergröße an
- **Themes**: Dark und Light live umschaltbar; die Auswahl bleibt über Neustarts erhalten

## Tastenkürzel

| Kürzel | Aktion |
| --- | --- |
| Klick | Kachel aus-/abwählen |
| Shift+Klick | Bereich ab der zuletzt angeklickten Kachel auswählen |
| Ziehen | Auswahlrechteck über mehrere Kacheln |
| Strg+A | Alle sichtbaren Kacheln auswählen |
| Esc | Auswahl aufheben |
| Entf | Ausgewählte Einträge löschen |
| Strg+F | Suche fokussieren |
| Doppelklick | Detailansicht öffnen |

## Projektstruktur

```
mediavault/
├── __main__.py        # Einstiegspunkt, Splash-Screen
├── config.py          # Configs, Datenbankpfade, Stick-Auflösung, Logging
├── models.py          # MediaItem und MediaDatabase (JSON-Persistenz)
├── library.py         # Filtern/Sortieren fürs Raster, Ordner indexieren
├── importer.py        # Import mit Duplikaterkennung
├── scanner.py         # Neue Medien in einem Ordner finden
├── transfer.py        # Dateien in den Mediathek-Ordner kopieren
├── volumes.py         # Stick-Marker und relative Pfade
├── rule34.py          # rule34-API, Downloads
├── media_preview.py   # Videoframes und System-Thumbnails
└── gui/
    ├── main_window.py # Hauptfenster: verdrahtet Seitenleiste, Raster, Dialoge
    ├── sidebar.py     # Seitenleiste mit Navigation und Statusanzeigen
    ├── card_grid.py   # Kachelraster, Auswahl, Vorschau-Cache
    ├── selection.py   # Auswahlrechteck mit Auto-Scroll
    ├── widgets.py     # Medienkacheln
    ├── folder_sync.py # Ordner-Sync mit Vorschau und Import
    ├── rule34_import.py # rule34: Posts holen, auswählen, einreihen
    ├── downloads.py   # Download-Warteschlange
    ├── dialogs.py     # Detail-, Bearbeiten-, Gruppen- und Config-Dialoge
    ├── file_dialogs.py # Native Dateiauswahl, Dateien öffnen
    └── theme.py       # Dark-/Light-Paletten und QSS
tests/
```

## Start

```bash
python -m mediavault
```

Abhängigkeiten: `PyQt6`, `opencv-python` (für Videovorschauen).
