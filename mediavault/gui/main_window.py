import os
from PyQt6.QtWidgets import QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, QPushButton, QLabel, QComboBox, QScrollArea, QGridLayout, QInputDialog, QMessageBox, QFileDialog
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPixmap

from mediavault.models import MediaDatabase, MediaItem
from mediavault.utils import OSHelper
from mediavault.gui.widgets import MediaCard
from mediavault.gui.dialogs import DetailDialog, EditDialog, GroupRandomDialog

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Media Score Tracker")
        self.resize(1100, 800)

        self.db = MediaDatabase()
        self.db.load()

        self.current_view = "Bilder"
        self.selected_entries = set()
        self.recent_picks = []
        self.thumbnail_cache = {}
        self.cards = [] # Hält Referenzen auf UI-Karten
        self.current_cols = 1

        self._setup_ui()
        self.refresh_data()

    def _setup_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QHBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # --- Sidebar ---
        sidebar = QWidget()
        sidebar.setFixedWidth(220)
        sidebar.setStyleSheet("background-color: #1e1e1e;")
        side_layout = QVBoxLayout(sidebar)
        side_layout.setContentsMargins(15, 20, 15, 20)

        lbl_title = QLabel("Media Tracker")
        lbl_title.setStyleSheet("font-size: 20px; font-weight: bold; margin-bottom: 20px;")
        side_layout.addWidget(lbl_title)

        self.btn_bilder = self._create_side_btn("🖼️ Bilder", lambda: self.switch_view("Bilder"))
        self.btn_videos = self._create_side_btn("🎬 Videos", lambda: self.switch_view("Videos"))
        side_layout.addWidget(QLabel("ANSICHTEN", styleSheet="color: gray; margin-top: 10px;"))
        side_layout.addWidget(self.btn_bilder)
        side_layout.addWidget(self.btn_videos)

        side_layout.addWidget(QLabel("ZUFALL (LOKAL)", styleSheet="color: gray; margin-top: 20px;"))
        side_layout.addWidget(self._create_side_btn("🎲 Normal", lambda: self._do_random(False, False)))
        side_layout.addWidget(self._create_side_btn("⚖️ Smart", lambda: self._do_random(True, False)))

        side_layout.addWidget(QLabel("ZUFALL (GLOBAL)", styleSheet="color: gray; margin-top: 20px;"))
        side_layout.addWidget(self._create_side_btn("🌍 Alles", lambda: self._do_random(False, True)))
        side_layout.addWidget(self._create_side_btn("⚖️🌍 Alles Smart", lambda: self._do_random(True, True)))
        side_layout.addWidget(self._create_side_btn("📂 Aus Gruppen", self._open_group_random))

        side_layout.addStretch()

        btn_new = QPushButton("+ Neuer Eintrag")
        btn_new.setFixedHeight(40)
        btn_new.setStyleSheet("background-color: #3b8ed0; font-weight: bold; border-radius: 5px;")
        btn_new.clicked.connect(self._create_new)
        side_layout.addWidget(btn_new)
        
        main_layout.addWidget(sidebar)

        # --- Content Area ---
        content = QWidget()
        content_layout = QVBoxLayout(content)
        
        # Top Bar
        top_bar = QHBoxLayout()
        self.lbl_view_title = QLabel("🖼️ Bilder")
        self.lbl_view_title.setStyleSheet("font-size: 26px; font-weight: bold;")
        top_bar.addWidget(self.lbl_view_title)
        top_bar.addStretch()
        
        self.combo_group = QComboBox()
        self.combo_group.currentTextChanged.connect(self.refresh_data)
        top_bar.addWidget(QLabel("Filter:"))
        top_bar.addWidget(self.combo_group)
        content_layout.addLayout(top_bar)

        # Action Bar
        self.action_bar = QWidget()
        self.action_bar.setStyleSheet("background-color: #2a2a2a; border-radius: 5px;")
        ab_layout = QHBoxLayout(self.action_bar)
        
        btn_sel_all = QPushButton("Alle"); btn_sel_all.clicked.connect(self._select_all)
        btn_sel_none = QPushButton("Keine"); btn_sel_none.clicked.connect(self._deselect_all)
        self.lbl_sel_count = QLabel("0 ausgewählt")
        
        self.btn_batch_score = QPushButton("Score setzen"); self.btn_batch_score.clicked.connect(self._batch_score)
        self.btn_batch_group = QPushButton("Gruppe setzen"); self.btn_batch_group.clicked.connect(self._batch_group)
        self.btn_batch_del = QPushButton("Löschen"); self.btn_batch_del.setStyleSheet("background-color: #B20710;")
        self.btn_batch_del.clicked.connect(self._batch_delete)

        ab_layout.addWidget(btn_sel_all); ab_layout.addWidget(btn_sel_none)
        ab_layout.addWidget(self.lbl_sel_count); ab_layout.addStretch()
        ab_layout.addWidget(self.btn_batch_score); ab_layout.addWidget(self.btn_batch_group)
        ab_layout.addWidget(self.btn_batch_del)
        content_layout.addWidget(self.action_bar)

        # Scroll Area for Grid
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setStyleSheet("QScrollArea { border: none; }")
        
        self.grid_container = QWidget()
        self.grid_layout = QGridLayout(self.grid_container)
        self.grid_layout.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self.scroll_area.setWidget(self.grid_container)
        
        content_layout.addWidget(self.scroll_area)
        main_layout.addWidget(content)
        
        self._update_action_bar()

    def _create_side_btn(self, text, callback):
        btn = QPushButton(text)
        btn.setStyleSheet("text-align: left; padding: 8px; border: none;")
        btn.clicked.connect(callback)
        return btn

    def switch_view(self, view):
        self.current_view = view
        self.lbl_view_title.setText("🖼️ Bilder" if view == "Bilder" else "🎬 Videos")
        self._deselect_all()
        self.refresh_data()

    def _get_pixmap(self, entry):
        key = entry.image_path or entry.video_link
        if key not in self.thumbnail_cache:
            pixmap = None
            if entry.image_path:
                try: pixmap = QPixmap(entry.image_path)
                except: pass
            elif entry.entry_type == "Videos":
                pixmap = OSHelper.get_video_frame_pixmap(entry.video_link)
                if not pixmap:
                    os_thumb = OSHelper.get_os_thumbnail(entry.video_link)
                    if os_thumb: pixmap = QPixmap(os_thumb)
            self.thumbnail_cache[key] = pixmap
        return self.thumbnail_cache[key]

    def refresh_data(self):
        # Update Dropdown
        current_filter = self.combo_group.currentText()
        self.combo_group.blockSignals(True)
        self.combo_group.clear()
        self.combo_group.addItems(["Alle Gruppen"] + self.db.get_all_groups())
        if current_filter in ["Alle Gruppen"] + self.db.get_all_groups():
            self.combo_group.setCurrentText(current_filter)
        self.combo_group.blockSignals(False)

        # Clear UI
        while self.grid_layout.count():
            item = self.grid_layout.takeAt(0)
            if item.widget(): item.widget().deleteLater()
        self.cards.clear()

        # Build Cards
        filter_grp = self.combo_group.currentText()
        entries = self.db.get_by_type(self.current_view)
        if filter_grp != "Alle Gruppen":
            entries = [e for e in entries if e.group == filter_grp]

        for entry in entries:
            card = MediaCard(entry, self._get_pixmap(entry))
            card.set_checked(entry in self.selected_entries)
            card.clicked.connect(self._open_detail)
            card.selection_changed.connect(self._on_card_selection)
            self.cards.append(card)

        self._reflow_grid()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        cols = max(1, self.scroll_area.viewport().width() // 200)
        if cols != self.current_cols:
            self.current_cols = cols
            self._reflow_grid()

    def _reflow_grid(self):
        # Ordnet existierende Karten neu an, ohne sie neu zu laden (sehr schnell)
        for i in range(self.grid_layout.count()):
            self.grid_layout.takeAt(0)
            
        for index, card in enumerate(self.cards):
            row, col = divmod(index, self.current_cols)
            self.grid_layout.addWidget(card, row, col)

    # --- Actions ---
    def _on_card_selection(self, entry, is_checked):
        if is_checked: self.selected_entries.add(entry)
        else: self.selected_entries.discard(entry)
        self._update_action_bar()

    def _select_all(self):
        for card in self.cards: card.set_checked(True)

    def _deselect_all(self):
        for card in self.cards: card.set_checked(False)

    def _update_action_bar(self):
        count = len(self.selected_entries)
        self.lbl_sel_count.setText(f"|  {count} ausgewählt")
        enabled = count > 0
        self.btn_batch_score.setEnabled(enabled)
        self.btn_batch_group.setEnabled(enabled)
        self.btn_batch_del.setEnabled(enabled)
        self.action_bar.setVisible(enabled)

    def _open_detail(self, entry):
        if entry in self.recent_picks: self.recent_picks.remove(entry)
        self.recent_picks.append(entry)
        if len(self.recent_picks) > 2: self.recent_picks.pop(0)

        dlg = DetailDialog(self, entry, self.db, self._get_pixmap)
        dlg.exec()
        if dlg.edit_requested:
            self._open_edit(entry)
        else:
            self.refresh_data()

    def _open_edit(self, entry):
        dlg = EditDialog(self, self.db, entry.entry_type, entry)
        if dlg.exec():
            self.db.save()
            key = entry.image_path or entry.video_link
            if key in self.thumbnail_cache: del self.thumbnail_cache[key]
            self.refresh_data()

    def _create_new(self):
        # Simples Menü (Bilder/Videos importieren oder einzeln)
        choice, ok = QInputDialog.getItem(self, "Neu", "Aktion wählen:", ["Bild einzeln", "Video einzeln", "Bilder Massenimport", "Videos Massenimport"], 0, False)
        if not ok: return

        if choice == "Bild einzeln":
            if EditDialog(self, self.db, "Bilder").exec(): self.refresh_data()
        elif choice == "Video einzeln":
            if EditDialog(self, self.db, "Videos").exec(): self.refresh_data()
        elif choice == "Bilder Massenimport":
            self._batch_import("Bilder")
        else:
            self._batch_import("Videos")

    def _batch_import(self, type_str):
        exts = "*.png *.jpg *.jpeg *.bmp *.webp" if type_str == "Bilder" else "*.mp4 *.mkv *.avi *.mov *.webm"
        paths, _ = QFileDialog.getOpenFileNames(self, "Importieren", "", f"Media ({exts});;Alle (*.*)")
        if not paths: return
        
        group = self.combo_group.currentText() if self.combo_group.currentText() != "Alle Gruppen" else ""
        existing = {e.image_path for e in self.db.get_by_type("Bilder")} if type_str == "Bilder" else {e.video_link for e in self.db.get_by_type("Videos")}
        
        count = 0
        for p in paths:
            if p in existing: continue
            t = os.path.splitext(os.path.basename(p))[0]
            img, vid = (p, "") if type_str == "Bilder" else ("", p)
            self.db.add(MediaItem(t, img, 50, "", type_str, vid, group=group))
            count += 1
        if count > 0: self.refresh_data()

    def _batch_delete(self):
        if QMessageBox.question(self, "Löschen", f"{len(self.selected_entries)} löschen?") == QMessageBox.StandardButton.Yes:
            for e in self.selected_entries:
                key = e.image_path or e.video_link
                if key in self.thumbnail_cache: del self.thumbnail_cache[key]
            self.db.delete_multiple(self.selected_entries)
            self._deselect_all()
            self.refresh_data()

    def _batch_score(self):
        score, ok = QInputDialog.getInt(self, "Score", "Neuer Score (1-100):", 50, 1, 100)
        if ok:
            for e in self.selected_entries: e.score = score
            self.db.save()
            self._deselect_all()
            self.refresh_data()

    def _batch_group(self):
        grp, ok = QInputDialog.getItem(self, "Gruppe", "Neue Gruppe (oder neuen Namen tippen):", [""] + self.db.get_all_groups(), 0, True)
        if ok:
            for e in self.selected_entries: e.group = grp.strip()
            self.db.save()
            self._deselect_all()
            self.refresh_data()

    def _do_random(self, smart, global_pool):
        pool = self.db.entries if global_pool else self.db.get_by_type(self.current_view)
        chosen = self.db.get_random(pool, smart, self.recent_picks)
        if chosen: self._open_detail(chosen)

    def _open_group_random(self):
        dlg = GroupRandomDialog(self, self.db)
        if dlg.exec() and dlg.result_pool:
            chosen = self.db.get_random(dlg.result_pool, dlg.smart, self.recent_picks)
            if chosen: self._open_detail(chosen)
