import os
import sys

def create_shortcuts():
    try:
        import win32com.client
    except ImportError:
        print("pywin32 not installed, attempting fallback...")
        return False

    base_dir = os.path.dirname(os.path.abspath(__file__))
    pythonw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
    if not os.path.exists(pythonw):
        pythonw = sys.executable

    main_py = os.path.join(base_dir, "main.py")
    icon_path = os.path.join(base_dir, "assets", "app_icon.ico")

    wsh = win32com.client.Dispatch("WScript.Shell")

    # 1. Start Menu Programs (Launchpad)
    programs_dir = wsh.SpecialFolders("Programs")
    start_shortcut_path = os.path.join(programs_dir, "KumaCleaner.lnk")
    shortcut = wsh.CreateShortcut(start_shortcut_path)
    shortcut.TargetPath = pythonw
    shortcut.Arguments = f'"{main_py}"'
    shortcut.WorkingDirectory = base_dir
    if os.path.exists(icon_path):
        shortcut.IconLocation = f"{icon_path},0"
    shortcut.Description = "KumaCleaner LDS - Desktop Robot Vacuum Simulator"
    shortcut.Save()
    print(f"Created Start Menu (Launchpad) shortcut: {start_shortcut_path}")

    # 2. Desktop
    desktop_dir = wsh.SpecialFolders("Desktop")
    desktop_shortcut_path = os.path.join(desktop_dir, "KumaCleaner.lnk")
    shortcut2 = wsh.CreateShortcut(desktop_shortcut_path)
    shortcut2.TargetPath = pythonw
    shortcut2.Arguments = f'"{main_py}"'
    shortcut2.WorkingDirectory = base_dir
    if os.path.exists(icon_path):
        shortcut2.IconLocation = f"{icon_path},0"
    shortcut2.Description = "KumaCleaner LDS - Desktop Robot Vacuum Simulator"
    shortcut2.Save()
    print(f"Created Desktop shortcut: {desktop_shortcut_path}")
    return True

if __name__ == '__main__':
    create_shortcuts()
