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
    Review dialog displayed when Kuma finishes vacuuming the desktop.
    Allows user to safely choose what to do with the collected files.
    """
    def __init__(self, collected_items: list[DesktopItem], parent=None):
        super().__init__(parent)
        self.collected_items = collected_items
        self.selected_action = "cancel"  # "recycle", "folder", "cancel"
        self.init_ui()

    def init_ui(self):
        self.setWindowTitle("🐻 KumaCleaner - Selesai Menyedot Desktop!")
        self.setMinimumSize(640, 520)
        self.setStyleSheet("""
            QDialog {
                background-color: #1e1e2e;
                color: #cdd6f4;
                font-family: 'Segoe UI', sans-serif;
            }
            QLabel {
                color: #cdd6f4;
            }
            QTableWidget {
                background-color: #181825;
                border: 1px solid #313244;
                border-radius: 8px;
                color: #cdd6f4;
                gridline-color: #313244;
                selection-background-color: #45475a;
            }
            QHeaderView::section {
                background-color: #11111b;
                color: #a6adc8;
                padding: 6px;
                border: none;
                font-weight: bold;
            }
            QPushButton {
                padding: 10px 18px;
                border-radius: 6px;
                font-size: 13px;
                font-weight: bold;
            }
            QPushButton#btnRecycle {
                background-color: #f38ba8;
                color: #11111b;
                border: none;
            }
            QPushButton#btnRecycle:hover {
                background-color: #eba0ac;
            }
            QPushButton#btnFolder {
                background-color: #89b4fa;
                color: #11111b;
                border: none;
            }
            QPushButton#btnFolder:hover {
                background-color: #b4befe;
            }
            QPushButton#btnCancel {
                background-color: #313244;
                color: #cdd6f4;
                border: 1px solid #45475a;
            }
            QPushButton#btnCancel:hover {
                background-color: #45475a;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)

        # Header Title
        title_box = QHBoxLayout()
        icon_label = QLabel()
        assets_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets")
        robot_preview = QPixmap(os.path.join(assets_dir, "robot_vacuum.png"))
        if not robot_preview.isNull():
            icon_label.setPixmap(robot_preview.scaled(48, 48, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        else:
            icon_label.setText("🤖")
            icon_label.setFont(QFont("Segoe UI Emoji", 26))
        title_box.addWidget(icon_label)

        title_text_box = QVBoxLayout()
        header = QLabel("Pembersihan Desktop Selesai!")
        header.setFont(QFont("Segoe UI", 16, QFont.Weight.Bold))
        header.setStyleSheet("color: #f9e2af;")

        total_bytes = sum(it.size_bytes for it in self.collected_items)
        if total_bytes < 1024 * 1024:
            size_str = f"{total_bytes / 1024:.1f} KB"
        else:
            size_str = f"{total_bytes / (1024 * 1024):.1f} MB"

        sub = QLabel(f"Robot vacuum berhasil menyedot {len(self.collected_items)} file ({size_str}) ke dustbin.")
        sub.setStyleSheet("color: #a6adc8; font-size: 13px;")

        title_text_box.addWidget(header)
        title_text_box.addWidget(sub)
        title_box.addLayout(title_text_box)
        title_box.addStretch()
        layout.addLayout(title_box)

        # Instructions / Guardrail note
        info_banner = QFrame()
        info_banner.setStyleSheet("background-color: #313244; border-radius: 6px; padding: 6px;")
        info_layout = QHBoxLayout(info_banner)
        info_layout.setContentsMargins(10, 6, 10, 6)
        info_lbl = QLabel("🛡️ <b>Aman:</b> File belum disentuh! Silakan pilih file yang ingin Anda buang atau rapikan ke folder.")
        info_lbl.setStyleSheet("color: #a6e3a1; font-size: 12px;")
        info_layout.addWidget(info_lbl)
        layout.addWidget(info_banner)

        # Table of items
        self.table = QTableWidget()
        self.table.setColumnCount(3)
        self.table.setHorizontalHeaderLabels(["Pilih", "Nama File", "Ukuran"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.table.verticalHeader().setVisible(False)
        self.table.setRowCount(len(self.collected_items))

        self.checkboxes = []
        for row, item in enumerate(self.collected_items):
            # Checkbox item
            chk_widget = QWidget()
            chk_layout = QHBoxLayout(chk_widget)
            chk_layout.setContentsMargins(6, 0, 6, 0)
            chk_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
            chk = QCheckBox()
            chk.setChecked(True)
            chk_layout.addWidget(chk)
            self.checkboxes.append(chk)
            self.table.setCellWidget(row, 0, chk_widget)

            # Name item with icon
            name_item = QTableWidgetItem(item.display_name)
            if item.pixmap:
                name_item.setIcon(QIcon(item.pixmap))
            name_item.setFlags(name_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.table.setItem(row, 1, name_item)

            # Size item
            size_item = QTableWidgetItem(item.formatted_size)
            size_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            size_item.setFlags(size_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.table.setItem(row, 2, size_item)

        layout.addWidget(self.table)

        # Select all / Deselect all links
        toggle_layout = QHBoxLayout()
        btn_all = QPushButton("Pilih Semua")
        btn_all.setStyleSheet("background: transparent; color: #89b4fa; text-decoration: underline; border: none; font-size: 12px;")
        btn_all.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_all.clicked.connect(lambda: self._set_all_checks(True))

        btn_none = QPushButton("Hapus Pilihan")
        btn_none.setStyleSheet("background: transparent; color: #a6adc8; text-decoration: underline; border: none; font-size: 12px;")
        btn_none.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_none.clicked.connect(lambda: self._set_all_checks(False))

        toggle_layout.addWidget(btn_all)
        toggle_layout.addWidget(btn_none)
        toggle_layout.addStretch()
        layout.addLayout(toggle_layout)

        # Action Buttons
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)

        self.btn_cancel = QPushButton("↩️ Batal & Kembalikan")
        self.btn_cancel.setObjectName("btnCancel")
        self.btn_cancel.clicked.connect(self.on_cancel)

        self.btn_folder = QPushButton("📁 Rapikan ke Folder")
        self.btn_folder.setObjectName("btnFolder")
        self.btn_folder.clicked.connect(self.on_folder)

        self.btn_recycle = QPushButton("🗑️ Buang ke Recycle Bin")
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
            QMessageBox.information(self, "Peringatan", "Tidak ada file yang dipilih.")
            return

        reply = QMessageBox.question(
            self,
            "Konfirmasi Recycle Bin",
            f"Kirim {len(paths)} file terpilih ke Recycle Bin?\n\n(Anda tetap bisa Restore atau tekan Ctrl+Z di Desktop jika berubah pikiran)",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            success = win32_helper.safe_recycle_files(paths)
            if success:
                QMessageBox.information(self, "Sukses!", f"{len(paths)} file berhasil dipindahkan ke Recycle Bin.")
                self.selected_action = "recycle"
                self.accept()
            else:
                QMessageBox.warning(self, "Gagal", "Gagal memindahkan sebagian file ke Recycle Bin.")

    def on_folder(self):
        paths = self.get_selected_paths()
        if not paths:
            QMessageBox.information(self, "Peringatan", "Tidak ada file yang dipilih.")
            return

        today_str = datetime.date.today().strftime("%Y-%m-%d")
        desktop_dir = os.path.join(os.path.expanduser("~"), "Desktop")
        target_dir = os.path.join(desktop_dir, f"Kuma_Cleaned_{today_str}")

        moved = win32_helper.organize_files_to_folder(paths, target_dir)
        QMessageBox.information(
            self,
            "Sukses Merapikan!",
            f"{len(moved)} file berhasil dirapikan ke folder:\n{target_dir}"
        )
        self.selected_action = "folder"
        self.accept()

    def on_cancel(self):
        self.selected_action = "cancel"
        self.reject()
