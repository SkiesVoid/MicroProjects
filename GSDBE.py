import sys
import os
import sqlite3
import time

from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QComboBox, QTreeWidget, QTreeWidgetItem, QGroupBox, QFileDialog, QMessageBox,
    QAbstractItemView, QMenu, QSizePolicy, QMainWindow, QTabWidget, QInputDialog
)
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QClipboard, QAction, QCursor

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

SCOPES = ['https://www.googleapis.com/auth/spreadsheets']
REFRESH_INTERVAL = 1000  # milliseconds

def col_num_to_letter(n):
    result = ''
    while n:
        n, rem = divmod(n - 1, 26)
        result = chr(65 + rem) + result
    return result

class SheetTabWidget(QWidget):
    def __init__(self, spreadsheet_id, credentials_path, parent=None):
        super().__init__(parent)
        self.spreadsheet_id = spreadsheet_id
        self.credentials_path = credentials_path
        self.setWindowTitle("GSDBE A.0.2.0")
        self.setMinimumSize(1440, 720)

        main_layout = QHBoxLayout(self)
        self.control_panel = QVBoxLayout()
        main_layout.addLayout(self.control_panel, 1)
        
        self.clipboard = QApplication.clipboard()
        self.last_selected_col = None
        self.last_selected_row = None

        self.build_update_section()
        self.build_row_operations()
        self.build_column_operations()
        self.build_cell_operations()
        self.build_export_button()

        # Display panel
        self.sheet_data_group = QGroupBox("Sheet Data")
        self.sheet_data_layout = QVBoxLayout()

        # Create tree widget before using it
        self.sheet_tree = QTreeWidget()
        self.sheet_tree.setUniformRowHeights(True)
        self.sheet_tree.setAlternatingRowColors(True)
        self.sheet_tree.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.sheet_tree.setSelectionBehavior(QTreeWidget.SelectItems)
        self.sheet_tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.sheet_tree.customContextMenuRequested.connect(self.open_context_menu)
        self.sheet_tree.itemClicked.connect(self.handle_item_click)

        # Add to layout once it's fully created
        self.sheet_data_layout.addWidget(self.sheet_tree)
        self.sheet_data_group.setLayout(self.sheet_data_layout)

        # Add to main window layout
        main_layout.addWidget(self.sheet_data_group, 3)


        # Spreadsheet config
        self.service = self.get_service()

        self.last_data = []
        self.refresh_sheet_display()

        # Timer-based auto-refresh
        self.timer = QTimer()
        self.sheet_tree.setAlternatingRowColors(True)
        self.apply_modern_style()
        self.timer.timeout.connect(self.auto_refresh_loop)
        self.timer.start(REFRESH_INTERVAL)

    def build_update_section(self):
        group = QGroupBox("Update Cell")
        layout = QVBoxLayout()

        self.entry = QLineEdit()
        self.column_combo = QComboBox()
        self.column_combo.addItems([col_num_to_letter(i) for i in range(1, 27)])
        self.row_combo = QComboBox()
        self.row_combo.addItems([str(i) for i in range(1, 101)])

        layout.addWidget(QLabel("Enter new cell value:"))
        layout.addWidget(self.entry)
        layout.addWidget(QLabel("Select column:"))
        layout.addWidget(self.column_combo)
        layout.addWidget(QLabel("Select row:"))
        layout.addWidget(self.row_combo)

        update_btn = QPushButton("Update Cell")
        update_btn.clicked.connect(self.update_sheet)
        layout.addWidget(update_btn)

        group.setLayout(layout)
        self.control_panel.addWidget(group)

    def build_row_operations(self):
        group = QGroupBox("Row Operations")
        layout = QVBoxLayout()

        self.row_delete_combo = QComboBox()
        self.row_delete_combo.addItems([str(i) for i in range(1, 101)])

        layout.addWidget(QLabel("Select row:"))
        layout.addWidget(self.row_delete_combo)

        clear_btn = QPushButton("Clear Row")
        clear_btn.clicked.connect(self.clear_row)
        layout.addWidget(clear_btn)

        delete_btn = QPushButton("Delete Row")
        delete_btn.clicked.connect(self.delete_row)
        layout.addWidget(delete_btn)

        add_btn = QPushButton("Add Row")
        add_btn.clicked.connect(self.add_row)
        layout.addWidget(add_btn)

        group.setLayout(layout)
        self.control_panel.addWidget(group)

    def build_column_operations(self):
        group = QGroupBox("Column Operations")
        layout = QVBoxLayout()

        self.column_delete_combo = QComboBox()
        self.column_delete_combo.addItems([col_num_to_letter(i) for i in range(1, 27)])

        layout.addWidget(QLabel("Select column:"))
        layout.addWidget(self.column_delete_combo)

        clear_btn = QPushButton("Clear Column")
        clear_btn.clicked.connect(self.clear_column)
        layout.addWidget(clear_btn)

        delete_btn = QPushButton("Delete Column")
        delete_btn.clicked.connect(self.delete_column)
        layout.addWidget(delete_btn)

        add_btn = QPushButton("Add Column")
        add_btn.clicked.connect(self.add_column)
        layout.addWidget(add_btn)

        group.setLayout(layout)
        self.control_panel.addWidget(group)

    def build_cell_operations(self):
        group = QGroupBox("Individual Cell Operations")
        layout = QVBoxLayout()

        self.cell_op_col_combo = QComboBox()
        self.cell_op_col_combo.addItems([col_num_to_letter(i) for i in range(1, 27)])
        self.cell_op_row_combo = QComboBox()
        self.cell_op_row_combo.addItems([str(i) for i in range(1, 101)])

        layout.addWidget(QLabel("Select column:"))
        layout.addWidget(self.cell_op_col_combo)
        layout.addWidget(QLabel("Select row:"))
        layout.addWidget(self.cell_op_row_combo)

        clear_btn = QPushButton("Clear Cell")
        clear_btn.clicked.connect(self.clear_cell)
        layout.addWidget(clear_btn)

        delete_btn = QPushButton("Delete Cell")
        delete_btn.clicked.connect(self.delete_cell)
        layout.addWidget(delete_btn)

        group.setLayout(layout)
        self.control_panel.addWidget(group)

    def build_export_button(self):
        export_btn = QPushButton("Export to SQLite")
        export_btn.clicked.connect(self.export_to_sqlite)
        self.control_panel.addWidget(export_btn)
        
    def open_context_menu(self, pos):
        item = self.sheet_tree.itemAt(pos)
        if not item:
            return

        menu = QMenu(self)

        copy_cell_action = QAction("Copy Cell", self)
        copy_row_action = QAction("Copy Row", self)
        copy_col_action = QAction("Copy Column", self)
        paste_cell_action = QAction("Paste into Cell", self)

        copy_cell_action.triggered.connect(self.copy_cell)
        copy_row_action.triggered.connect(self.copy_row)
        copy_col_action.triggered.connect(self.copy_column)
        paste_cell_action.triggered.connect(self.paste_cell)

        menu.addAction(copy_cell_action)
        menu.addAction(copy_row_action)
        menu.addAction(copy_col_action)
        menu.addSeparator()
        menu.addAction(paste_cell_action)
        menu.exec(QCursor.pos())

    def handle_item_click(self, item, column):
        if column == 0:
            return
        self.last_selected_row = self.sheet_tree.indexOfTopLevelItem(item)
        self.last_selected_col = column
        self.sheet_tree.clearSelection()
        item.setSelected(True)

    def copy_cell(self):
        if self.last_selected_row is not None and self.last_selected_col is not None:
            if self.last_selected_col == 0:
                QMessageBox.warning(self, "Warning", "Row number column can't be copied.")
                return
            item = self.sheet_tree.topLevelItem(self.last_selected_row)
            value = item.text(self.last_selected_col)
            self.clipboard.setText(value)

    def paste_cell(self):
        if self.last_selected_row is not None and self.last_selected_col is not None:
            if self.last_selected_col == 0:
                QMessageBox.warning(self, "Warning", "Can't paste into row number column.")
                return
            value = self.clipboard.text()
            item = self.sheet_tree.topLevelItem(self.last_selected_row)
            item.setText(self.last_selected_col, value)
            self.update_cell_in_sheet(self.last_selected_row, self.last_selected_col, value)

    def copy_row(self):
        if self.last_selected_row is not None:
            item = self.sheet_tree.topLevelItem(self.last_selected_row)
            values = [item.text(i) for i in range(item.columnCount())]
            self.clipboard.setText('\t'.join(values))

    def copy_column(self):
        if self.last_selected_col is not None:
            if self.last_selected_col == 0:
                QMessageBox.warning(self, "Warning", "Can't copy row number column.")
                return
            values = []
            for i in range(self.sheet_tree.topLevelItemCount()):
                item = self.sheet_tree.topLevelItem(i)
                values.append(item.text(self.last_selected_col))
            self.clipboard.setText('\n'.join(values))
    
    def update_cell_in_sheet(self, row_idx, col_idx, new_value):
        col_letter = col_num_to_letter(col_idx)
        cell_ref = f"Sheet1!{col_letter}{row_idx + 1}"
        body = {'values': [[new_value]]}
        try:
            self.service.spreadsheets().values().update(
                spreadsheetId=self.spreadsheet_id,
                range=cell_ref,
                valueInputOption='USER_ENTERED',
                body=body
            ).execute()
        except Exception as e:
            QMessageBox.critical(self, "Update Error", f"Failed to update cell {cell_ref}: {e}")
        
    def apply_modern_style(self):
        self.setStyleSheet("""
            QWidget {
                background-color: #fdfdfd;
                font-family: 'Segoe UI', sans-serif;
                font-size: 13px;
                color: #2c2c2c;
            }

            QGroupBox {
                border: 1px solid #dcdcdc;
                border-radius: 5px;
                margin-top: 20px;
            }

            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 3px 0 3px;
                color: #fff;
                font-weight: bold;
            }

            QPushButton {
                background-color: #e9e9e9;
                border: 1px solid #cccccc;
                border-radius: 4px;
                padding: 6px 12px;
            }

            QPushButton:hover {
                background-color: #dcdcdc;
            }

            QLineEdit, QComboBox {
                border: 1px solid #ccc;
                border-radius: 4px;
                padding: 4px;
            }

            QTreeWidget {
                background-color: #ffffff;
                alternate-background-color: #f5f5f5;
                border: 1px solid #ccc;
                selection-background-color: #0078d7;  /* bright blue */
                selection-color: #ffffff;             /* white text on selection */
                show-decoration-selected: 1;
            }

            QHeaderView::section {
                background-color: #f0f0f0;
                padding: 4px;
                border: 1px solid #ccc;
            }
        """)

    def get_service(self):
        creds = None
        token_path = os.path.join(os.path.dirname(self.credentials_path), 'token.json')
        if os.path.exists(token_path):
            creds = Credentials.from_authorized_user_file(token_path, SCOPES)
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file(self.credentials_path, SCOPES)
                creds = flow.run_local_server(port=0)
            with open(token_path, 'w') as token:
                token.write(creds.to_json())
        return build('sheets', 'v4', credentials=creds)

    def fetch_sheet_data(self):
        result = self.service.spreadsheets().values().get(
            spreadsheetId=self.spreadsheet_id,
            range='Sheet1!A1:Z100'
        ).execute()
        return result.get('values', [])

    def auto_refresh_loop(self):
        try:
            new_data = self.fetch_sheet_data()
            if new_data != self.last_data:
                self.refresh_sheet_display()
        except Exception:
            pass

    def refresh_sheet_display(self):
        try:
            data = self.fetch_sheet_data()
            self.last_data = data

            self.sheet_tree.clear()
            max_cols = max((len(row) for row in data), default=0)
            headers = ["Row"] + [col_num_to_letter(i) for i in range(1, max_cols + 1)]
            self.sheet_tree.setHeaderLabels(headers)

            for idx, row in enumerate(data, start=1):
                display_row = [str(idx)] + row + [''] * (max_cols - len(row))
                row_item = QTreeWidgetItem(display_row)

                # This part must be INSIDE the loop!
                for col in range(len(display_row)):
                    row_item.setTextAlignment(col, Qt.AlignLeft)
                    row_item.setFlags(row_item.flags() | Qt.ItemIsSelectable | Qt.ItemIsEnabled)

                self.sheet_tree.addTopLevelItem(row_item)

            print(f"Loaded {self.sheet_tree.topLevelItemCount()} rows")

        except Exception as e:
            QMessageBox.critical(self, "Display Error", f"Failed to fetch sheet data: {e}")

    def update_sheet(self):
        new_value = self.entry.text().strip()
        if not new_value:
            QMessageBox.critical(self, "Input Error", "Please enter a value to update.")
            return
        selected_column = self.column_combo.currentText()
        selected_row = self.row_combo.currentText()
        cell_address = f"{selected_column}{selected_row}"
        update_range = f"Sheet1!{cell_address}"
        values = [[new_value]]
        body = {'values': values}
        try:
            result = self.service.spreadsheets().values().update(
                spreadsheetId=self.spreadsheet_id,
                range=update_range,
                valueInputOption='USER_ENTERED',
                body=body
            ).execute()
            updated_cells = result.get('updatedCells')
            QMessageBox.information(self, "Success", f"{updated_cells} cell(s) updated at {cell_address}.")
            self.refresh_sheet_display()
        except Exception as e:
            QMessageBox.critical(self, "Update Error", f"An error occurred: {e}")

    def export_to_sqlite(self):
        data = self.last_data
        if not data:
            QMessageBox.critical(self, "Export Error", "No data to export.")
            return

        db_path, _ = QFileDialog.getSaveFileName(self, "Save As", "gsdbe_export.db", "SQLite Database (*.db)")
        if not db_path:
            return

        try:
            conn = sqlite3.connect(db_path)
            c = conn.cursor()

            max_cols = max(len(row) for row in data)
            if len(data[0]) == max_cols and all(cell.strip() != '' for cell in data[0]):
                headers = [cell.strip().replace(" ", "_") or f"col{i+1}" for i, cell in enumerate(data[0])]
                rows = data[1:]
            else:
                headers = [f"col{i+1}" for i in range(max_cols)]
                rows = data

            c.execute("DROP TABLE IF EXISTS sheet_data")
            col_defs = ', '.join([f'"{col}" TEXT' for col in headers])
            c.execute(f"CREATE TABLE sheet_data ({col_defs})")

            for row in rows:
                padded_row = row + [''] * (max_cols - len(row))
                c.execute(f"INSERT INTO sheet_data VALUES ({','.join('?' * max_cols)})", padded_row)

            conn.commit()
            conn.close()
            QMessageBox.information(self, "Success", f"Data exported to:\n{db_path}")
        except Exception as e:
            QMessageBox.critical(self, "Export Error", f"Failed to export to SQLite:\n{e}")

    def add_row(self):
        try:
            row_index = int(self.row_delete_combo.currentText()) - 1
            body = {
                "requests": [{
                    "insertDimension": {
                        "range": {
                            "sheetId": 0,
                            "dimension": "ROWS",
                            "startIndex": row_index,
                            "endIndex": row_index + 1
                        },
                        "inheritFromBefore": False
                    }
                }]
            }
            self.service.spreadsheets().batchUpdate(
                spreadsheetId=self.spreadsheet_id,
                body=body
            ).execute()
            QMessageBox.information(self, "Success", f"Blank row inserted before row {row_index + 1}.")
            self.refresh_sheet_display()
        except Exception as e:
            QMessageBox.critical(self, "Add Error", f"Failed to insert row: {e}")

    def add_column(self):
        try:
            col_index = ord(self.column_delete_combo.currentText().upper()) - ord('A')
            body = {
                "requests": [{
                    "insertDimension": {
                        "range": {
                            "sheetId": 0,
                            "dimension": "COLUMNS",
                            "startIndex": col_index,
                            "endIndex": col_index + 1
                        },
                        "inheritFromBefore": False
                    }
                }]
            }
            self.service.spreadsheets().batchUpdate(
                spreadsheetId=self.spreadsheet_id,
                body=body
            ).execute()
            QMessageBox.information(self, "Success", f"Blank column inserted before column {self.column_delete_combo.currentText()}.")
            self.refresh_sheet_display()
        except Exception as e:
            QMessageBox.critical(self, "Add Error", f"Failed to insert column: {e}")

    def clear_row(self):
        row = self.row_delete_combo.currentText()
        try:
            self.service.spreadsheets().values().clear(
                spreadsheetId=self.spreadsheet_id,
                range=f"Sheet1!A{row}:Z{row}"
            ).execute()
            QMessageBox.information(self, "Success", f"Row {row} cleared.")
            self.refresh_sheet_display()
        except Exception as e:
            QMessageBox.critical(self, "Clear Error", f"Failed to clear row: {e}")

    def clear_column(self):
        col = self.column_delete_combo.currentText()
        try:
            self.service.spreadsheets().values().clear(
                spreadsheetId=self.spreadsheet_id,
                range=f"Sheet1!{col}:{col}"
            ).execute()
            QMessageBox.information(self, "Success", f"Column {col} cleared.")
            self.refresh_sheet_display()
        except Exception as e:
            QMessageBox.critical(self, "Clear Error", f"Failed to clear column: {e}")

    def delete_row(self):
        try:
            row_index = int(self.row_delete_combo.currentText()) - 1
            body = {
                "requests": [{
                    "deleteDimension": {
                        "range": {
                            "sheetId": 0,
                            "dimension": "ROWS",
                            "startIndex": row_index,
                            "endIndex": row_index + 1
                        }
                    }
                }]
            }
            self.service.spreadsheets().batchUpdate(
                spreadsheetId=self.spreadsheet_id,
                body=body
            ).execute()
            QMessageBox.information(self, "Success", f"Row {row_index + 1} deleted.")
            self.refresh_sheet_display()
        except Exception as e:
            QMessageBox.critical(self, "Delete Error", f"Failed to delete row: {e}")

    def delete_column(self):
        try:
            col_index = ord(self.column_delete_combo.currentText().upper()) - ord('A')
            body = {
                "requests": [{
                    "deleteDimension": {
                        "range": {
                            "sheetId": 0,
                            "dimension": "COLUMNS",
                            "startIndex": col_index,
                            "endIndex": col_index + 1
                        }
                    }
                }]
            }
            self.service.spreadsheets().batchUpdate(
                spreadsheetId=self.spreadsheet_id,
                body=body
            ).execute()
            QMessageBox.information(self, "Success", f"Column {self.column_delete_combo.currentText()} deleted.")
            self.refresh_sheet_display()
        except Exception as e:
            QMessageBox.critical(self, "Delete Error", f"Failed to delete column: {e}")

    def clear_cell(self):
        col = self.cell_op_col_combo.currentText()
        row = self.cell_op_row_combo.currentText()
        try:
            self.service.spreadsheets().values().clear(
                spreadsheetId=self.spreadsheet_id,
                range=f"Sheet1!{col}{row}"
            ).execute()
            QMessageBox.information(self, "Success", f"Cell {col}{row} cleared.")
            self.refresh_sheet_display()
        except Exception as e:
            QMessageBox.critical(self, "Clear Error", f"Failed to clear cell: {e}")

    def delete_cell(self):
        try:
            col = self.cell_op_col_combo.currentText()
            row = self.cell_op_row_combo.currentText()
            col_index = ord(col.upper()) - ord('A')
            row_index = int(row) - 1
            body = {
                "requests": [{
                    "deleteRange": {
                        "range": {
                            "sheetId": 0,
                            "startRowIndex": row_index,
                            "endRowIndex": row_index + 1,
                            "startColumnIndex": col_index,
                            "endColumnIndex": col_index + 1,
                        },
                        "shiftDimension": "ROWS"
                    }
                }]
            }
            self.service.spreadsheets().batchUpdate(
                spreadsheetId=self.spreadsheet_id,
                body=body
            ).execute()
            QMessageBox.information(self, "Success", f"Cell {col}{row} deleted (cells shifted upward).")
            self.refresh_sheet_display()
        except Exception as e:
            QMessageBox.critical(self, "Delete Error", f"Failed to delete cell: {e}")
            
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("GSDBE A.0.2.0")
        self.setMinimumSize(1440, 800)
        self.credentials_path = None  # store this
        self.open_spreadsheet_ids = set()  # Track open sheets

        self.tab_widget = QTabWidget()
        self.tab_widget.setTabsClosable(True)  # Enable close ("X") buttons
        self.tab_widget.tabCloseRequested.connect(self.close_tab)  # Connect to handler
        self.setCentralWidget(self.tab_widget)

        self.init_menu()

    def init_menu(self):
        menubar = self.menuBar()
        file_menu = menubar.addMenu("File")

        new_sheet_action = QAction("Add New Sheet", self)
        new_sheet_action.triggered.connect(self.add_new_sheet)
        file_menu.addAction(new_sheet_action)

        load_action = QAction("Load Sheets from File...", self)
        load_action.triggered.connect(self.prompt_for_sheets_file)
        file_menu.addAction(load_action)

    def prompt_for_sheets_file(self):
        filepath, _ = QFileDialog.getOpenFileName(self, "Select sheets.txt file", "", "Text Files (*.txt)")
        if filepath:
            self.load_sheets_from_file(filepath)

    def add_new_sheet(self):
        credentials_path, _ = QFileDialog.getOpenFileName(self, "Select credentials.json", "", "JSON Files (*.json)")
        if not credentials_path:
            return

        spreadsheet_id, ok = QInputDialog.getText(self, "Spreadsheet ID", "Enter Google Spreadsheet ID:")
        if not ok or not spreadsheet_id.strip():
            return
        spreadsheet_id = spreadsheet_id.strip()

        # Prompt for custom tab name
        tab_name, ok = QInputDialog.getText(self, "Tab Name", "Enter custom name for the tab (optional):")
        if not ok:
            return  # user cancelled

        self.credentials_path = credentials_path.strip()
        self.open_spreadsheet_ids.add(spreadsheet_id)

        # Authorize and get sheet metadata
        SCOPES = ['https://www.googleapis.com/auth/spreadsheets']
        token_path = os.path.join(os.path.dirname(credentials_path), 'token.json')
        if os.path.exists(token_path):
            creds = Credentials.from_authorized_user_file(token_path, SCOPES)
            if creds.expired and creds.refresh_token:
                creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(credentials_path, SCOPES)
            creds = flow.run_local_server(port=0)
            with open(token_path, 'w') as token:
                token.write(creds.to_json())

        try:
            service = build('sheets', 'v4', credentials=creds)
            metadata = service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
            sheet_title = metadata.get("properties", {}).get("title", spreadsheet_id[:12] + "...")

            # Use custom tab name if provided, else use sheet title
            final_tab_name = tab_name.strip() if tab_name.strip() else sheet_title

            sheet_widget = SheetTabWidget(spreadsheet_id, credentials_path)
            self.tab_widget.addTab(sheet_widget, final_tab_name)

        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to load sheet metadata:\n{e}")
                    
    def close_tab(self, index):
        widget = self.tab_widget.widget(index)
        if widget:
            widget.deleteLater()
        self.tab_widget.removeTab(index)

    def load_sheets_from_file(self, filepath):
        if not self.credentials_path:
            QMessageBox.critical(self, "Error", "Load the credentials file before sheet files.")
            return

        SCOPES = ['https://www.googleapis.com/auth/spreadsheets']
        token_path = os.path.join(os.path.dirname(self.credentials_path), 'token.json')
        if os.path.exists(token_path):
            creds = Credentials.from_authorized_user_file(token_path, SCOPES)
            if creds.expired and creds.refresh_token:
                creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(self.credentials_path, SCOPES)
            creds = flow.run_local_server(port=0)
            with open(token_path, 'w') as token:
                token.write(creds.to_json())

        service = build('sheets', 'v4', credentials=creds)

        sheets_loaded = 0
        with open(filepath, 'r') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue

                parts = line.split(',')
                spreadsheet_id = parts[0].strip()
                custom_name = parts[1].strip() if len(parts) > 1 else None

                if spreadsheet_id in self.open_spreadsheet_ids:
                    continue  # Skip if already open

                try:
                    metadata = service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
                    sheet_title = metadata.get("properties", {}).get("title", spreadsheet_id[:12] + "...")
                    tab_name = custom_name if custom_name else sheet_title

                    sheet_widget = SheetTabWidget(spreadsheet_id, self.credentials_path)
                    self.tab_widget.addTab(sheet_widget, tab_name)
                    self.open_spreadsheet_ids.add(spreadsheet_id)  # Track this one
                    sheets_loaded += 1
                except Exception as e:
                    QMessageBox.warning(self, "Error", f"Could not load sheet {spreadsheet_id}:\n{e}")

        if sheets_loaded == 0:
            QMessageBox.information(self, "Info", "All sheets already open.")


if __name__ == "__main__":
    app = QApplication(sys.argv)
    main_window = MainWindow()
    main_window.show()
    sys.exit(app.exec())
