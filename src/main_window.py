import os
import sys
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QCheckBox, QSlider, QFrame, QMessageBox,
    QGroupBox
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
        self.setWindowTitle("KumaCleaner LDS - Workspace Organizer")
        self.setFixedSize(500, 560)
        self.setStyleSheet("""
            QMainWindow {
                background-color: #0F1013;
                color: #E2E8F0;
                font-family: 'Segoe UI', -apple-system, sans-serif;
            }
            QLabel {
                color: #E2E8F0;
            }
            QFrame#cardStats {
                background-color: #16181D;
                border: 1px solid rgba(255, 255, 255, 0.07);
                border-radius: 8px;
                padding: 14px;
            }
            QGroupBox {
                border: 1px solid rgba(255, 255, 255, 0.07);
                border-radius: 8px;
                margin-top: 18px;
                padding-top: 14px;
                font-weight: 600;
                font-size: 11px;
                color: #94A3B8;
                letter-spacing: 0.5px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 12px;
                padding: 0 4px;
            }
            QCheckBox {
                color: #CBD5E1;
                font-size: 13px;
                spacing: 8px;
            }
            QCheckBox::indicator {
                width: 16px;
                height: 16px;
                border-radius: 3px;
                border: 1px solid #334155;
                background-color: #0F1013;
            }
            QCheckBox::indicator:checked {
                background-color: #38BDF8;
                border: 1px solid #38BDF8;
            }
            QSlider::groove:horizontal {
                height: 4px;
                background: #1E293B;
                border-radius: 2px;
            }
            QSlider::sub-page:horizontal {
                background: #38BDF8;
                border-radius: 2px;
            }
            QSlider::handle:horizontal {
                background: #F8FAFC;
                width: 14px;
                margin-top: -5px;
                margin-bottom: -5px;
                border-radius: 7px;
            }
            QPushButton#btnStart {
                background-color: #F8FAFC;
                color: #0F172A;
                border: none;
                border-radius: 6px;
                padding: 12px;
                font-size: 14px;
                font-weight: 600;
                letter-spacing: 0.2px;
            }
            QPushButton#btnStart:hover {
                background-color: #E2E8F0;
            }
            QPushButton#btnStart:pressed {
                background-color: #CBD5E1;
            }
            QPushButton#btnEmergency {
                background-color: transparent;
                border: 1px solid #334155;
                color: #94A3B8;
                border-radius: 4px;
                padding: 5px 10px;
                font-size: 11px;
            }
            QPushButton#btnEmergency:hover {
                border-color: #64748B;
                color: #F1F5F9;
            }
        """)

        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(22, 22, 22, 22)
        main_layout.setSpacing(14)

        # Header Title
        header_layout = QHBoxLayout()
        title_layout = QVBoxLayout()
        title = QLabel("KumaCleaner LDS")
        title.setFont(QFont("Segoe UI", 16, QFont.Weight.Bold))
        title.setStyleSheet("color: #F8FAFC;")
        subtitle = QLabel("Desktop workspace organizer with LDS navigation")
        subtitle.setStyleSheet("color: #64748B; font-size: 12px;")
        title_layout.addWidget(title)
        title_layout.addWidget(subtitle)
        header_layout.addLayout(title_layout)
        header_layout.addStretch()

        main_layout.addLayout(header_layout)

        # Status Card (Desktop Scan Details)
        self.card = QFrame()
        self.card.setObjectName("cardStats")
        card_layout = QVBoxLayout(self.card)
        card_layout.setSpacing(6)

        card_title = QLabel("DESKTOP STATUS")
        card_title.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        card_title.setStyleSheet("color: #64748B; letter-spacing: 0.8px;")
        card_layout.addWidget(card_title)

        self.lbl_stats = QLabel("Scanning desktop items...")
        self.lbl_stats.setStyleSheet("font-size: 13px; line-height: 1.5; color: #CBD5E1;")
        card_layout.addWidget(self.lbl_stats)

        main_layout.addWidget(self.card)

        # Configuration Group
        settings_group = QGroupBox("CONFIGURATION & SAFETY")
        settings_layout = QVBoxLayout(settings_group)
        settings_layout.setSpacing(10)

        self.chk_protect_recent = QCheckBox("Protect recently modified files (< 15 minutes)")
        self.chk_protect_recent.setChecked(True)
        self.chk_protect_recent.stateChanged.connect(self.refresh_stats)
        settings_layout.addWidget(self.chk_protect_recent)

        self.chk_include_shortcuts = QCheckBox("Include application shortcuts (.lnk)")
        self.chk_include_shortcuts.setChecked(True)
        self.chk_include_shortcuts.stateChanged.connect(self.refresh_stats)
        settings_layout.addWidget(self.chk_include_shortcuts)

        self.chk_sound = QCheckBox("Enable acoustic audio cues")
        self.chk_sound.setChecked(True)
        self.chk_sound.stateChanged.connect(lambda s: sound_fx.set_enabled(s == 2))
        settings_layout.addWidget(self.chk_sound)

        # Speed slider
        speed_box = QHBoxLayout()
        speed_lbl = QLabel("Navigation speed:")
        speed_lbl.setStyleSheet("color: #94A3B8; font-size: 12px;")
        self.speed_slider = QSlider(Qt.Orientation.Horizontal)
        self.speed_slider.setRange(1, 3)
        self.speed_slider.setValue(1)
        self.speed_val_lbl = QLabel("Standard (1.0x)")
        self.speed_val_lbl.setStyleSheet("color: #38BDF8; font-size: 12px; min-width: 100px;")
        self.speed_slider.valueChanged.connect(self._on_speed_changed)

        speed_box.addWidget(speed_lbl)
        speed_box.addWidget(self.speed_slider)
        speed_box.addWidget(self.speed_val_lbl)
        settings_layout.addLayout(speed_box)

        main_layout.addWidget(settings_group)

        main_layout.addStretch()

        # Primary Action Button
        self.btn_start = QPushButton("Start KumaCleaner")
        self.btn_start.setObjectName("btnStart")
        self.btn_start.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_start.clicked.connect(self.start_cleaning)
        main_layout.addWidget(self.btn_start)

        # Footer
        footer_layout = QHBoxLayout()
        hint = QLabel("Press Esc during cleaning to immediately cancel and restore icons.")
        hint.setStyleSheet("color: #64748B; font-size: 11px;")
        footer_layout.addWidget(hint)
        footer_layout.addStretch()

        btn_emergency = QPushButton("Restore Icons")
        btn_emergency.setObjectName("btnEmergency")
        btn_emergency.setToolTip("Force Windows Explorer to refresh and show all desktop icons")
        btn_emergency.clicked.connect(self.emergency_restore)
        footer_layout.addWidget(btn_emergency)

        main_layout.addLayout(footer_layout)

    def _on_speed_changed(self, val: int):
        speeds = {1: "Standard (1.0x)", 2: "Accelerated (1.7x)", 3: "Fast (2.8x)"}
        self.speed_val_lbl.setText(speeds.get(val, "Standard (1.0x)"))

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
            f"<b>{len(items)} items</b> detected on desktop.<br>"
            f"<b>{len(eligible)} items</b> ready for cleaning ({size_str})<br>"
            f"<span style='color: #64748B;'>{len(protected)} items protected (System, recent, or Git)</span>"
        )
        self.scanned_items = items

    def start_cleaning(self):
        self.refresh_stats()
        eligible = [it for it in self.scanned_items if it.is_eligible]
        if not eligible:
            QMessageBox.information(
                self,
                "Desktop Clean",
                "No eligible items found for cleaning."
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

        win32_helper.set_desktop_icons_visible(True)

        if not sucked_items:
            self.show()
            self.refresh_stats()
            return

        dialog = ReviewDialog(sucked_items, parent=self)
        dialog.exec()

        self.show()
        self.refresh_stats()

    def emergency_restore(self):
        win32_helper.set_desktop_icons_visible(True)
        QMessageBox.information(
            self,
            "Icons Restored",
            "Windows desktop icons have been restored."
        )

    def closeEvent(self, event):
        win32_helper.set_desktop_icons_visible(True)
        super().closeEvent(event)
