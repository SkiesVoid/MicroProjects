import sys
import requests
import datetime
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QVBoxLayout, QPushButton, QLineEdit, QWidget,
    QHBoxLayout, QTabWidget, QMenu, QSizePolicy, QComboBox, QDialog, QLabel,
    QFileDialog, QListWidget, QListWidgetItem, QDockWidget, QGroupBox, QInputDialog, QMessageBox
)
from PyQt6.QtPrintSupport import QPrintDialog
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWebEngineCore import QWebEngineProfile
from PyQt6.QtCore import QUrl, Qt, QTimer
from PyQt6.QtGui import QIcon, QPixmap, QPainter


class DownloadProgressIndicator(QWidget):
    """A small circular progress indicator that fills with blue as progress increases."""
    def __init__(self, parent=None, size=32):
        super().__init__(parent)
        self.progress = 0.0  # Range: 0.0 to 1.0
        self.setFixedSize(size, size)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool)

    def setProgress(self, progress):
        self.progress = progress
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = self.rect().adjusted(2, 2, -2, -2)
        painter.setPen(Qt.GlobalColor.white)
        painter.setBrush(Qt.GlobalColor.white)
        painter.drawEllipse(rect)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(Qt.GlobalColor.blue)
        angle = int(360 * self.progress)
        spanAngle = int(angle * 16)
        painter.drawPie(rect, 90 * 16, -spanAngle)


class FavoritePopup(QDialog):
    """Popup for naming a favorite."""
    def __init__(self, parent, default_name, url):
        super().__init__(parent)
        self.setWindowTitle("Add to Favorites")
        self.setGeometry(1000, 600, 300, 150)
        self.url = url
        layout = QVBoxLayout()
        self.label = QLabel("Enter a name for this favorite:")
        self.name_input = QLineEdit()
        self.name_input.setText(default_name)
        self.favorite_button = QPushButton("Favorite")
        self.favorite_button.clicked.connect(self.accept)
        layout.addWidget(self.label)
        layout.addWidget(self.name_input)
        layout.addWidget(self.favorite_button)
        self.setLayout(layout)

    def get_favorite_name(self):
        return self.name_input.text().strip()


class WebBrowser(QMainWindow):
    def __init__(self):
        super().__init__()
        "Browser Window Title"
        self.setWindowTitle("Void Browser")
        self.setGeometry(100, 100, 1200, 800)

        # Data storage
        self.favorites = {}
        self.history = []           # List of tuples: (title, URL)
        self.downloads = []         # Finished download entries
        self.passwords = []         # Placeholder for stored passwords
        self.account = None         # Account info as (username, master_password)

        # Main tab widget
        self.tabs = QTabWidget()
        self.tabs.setTabsClosable(True)
        self.tabs.tabCloseRequested.connect(self.close_tab)
        self.tabs.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tabs.customContextMenuRequested.connect(self.show_tab_menu)
        self.add_tab(QUrl("https://www.google.com"))

        # Navigation buttons
        new_tab_button = QPushButton("+")
        new_tab_button.clicked.connect(lambda: self.add_tab(QUrl("https://www.google.com")))

        self.back_button = QPushButton("<")
        self.back_button.clicked.connect(lambda: self.current_browser().back())

        self.forward_button = QPushButton(">")
        self.forward_button.clicked.connect(lambda: self.current_browser().forward())

        self.reload_button = QPushButton("↺")
        self.reload_button.clicked.connect(lambda: self.current_browser().reload())

        self.home_button = QPushButton("🏠")
        self.home_button.clicked.connect(lambda: self.current_browser().setUrl(QUrl("https://www.google.com")))

        self.favorite_button = QPushButton("⭐")
        self.favorite_button.clicked.connect(self.open_favorite_popup)

        self.settings_button = QPushButton("⚙️")
        self.settings_button.clicked.connect(self.toggle_settings_sidebar)

        self.favorites_dropdown = QComboBox()
        self.favorites_dropdown.addItem("Favorites ▼")
        self.favorites_dropdown.currentIndexChanged.connect(self.load_favorite)
        self.favorites_dropdown.setMaximumWidth(200)

        # Resize buttons
        for button in [new_tab_button, self.back_button, self.forward_button,
                       self.reload_button, self.home_button, self.favorite_button, self.settings_button]:
            button.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
            button.setMaximumWidth(40)

        self.url_bar = QLineEdit()
        self.url_bar.setPlaceholderText("Enter URL or search terms and press Enter")
        self.url_bar.returnPressed.connect(self.load_url)

        nav_layout = QHBoxLayout()
        nav_layout.addWidget(new_tab_button)
        nav_layout.addWidget(self.back_button)
        nav_layout.addWidget(self.forward_button)
        nav_layout.addWidget(self.reload_button)
        nav_layout.addWidget(self.home_button)
        nav_layout.addWidget(self.url_bar, 1)
        nav_layout.addWidget(self.favorite_button)
        nav_layout.addWidget(self.settings_button)
        nav_layout.addWidget(self.favorites_dropdown)

        layout = QVBoxLayout()
        layout.addLayout(nav_layout)
        layout.addWidget(self.tabs)

        container = QWidget()
        container.setLayout(layout)
        self.setCentralWidget(container)

        # Settings sidebar (dock widget)
        self.settings_dock = QDockWidget("Settings", self)
        self.settings_dock.setAllowedAreas(Qt.DockWidgetArea.RightDockWidgetArea)
        self.settings_widget = QWidget()
        self.settings_layout = QVBoxLayout()

        # --- Account Section ---
        account_group = QGroupBox("Account")
        account_layout = QVBoxLayout()  # Vertical layout for multiple buttons
        self.login_button = QPushButton("Login")
        self.login_button.clicked.connect(self.login_account)
        self.account_button = QPushButton("Register Account")
        self.account_button.clicked.connect(self.register_account)
        account_layout.addWidget(self.login_button)
        account_layout.addWidget(self.account_button)
        account_group.setLayout(account_layout)
        self.settings_layout.addWidget(account_group)

        # --- History Section ---
        history_group = QGroupBox("History")
        history_layout = QVBoxLayout()
        self.history_list_widget = QListWidget()
        self.history_list_widget.itemClicked.connect(self.load_history_item)
        history_layout.addWidget(self.history_list_widget)
        history_group.setLayout(history_layout)
        self.settings_layout.addWidget(history_group)

        # --- Zoom Controls ---
        zoom_group = QGroupBox("Zoom")
        zoom_layout = QHBoxLayout()
        self.zoom_out_btn = QPushButton("-")
        self.zoom_label = QLabel("100%")
        self.zoom_in_btn = QPushButton("+")
        zoom_layout.addWidget(self.zoom_out_btn)
        zoom_layout.addWidget(self.zoom_label)
        zoom_layout.addWidget(self.zoom_in_btn)
        zoom_group.setLayout(zoom_layout)
        self.zoom_out_btn.clicked.connect(self.zoom_out)
        self.zoom_in_btn.clicked.connect(self.zoom_in)
        self.settings_layout.addWidget(zoom_group)

        # --- Print Button ---
        self.print_btn = QPushButton("Print")
        self.print_btn.clicked.connect(self.print_page)
        self.settings_layout.addWidget(self.print_btn)

        # --- Downloads List ---
        downloads_group = QGroupBox("Downloads")
        downloads_layout = QVBoxLayout()
        self.downloads_list_widget = QListWidget()
        downloads_layout.addWidget(self.downloads_list_widget)
        downloads_group.setLayout(downloads_layout)
        self.settings_layout.addWidget(downloads_group)

        # --- Passwords Section ---
        passwords_group = QGroupBox("Passwords")
        passwords_layout = QVBoxLayout()
        self.passwords_btn = QPushButton("Show Passwords")
        self.passwords_btn.clicked.connect(self.show_passwords)
        passwords_layout.addWidget(self.passwords_btn)
        passwords_group.setLayout(passwords_layout)
        self.settings_layout.addWidget(passwords_group)

        self.settings_widget.setLayout(self.settings_layout)
        self.settings_dock.setWidget(self.settings_widget)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.settings_dock)
        self.settings_dock.hide()

        # Connect download handler
        profile = QWebEngineProfile.defaultProfile()
        profile.downloadRequested.connect(self.handle_download)

    def add_tab(self, url):
        browser = QWebEngineView()
        browser.setUrl(url)
        index = self.tabs.addTab(browser, "Loading...")
        self.tabs.setCurrentIndex(index)
        browser.loadFinished.connect(lambda: self.update_tab(index, browser))
        browser.urlChanged.connect(self.update_url_bar)

    def close_tab(self, index):
        if self.tabs.count() > 1:
            self.tabs.removeTab(index)

    def current_browser(self):
        return self.tabs.currentWidget()

    def load_url(self):
        query = self.url_bar.text().strip()
        if not query:
            return
        if query.startswith(("http://", "https://")):
            url = query
        elif " " in query or "." not in query:
            url = "https://www.google.com/search?q=" + query.replace(" ", "+")
        else:
            url = "https://" + query
        self.current_browser().setUrl(QUrl(url))

    def update_tab(self, index, browser):
        title = browser.page().title()
        if not title:
            title = QUrl(browser.url()).host()
        self.tabs.setTabText(index, title)
        url = browser.url().toString()
        favicon_url = self.get_favicon_url(url)
        if favicon_url:
            icon = self.fetch_favicon(favicon_url)
            if icon:
                self.tabs.setTabIcon(index, icon)
        # Add history entry if not duplicate
        if not self.history or self.history[-1][1] != url:
            self.history.append((title, url))
            self.update_history_list()

    def update_url_bar(self, url):
        text = url.toString()
        self.url_bar.setText(text)
        self.update_favorite_button(text)

    def open_favorite_popup(self):
        url = self.url_bar.text()
        default_name = self.tabs.tabText(self.tabs.currentIndex())
        popup = FavoritePopup(self, default_name, url)
        if popup.exec():
            favorite_name = popup.get_favorite_name()
            self.add_favorite(favorite_name, url)

    def add_favorite(self, name, url):
        favicon_url = self.get_favicon_url(url)
        icon = self.fetch_favicon(favicon_url) if favicon_url else None
        self.favorites[name] = (url, icon)
        self.favorite_button.setText("★")
        self.update_favorites_dropdown()

    def update_favorite_button(self, url):
        if url in [data[0] for data in self.favorites.values()]:
            self.favorite_button.setText("★")
        else:
            self.favorite_button.setText("⭐")

    def update_favorites_dropdown(self):
        self.favorites_dropdown.blockSignals(True)
        self.favorites_dropdown.clear()
        self.favorites_dropdown.addItem("Favorites ▼")
        for name, (url, icon) in sorted(self.favorites.items()):
            if icon:
                self.favorites_dropdown.addItem(icon, name)
            else:
                self.favorites_dropdown.addItem(name)
        self.favorites_dropdown.setCurrentIndex(0)
        self.favorites_dropdown.blockSignals(False)

    def load_favorite(self, index):
        if index == 0:
            return
        name = self.favorites_dropdown.currentText()
        url, _ = self.favorites[name]
        self.current_browser().setUrl(QUrl(url))
        self.favorites_dropdown.setCurrentIndex(0)

    def update_history_list(self):
        self.history_list_widget.clear()
        for title, url in self.history:
            item = QListWidgetItem(title)
            item.setData(Qt.ItemDataRole.UserRole, url)
            self.history_list_widget.addItem(item)

    def load_history_item(self, item):
        url = item.data(Qt.ItemDataRole.UserRole)
        self.add_tab(QUrl(url))

    def get_favicon_url(self, website_url):
        try:
            domain = QUrl(website_url).host()
            return f"https://{domain}/favicon.ico" if domain else None
        except Exception:
            return None

    def fetch_favicon(self, url):
        try:
            response = requests.get(url, stream=True, timeout=3)
            if response.status_code == 200:
                pixmap = QPixmap()
                pixmap.loadFromData(response.content)
                return QIcon(pixmap)
        except Exception:
            return None
        return None

    def show_tab_menu(self, position):
        menu = QMenu()
        close_action = menu.addAction("Close Tab")
        duplicate_action = menu.addAction("Duplicate Tab")
        action = menu.exec(self.tabs.mapToGlobal(position))
        index = self.tabs.currentIndex()
        if action == close_action:
            self.close_tab(index)
        elif action == duplicate_action:
            current_url = self.current_browser().url()
            self.add_tab(current_url)

    def poll_download_progress(self, download_item, indicator, timer):
        try:
            received = download_item.receivedBytes()
            total = download_item.totalBytes()
        except Exception:
            timer.stop()
            indicator.hide()
            return
        if total > 0:
            progress = received / total
            indicator.setProgress(progress)
            if received >= total:
                timer.stop()
                indicator.hide()

    def handle_download(self, download_item):
        save_path, _ = QFileDialog.getSaveFileName(self, "Save File", download_item.downloadFileName())
        if save_path:
            download_item.setDownloadFileName(save_path)
            download_item.accept()
            progress_indicator = DownloadProgressIndicator(self)
            progress_indicator.move(self.width() - progress_indicator.width() - 10,
                                    self.height() - progress_indicator.height() - 10)
            progress_indicator.show()
            timer = QTimer(self)
            timer.setInterval(100)
            timer.timeout.connect(lambda: self.poll_download_progress(download_item, progress_indicator, timer))
            timer.start()
            download_item.isFinished.connect(lambda: self.download_finished(download_item))

    def download_finished(self, download_item):
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        entry = f"{download_item.downloadFileName()} - {timestamp}"
        self.downloads.append(entry)
        self.update_downloads_list()

    def update_downloads_list(self):
        if self.downloads_list_widget:
            self.downloads_list_widget.clear()
            for entry in sorted(self.downloads, reverse=True):
                self.downloads_list_widget.addItem(entry)

    # --- Settings Sidebar Methods ---

    def zoom_in(self):
        current_zoom = self.current_browser().zoomFactor()
        new_zoom = min(current_zoom + 0.1, 3.0)
        self.current_browser().setZoomFactor(new_zoom)
        self.zoom_label.setText(f"{int(new_zoom * 100)}%")

    def zoom_out(self):
        current_zoom = self.current_browser().zoomFactor()
        new_zoom = max(current_zoom - 0.1, 0.25)
        self.current_browser().setZoomFactor(new_zoom)
        self.zoom_label.setText(f"{int(new_zoom * 100)}%")

    def print_page(self):
        page = self.current_browser().page()
        printer_dialog = QPrintDialog()
        if printer_dialog.exec() == QDialog.DialogCode.Accepted:
            page.print(printer_dialog.printer(), lambda success: print("Printed successfully" if success else "Print failed"))

    def show_passwords(self):
        if self.account is None:
            QMessageBox.warning(self, "Error", "No account registered. Please register an account first.")
            return
        master, ok = QInputDialog.getText(self, "Master Password", "Enter master password:", QLineEdit.EchoMode.Password)
        if ok:
            if master == self.account[1]:
                if self.passwords:
                    msg = "\n".join([f"{site}: {user} / {pwd}" for (site, user, pwd) in self.passwords])
                else:
                    msg = "No passwords stored."
                QMessageBox.information(self, "Stored Passwords", msg)
            else:
                QMessageBox.warning(self, "Error", "Incorrect master password.")

    def toggle_settings_sidebar(self):
        if self.settings_dock.isVisible():
            self.settings_dock.hide()
        else:
            self.settings_dock.show()

    def register_account(self):
        if self.account is not None:
            reply = QMessageBox.question(self, "Update Account", "An account is already registered. Do you want to update it?",
                                         QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            if reply != QMessageBox.StandardButton.Yes:
                return
        username, ok = QInputDialog.getText(self, "Register Account", "Enter username:")
        if not ok or not username:
            return
        password, ok = QInputDialog.getText(self, "Register Account", "Enter master password:", QLineEdit.EchoMode.Password)
        if not ok or not password:
            return
        self.account = (username, password)
        self.account_button.setText(f"Account: {username}")

    def login_account(self):
        if self.account is None:
            QMessageBox.warning(self, "Login Error", "No account registered. Please register an account first.")
            return
        username, ok = QInputDialog.getText(self, "Login", "Enter username:")
        if not ok or not username:
            return
        password, ok = QInputDialog.getText(self, "Login", "Enter master password:", QLineEdit.EchoMode.Password)
        if not ok or not password:
            return
        if username == self.account[0] and password == self.account[1]:
            QMessageBox.information(self, "Login", "Login successful.")
        else:
            QMessageBox.warning(self, "Login", "Incorrect credentials.")


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = WebBrowser()
    window.show()
    sys.exit(app.exec())
