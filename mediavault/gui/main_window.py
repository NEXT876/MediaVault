"""Hauptfenster von MediaVault."""

import logging
import os

from PyQt6.QtCore import QEvent, QPoint, QRect, Qt, QTimer
from PyQt6.QtGui import QKeySequence, QPixmap
from PyQt6.QtWidgets import (
    QApplication,
    QComboBox,
    QGridLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QRubberBand,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from mediavault.config import DEFAULT_DB_PATH
from mediavault.gui.dialogs import DetailDialog, EditDialog, GroupRandomDialog
from mediavault.gui.theme import ThemeManager
from mediavault.gui.widgets import CARD_WIDTH, MediaCard
from mediavault.models import MediaDatabase, MediaItem
from mediavault.utils import OSHelper

logger = logging.getLogger(__name__)


class MainWindow(QMainWindow):
    """Hauptfenster mit Sidebar, Filterleiste, Kachel-Grid und Batch-Aktionen."""

    GRID_SPACING = 12
    SCROLLBAR_RESERVE = 12
    AUTOSCROLL_MARGIN = 24
    AUTOSCROLL_STEP = 28

    def __init__(self, theme_manager=None):
        """Initialisiert Datenbank, Zustand und die komplette Benutzeroberfläche."""
        super().__init__()
        self.setWindowTitle("MediaVault")
        self.resize(1180, 820)

        self.db = MediaDatabase(DEFAULT_DB_PATH)
        self.db.load()

        self.theme = theme_manager or ThemeManager()
        self.current_view = "Bilder"
        self.selected_entries = set()
        self.recent_picks = []
        self.thumbnail_cache = {}
        self.cards = []
        self.current_cols = 1

        self._anchor_entry = None
        self._press_snapshot = set()
        self._drag_base = set()
        self._drag_origin_global = None
        self._last_drag_global = None
        self._rubber_band = None
        self._autoscroll_direction = 0

        self._autoscroll_timer = QTimer(self)
        self._autoscroll_timer.setInterval(40)
        self._autoscroll_timer.timeout.connect(self._autoscroll_step)

        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(200)
        self._search_timer.timeout.connect(self.refresh_data)

        self._setup_ui()
        self._sync_theme_button()
        self.refresh_data()

    # --- UI-Aufbau ---
    def _setup_ui(self):
        """Baut Sidebar, Top-Bar, Action-Bar und das scrollbare Kachel-Grid auf."""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QHBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        sidebar = QWidget()
        sidebar.setObjectName("Sidebar")
        sidebar.setFixedWidth(250)
        side_layout = QVBoxLayout(sidebar)
        side_layout.setContentsMargins(16, 22, 16, 22)
        side_layout.setSpacing(6)

        lbl_title = QLabel("MediaVault")
        lbl_title.setObjectName("AppTitle")
        side_layout.addWidget(lbl_title)
        lbl_sub = QLabel("Deine Medienbibliothek")
        lbl_sub.setObjectName("AppSubtitle")
        side_layout.addWidget(lbl_sub)
        side_layout.addSpacing(12)

        side_layout.addWidget(self._create_section_label("ANSICHTEN"))
        self.btn_bilder = self._create_side_btn(
            "🖼️  Bilder", lambda: self.switch_view("Bilder"), checkable=True
        )
        self.btn_videos = self._create_side_btn(
            "🎬  Videos", lambda: self.switch_view("Videos"), checkable=True
        )
        self.btn_bilder.setChecked(True)
        side_layout.addWidget(self.btn_bilder)
        side_layout.addWidget(self.btn_videos)

        side_layout.addWidget(self._create_section_label("ZUFALL (LOKAL)"))
        side_layout.addWidget(
            self._create_side_btn("🎲  Normal", lambda: self._do_random(False, False))
        )
        side_layout.addWidget(
            self._create_side_btn("⚖️  Smart", lambda: self._do_random(True, False))
        )

        side_layout.addWidget(self._create_section_label("ZUFALL (GLOBAL)"))
        side_layout.addWidget(
            self._create_side_btn("🌍  Alles", lambda: self._do_random(False, True))
        )
        side_layout.addWidget(
            self._create_side_btn("⚖️🌍  Alles Smart", lambda: self._do_random(True, True))
        )
        side_layout.addWidget(
            self._create_side_btn("📂  Aus Gruppen", self._open_group_random)
        )

        side_layout.addStretch()

        self.btn_theme = QPushButton()
        self.btn_theme.setProperty("nav", True)
        self.btn_theme.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_theme.clicked.connect(self._toggle_theme)
        side_layout.addWidget(self.btn_theme)

        btn_new = QPushButton("+  Neuer Eintrag")
        btn_new.setProperty("variant", "primary")
        btn_new.setFixedHeight(40)
        btn_new.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_new.clicked.connect(self._create_new)
        side_layout.addWidget(btn_new)

        main_layout.addWidget(sidebar)

        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(24, 20, 24, 20)
        content_layout.setSpacing(12)

        top_bar = QHBoxLayout()
        top_bar.setSpacing(10)
        self.lbl_view_title = QLabel("🖼️ Bilder")
        self.lbl_view_title.setObjectName("PageTitle")
        top_bar.addWidget(self.lbl_view_title)
        top_bar.addStretch()

        self.inp_search = QLineEdit()
        self.inp_search.setPlaceholderText("Titel, Beschreibung, Gruppe suchen…")
        self.inp_search.setClearButtonEnabled(True)
        self.inp_search.setFixedWidth(240)
        self.inp_search.textChanged.connect(self._schedule_search_refresh)
        self.inp_search.returnPressed.connect(self._flush_search)
        top_bar.addWidget(self.inp_search)

        lbl_group = QLabel("Gruppe")
        lbl_group.setObjectName("MutedLabel")
        top_bar.addWidget(lbl_group)
        self.combo_group = QComboBox()
        self.combo_group.setMinimumWidth(140)
        self.combo_group.currentTextChanged.connect(self.refresh_data)
        top_bar.addWidget(self.combo_group)

        self.combo_sort = QComboBox()
        self.combo_sort.setMinimumWidth(160)
        for sort_key, sort_label in (
            ("title", "Titel A–Z"),
            ("score_desc", "Score ↓"),
            ("score_asc", "Score ↑"),
            ("last_watched", "Zuletzt gesehen"),
        ):
            self.combo_sort.addItem(sort_label, sort_key)
        self.combo_sort.currentIndexChanged.connect(self.refresh_data)
        top_bar.addWidget(self.combo_sort)

        content_layout.addLayout(top_bar)

        self.action_bar = QWidget()
        self.action_bar.setObjectName("ActionBar")
        ab_layout = QHBoxLayout(self.action_bar)
        ab_layout.setContentsMargins(12, 8, 12, 8)
        ab_layout.setSpacing(8)

        self.btn_sel_all = QPushButton("Alle")
        self.btn_sel_all.setProperty("variant", "ghost")
        self.btn_sel_all.clicked.connect(self._select_all)
        self.btn_sel_none = QPushButton("Keine")
        self.btn_sel_none.setProperty("variant", "ghost")
        self.btn_sel_none.clicked.connect(self._deselect_all)
        self.lbl_sel_count = QLabel("Keine Auswahl")
        self.lbl_sel_count.setObjectName("SelectionCount")
        self.lbl_hint = QLabel("Shift = Bereich · Ziehen = Rahmen")
        self.lbl_hint.setObjectName("HintLabel")
        self.lbl_hint.setToolTip(
            "Klick toggelt die Auswahl · Shift+Klick wählt einen Bereich · "
            "Ziehen markiert mehrere Kacheln"
        )
        self.lbl_hint.setSizePolicy(
            QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred
        )

        self.btn_batch_score = QPushButton("Score setzen")
        self.btn_batch_score.setProperty("variant", "secondary")
        self.btn_batch_score.clicked.connect(self._batch_score)
        self.btn_batch_group = QPushButton("Gruppe setzen")
        self.btn_batch_group.setProperty("variant", "secondary")
        self.btn_batch_group.clicked.connect(self._batch_group)
        self.btn_batch_del = QPushButton("Löschen")
        self.btn_batch_del.setProperty("variant", "danger")
        self.btn_batch_del.clicked.connect(self._batch_delete)

        ab_layout.addWidget(self.btn_sel_all)
        ab_layout.addWidget(self.btn_sel_none)
        ab_layout.addWidget(self.lbl_sel_count)
        ab_layout.addWidget(self.lbl_hint)
        ab_layout.addStretch()
        ab_layout.addWidget(self.btn_batch_score)
        ab_layout.addWidget(self.btn_batch_group)
        ab_layout.addWidget(self.btn_batch_del)
        content_layout.addWidget(self.action_bar)

        self.lbl_empty = QLabel("Keine Einträge gefunden.")
        self.lbl_empty.setObjectName("MutedLabel")
        self.lbl_empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_empty.hide()
        content_layout.addWidget(self.lbl_empty)

        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setObjectName("CardScroll")
        self.grid_container = QWidget()
        self.grid_container.setObjectName("GridContainer")
        self.grid_layout = QGridLayout(self.grid_container)
        self.grid_layout.setContentsMargins(0, 0, 0, 0)
        self.grid_layout.setSpacing(self.GRID_SPACING)
        self.grid_layout.setAlignment(
            Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft
        )
        self.scroll_area.setWidget(self.grid_container)
        self.scroll_area.viewport().setObjectName("GridViewport")
        self.scroll_area.viewport().installEventFilter(self)
        content_layout.addWidget(self.scroll_area, 1)

        main_layout.addWidget(content, 1)

    def _create_section_label(self, text):
        """Erzeugt ein gedämpftes Abschnittslabel für die Sidebar."""
        label = QLabel(text)
        label.setObjectName("SectionLabel")
        label.setContentsMargins(4, 10, 0, 2)
        return label

    def _create_side_btn(self, text, callback, checkable=False):
        """Erzeugt einen linksbündigen Sidebar-Button mit Callback."""
        btn = QPushButton(text)
        btn.setProperty("nav", True)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        if checkable:
            btn.setCheckable(True)
            btn.setAutoExclusive(True)
        btn.clicked.connect(callback)
        return btn

    # --- Daten und Ansicht ---
    def switch_view(self, view):
        """Wechselt zwischen Bilder- und Videos-Ansicht und lädt neu."""
        self.current_view = view
        self.btn_bilder.setChecked(view == "Bilder")
        self.btn_videos.setChecked(view == "Videos")
        self.lbl_view_title.setText("🖼️ Bilder" if view == "Bilder" else "🎬 Videos")
        self._cancel_drag()
        self._apply_selection(set())
        self._anchor_entry = None
        self.refresh_data()

    def _get_pixmap(self, entry):
        """Liefert das Vorschaubild eines Eintrags, gecacht im Thumbnail-Cache."""
        key = entry.image_path or entry.video_link
        if key not in self.thumbnail_cache:
            pixmap = None
            if entry.image_path:
                try:
                    pixmap = QPixmap(entry.image_path)
                except (OSError, TypeError, ValueError):
                    logger.debug(
                        "Bild konnte nicht geladen werden: %s",
                        entry.image_path,
                        exc_info=True,
                    )
            elif entry.entry_type == "Videos":
                pixmap = OSHelper.get_video_frame_pixmap(entry.video_link)
                if not pixmap:
                    os_thumb = OSHelper.get_os_thumbnail(entry.video_link)
                    if os_thumb:
                        pixmap = QPixmap(os_thumb)
            self.thumbnail_cache[key] = pixmap
        return self.thumbnail_cache[key]

    def _visible_entries(self):
        """Liefert die sichtbaren Einträge nach Gruppenfilter, Suche und Sortierung."""
        entries = self.db.get_by_type(self.current_view)

        filter_grp = self.combo_group.currentText()
        if filter_grp and filter_grp != "Alle Gruppen":
            entries = [entry for entry in entries if entry.group == filter_grp]

        query = self.inp_search.text().strip().casefold()
        if query:
            entries = [
                entry
                for entry in entries
                if query in (entry.title or "").casefold()
                or query in (entry.description or "").casefold()
                or query in (entry.group or "").casefold()
            ]

        sort_mode = self.combo_sort.currentData()
        if sort_mode == "score_desc":
            entries.sort(key=lambda entry: (-entry.score, entry.title.casefold()))
        elif sort_mode == "score_asc":
            entries.sort(key=lambda entry: (entry.score, entry.title.casefold()))
        elif sort_mode == "last_watched":
            entries.sort(
                key=lambda entry: (entry.last_watched > 0, entry.last_watched),
                reverse=True,
            )
        else:
            entries.sort(key=lambda entry: entry.title.casefold())
        return entries

    def refresh_data(self, *_args):
        """Aktualisiert Filter, Kacheln und Grid anhand der aktuellen Ansicht."""
        self._cancel_drag()

        current_filter = self.combo_group.currentText()
        groups = self.db.get_all_groups()
        self.combo_group.blockSignals(True)
        self.combo_group.clear()
        self.combo_group.addItems(["Alle Gruppen"] + groups)
        if current_filter in ["Alle Gruppen"] + groups:
            self.combo_group.setCurrentText(current_filter)
        self.combo_group.blockSignals(False)

        while self.grid_layout.count():
            item = self.grid_layout.takeAt(0)
            widget = item.widget() if item else None
            if widget is not None:
                widget.hide()
                widget.setParent(None)
                widget.deleteLater()
        self.cards.clear()

        for entry in self._visible_entries():
            card = MediaCard(entry, self._get_pixmap(entry))
            card.clicked.connect(self._on_card_clicked)
            card.double_clicked.connect(self._on_card_double_clicked)
            card.drag_pressed.connect(self._on_drag_pressed)
            card.drag_moved.connect(self._on_drag_moved)
            card.drag_finished.connect(self._on_drag_finished)
            self.cards.append(card)

        visible = {card.entry for card in self.cards}
        self.selected_entries.intersection_update(visible)
        if self._anchor_entry not in visible:
            self._anchor_entry = None

        for card in self.cards:
            card.set_selected(card.entry in self.selected_entries)

        self.lbl_empty.setVisible(not self.cards)
        self._update_columns()
        self._reflow_grid()
        self._update_action_bar()

    # --- Grid ---
    def resizeEvent(self, event):
        """Passt die Spaltenanzahl des Grids an die Fensterbreite an."""
        super().resizeEvent(event)
        self._update_columns()

    def eventFilter(self, obj, event):
        """Reagiert auf Breitenänderungen des Scroll-Viewports."""
        if (
            hasattr(self, "scroll_area")
            and obj is self.scroll_area.viewport()
            and event.type() == QEvent.Type.Resize
        ):
            self._update_columns()
        return super().eventFilter(obj, event)

    def changeEvent(self, event):
        """Bricht eine laufende Rechteckauswahl beim Fensterwechsel ab."""
        if event.type() == QEvent.Type.WindowDeactivate:
            self._cancel_drag()
        super().changeEvent(event)

    def _update_columns(self):
        """Berechnet die Spaltenzahl aus der Viewport-Breite."""
        if not hasattr(self, "scroll_area"):
            return
        available = self.scroll_area.viewport().width() - self.SCROLLBAR_RESERVE
        cols = max(
            1,
            (available + self.GRID_SPACING) // (CARD_WIDTH + self.GRID_SPACING),
        )
        if cols != self.current_cols:
            self.current_cols = cols
            self._reflow_grid()

    def _reflow_grid(self):
        """Ordnet die vorhandenen Kacheln neu im Grid an, ohne sie neu zu laden."""
        while self.grid_layout.count():
            self.grid_layout.takeAt(0)

        for index, card in enumerate(self.cards):
            row, col = divmod(index, self.current_cols)
            self.grid_layout.addWidget(card, row, col)

    # --- Auswahl ---
    def _apply_selection(self, entries):
        """Synchronisiert Auswahlmenge und Kartenoptik an einer Stelle."""
        self.selected_entries = set(entries)
        for card in self.cards:
            card.set_selected(card.entry in self.selected_entries)
        self._update_action_bar()

    def _on_card_clicked(self, entry, modifiers):
        """Toggelt eine Karte oder wählt bei Shift einen Bereich aus."""
        # Änderung erst nach dem Snapshot: ein folgender Doppelklick kann sie
        # so vollständig rückgängig machen.
        self._press_snapshot = set(self.selected_entries)
        if (
            modifiers & Qt.KeyboardModifier.ShiftModifier
            and self._anchor_entry is not None
        ):
            entries = [card.entry for card in self.cards]
            if entry in entries and self._anchor_entry in entries:
                start = entries.index(self._anchor_entry)
                end = entries.index(entry)
                lo, hi = sorted((start, end))
                self._apply_selection(
                    self.selected_entries | set(entries[lo : hi + 1])
                )
                return

        new_selection = set(self.selected_entries)
        if entry in new_selection:
            new_selection.discard(entry)
        else:
            new_selection.add(entry)
        self._apply_selection(new_selection)
        self._anchor_entry = entry

    def _on_card_double_clicked(self, entry):
        """Öffnet Details und macht das Toggeln des ersten Klicks rückgängig."""
        self._cancel_drag()
        self._apply_selection(self._press_snapshot)
        self._open_detail(entry)

    def _select_all(self):
        """Markiert alle sichtbaren Kacheln als ausgewählt."""
        self._apply_selection({card.entry for card in self.cards})

    def _deselect_all(self):
        """Hebt die Auswahl aller sichtbaren Kacheln auf."""
        self._cancel_drag()
        self._apply_selection(set())

    def _update_action_bar(self):
        """Aktualisiert Auswahlzähler und den Zustand der Batch-Buttons."""
        count = len(self.selected_entries)
        self.lbl_sel_count.setText(
            f"{count} ausgewählt" if count else "Keine Auswahl"
        )
        enabled = count > 0
        self.btn_batch_score.setEnabled(enabled)
        self.btn_batch_group.setEnabled(enabled)
        self.btn_batch_del.setEnabled(enabled)
        self.btn_sel_none.setEnabled(count > 0)
        self.btn_sel_all.setEnabled(bool(self.cards))
        self.lbl_hint.setVisible(count == 0)

    # --- Rechteckauswahl ---
    def _ensure_rubber_band(self):
        """Erzeugt das Auswahlrechteck bei Bedarf."""
        if self._rubber_band is None:
            self._rubber_band = QRubberBand(
                QRubberBand.Shape.Rectangle, self.scroll_area.viewport()
            )
            self._rubber_band.setAttribute(
                Qt.WidgetAttribute.WA_TransparentForMouseEvents, True
            )
        return self._rubber_band

    def _on_drag_pressed(self, entry, global_pos):
        """Sichert die Ausgangsauswahl vor dem ersten Klick."""
        self._press_snapshot = set(self.selected_entries)
        self._drag_base = set(self.selected_entries)
        self._drag_origin_global = global_pos
        self._last_drag_global = global_pos

    def _on_drag_moved(self, global_pos):
        """Zeichnet das Auswahlrechteck und markiert berührte Karten."""
        if self._drag_origin_global is None:
            return
        self._last_drag_global = global_pos
        viewport = self.scroll_area.viewport()
        origin = viewport.mapFromGlobal(self._drag_origin_global)
        current = viewport.mapFromGlobal(global_pos)
        rect = QRect(origin, current).normalized().intersected(viewport.rect())

        band = self._ensure_rubber_band()
        band.setGeometry(rect)
        if not band.isVisible():
            band.show()
        band.raise_()

        self._apply_selection(self._drag_base | self._cards_intersecting(rect))
        self._update_autoscroll(current)

    def _on_drag_finished(self):
        """Beendet die Rechteckauswahl."""
        self._cancel_drag()

    def _cancel_drag(self):
        """Blendet das Auswahlrechteck aus und stoppt den Auto-Scroll."""
        self._autoscroll_timer.stop()
        self._autoscroll_direction = 0
        self._drag_origin_global = None
        self._last_drag_global = None
        self._drag_base = set()
        if self._rubber_band is not None:
            self._rubber_band.hide()
            self._rubber_band.setGeometry(QRect())

    def _cards_intersecting(self, rect):
        """Liefert alle Karten, die das Rechteck im Viewport schneidet."""
        viewport = self.scroll_area.viewport()
        hits = set()
        for card in self.cards:
            top_left = card.mapTo(viewport, QPoint(0, 0))
            if rect.intersects(QRect(top_left, card.size())):
                hits.add(card.entry)
        return hits

    def _update_autoscroll(self, pos_in_viewport):
        """Startet oder stoppt das Scrollen am oberen/unteren Rand."""
        viewport = self.scroll_area.viewport()
        direction = 0
        if pos_in_viewport.y() < self.AUTOSCROLL_MARGIN:
            direction = -1
        elif pos_in_viewport.y() > viewport.height() - self.AUTOSCROLL_MARGIN:
            direction = 1
        self._autoscroll_direction = direction
        if direction and not self._autoscroll_timer.isActive():
            self._autoscroll_timer.start()
        elif not direction:
            self._autoscroll_timer.stop()

    def _autoscroll_step(self):
        """Scrollt während einer Rechteckauswahl schrittweise weiter."""
        if not self._autoscroll_direction or self._last_drag_global is None:
            self._autoscroll_timer.stop()
            return
        bar = self.scroll_area.verticalScrollBar()
        before = bar.value()
        bar.setValue(before + self._autoscroll_direction * self.AUTOSCROLL_STEP)
        if bar.value() == before:
            self._autoscroll_timer.stop()
            return
        self._on_drag_moved(self._last_drag_global)

    # --- Tastatur und Suche ---
    def keyPressEvent(self, event):
        """Verarbeitet Tastenkürzel für Auswahl, Löschen und Suche."""
        if event.matches(QKeySequence.StandardKey.SelectAll):
            self._select_all()
            event.accept()
            return
        if event.matches(QKeySequence.StandardKey.Find):
            self.inp_search.setFocus()
            self.inp_search.selectAll()
            event.accept()
            return
        if event.key() == Qt.Key.Key_Escape:
            if self._drag_origin_global is not None:
                self._cancel_drag()
                self._apply_selection(self._press_snapshot)
            else:
                self._deselect_all()
            event.accept()
            return
        if event.key() == Qt.Key.Key_Delete and self.selected_entries:
            self._batch_delete()
            event.accept()
            return
        super().keyPressEvent(event)

    def _schedule_search_refresh(self, _text=None):
        """Verzögert den Neuaufbau des Grids während der Eingabe."""
        if not self.inp_search.text():
            self._search_timer.stop()
            self.refresh_data()
        else:
            self._search_timer.start()

    def _flush_search(self):
        """Aktualisiert die Suche sofort (Enter)."""
        self._search_timer.stop()
        self.refresh_data()

    # --- Theme ---
    def _sync_theme_button(self):
        """Passt Beschriftung des Theme-Umschalters an."""
        dark = self.theme.name == "dark"
        self.btn_theme.setText("☀️  Helles Theme" if dark else "🌙  Dunkles Theme")
        self.btn_theme.setToolTip(
            "Zu hellem Theme wechseln" if dark else "Zu dunklem Theme wechseln"
        )

    def _toggle_theme(self):
        """Wechselt live zwischen Dark und Light."""
        self.theme.toggle(QApplication.instance())
        self._sync_theme_button()

    # --- Aktionen ---
    def _open_detail(self, entry):
        """Öffnet den Detaildialog und merkt den Eintrag als letzten Pick."""
        if entry in self.recent_picks:
            self.recent_picks.remove(entry)
        self.recent_picks.append(entry)
        if len(self.recent_picks) > 2:
            self.recent_picks.pop(0)

        dlg = DetailDialog(self, entry, self.db, self._get_pixmap)
        dlg.exec()
        if dlg.edit_requested:
            self._open_edit(entry)
        else:
            self.refresh_data()

    def _open_edit(self, entry):
        """Öffnet den Bearbeiten-Dialog und lädt die Ansicht nach dem Speichern neu."""
        dlg = EditDialog(self, self.db, entry.entry_type, entry)
        if dlg.exec():
            self.db.save()
            key = entry.image_path or entry.video_link
            if key in self.thumbnail_cache:
                del self.thumbnail_cache[key]
            self.refresh_data()

    def _create_new(self):
        """Zeigt ein Menü zur Auswahl zwischen Einzel- und Massenanlage."""
        choice, ok = QInputDialog.getItem(
            self,
            "Neu",
            "Aktion wählen:",
            ["Bild einzeln", "Video einzeln", "Bilder Massenimport", "Videos Massenimport"],
            0,
            False,
        )
        if not ok:
            return

        if choice == "Bild einzeln":
            self._create_single("Bilder")
        elif choice == "Video einzeln":
            self._create_single("Videos")
        elif choice == "Bilder Massenimport":
            self._batch_import("Bilder")
        else:
            self._batch_import("Videos")

    def _create_single(self, type_str):
        """Öffnet den nativen Datei-Explorer und legt danach einen Eintrag an."""
        if type_str == "Bilder":
            file_filter = "Bilder (*.png *.jpg *.jpeg *.bmp *.webp);;Alle Dateien (*.*)"
        else:
            file_filter = "Videos (*.mp4 *.mkv *.avi *.mov *.webm);;Alle Dateien (*.*)"

        path, _ = OSHelper.pick_file(self, "Datei auswählen", file_filter)
        if not path:
            return

        dlg = EditDialog(self, self.db, type_str)
        if type_str == "Bilder":
            dlg.inp_img.setText(path)
        else:
            dlg.inp_video.setText(path)

        if dlg.exec():
            self.db.save()
            self.refresh_data()

    def _batch_import(self, type_str):
        """Importiert mehrere Dateien als Einträge und überspringt Duplikate."""
        exts = (
            "*.png *.jpg *.jpeg *.bmp *.webp"
            if type_str == "Bilder"
            else "*.mp4 *.mkv *.avi *.mov *.webm"
        )
        paths, _ = OSHelper.pick_files(
            self, "Importieren", f"Media ({exts});;Alle (*.*)"
        )
        if not paths:
            return

        group = (
            self.combo_group.currentText()
            if self.combo_group.currentText() != "Alle Gruppen"
            else ""
        )
        existing = (
            {entry.image_path for entry in self.db.get_by_type("Bilder")}
            if type_str == "Bilder"
            else {entry.video_link for entry in self.db.get_by_type("Videos")}
        )
        existing_titles = {entry.title for entry in self.db.get_by_type(type_str)}

        count = 0
        for path in paths:
            if path in existing:
                continue
            title = os.path.splitext(os.path.basename(path))[0]
            if title in existing_titles:
                continue
            img, vid = (path, "") if type_str == "Bilder" else ("", path)
            self.db.add(MediaItem(title, img, 50, "", type_str, vid, group=group))
            count += 1
        if count > 0:
            self.db.save()
            self.refresh_data()

    def _batch_delete(self):
        """Löscht alle ausgewählten Einträge nach Bestätigung."""
        if (
            QMessageBox.question(
                self, "Löschen", f"{len(self.selected_entries)} löschen?"
            )
            == QMessageBox.StandardButton.Yes
        ):
            for entry in self.selected_entries:
                key = entry.image_path or entry.video_link
                if key in self.thumbnail_cache:
                    del self.thumbnail_cache[key]
            self.db.delete_multiple(self.selected_entries)
            self.recent_picks = [
                entry
                for entry in self.recent_picks
                if entry not in self.selected_entries
            ]
            self._deselect_all()
            self.refresh_data()

    def _batch_score(self):
        """Setzt den Score für alle ausgewählten Einträge auf einen neuen Wert."""
        score, ok = QInputDialog.getInt(
            self, "Score", "Neuer Score (1-100):", 50, 1, 100
        )
        if ok:
            for entry in self.selected_entries:
                entry.score = score
            self.db.save()
            self._deselect_all()
            self.refresh_data()

    def _batch_group(self):
        """Weist allen ausgewählten Einträgen eine neue Gruppe zu."""
        grp, ok = QInputDialog.getItem(
            self,
            "Gruppe",
            "Neue Gruppe (oder neuen Namen tippen):",
            [""] + self.db.get_all_groups(),
            0,
            True,
        )
        if ok:
            for entry in self.selected_entries:
                entry.group = grp.strip()
            self.db.save()
            self._deselect_all()
            self.refresh_data()

    def _do_random(self, smart, global_pool):
        """Wählt zufällig einen Eintrag (lokal oder global) und öffnet ihn."""
        pool = (
            self.db.entries
            if global_pool
            else self.db.get_by_type(self.current_view)
        )
        chosen = self.db.get_random(pool, smart, self.recent_picks)
        if chosen:
            self._open_detail(chosen)

    def _open_group_random(self):
        """Öffnet den Gruppen-Zufallsdialog und zeigt den gewählten Eintrag."""
        dlg = GroupRandomDialog(self, self.db)
        if dlg.exec() and dlg.result_pool:
            chosen = self.db.get_random(
                dlg.result_pool, dlg.smart, self.recent_picks
            )
            if chosen:
                self._open_detail(chosen)
