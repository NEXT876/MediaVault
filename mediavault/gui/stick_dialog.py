"""Dialog that binds a config to a folder on a removable volume."""

import os

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QVBoxLayout,
    QWidget,
)

from mediavault import volumes
from mediavault.config import (
    MODE_AI,
    MODE_NORMAL,
    VaultConfig,
    create_config,
    save_configs,
)
from mediavault.gui.widgets import button, field_label, hint_label


class StickDialog(QDialog):
    """Create a config from a stick folder or bind the active config to one."""

    def __init__(
        self,
        parent: QWidget | None,
        configs: list[VaultConfig],
        config: VaultConfig,
    ) -> None:
        """Initialize the dialog for the currently active config."""
        super().__init__(parent)
        self.configs = list(configs)
        self.config = config
        self.target_db_path = ""
        # Volume root whose existing absolute entries should become relative.
        self.migrate_root = ""
        self._roots: list[str] = []
        self._mount = ""
        self._volume_uuid = ""
        self._volume_label = ""
        self._folder_rel = ""
        self.setWindowTitle("Stick einrichten")
        self.setMinimumSize(620, 540)
        self._build_ui()
        self._fill_volumes()

    def _build_ui(self) -> None:
        """Build the drive list, the folder picker and the two actions."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(10)

        intro = hint_label(
            "Stick einstecken, hier den Medien-Ordner wählen und dann entweder "
            "eine neue Config anlegen oder die aktive Config auf diesen Ordner "
            "umstellen. Alles, was du danach von Hand hinzufügst, kopiert die App "
            "in genau diesen Ordner.",
            "MutedLabel",
        )
        layout.addWidget(intro)

        layout.addWidget(field_label("Laufwerke"))
        self.list_volumes = QListWidget()
        self.list_volumes.currentItemChanged.connect(self._on_volume_selected)
        layout.addWidget(self.list_volumes, 1)

        self.btn_pick = button(
            "Ordner auf diesem Laufwerk wählen…",
            "secondary",
            self._choose_folder,
        )
        self.btn_pick.setEnabled(False)
        layout.addWidget(self.btn_pick)

        self.lbl_folder = hint_label("Noch kein Ordner gewählt.")
        layout.addWidget(self.lbl_folder)

        layout.addSpacing(6)
        layout.addWidget(field_label("Neue Config"))
        name_row = QHBoxLayout()
        name_row.setSpacing(8)
        self.inp_name = QLineEdit()
        self.inp_name.setPlaceholderText("Name der neuen Config")
        name_row.addWidget(self.inp_name, 1)
        self.combo_mode = QComboBox()
        self.combo_mode.addItem("Normale Medien", MODE_NORMAL)
        self.combo_mode.addItem("KI-Bilder", MODE_AI)
        name_row.addWidget(self.combo_mode)
        layout.addLayout(name_row)

        buttons = QHBoxLayout()
        buttons.setSpacing(8)
        btn_cancel = button("Abbrechen", "ghost", self.reject)
        self.btn_assign = button(
            "Aktiver Config zuweisen",
            "secondary",
            self._assign_to_current,
        )
        self.btn_assign.setEnabled(False)
        self.btn_create = button("Neue Config anlegen", "primary", self._create_new)
        self.btn_create.setEnabled(False)
        buttons.addWidget(btn_cancel)
        buttons.addStretch()
        buttons.addWidget(self.btn_assign)
        buttons.addWidget(self.btn_create)
        layout.addLayout(buttons)

    def _fill_volumes(self) -> None:
        """List every mounted volume, marking the vault-enabled ones."""
        self.list_volumes.clear()
        self._roots = volumes.mounted_roots()
        preselect = -1
        for index, root in enumerate(self._roots):
            info = volumes.read_marker(root)
            if info is not None:
                owners = (c.name for c in self.configs if c.volume_uuid == info.uuid)
                owner = next(owners, "")
                state = f"Config \u201e{owner}\u201c" if owner else "noch nicht zugeordnet"
                text = f"🔌 {info.label or root} · {root} · {state}"
                if self.config.volume_uuid and info.uuid == self.config.volume_uuid:
                    preselect = index
            else:
                text = f"💾 {root} · kein Stick"
            item = QListWidgetItem(text)
            item.setData(Qt.ItemDataRole.UserRole, root)
            self.list_volumes.addItem(item)

        if not self._roots:
            self.lbl_folder.setText(
                "Kein Laufwerk erkannt. Stick einstecken und den Dialog erneut öffnen."
            )
            self.btn_pick.setEnabled(False)
            return
        self.btn_pick.setEnabled(True)
        preselect = max(preselect, 0)
        self.list_volumes.setCurrentRow(preselect)

    def _on_volume_selected(self, *_args: object) -> None:
        """Re-enable the folder picker when the selection changes."""
        self.btn_pick.setEnabled(self.list_volumes.currentItem() is not None)

    def _choose_folder(self) -> None:
        """Pick a media folder on the selected drive and remember its volume."""
        item = self.list_volumes.currentItem()
        if item is None:
            QMessageBox.information(self, "Stick", "Bitte zuerst ein Laufwerk wählen.")
            return
        root = str(item.data(Qt.ItemDataRole.UserRole) or "")
        folder = QFileDialog.getExistingDirectory(
            self, "Ordner auf dem Laufwerk wählen", root
        )
        if not folder:
            return
        actual_root, info = volumes.volume_for_path(folder, self._roots)
        if not actual_root:
            QMessageBox.warning(
                self, "Stick", "Der Ordner liegt auf keinem erkannten Laufwerk."
            )
            return
        if info is None:
            answer = QMessageBox.question(
                self,
                "Stick registrieren",
                "Dieses Laufwerk ist noch nicht als Mediathek registriert.\n\n"
                f"Es wird die kleine Datei {volumes.MARKER_NAME} im "
                f"Wurzelverzeichnis {actual_root} angelegt. Damit findet die App "
                "den Ordner auch nach einem Laufwerksbuchstaben-Wechsel wieder.",
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
            info = volumes.write_marker(
                actual_root, label=os.path.basename(actual_root.rstrip("\\/")) or actual_root
            )
            self._fill_volumes()
            if actual_root in self._roots:
                self.list_volumes.setCurrentRow(self._roots.index(actual_root))

        self._mount = actual_root
        self._volume_uuid = info.uuid
        self._volume_label = info.label or actual_root
        self._folder_rel = volumes.relative_to_root(folder, actual_root)
        self.lbl_folder.setText(f"Ordner: {folder}")
        if not self.inp_name.text().strip():
            self.inp_name.setText(os.path.basename(folder.rstrip("\\/")) or "Stick")
        self.btn_assign.setEnabled(True)
        self.btn_create.setEnabled(True)

    def _assign_to_current(self) -> None:
        """Point the active config at the chosen folder."""
        if not self._volume_uuid:
            return
        self.config.volume_uuid = self._volume_uuid
        self.config.volume_label = self._volume_label
        self.config.folder_rel = self._folder_rel
        self.config.folder = ""
        save_configs(self.configs, self.config.db_path)
        self.target_db_path = self.config.db_path
        self.migrate_root = self._mount
        self.accept()

    def _create_new(self) -> None:
        """Create a new config bound to the chosen folder."""
        name = self.inp_name.text().strip()
        if not name:
            QMessageBox.warning(self, "Fehler", "Name ist erforderlich.")
            return
        if any(item.name.casefold() == name.casefold() for item in self.configs):
            QMessageBox.warning(
                self, "Fehler", "Eine Config mit diesem Namen existiert bereits."
            )
            return
        if not self._volume_uuid:
            QMessageBox.warning(self, "Fehler", "Bitte zuerst einen Ordner wählen.")
            return
        config = create_config(
            name,
            self.combo_mode.currentData(),
            "",
            self.configs,
            volume_uuid=self._volume_uuid,
            volume_label=self._volume_label,
            folder_rel=self._folder_rel,
        )
        self.configs.append(config)
        save_configs(self.configs, config.db_path)
        self.target_db_path = config.db_path
        self.accept()
