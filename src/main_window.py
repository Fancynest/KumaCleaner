import os
import sys
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QCheckBox, QSlider, QFrame, QMessageBox,
    QProgressBar, QGroupBox
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont, QIcon, QColor, QPixmap

from desktop_scanner import DesktopScanner
from overlay_window import OverlayWindow
from review_dialog import ReviewDialog
from sound_fx import sound_fx
import win32_helper


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.scanner = DesktopScanner()
        self.overlay: OverlayWindow = None
        self.init_ui()
        self.refresh_stats()

    def init_ui(self):
        self.setWindowTitle("🐻 KumaCleaner - Desktop Robot Vacuum for Windows")
        self.setFixedSize(540, 620)
        self.setStyleSheet("""
            QMainWindow {
                background-color: #1e1e2e;
                color: #cdd6f4;
                font-family: 'Segoe UI', sans-serif;
            }
            QLabel {
                color: #cdd6f4;
            }
            QGroupBox {
                border: 1px solid #313244;
                border-radius: 10px;
                margin-top: 14px;
                padding-top: 14px;
                font-weight: bold;
                color: #f9e2af;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 14px;
                padding: 0 5px;
            }
            QCheckBox {
                color: #cdd6f4;
                font-size: 13px;
                spacing: 8px;
            }
            QCheckBox::indicator {
                width: 18px;
                height: 18px;
                border-radius: 4px;
                border: 1px solid #45475a;
                background-color: #181825;
            }
            QCheckBox::indicator:checked {
                background-color: #89b4fa;
                border: 1px solid #89b4fa;
            }
            QSlider::groove:horizontal {
                height: 6px;
                background: #313244;
                border-radius: 3px;
            }
            QSlider::sub-page:horizontal {
                background: #89b4fa;
                border-radius: 3px;
            }
            QSlider::handle:horizontal {
                background: #cdd6f4;
                width: 16px;
                margin-top: -5px;
                margin-bottom: -5px;
                border-radius: 8px;
            }
            QPushButton#btnStart {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #89b4fa, stop:1 #a6e3a1);
                color: #11111b;
                border: none;
                border-radius: 10px;
                padding: 14px;
                font-size: 15px;
                font-weight: bold;
            }
            QPushButton#btnStart:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #b4befe, stop:1 #94e2d5);
            }
            QPushButton#btnEmergency {
                background-color: transparent;
                border: 1px solid #f38ba8;
                color: #f38ba8;
                border-radius: 6px;
                padding: 6px 12px;
                font-size: 11px;
            }
            QPushButton#btnEmergency:hover {
                background-color: rgba(243, 139, 168, 0.15);
            }
        """)

        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(24, 24, 24, 24)
        main_layout.setSpacing(16)

        # Header with Logo & Mascot
        header_layout = QHBoxLayout()
        mascot_lbl = QLabel()
        assets_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets")
        robot_preview = QPixmap(os.path.join(assets_dir, "robot_vacuum.png"))
        if not robot_preview.isNull():
            mascot_lbl.setPixmap(robot_preview.scaled(56, 56, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        else:
            mascot_lbl.setText("🤖")
            mascot_lbl.setFont(QFont("Segoe UI Emoji", 32))
        header_layout.addWidget(mascot_lbl)

        title_layout = QVBoxLayout()
        title = QLabel("KumaCleaner LDS")
        title.setFont(QFont("Segoe UI", 18, QFont.Weight.Bold))
        title.setStyleSheet("color: #f9e2af;")
        subtitle = QLabel("Realistic Desktop Robot Vacuum & Auto-Empty Dock")
        subtitle.setStyleSheet("color: #a6adc8; font-size: 12px;")
        title_layout.addWidget(title)
        title_layout.addWidget(subtitle)
        header_layout.addLayout(title_layout)
        header_layout.addStretch()

        main_layout.addLayout(header_layout)

        # Status Card (Desktop Mess Radar)
        self.card = QFrame()
        self.card.setStyleSheet("""
            QFrame {
                background-color: #181825;
                border: 1px solid #313244;
                border-radius: 10px;
                padding: 12px;
            }
        """)
        card_layout = QVBoxLayout(self.card)

        card_title = QLabel("📊 Status Desktop Saat Ini")
        card_title.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        card_title.setStyleSheet("color: #89b4fa;")
        card_layout.addWidget(card_title)

        self.lbl_stats = QLabel("Memindai desktop...")
        self.lbl_stats.setStyleSheet("font-size: 13px; line-height: 1.5;")
        card_layout.addWidget(self.lbl_stats)

        main_layout.addWidget(self.card)

        # Settings Group
        settings_group = QGroupBox("⚙️ Pengaturan & Keamanan")
        settings_layout = QVBoxLayout(settings_group)
        settings_layout.setSpacing(12)

        self.chk_protect_recent = QCheckBox("🛡️ Lindungi file yang baru diedit (< 15 menit)")
        self.chk_protect_recent.setChecked(True)
        self.chk_protect_recent.stateChanged.connect(self.refresh_stats)
        settings_layout.addWidget(self.chk_protect_recent)

        self.chk_include_shortcuts = QCheckBox("🔗 Sertakan file shortcut (.lnk)")
        self.chk_include_shortcuts.setChecked(True)
        self.chk_include_shortcuts.stateChanged.connect(self.refresh_stats)
        settings_layout.addWidget(self.chk_include_shortcuts)

        self.chk_sound = QCheckBox("🔊 Aktifkan efek suara lucu (ping, sedot, komplain)")
        self.chk_sound.setChecked(True)
        self.chk_sound.stateChanged.connect(lambda s: sound_fx.set_enabled(s == 2))
        settings_layout.addWidget(self.chk_sound)

        # Speed slider
        speed_box = QHBoxLayout()
        speed_lbl = QLabel("⚡ Kecepatan Kuma:")
        speed_lbl.setStyleSheet("color: #a6adc8; font-size: 12px;")
        self.speed_slider = QSlider(Qt.Orientation.Horizontal)
        self.speed_slider.setRange(1, 3)
        self.speed_slider.setValue(1)
        self.speed_val_lbl = QLabel("1.0x (Santai)")
        self.speed_val_lbl.setStyleSheet("color: #89b4fa; font-weight: bold; font-size: 12px; min-width: 80px;")
        self.speed_slider.valueChanged.connect(self._on_speed_changed)

        speed_box.addWidget(speed_lbl)
        speed_box.addWidget(self.speed_slider)
        speed_box.addWidget(self.speed_val_lbl)
        settings_layout.addLayout(speed_box)

        main_layout.addWidget(settings_group)

        main_layout.addStretch()

        # Big Action Button
        self.btn_start = QPushButton("🚀 Jalankan KumaCleaner!")
        self.btn_start.setObjectName("btnStart")
        self.btn_start.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_start.clicked.connect(self.start_cleaning)
        main_layout.addWidget(self.btn_start)

        # Footer with Emergency Restore button
        footer_layout = QHBoxLayout()
        hint = QLabel("Tekan ESC kapan saja saat membersihkan untuk batal")
        hint.setStyleSheet("color: #6c7086; font-size: 11px;")
        footer_layout.addWidget(hint)
        footer_layout.addStretch()

        btn_emergency = QPushButton("🚨 Pulihkan Icon")
        btn_emergency.setObjectName("btnEmergency")
        btn_emergency.setToolTip("Paksa Windows menampilkan kembali seluruh icon desktop")
        btn_emergency.clicked.connect(self.emergency_restore)
        footer_layout.addWidget(btn_emergency)

        main_layout.addLayout(footer_layout)

    def _on_speed_changed(self, val: int):
        speeds = {1: "1.0x (Santai)", 2: "1.7x (Normal)", 3: "2.8x (Turbo)"}
        self.speed_val_lbl.setText(speeds.get(val, "1.0x"))

    def get_speed_multiplier(self) -> float:
        val = self.speed_slider.value()
        return {1: 1.0, 2: 1.7, 3: 2.8}.get(val, 1.0)

    def refresh_stats(self):
        protect_recent = 15 if self.chk_protect_recent.isChecked() else 0
        include_shortcuts = self.chk_include_shortcuts.isChecked()

        items = self.scanner.scan(
            protect_recent_minutes=protect_recent,
            include_shortcuts=include_shortcuts
        )

        eligible = [it for it in items if it.is_eligible]
        protected = [it for it in items if not it.is_eligible]

        total_bytes = sum(it.size_bytes for it in eligible)
        if total_bytes < 1024 * 1024:
            size_str = f"{total_bytes / 1024:.1f} KB"
        else:
            size_str = f"{total_bytes / (1024 * 1024):.1f} MB"

        self.lbl_stats.setText(
            f"• Ditemukan <b>{len(items)} item</b> di desktop.<br>"
            f"• <b>{len(eligible)} item siap disedot</b> (Total: {size_str})<br>"
            f"• <span style='color: #a6e3a1;'>{len(protected)} item dilindungi</span> (Sistem / Baru diedit / Git)"
        )
        self.scanned_items = items

    def start_cleaning(self):
        self.refresh_stats()
        eligible = [it for it in self.scanned_items if it.is_eligible]
        if not eligible:
            QMessageBox.information(
                self,
                "Desktop Sudah Bersih!",
                "Tidak ada file yang memenuhi syarat untuk disedot saat ini."
            )
            return

        self.hide()
        speed = self.get_speed_multiplier()
        self.overlay = OverlayWindow(self.scanned_items, speed_multiplier=speed)
        self.overlay.finished_cleaning.connect(self.on_cleaning_finished)
        self.overlay.show()

    def on_cleaning_finished(self, sucked_items: list):
        if self.overlay:
            self.overlay.close()
            self.overlay = None

        # Always ensure desktop icons are restored
        win32_helper.set_desktop_icons_visible(True)

        if not sucked_items:
            self.show()
            self.refresh_stats()
            return

        # Show review dialog
        dialog = ReviewDialog(sucked_items, parent=self)
        dialog.exec()

        self.show()
        self.refresh_stats()

    def emergency_restore(self):
        win32_helper.set_desktop_icons_visible(True)
        QMessageBox.information(
            self,
            "Icon Dipulihkan",
            "Icon desktop Windows telah dipulihkan secara normal."
        )

    def closeEvent(self, event):
        win32_helper.set_desktop_icons_visible(True)
        super().closeEvent(event)
