import os
import time
from dataclasses import dataclass
from typing import Optional
from PyQt6.QtWidgets import QFileIconProvider
from PyQt6.QtCore import QFileInfo
from PyQt6.QtGui import QPixmap, QIcon

from win32_helper import get_desktop_icons_info

SYSTEM_ITEM_NAMES = {
    'recycle bin', 'this pc', 'control panel', 'network',
    'user files', 'libraries', 'tempat sampah', 'komputer saya'
}


@dataclass
class DesktopItem:
    name: str
    display_name: str
    path: Optional[str]
    x: int
    y: int
    size_bytes: int
    is_dir: bool
    is_system: bool
    is_git: bool
    is_recent: bool
    is_shortcut: bool
    is_eligible: bool = True
    pixmap: Optional[QPixmap] = None

    @property
    def is_heavy(self) -> bool:
        """Files > 25 MB are considered heavy and make Kuma strain."""
        return self.size_bytes > 25 * 1024 * 1024

    @property
    def formatted_size(self) -> str:
        if self.is_dir:
            return "Folder"
        if self.size_bytes < 1024:
            return f"{self.size_bytes} B"
        elif self.size_bytes < 1024 * 1024:
            return f"{self.size_bytes / 1024:.1f} KB"
        elif self.size_bytes < 1024 * 1024 * 1024:
            return f"{self.size_bytes / (1024 * 1024):.1f} MB"
        else:
            return f"{self.size_bytes / (1024 * 1024 * 1024):.2f} GB"


class DesktopScanner:
    def __init__(self):
        self._icon_provider = QFileIconProvider()
        self.desktop_path = os.path.join(os.path.expanduser('~'), 'Desktop')
        self.public_desktop = os.path.join(os.environ.get('PUBLIC', 'C:\\Users\\Public'), 'Desktop')

    def scan(
        self,
        protect_recent_minutes: int = 15,
        include_shortcuts: bool = True,
        ignore_git: bool = True
    ) -> list[DesktopItem]:
        """
        Scan desktop icons with screen coordinates and safety guardrails.
        """
        lv_icons = get_desktop_icons_info()
        now = time.time()
        recent_threshold = protect_recent_minutes * 60

        # Build map of disk files
        disk_files = {}
        for base_dir in [self.desktop_path, self.public_desktop]:
            if not os.path.exists(base_dir):
                continue
            for entry in os.listdir(base_dir):
                if entry.lower() in ('desktop.ini', 'thumbs.db'):
                    continue
                full_path = os.path.join(base_dir, entry)
                disk_files[entry.lower()] = full_path
                # Also store without extension for matching Windows Explorer view
                no_ext = os.path.splitext(entry)[0].lower()
                if no_ext not in disk_files:
                    disk_files[no_ext] = full_path

        items: list[DesktopItem] = []

        # If lv_icons is empty (e.g. desktop listview wasn't queried), fallback to grid layout
        if not lv_icons:
            grid_x = 40
            grid_y = 40
            for idx, entry in enumerate(os.listdir(self.desktop_path)):
                if entry.lower() in ('desktop.ini', 'thumbs.db'):
                    continue
                lv_icons.append({
                    'index': idx,
                    'name': entry,
                    'x': grid_x,
                    'y': grid_y
                })
                grid_y += 90
                if grid_y > 800:
                    grid_y = 40
                    grid_x += 100

        for lv in lv_icons:
            name = lv['name']
            clean_name = name.strip()
            name_lower = clean_name.lower()

            is_system = name_lower in SYSTEM_ITEM_NAMES
            matched_path = disk_files.get(name_lower)

            size_bytes = 0
            is_dir = False
            is_git = False
            is_recent = False
            is_shortcut = False

            if matched_path and os.path.exists(matched_path):
                is_dir = os.path.isdir(matched_path)
                is_shortcut = matched_path.lower().endswith('.lnk')

                # Check git repo
                if is_dir and os.path.exists(os.path.join(matched_path, '.git')):
                    is_git = True

                # Check recent modifications
                try:
                    mtime = os.path.getmtime(matched_path)
                    if (now - mtime) < recent_threshold:
                        is_recent = True
                except Exception:
                    pass

                # Calculate size
                try:
                    if is_dir:
                        # Folder size (rough estimate first level)
                        size_bytes = sum(
                            os.path.getsize(os.path.join(matched_path, f))
                            for f in os.listdir(matched_path)
                            if os.path.isfile(os.path.join(matched_path, f))
                        )
                    else:
                        size_bytes = os.path.getsize(matched_path)
                except Exception:
                    size_bytes = 0
            elif not is_system:
                # Could be system icon not in dictionary
                is_system = True

            # Determine eligibility for cleaning
            is_eligible = True
            if is_system:
                is_eligible = False
            elif is_git and ignore_git:
                is_eligible = False
            elif is_recent and protect_recent_minutes > 0:
                is_eligible = False
            elif is_shortcut and not include_shortcuts:
                is_eligible = False

            # Extract icon pixmap
            pixmap = None
            if matched_path and os.path.exists(matched_path):
                try:
                    info = QFileInfo(matched_path)
                    icon = self._icon_provider.icon(info)
                    pixmap = icon.pixmap(48, 48)
                except Exception:
                    pass

            item = DesktopItem(
                name=clean_name,
                display_name=os.path.basename(matched_path) if matched_path else clean_name,
                path=matched_path,
                x=lv['x'],
                y=lv['y'],
                size_bytes=size_bytes,
                is_dir=is_dir,
                is_system=is_system,
                is_git=is_git,
                is_recent=is_recent,
                is_shortcut=is_shortcut,
                is_eligible=is_eligible,
                pixmap=pixmap
            )
            items.append(item)

        return items
