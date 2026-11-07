import sys
import os

# Add src to python path
current_dir = os.path.dirname(os.path.abspath(__file__))
src_dir = os.path.join(current_dir, 'src')
if src_dir not in sys.path:
    sys.path.insert(0, src_dir)

import win32_helper

# Critical: bind to default interactive desktop before Qt initializes its GUI thread
win32_helper.ensure_default_desktop()

from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QIcon
from main_window import MainWindow


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("KumaCleaner")
    app.setApplicationDisplayName("KumaCleaner")

    window = MainWindow()
    window.show()

    exit_code = app.exec()
    # Always guarantee icons are visible when app exits
    win32_helper.set_desktop_icons_visible(True)
    sys.exit(exit_code)


if __name__ == '__main__':
    main()
