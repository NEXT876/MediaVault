# MediaVault

Ein Desktop-Tool zum Verwalten, Bewerten und Durchstöbern von Medien (Bilder und Videos) – mit Bewertungssystem, Zufallsauswahl und Batch-Funktionen.

## Überblick

MediaVault ("Media Score Tracker") ist eine PyQt6-basierte Desktop-Anwendung, mit der du deine Bilder- und Videosammlung organisierst, bewertest und per Zufall durchstöbern kannst. Alle Einträge werden in einer lokalen JSON-Datei (`media_data.json`) im Arbeitsverzeichnis gespeichert. Die Oberfläche nutzt ein dunkles Theme (Fusion-Stil).

## Features

- **Medienverwaltung**: Bilder und Videos als Kacheln (Grid) anzeigen, anlegen, bearbeiten und löschen
- **Bewertungssystem**: Medien mit einem Score (1–100) bewerten; Bewertungsanzahl und Zeitpunkt der letzten Bewertung werden erfasst
- **Detailansicht**: Vorschaubild, Statistiken, Beschreibung, direkte Wiedergabe/Öffnen sowie Schnellbewertung über die Buttons `1`–`5`
- **Zufallsauswahl**: Lokaler und globaler Zufall, inkl. "Smart"-Modus (gewichtet nach Score, Aufrufen und letzter Wiedergabe) sowie Zufall innerhalb ausgewählter Gruppen
- **Batch-Aktionen**: Mehrfachauswahl zum gleichzeitigen Bewerten, Gruppieren und Löschen
- **Massenimport**: Mehrere Bilder oder Videos auf einmal importieren (Duplikate werden übersprungen)
- **Thumbnails**: Automatische Vorschaubilder über OS-Thumbnails (nur Linux) bzw. extrahierte Videoframes (via OpenCV)
- **Responsive Grid**: Die Kachelansicht passt die Spaltenanzahl automatisch an die Fenstergröße an

## Projektstruktur

