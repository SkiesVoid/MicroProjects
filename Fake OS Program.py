import json
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, List, Optional

from PySide6.QtCore import QAbstractTableModel, QModelIndex, QObject, QTimer, Qt, Signal, QSize, QMimeData
from PySide6.QtGui import QAction, QDrag, QIcon
from PySide6.QtCore import QUrl
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMdiArea,
    QMdiSubWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QSplitter,
    QStatusBar,
    QStyle,
    QTableView,
    QTextEdit,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

APP_NAME = "SkiesOS"
APP_VERSION = "0.2.1"
DATA_DIR = Path.cwd() / "skiesos_data"
SETTINGS_FILE = DATA_DIR / "settings.json"
USER_FS_DIR = DATA_DIR / "userfs"

DEFAULT_SETTINGS = {
    "theme": "dark",
    "accent": "#3b82f6",
    "desktop_color": "#0f172a",
    "wallpaper_text": "SkiesOS",
    "icon_size": 72,
    "username": "Skies",
    "desktop_shortcuts": ["files", "task_manager", "desktop_manager", "notes", "browser"],
}

@dataclass
class AppManifest:
    app_id: str
    name: str
    category: str
    launcher: Callable[["OSContext"], None]
    description: str = ""
    preinstalled: bool = True

class SettingsStore:
    def __init__(self) -> None:
        DATA_DIR.mkdir(exist_ok=True)
        USER_FS_DIR.mkdir(exist_ok=True)
        self._ensure_default_dirs()
        self.settings = self._load_settings()

    def _ensure_default_dirs(self) -> None:
        for folder in [
            USER_FS_DIR / "Desktop",
            USER_FS_DIR / "Documents",
            USER_FS_DIR / "Downloads",
            USER_FS_DIR / "Pictures",
            USER_FS_DIR / "Apps",
        ]:
            folder.mkdir(parents=True, exist_ok=True)

        welcome_file = USER_FS_DIR / "Documents" / "welcome.txt"
        if not welcome_file.exists():
            welcome_file.write_text(
                "Welcome to SkiesOS.\n\n"
                "This is your internal operating system file space.\n"
                "Built-in apps should store their data here.\n",
                encoding="utf-8",
            )

        note_file = USER_FS_DIR / "Documents" / "quick_note.txt"
        if not note_file.exists():
            note_file.write_text(
                "This is the default quick note for SkiesOS.\n",
                encoding="utf-8",
            )

    def _load_settings(self) -> dict:
        if SETTINGS_FILE.exists():
            try:
                data = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
                return {**DEFAULT_SETTINGS, **data}
            except Exception:
                return DEFAULT_SETTINGS.copy()

        self.save(DEFAULT_SETTINGS.copy())
        return DEFAULT_SETTINGS.copy()

    def save(self, settings: Optional[dict] = None) -> None:
        payload = settings if settings is not None else self.settings
        SETTINGS_FILE.write_text(json.dumps(payload, indent=2), encoding="utf-8")

class OSContext(QObject):
    settings_changed = Signal(dict)
    window_opened = Signal(str)
    window_closed = Signal(str)

    def __init__(self, main_window: "SkiesOSWindow", settings_store: SettingsStore) -> None:
        super().__init__()
        self.main_window = main_window
        self.settings_store = settings_store
        self.registry: Dict[str, AppManifest] = {}

    @property
    def settings(self) -> dict:
        return self.settings_store.settings

    @property
    def user_fs(self) -> Path:
        return USER_FS_DIR

    @property
    def desktop_shortcuts(self) -> List[str]:
        shortcuts = self.settings_store.settings.get("desktop_shortcuts", [])
        return [app_id for app_id in shortcuts if app_id in self.registry]

    def register_app(self, manifest: AppManifest) -> None:
        self.registry[manifest.app_id] = manifest

    def launch_app(self, app_id: str) -> None:
        manifest = self.registry.get(app_id)
        if not manifest:
            QMessageBox.warning(self.main_window, "Missing app", f"App '{app_id}' is not registered.")
            return
        manifest.launcher(self)

    def open_internal_window(
        self,
        title: str,
        widget: QWidget,
        app_id: str,
        width: int = 800,
        height: int = 520,
    ) -> QMdiSubWindow:
        sub = QMdiSubWindow()
        sub.setWidget(widget)
        sub.setWindowTitle(title)
        sub.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        sub.resize(width, height)
        self.main_window.mdi.addSubWindow(sub)
        sub.show()
        self.window_opened.emit(app_id)

        old_close = sub.closeEvent

        def close_event(event):
            self.window_closed.emit(app_id)
            old_close(event)

        sub.closeEvent = close_event  # type: ignore[method-assign]
        return sub

    def update_setting(self, key: str, value) -> None:
        self.settings_store.settings[key] = value
        self.settings_store.save()
        self.settings_changed.emit(self.settings_store.settings.copy())

    def add_desktop_shortcut(self, app_id: str) -> bool:
        if app_id not in self.registry:
            return False
        shortcuts = self.settings_store.settings.setdefault("desktop_shortcuts", [])
        if app_id in shortcuts:
            return False
        shortcuts.append(app_id)
        self.settings_store.save()
        self.settings_changed.emit(self.settings_store.settings.copy())
        return True

    def remove_desktop_shortcut(self, app_id: str) -> bool:
        shortcuts = self.settings_store.settings.setdefault("desktop_shortcuts", [])
        if app_id not in shortcuts:
            return False
        shortcuts.remove(app_id)
        self.settings_store.save()
        self.settings_changed.emit(self.settings_store.settings.copy())
        return True

    def notify(self, title: str, message: str) -> None:
        self.main_window.statusBar().showMessage(f"{title}: {message}", 5000)


class AppListWidget(QListWidget):
    def startDrag(self, supported_actions) -> None:
        item = self.currentItem()
        if not item:
            return

        app_id = item.data(Qt.ItemDataRole.UserRole)
        if not app_id:
            return

        drag = QDrag(self)
        mime = QMimeData()
        mime.setData("application/x-skiesos-app", str(app_id).encode("utf-8"))
        drag.setMimeData(mime)

        rect = self.visualItemRect(item)
        pixmap = self.viewport().grab(rect)
        drag.setPixmap(pixmap)
        drag.setHotSpot(rect.center())
        drag.exec(Qt.DropAction.CopyAction)

class DesktopWidget(QWidget):
    def __init__(self, os_context: OSContext) -> None:
        super().__init__()
        self.os = os_context
        self.setObjectName("desktopRoot")
        self.icon_buttons: List[QPushButton] = []

        self.wallpaper = QLabel(self)
        self.wallpaper.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.wallpaper.setObjectName("wallpaperLabel")
        self.wallpaper.lower()

        self.icon_container = QWidget(self)
        self.icon_container.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        self.os.settings_changed.connect(self.refresh_style)
        self.refresh_style(self.os.settings)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self.wallpaper.setGeometry(self.rect())
        self.icon_container.setGeometry(self.rect())

    def set_apps(self, apps: List[AppManifest]) -> None:
        self.set_apps_from_shortcuts()

    def set_apps_from_shortcuts(self) -> None:
        for btn in self.icon_buttons:
            btn.deleteLater()
        self.icon_buttons.clear()

        x, y = 28, 28
        column_width = 110
        row_height = 110
        icon_size = int(self.os.settings.get("icon_size", 72))

        for app_id in self.os.desktop_shortcuts:
            manifest = self.os.registry.get(app_id)
            if not manifest:
                continue

            btn = QPushButton(manifest.name, self.icon_container)
            btn.setObjectName("desktopIcon")
            btn.setToolTip(manifest.description or manifest.name)
            btn.setGeometry(x, y, column_width - 10, row_height - 10)
            btn.setIcon(self._pick_icon(manifest.app_id))
            btn.setIconSize(QSize(icon_size, icon_size))
            btn.clicked.connect(lambda checked=False, launch_id=manifest.app_id: self.os.launch_app(launch_id))
            btn.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            btn.customContextMenuRequested.connect(
                lambda pos, remove_id=manifest.app_id, button=btn: self.show_icon_menu(remove_id, button.mapToGlobal(pos))
            )
            btn.show()
            self.icon_buttons.append(btn)

            y += row_height
            if y + row_height > max(self.height() - 60, 300):
                y = 28
                x += column_width

    def show_icon_menu(self, app_id: str, global_pos) -> None:
        menu = QMenu(self)
        open_action = menu.addAction("Open")
        remove_action = menu.addAction("Remove from Desktop")
        chosen = menu.exec(global_pos)
        if chosen == open_action:
            self.os.launch_app(app_id)
        elif chosen == remove_action:
            if self.os.remove_desktop_shortcut(app_id):
                manifest = self.os.registry.get(app_id)
                if manifest:
                    self.os.notify("Desktop", f"Removed {manifest.name} from desktop")
                self.set_apps_from_shortcuts()

    def _pick_icon(self, app_id: str) -> QIcon:
        style = QApplication.style()
        mapping = {
            "files": QStyle.StandardPixmap.SP_DirHomeIcon,
            "task_manager": QStyle.StandardPixmap.SP_ComputerIcon,
            "desktop_manager": QStyle.StandardPixmap.SP_FileDialogDetailedView,
            "notes": QStyle.StandardPixmap.SP_FileIcon,
            "browser": QStyle.StandardPixmap.SP_BrowserReload,
        }
        return style.standardIcon(mapping.get(app_id, QStyle.StandardPixmap.SP_DesktopIcon))

    def refresh_style(self, settings: dict) -> None:
        desktop_color = settings.get("desktop_color", DEFAULT_SETTINGS["desktop_color"])
        wallpaper_text = settings.get("wallpaper_text", APP_NAME)

        self.wallpaper.setText(
            f"{wallpaper_text}\n\n{settings.get('username', 'User')}"
        )

        self.wallpaper.setStyleSheet(
            f"""
            QLabel#wallpaperLabel {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 {desktop_color},
                    stop:0.55 #111827,
                    stop:1 #1e293b);
                color: rgba(255,255,255,0.16);
                font-size: 36px;
                font-weight: 700;
            }}
            """
        )

        self.icon_container.setStyleSheet(
            """
            QPushButton#desktopIcon {
                background: rgba(255,255,255,0.04);
                color: white;
                border: 1px solid rgba(255,255,255,0.08);
                border-radius: 12px;
                padding: 10px;
                text-align: bottom center;
                font-size: 12px;
            }
            QPushButton#desktopIcon:hover {
                background: rgba(255,255,255,0.10);
                border: 1px solid rgba(255,255,255,0.18);
            }
            QPushButton#desktopIcon:pressed {
                background: rgba(255,255,255,0.16);
            }
            """
        )
        self.set_apps_from_shortcuts()

class DesktopDropArea(QMdiArea):
    def __init__(self, os_context: OSContext) -> None:
        super().__init__()
        self.os = os_context
        self.setAcceptDrops(True)
        self.setViewMode(QMdiArea.ViewMode.SubWindowView)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setBackground(Qt.GlobalColor.transparent)
        self.setStyleSheet("background: transparent;")
        self.viewport().setAutoFillBackground(False)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setViewportMargins(0, 0, 0, 0)

    def dragEnterEvent(self, event) -> None:
        if event.mimeData().hasFormat("application/x-skiesos-app"):
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event) -> None:
        if event.mimeData().hasFormat("application/x-skiesos-app"):
            event.acceptProposedAction()
        else:
            super().dragMoveEvent(event)

    def dropEvent(self, event) -> None:
        mime = event.mimeData()
        if mime.hasFormat("application/x-skiesos-app"):
            app_id = bytes(mime.data("application/x-skiesos-app")).decode("utf-8")
            added = self.os.add_desktop_shortcut(app_id)
            manifest = self.os.registry.get(app_id)

            if added and manifest:
                self.os.notify("Desktop", f"Added {manifest.name} to desktop")
                self.os.main_window.desktop.set_apps_from_shortcuts()
                event.acceptProposedAction()
                return

            if manifest:
                self.os.notify("Desktop", f"{manifest.name} is already on the desktop")
                event.accept()
                return

        super().dropEvent(event)

class FileSystemApp(QWidget):
    def __init__(self, os_context: OSContext) -> None:
        super().__init__()
        self.os = os_context
        self.current_path: Optional[Path] = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        splitter = QSplitter()
        layout.addWidget(splitter)

        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Name", "Type"])
        self.tree.itemClicked.connect(self.on_item_clicked)
        splitter.addWidget(self.tree)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(12, 12, 12, 12)

        self.path_label = QLabel("Select a file or folder")
        self.editor = QTextEdit()
        self.editor.setPlaceholderText("Text file preview / editor")

        self.save_btn = QPushButton("Save file")
        self.save_btn.clicked.connect(self.save_current_file)
        self.save_btn.setEnabled(False)

        self.rename_btn = QPushButton("Rename")
        self.rename_btn.clicked.connect(self.rename_current_item)
        self.rename_btn.setEnabled(False)

        button_row = QHBoxLayout()
        button_row.addWidget(self.save_btn)
        button_row.addWidget(self.rename_btn)

        right_layout.addWidget(self.path_label)
        right_layout.addWidget(self.editor, 1)
        right_layout.addLayout(button_row)

        splitter.addWidget(right)
        splitter.setSizes([280, 520])

        self.populate_tree()

    def populate_tree(self) -> None:
        self.tree.clear()
        root_item = QTreeWidgetItem([self.os.user_fs.name, "Folder"])
        root_item.setData(0, Qt.ItemDataRole.UserRole, str(self.os.user_fs))
        self.tree.addTopLevelItem(root_item)
        self._add_path_children(root_item, self.os.user_fs)
        root_item.setExpanded(True)

    def _add_path_children(self, parent_item: QTreeWidgetItem, path: Path) -> None:
        for child in sorted(path.iterdir(), key=lambda p: (p.is_file(), p.name.lower())):
            item = QTreeWidgetItem([child.name, "File" if child.is_file() else "Folder"])
            item.setData(0, Qt.ItemDataRole.UserRole, str(child))
            parent_item.addChild(item)
            if child.is_dir():
                self._add_path_children(item, child)

    def on_item_clicked(self, item: QTreeWidgetItem, column: int) -> None:
        path = Path(item.data(0, Qt.ItemDataRole.UserRole))
        self.current_path = path
        self.path_label.setText(str(path))
        self.rename_btn.setEnabled(True)

        if path.is_file() and path.suffix.lower() in {".txt", ".md", ".json", ".py"}:
            try:
                self.editor.setPlainText(path.read_text(encoding="utf-8"))
                self.editor.setReadOnly(False)
                self.save_btn.setEnabled(True)
            except Exception as exc:
                self.editor.setPlainText(f"Could not open file:\n{exc}")
                self.editor.setReadOnly(True)
                self.save_btn.setEnabled(False)
        else:
            self.editor.setPlainText("Folder selected." if path.is_dir() else "Binary or unsupported file type.")
            self.editor.setReadOnly(True)
            self.save_btn.setEnabled(False)

    def save_current_file(self) -> None:
        if not self.current_path or not self.current_path.is_file():
            return
        try:
            self.current_path.write_text(self.editor.toPlainText(), encoding="utf-8")
            self.os.notify("Files", f"Saved {self.current_path.name}")
        except Exception as exc:
            QMessageBox.critical(self, "Save failed", str(exc))

    def rename_current_item(self) -> None:
        if not self.current_path:
            return

        old_path = self.current_path
        parent_dir = old_path.parent

        new_name, ok = QInputDialog.getText(
            self,
            "Rename",
            "Enter a new name:",
            text=old_path.name,
        )

        if not ok or not new_name.strip():
            return

        new_name = new_name.strip()
        invalid_chars = '\\/:*?"<>|'
        if any(ch in new_name for ch in invalid_chars):
            QMessageBox.warning(self, "Invalid name", "That name contains invalid characters.")
            return

        new_path = parent_dir / new_name

        if new_path.exists():
            QMessageBox.warning(self, "Already exists", "A file or folder with that name already exists.")
            return

        try:
            old_path.rename(new_path)
            self.current_path = new_path
            self.path_label.setText(str(new_path))
            self.os.notify("Files", f"Renamed to {new_path.name}")
            self.populate_tree()
        except Exception as exc:
            QMessageBox.critical(self, "Rename failed", str(exc))

class WindowTableModel(QAbstractTableModel):
    def __init__(self, os_context: OSContext, main_window: "SkiesOSWindow") -> None:
        super().__init__()
        self.os = os_context
        self.main_window = main_window
        self.headers = ["Window Title", "State", "Size"]

    def rowCount(self, parent=QModelIndex()) -> int:
        return len(self.main_window.mdi.subWindowList())

    def columnCount(self, parent=QModelIndex()) -> int:
        return len(self.headers)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or role != Qt.ItemDataRole.DisplayRole:
            return None
        sub = self.main_window.mdi.subWindowList()[index.row()]
        if index.column() == 0:
            return sub.windowTitle()
        if index.column() == 1:
            return "Active" if self.main_window.mdi.activeSubWindow() == sub else "Open"
        if index.column() == 2:
            return f"{sub.width()} × {sub.height()}"
        return None

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if role != Qt.ItemDataRole.DisplayRole:
            return None
        if orientation == Qt.Orientation.Horizontal:
            return self.headers[section]
        return str(section + 1)

    def refresh(self) -> None:
        self.beginResetModel()
        self.endResetModel()

class TaskManagerApp(QWidget):
    def __init__(self, os_context: OSContext) -> None:
        super().__init__()
        self.os = os_context
        self.main = os_context.main_window

        layout = QVBoxLayout(self)
        header = QLabel("Running apps and windows")
        header.setStyleSheet("font-size: 18px; font-weight: 700;")
        layout.addWidget(header)

        stats_row = QHBoxLayout()
        self.uptime_label = QLabel()
        self.window_count_label = QLabel()
        self.installed_label = QLabel(f"Installed apps: {len(self.os.registry)}")
        stats_row.addWidget(self.uptime_label)
        stats_row.addWidget(self.window_count_label)
        stats_row.addWidget(self.installed_label)
        stats_row.addStretch(1)
        layout.addLayout(stats_row)

        self.table = QTableView()
        self.model = WindowTableModel(self.os, self.main)
        self.table.setModel(self.model)
        self.table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.table, 1)

        actions = QHBoxLayout()
        refresh_btn = QPushButton("Refresh")
        refresh_btn.clicked.connect(self.refresh)
        focus_btn = QPushButton("Focus Selected")
        focus_btn.clicked.connect(self.focus_selected)
        close_btn = QPushButton("Close Selected")
        close_btn.clicked.connect(self.close_selected)
        actions.addWidget(refresh_btn)
        actions.addWidget(focus_btn)
        actions.addWidget(close_btn)
        actions.addStretch(1)
        layout.addLayout(actions)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh)
        self.timer.start(1000)
        self.refresh()

    def refresh(self) -> None:
        uptime_seconds = int(time.time() - self.main.start_time)
        hours, remainder = divmod(uptime_seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        self.uptime_label.setText(f"Uptime: {hours:02d}:{minutes:02d}:{seconds:02d}")
        self.window_count_label.setText(f"Open windows: {len(self.main.mdi.subWindowList())}")
        self.model.refresh()

    def _selected_window(self) -> Optional[QMdiSubWindow]:
        selected = self.table.selectionModel().selectedRows()
        if not selected:
            return None
        row = selected[0].row()
        windows = self.main.mdi.subWindowList()
        if row >= len(windows):
            return None
        return windows[row]

    def focus_selected(self) -> None:
        sub = self._selected_window()
        if sub:
            self.main.mdi.setActiveSubWindow(sub)
            sub.showNormal()
            sub.raise_()

    def close_selected(self) -> None:
        sub = self._selected_window()
        if sub:
            sub.close()
            self.refresh()

class DesktopManagerApp(QWidget):
    def __init__(self, os_context: OSContext) -> None:
        super().__init__()
        self.os = os_context

        layout = QVBoxLayout(self)
        title = QLabel("Desktop Manager")
        title.setStyleSheet("font-size: 18px; font-weight: 700;")
        layout.addWidget(title)

        form_wrap = QWidget()
        form = QFormLayout(form_wrap)

        self.username_input = QLineEdit(self.os.settings.get("username", "Skies"))
        self.wallpaper_input = QLineEdit(self.os.settings.get("wallpaper_text", APP_NAME))
        self.color_input = QLineEdit(self.os.settings.get("desktop_color", DEFAULT_SETTINGS["desktop_color"]))
        self.accent_input = QLineEdit(self.os.settings.get("accent", DEFAULT_SETTINGS["accent"]))
        self.icon_size_input = QLineEdit(str(self.os.settings.get("icon_size", 72)))

        form.addRow("Username", self.username_input)
        form.addRow("Wallpaper text", self.wallpaper_input)
        form.addRow("Desktop color", self.color_input)
        form.addRow("Accent color", self.accent_input)
        form.addRow("Icon size", self.icon_size_input)
        layout.addWidget(form_wrap)

        buttons = QHBoxLayout()
        apply_btn = QPushButton("Apply")
        apply_btn.clicked.connect(self.apply_changes)
        reset_btn = QPushButton("Reset to defaults")
        reset_btn.clicked.connect(self.reset_defaults)
        buttons.addWidget(apply_btn)
        buttons.addWidget(reset_btn)
        buttons.addStretch(1)
        layout.addLayout(buttons)
        layout.addStretch(1)

    def apply_changes(self) -> None:
        try:
            icon_size = max(48, min(128, int(self.icon_size_input.text().strip())))
        except ValueError:
            QMessageBox.warning(self, "Invalid icon size", "Icon size must be a number between 48 and 128.")
            return

        updates = {
            "username": self.username_input.text().strip() or "Skies",
            "wallpaper_text": self.wallpaper_input.text().strip() or APP_NAME,
            "desktop_color": self.color_input.text().strip() or DEFAULT_SETTINGS["desktop_color"],
            "accent": self.accent_input.text().strip() or DEFAULT_SETTINGS["accent"],
            "icon_size": icon_size,
        }
        for key, value in updates.items():
            self.os.update_setting(key, value)

        self.os.main_window.desktop.set_apps_from_shortcuts()
        self.os.main_window.apply_theme()
        self.os.notify("Desktop Manager", "Desktop settings applied")

    def reset_defaults(self) -> None:
        for key, value in DEFAULT_SETTINGS.items():
            self.os.update_setting(key, value)

        self.username_input.setText(DEFAULT_SETTINGS["username"])
        self.wallpaper_input.setText(DEFAULT_SETTINGS["wallpaper_text"])
        self.color_input.setText(DEFAULT_SETTINGS["desktop_color"])
        self.accent_input.setText(DEFAULT_SETTINGS["accent"])
        self.icon_size_input.setText(str(DEFAULT_SETTINGS["icon_size"]))
        self.os.main_window.desktop.set_apps_from_shortcuts()
        self.os.main_window.apply_theme()

class BrowserApp(QWidget):
    def __init__(self, os_context: OSContext) -> None:
        super().__init__()
        self.os = os_context

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        toolbar = QHBoxLayout()

        self.back_btn = QPushButton("←")
        self.forward_btn = QPushButton("→")
        self.reload_btn = QPushButton("⟳")
        self.home_btn = QPushButton("Home")

        self.address_bar = QLineEdit()
        self.address_bar.setPlaceholderText("Enter URL or search term")

        self.go_btn = QPushButton("Go")

        toolbar.addWidget(self.back_btn)
        toolbar.addWidget(self.forward_btn)
        toolbar.addWidget(self.reload_btn)
        toolbar.addWidget(self.home_btn)
        toolbar.addWidget(self.address_bar, 1)
        toolbar.addWidget(self.go_btn)

        layout.addLayout(toolbar)

        self.status_label = QLabel("Ready")
        layout.addWidget(self.status_label)

        self.browser = QWebEngineView()
        layout.addWidget(self.browser, 1)

        self.back_btn.clicked.connect(self.browser.back)
        self.forward_btn.clicked.connect(self.browser.forward)
        self.reload_btn.clicked.connect(self.browser.reload)
        self.home_btn.clicked.connect(self.go_home)
        self.go_btn.clicked.connect(self.navigate)
        self.address_bar.returnPressed.connect(self.navigate)

        self.browser.urlChanged.connect(self.on_url_changed)
        self.browser.loadProgress.connect(self.on_load_progress)
        self.browser.loadFinished.connect(self.on_load_finished)

        self.go_home()

    def normalize_input(self, text: str) -> str:
        text = text.strip()
        if not text:
            return "https://www.google.com"

        if "://" in text:
            return text

        if "." in text and " " not in text:
            return f"https://{text}"

        query = text.replace(" ", "+")
        return f"https://www.google.com/search?q={query}"

    def navigate(self) -> None:
        target = self.normalize_input(self.address_bar.text())
        self.browser.load(QUrl(target))

    def go_home(self) -> None:
        self.browser.load(QUrl("https://www.google.com"))

    def on_url_changed(self, url: QUrl) -> None:
        self.address_bar.setText(url.toString())

    def on_load_progress(self, progress: int) -> None:
        self.status_label.setText(f"Loading... {progress}%")

    def on_load_finished(self, ok: bool) -> None:
        self.status_label.setText("Done" if ok else "Failed to load page")

class NotesApp(QWidget):
    def __init__(self, os_context: OSContext) -> None:
        super().__init__()
        self.os = os_context
        self.current_file = self.os.user_fs / "Documents" / "quick_note.txt"

        layout = QVBoxLayout(self)
        self.title_label = QLabel(f"Editing: {self.current_file.name}")
        self.editor = QTextEdit()
        if self.current_file.exists():
            self.editor.setPlainText(self.current_file.read_text(encoding="utf-8"))

        buttons = QHBoxLayout()
        save_btn = QPushButton("Save")
        save_btn.clicked.connect(self.save)
        save_as_btn = QPushButton("Save As")
        save_as_btn.clicked.connect(self.save_as)
        buttons.addWidget(save_btn)
        buttons.addWidget(save_as_btn)
        buttons.addStretch(1)

        layout.addWidget(self.title_label)
        layout.addWidget(self.editor, 1)
        layout.addLayout(buttons)

    def save(self) -> None:
        self.current_file.parent.mkdir(parents=True, exist_ok=True)
        self.current_file.write_text(self.editor.toPlainText(), encoding="utf-8")
        self.os.notify("Notes", f"Saved {self.current_file.name}")

    def save_as(self) -> None:
        documents_dir = self.os.user_fs / "Documents"
        documents_dir.mkdir(parents=True, exist_ok=True)

        file_name, ok = QInputDialog.getText(
            self,
            "Save As",
            "Enter a file name:",
            text=self.current_file.name if self.current_file else "new_note.txt",
        )

        if not ok or not file_name.strip():
            return

        file_name = file_name.strip()

        if "." not in file_name:
            file_name += ".txt"

        safe_name = "".join(c for c in file_name if c not in r'\\/:*?"<>|').strip()
        if not safe_name:
            QMessageBox.warning(self, "Invalid file name", "Please enter a valid file name.")
            return

        target_path = documents_dir / safe_name

        try:
            target_path.write_text(self.editor.toPlainText(), encoding="utf-8")
            self.current_file = target_path
            self.title_label.setText(f"Editing: {self.current_file.name}")
            self.os.notify("Notes", f"Saved {self.current_file.name}")
        except Exception as exc:
            QMessageBox.critical(self, "Save failed", str(exc))

class StartMenu(QDialog):
    def __init__(self, os_context: OSContext, parent: QWidget = None) -> None:
        super().__init__(parent)
        self.os = os_context
        self.setWindowFlags(Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint)
        self.setFixedSize(320, 420)

        layout = QVBoxLayout(self)
        header = QLabel(
            f"{APP_NAME}\nWelcome back, {self.os.settings.get('username', 'Skies')}"
        )
        header.setObjectName("startHeader")
        layout.addWidget(header)

        self.list_widget = AppListWidget()
        self.list_widget.setDragEnabled(True)
        self.list_widget.setSelectionMode(QListWidget.SelectionMode.SingleSelection)
        self.list_widget.setDefaultDropAction(Qt.DropAction.CopyAction)

        for app in self.os.registry.values():
            item = QListWidgetItem(app.name)
            item.setData(Qt.ItemDataRole.UserRole, app.app_id)
            item.setToolTip("Double-click to open, or drag to the desktop")
            self.list_widget.addItem(item)

        self.list_widget.itemDoubleClicked.connect(self.launch_selected)
        layout.addWidget(self.list_widget, 1)

        help_label = QLabel("Tip: drag an app from this menu onto the desktop to create a shortcut.")
        help_label.setWordWrap(True)
        layout.addWidget(help_label)

        open_btn = QPushButton("Open")
        open_btn.clicked.connect(self.launch_selected)
        layout.addWidget(open_btn)

    def launch_selected(self, item=None) -> None:
        current = item or self.list_widget.currentItem()
        if not current:
            return
        self.os.launch_app(current.data(Qt.ItemDataRole.UserRole))
        self.close()

class SkiesOSWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.start_time = time.time()
        self.settings_store = SettingsStore()
        self.os = OSContext(self, self.settings_store)
        self.start_menu: Optional[StartMenu] = None

        self.setWindowTitle(f"{APP_NAME} {APP_VERSION}")
        self.resize(1440, 900)
        self.setMinimumSize(1100, 720)

        self.desktop = DesktopWidget(self.os)
        self.mdi = DesktopDropArea(self.os)

        central = QWidget()
        central_layout = QVBoxLayout(central)
        central_layout.setContentsMargins(0, 0, 0, 0)
        central_layout.setSpacing(0)

        self.workspace = QFrame()
        self.workspace.setObjectName("workspace")
        ws_layout = QVBoxLayout(self.workspace)
        ws_layout.setContentsMargins(0, 0, 0, 0)
        ws_layout.addWidget(self.desktop)
        ws_layout.addWidget(self.mdi)

        self.desktop.lower()
        self.mdi.raise_()
        central_layout.addWidget(self.workspace, 1)

        self.taskbar = self._build_taskbar()
        central_layout.addWidget(self.taskbar)
        self.setCentralWidget(central)

        self.setStatusBar(QStatusBar())
        self._register_preinstalled_apps()
        self.desktop.set_apps_from_shortcuts()
        self._wire_signals()
        self.apply_theme()
        self._build_menu_bar()
        
        self.os.register_app(AppManifest(
            app_id="browser",
            name="HawkEye",
            category="Internet",
            description="Browse the web inside SkiesOS.",
            launcher=lambda os_ctx: os_ctx.open_internal_window("HawkEye", BrowserApp(os_ctx), "browser", 1100, 700),
        ))

    def _wire_signals(self) -> None:
        self.os.settings_changed.connect(lambda _: self.apply_theme())
        self.os.window_opened.connect(lambda _: self.refresh_taskbar_windows())
        self.os.window_closed.connect(lambda _: self.refresh_taskbar_windows())
        self.mdi.subWindowActivated.connect(lambda _: self.refresh_taskbar_windows())

    def _build_menu_bar(self) -> None:
        menu = self.menuBar()

        system_menu = menu.addMenu("System")
        about_action = QAction("About", self)
        about_action.triggered.connect(self.show_about)
        system_menu.addAction(about_action)

        apps_menu = menu.addMenu("Apps")
        for manifest in self.os.registry.values():
            action = QAction(manifest.name, self)
            action.triggered.connect(lambda checked=False, app_id=manifest.app_id: self.os.launch_app(app_id))
            apps_menu.addAction(action)

    def _build_taskbar(self) -> QWidget:
        bar = QFrame()
        bar.setObjectName("taskbar")
        bar.setFixedHeight(54)

        layout = QHBoxLayout(bar)
        layout.setContentsMargins(10, 6, 10, 6)
        layout.setSpacing(8)

        self.start_button = QPushButton("Start")
        self.start_button.setObjectName("startButton")
        self.start_button.clicked.connect(self.toggle_start_menu)
        layout.addWidget(self.start_button)

        self.window_strip = QHBoxLayout()
        self.window_strip.setSpacing(6)
        layout.addLayout(self.window_strip, 1)

        self.clock_label = QLabel()
        self.clock_label.setObjectName("clockLabel")
        layout.addWidget(self.clock_label)

        timer = QTimer(self)
        timer.timeout.connect(self.update_clock)
        timer.start(1000)
        self.update_clock()
        return bar

    def update_clock(self) -> None:
        self.clock_label.setText(time.strftime("%I:%M:%S %p"))

    def toggle_start_menu(self) -> None:
        if self.start_menu and self.start_menu.isVisible():
            self.start_menu.close()
            return

        self.start_menu = StartMenu(self.os, self)
        geo = self.geometry()
        pos_x = geo.x() + 14
        pos_y = geo.y() + geo.height() - self.taskbar.height() - self.start_menu.height() - 18
        self.start_menu.move(pos_x, pos_y)
        self.start_menu.show()
        self.start_menu.raise_()

    def refresh_taskbar_windows(self) -> None:
        while self.window_strip.count():
            item = self.window_strip.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

        for sub in self.mdi.subWindowList():
            btn = QPushButton(sub.windowTitle())
            btn.setObjectName("taskbarWindowButton")
            btn.setCheckable(True)
            btn.setChecked(sub == self.mdi.activeSubWindow())
            btn.clicked.connect(lambda checked=False, window=sub: self.focus_window(window))
            self.window_strip.addWidget(btn)

        self.window_strip.addStretch(1)

    def focus_window(self, sub: QMdiSubWindow) -> None:
        self.mdi.setActiveSubWindow(sub)
        sub.showNormal()
        sub.raise_()
        self.refresh_taskbar_windows()

    def _register_preinstalled_apps(self) -> None:
        self.os.register_app(AppManifest(
            app_id="files",
            name="File System",
            category="System",
            description="Browse the internal SkiesOS file system.",
            launcher=lambda os_ctx: os_ctx.open_internal_window("File System", FileSystemApp(os_ctx), "files", 950, 580),
        ))
        self.os.register_app(AppManifest(
            app_id="task_manager",
            name="Task Manager",
            category="System",
            description="See running windows and basic OS stats.",
            launcher=lambda os_ctx: os_ctx.open_internal_window("Task Manager", TaskManagerApp(os_ctx), "task_manager", 760, 460),
        ))
        self.os.register_app(AppManifest(
            app_id="desktop_manager",
            name="Desktop Manager",
            category="System",
            description="Change wallpaper text, colors, and icon size.",
            launcher=lambda os_ctx: os_ctx.open_internal_window("Desktop Manager", DesktopManagerApp(os_ctx), "desktop_manager", 620, 420),
        ))
        self.os.register_app(AppManifest(
            app_id="notes",
            name="Notes",
            category="Utilities",
            description="Simple preinstalled note editor.",
            launcher=lambda os_ctx: os_ctx.open_internal_window("Notes", NotesApp(os_ctx), "notes", 760, 520),
        ))

    def show_about(self) -> None:
        QMessageBox.information(
            self,
            "About SkiesOS",
            f"{APP_NAME} {APP_VERSION}\n\n"
            "A self-contained desktop-style OS shell built with PySide6.\n"
            "Preinstalled apps include File System, Task Manager, Desktop Manager, and Notes.\n\n"
            f"User data folder: {USER_FS_DIR}"
        )

    def apply_theme(self) -> None:
        settings = self.os.settings
        accent = settings.get("accent", DEFAULT_SETTINGS["accent"])

        self.setStyleSheet(
            f"""
            QMainWindow, QWidget#workspace {{
                background: #0b1220;
                color: #e5e7eb;
            }}
            QFrame#taskbar {{
                background: rgba(17, 24, 39, 0.96);
                border-top: 1px solid rgba(255, 255, 255, 0.08);
            }}
            QPushButton {{
                background: #1f2937;
                color: #f9fafb;
                border: 1px solid rgba(255,255,255,0.08);
                border-radius: 10px;
                padding: 8px 12px;
            }}
            QPushButton:hover {{
                background: #2b3647;
            }}
            QPushButton#startButton {{
                background: {accent};
                font-weight: 700;
                min-width: 86px;
            }}
            QPushButton#taskbarWindowButton:checked {{
                background: {accent};
            }}
            QLabel#clockLabel {{
                color: white;
                font-size: 13px;
                padding: 0 8px;
            }}
            QDialog {{
                background: #111827;
                color: white;
                border: 1px solid rgba(255,255,255,0.08);
                border-radius: 14px;
            }}
            QLabel#startHeader {{
                background: {accent};
                color: white;
                border-radius: 10px;
                padding: 16px;
                font-size: 18px;
                font-weight: 700;
            }}
            QTextEdit, QLineEdit, QTreeWidget, QListWidget, QTableView {{
                background: #0f172a;
                color: #e5e7eb;
                border: 1px solid rgba(255,255,255,0.08);
                border-radius: 10px;
                padding: 6px;
            }}
            QHeaderView::section {{
                background: #1e293b;
                color: white;
                padding: 8px;
                border: none;
            }}
            QMdiSubWindow {{
                background: #111827;
                border: 1px solid rgba(255,255,255,0.12);
            }}
            """
        )
        self.desktop.refresh_style(settings)
        self.refresh_taskbar_windows()

def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(APP_VERSION)
    app.setStyle("Fusion")

    window = SkiesOSWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()