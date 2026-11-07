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
    Allows user to select which items to Tidy Up, Clean (Recycle), or Delete.
    """
    def __init__(self, collected_items: list[DesktopItem], initial_mode: str = "clean", parent=None):
        super().__init__(parent)
        self.collected_items = collected_items
        self.initial_mode = initial_mode
        self.selected_action = "cancel"
        self.init_ui()

    def init_ui(self):
        self.setWindowTitle("Cleaning Review")
        self.setMinimumSize(640, 500)
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
                padding: 9px 15px;
                border-radius: 5px;
                font-size: 12px;
                font-weight: 600;
            }
            QPushButton#btnTidy {
                background-color: #F8FAFC;
                color: #0F172A;
                border: none;
            }
            QPushButton#btnTidy:hover {
                background-color: #E2E8F0;
            }
            QPushButton#btnClean {
                background-color: #38BDF8;
                color: #0F172A;
                border: none;
            }
            QPushButton#btnClean:hover {
                background-color: #7DD3FC;
            }
            QPushButton#btnDelete {
                background-color: transparent;
                color: #EF4444;
                border: 1px solid #7F1D1D;
            }
            QPushButton#btnDelete:hover {
                background-color: #7F1D1D;
                color: #FEF2F2;
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
        header = QLabel("Desktop Cleanup Review")
        header.setFont(QFont("Segoe UI", 15, QFont.Weight.Bold))
        header.setStyleSheet("color: #F8FAFC;")

        total_bytes = sum(it.size_bytes for it in self.collected_items)
        if total_bytes < 1024 * 1024:
            size_str = f"{total_bytes / 1024:.1f} KB"
        else:
            size_str = f"{total_bytes / (1024 * 1024):.1f} MB"

        sub = QLabel(f"{len(self.collected_items)} items collected ({size_str}). Choose how to process your desktop clutter:")
        sub.setStyleSheet("color: #64748B; font-size: 12px;")

        title_box.addWidget(header)
        title_box.addWidget(sub)
        layout.addLayout(title_box)

        # Table of items
        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["SELECT", "CATEGORY", "FILE NAME", "SIZE"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
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

            cat_item = QTableWidgetItem(getattr(item, 'category', 'General'))
            cat_item.setFlags(cat_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            cat_item.setForeground(QColor("#94A3B8"))
            self.table.setItem(row, 1, cat_item)

            name_item = QTableWidgetItem(item.display_name)
            if item.pixmap:
                name_item.setIcon(QIcon(item.pixmap))
            name_item.setFlags(name_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.table.setItem(row, 2, name_item)

            size_item = QTableWidgetItem(item.formatted_size)
            size_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            size_item.setFlags(size_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.table.setItem(row, 3, size_item)

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

        # 3 Action Buttons + Cancel (RoboDust Paradigm: Tidy Up, Clean, Delete)
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(8)

        self.btn_cancel = QPushButton("Cancel (Restore)")
        self.btn_cancel.setObjectName("btnCancel")
        self.btn_cancel.clicked.connect(self.on_cancel)

        self.btn_delete = QPushButton("Permanent Delete")
        self.btn_delete.setObjectName("btnDelete")
        self.btn_delete.clicked.connect(self.on_delete)

        self.btn_tidy = QPushButton("Tidy Up (Folder)")
        self.btn_tidy.setObjectName("btnTidy")
        self.btn_tidy.clicked.connect(self.on_tidy)

        self.btn_clean = QPushButton("Clean (Recycle Bin)")
        self.btn_clean.setObjectName("btnClean")
        self.btn_clean.clicked.connect(self.on_clean)

        btn_layout.addWidget(self.btn_cancel)
        btn_layout.addStretch()
        btn_layout.addWidget(self.btn_delete)
        btn_layout.addWidget(self.btn_tidy)
        btn_layout.addWidget(self.btn_clean)
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

    def on_clean(self):
        """Clean: Moves files safely to Recycle Bin with Ctrl+Z undo."""
        paths = self.get_selected_paths()
        if not paths:
            QMessageBox.information(self, "No Selection", "No items selected.")
            return

        reply = QMessageBox.question(
            self,
            "Confirm Clean",
            f"Move {len(paths)} selected items to the Recycle Bin?\n\nThis operation can be undone using Ctrl+Z in Windows Explorer.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            success = win32_helper.safe_recycle_files(paths)
            if success:
                self.selected_action = "clean"
                self.accept()
            else:
                QMessageBox.warning(self, "Error", "Failed to move one or more items to the Recycle Bin.")

    def on_tidy(self):
        """Tidy Up: Organizes clutter into categorized folders on Desktop."""
        paths = self.get_selected_paths()
        if not paths:
            QMessageBox.information(self, "No Selection", "No items selected.")
            return

        today_str = datetime.date.today().strftime("%Y-%m-%d")
        desktop_dir = os.path.join(os.path.expanduser("~"), "Desktop")
        target_dir = os.path.join(desktop_dir, f"Tidy_{today_str}")

        moved = win32_helper.tidy_up_files_categorized(paths, target_dir)
        QMessageBox.information(
            self,
            "Tidy Up Complete",
            f"{len(moved)} items organized into categorized folders in:\n{target_dir}"
        )
        self.selected_action = "tidy"
        self.accept()

    def on_delete(self):
        """Delete: Permanently delete files from disk."""
        paths = self.get_selected_paths()
        if not paths:
            QMessageBox.information(self, "No Selection", "No items selected.")
            return

        reply = QMessageBox.warning(
            self,
            "PERMANENT DELETE WARNING",
            f"Are you sure you want to PERMANENTLY DELETE {len(paths)} items from your disk?\n\nWARNING: This action CANNOT be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            success = win32_helper.permanent_delete_files(paths)
            if success:
                self.selected_action = "delete"
                self.accept()
            else:
                QMessageBox.warning(self, "Error", "Some items could not be deleted (they may be in use).")

    def on_cancel(self):
        self.selected_action = "cancel"
        self.reject()
