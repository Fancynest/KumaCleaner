import os
import datetime
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QCheckBox,
    QWidget, QMessageBox, QFrame
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QIcon, QFont, QColor, QPixmap

from desktop_scanner import DesktopItem
import win32_helper


class ReviewDialog(QDialog):
    """
    Review dialog displayed when vacuum finishes desktop collection.
    Allows user to select which items to recycle, organize, or restore.
    """
    def __init__(self, collected_items: list[DesktopItem], parent=None):
        super().__init__(parent)
        self.collected_items = collected_items
        self.selected_action = "cancel"
        self.init_ui()

    def init_ui(self):
        self.setWindowTitle("Cleaning Review")
        self.setMinimumSize(600, 480)
        self.setStyleSheet("""
            QDialog {
                background-color: #0F1013;
                color: #E2E8F0;
                font-family: 'Segoe UI', -apple-system, sans-serif;
            }
            QLabel {
                color: #E2E8F0;
            }
            QTableWidget {
                background-color: #16181D;
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 6px;
                color: #CBD5E1;
                gridline-color: rgba(255, 255, 255, 0.04);
                selection-background-color: #2D3748;
            }
            QHeaderView::section {
                background-color: #111216;
                color: #64748B;
                padding: 6px 8px;
                border: none;
                font-size: 11px;
                font-weight: 600;
                letter-spacing: 0.5px;
            }
            QPushButton {
                padding: 9px 16px;
                border-radius: 5px;
                font-size: 12px;
                font-weight: 600;
            }
            QPushButton#btnRecycle {
                background-color: #EF4444;
                color: #FFFFFF;
                border: none;
            }
            QPushButton#btnRecycle:hover {
                background-color: #DC2626;
            }
            QPushButton#btnFolder {
                background-color: #F8FAFC;
                color: #0F172A;
                border: none;
            }
            QPushButton#btnFolder:hover {
                background-color: #E2E8F0;
            }
            QPushButton#btnCancel {
                background-color: transparent;
                color: #94A3B8;
                border: 1px solid #334155;
            }
            QPushButton#btnCancel:hover {
                border-color: #64748B;
                color: #F1F5F9;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        # Header Title
        title_box = QVBoxLayout()
        header = QLabel("Cleaning Review")
        header.setFont(QFont("Segoe UI", 15, QFont.Weight.Bold))
        header.setStyleSheet("color: #F8FAFC;")

        total_bytes = sum(it.size_bytes for it in self.collected_items)
        if total_bytes < 1024 * 1024:
            size_str = f"{total_bytes / 1024:.1f} KB"
        else:
            size_str = f"{total_bytes / (1024 * 1024):.1f} MB"

        sub = QLabel(f"{len(self.collected_items)} items collected ({size_str}). Physical files remain in place until confirmed.")
        sub.setStyleSheet("color: #64748B; font-size: 12px;")

        title_box.addWidget(header)
        title_box.addWidget(sub)
        layout.addLayout(title_box)

        # Table of items
        self.table = QTableWidget()
        self.table.setColumnCount(3)
        self.table.setHorizontalHeaderLabels(["SELECT", "FILE NAME", "SIZE"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.table.verticalHeader().setVisible(False)
        self.table.setRowCount(len(self.collected_items))

        self.checkboxes = []
        for row, item in enumerate(self.collected_items):
            chk_widget = QWidget()
            chk_layout = QHBoxLayout(chk_widget)
            chk_layout.setContentsMargins(6, 0, 6, 0)
            chk_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
            chk = QCheckBox()
            chk.setChecked(True)
            chk_layout.addWidget(chk)
            self.checkboxes.append(chk)
            self.table.setCellWidget(row, 0, chk_widget)

            name_item = QTableWidgetItem(item.display_name)
            if item.pixmap:
                name_item.setIcon(QIcon(item.pixmap))
            name_item.setFlags(name_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.table.setItem(row, 1, name_item)

            size_item = QTableWidgetItem(item.formatted_size)
            size_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            size_item.setFlags(size_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.table.setItem(row, 2, size_item)

        layout.addWidget(self.table)

        # Toggle all links
        toggle_layout = QHBoxLayout()
        btn_all = QPushButton("Select all")
        btn_all.setStyleSheet("background: transparent; color: #38BDF8; border: none; font-size: 11px; padding: 0;")
        btn_all.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_all.clicked.connect(lambda: self._set_all_checks(True))

        btn_none = QPushButton("Clear selection")
        btn_none.setStyleSheet("background: transparent; color: #64748B; border: none; font-size: 11px; padding: 0;")
        btn_none.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_none.clicked.connect(lambda: self._set_all_checks(False))

        toggle_layout.addWidget(btn_all)
        toggle_layout.addSpacing(12)
        toggle_layout.addWidget(btn_none)
        toggle_layout.addStretch()
        layout.addLayout(toggle_layout)

        # Action Buttons
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(8)

        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.setObjectName("btnCancel")
        self.btn_cancel.clicked.connect(self.on_cancel)

        self.btn_folder = QPushButton("Move to Folder")
        self.btn_folder.setObjectName("btnFolder")
        self.btn_folder.clicked.connect(self.on_folder)

        self.btn_recycle = QPushButton("Recycle")
        self.btn_recycle.setObjectName("btnRecycle")
        self.btn_recycle.clicked.connect(self.on_recycle)

        btn_layout.addWidget(self.btn_cancel)
        btn_layout.addStretch()
        btn_layout.addWidget(self.btn_folder)
        btn_layout.addWidget(self.btn_recycle)
        layout.addLayout(btn_layout)

    def _set_all_checks(self, checked: bool):
        for chk in self.checkboxes:
            chk.setChecked(checked)

    def get_selected_paths(self) -> list[str]:
        paths = []
        for idx, chk in enumerate(self.checkboxes):
            if chk.isChecked():
                p = self.collected_items[idx].path
                if p and os.path.exists(p):
                    paths.append(p)
        return paths

    def on_recycle(self):
        paths = self.get_selected_paths()
        if not paths:
            QMessageBox.information(self, "No Selection", "No items selected.")
            return

        reply = QMessageBox.question(
            self,
            "Confirm Recycle",
            f"Move {len(paths)} selected items to the Recycle Bin?\n\nThis operation can be undone using Ctrl+Z in Windows Explorer.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            success = win32_helper.safe_recycle_files(paths)
            if success:
                self.selected_action = "recycle"
                self.accept()
            else:
                QMessageBox.warning(self, "Error", "Failed to move one or more items to the Recycle Bin.")

    def on_folder(self):
        paths = self.get_selected_paths()
        if not paths:
            QMessageBox.information(self, "No Selection", "No items selected.")
            return

        today_str = datetime.date.today().strftime("%Y-%m-%d")
        desktop_dir = os.path.join(os.path.expanduser("~"), "Desktop")
        target_dir = os.path.join(desktop_dir, f"Cleaned_{today_str}")

        win32_helper.organize_files_to_folder(paths, target_dir)
        self.selected_action = "folder"
        self.accept()

    def on_cancel(self):
        self.selected_action = "cancel"
        self.reject()
