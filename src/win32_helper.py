import os
import sys
import time
import ctypes
from ctypes import wintypes
import shutil

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32
shell32 = ctypes.windll.shell32

# Win32 Constants
SW_HIDE = 0
SW_SHOW = 5
LVM_GETITEMCOUNT = 0x1004
LVM_GETITEMPOSITION = 0x1010
LVM_GETITEMTEXTW = 0x1073

PROCESS_VM_OPERATION = 0x0008
PROCESS_VM_READ = 0x0010
PROCESS_VM_WRITE = 0x0020
MEM_COMMIT = 0x1000
MEM_RESERVE = 0x2000
MEM_RELEASE = 0x8000
PAGE_READWRITE = 0x04

FO_DELETE = 3
FOF_ALLOWUNDO = 0x0040
FOF_NOCONFIRMATION = 0x0010
FOF_SILENT = 0x0004
FOF_NOERRORUI = 0x0400


class POINT(ctypes.Structure):
    _fields_ = [('x', ctypes.c_long), ('y', ctypes.c_long)]


class LVITEMW(ctypes.Structure):
    _fields_ = [
        ('mask', wintypes.UINT),
        ('iItem', ctypes.c_int),
        ('iSubItem', ctypes.c_int),
        ('state', wintypes.UINT),
        ('stateMask', wintypes.UINT),
        ('pszText', ctypes.c_uint64),
        ('cchTextMax', ctypes.c_int),
        ('iImage', ctypes.c_int),
        ('lParam', ctypes.c_uint64),
        ('iIndent', ctypes.c_int),
        ('iGroupId', ctypes.c_int),
        ('cColumns', wintypes.UINT),
        ('puColumns', ctypes.c_uint64),
        ('piColFmt', ctypes.c_uint64),
        ('iGroup', ctypes.c_int),
    ]


class SHFILEOPSTRUCTW(ctypes.Structure):
    _fields_ = [
        ('hwnd', wintypes.HWND),
        ('wFunc', wintypes.UINT),
        ('pFrom', wintypes.LPCWSTR),
        ('pTo', wintypes.LPCWSTR),
        ('fFlags', wintypes.WORD),
        ('fAnyOperationsAborted', wintypes.BOOL),
        ('hNameMappings', wintypes.LPVOID),
        ('lpszProgressTitle', wintypes.LPCWSTR),
    ]


def ensure_default_desktop():
    """Ensure current thread can access default interactive desktop."""
    try:
        hdesk = user32.OpenDesktopW('default', 0, False, 0x01FF)
        if hdesk:
            user32.SetThreadDesktop(hdesk)
    except Exception:
        pass


def get_desktop_listview_hwnd():
    """Find the HWND of SysListView32 on the Windows desktop."""
    ensure_default_desktop()
    progman = user32.FindWindowW('Progman', 'Program Manager')
    defview = user32.FindWindowExW(progman, 0, 'SHELLDLL_DefView', None)

    if not defview:
        # Check WorkerW windows
        hworker = 0
        while True:
            hworker = user32.FindWindowExW(0, hworker, 'WorkerW', None)
            if not hworker:
                break
            v = user32.FindWindowExW(hworker, 0, 'SHELLDLL_DefView', None)
            if v:
                defview = v
                break

    if defview:
        return user32.FindWindowExW(defview, 0, 'SysListView32', None)
    return 0


def set_desktop_icons_visible(visible: bool):
    """Hide or show real Windows desktop icons."""
    hwnd = get_desktop_listview_hwnd()
    if hwnd:
        user32.ShowWindow(hwnd, SW_SHOW if visible else SW_HIDE)
        # Redraw desktop to avoid residual artifacts
        user32.InvalidateRect(hwnd, None, True)
        user32.UpdateWindow(hwnd)


def get_desktop_icons_info():
    """
    Query SysListView32 in explorer.exe to get list of:
    [{'name': str, 'x': int, 'y': int, 'index': int}, ...]
    """
    ensure_default_desktop()
    hwnd = get_desktop_listview_hwnd()
    if not hwnd:
        return []

    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    if not pid.value:
        return []

    hprocess = kernel32.OpenProcess(
        PROCESS_VM_OPERATION | PROCESS_VM_READ | PROCESS_VM_WRITE,
        False,
        pid.value
    )
    if not hprocess:
        return []

    results = []
    try:
        # Allocate 4KB memory in explorer process
        remote_mem = kernel32.VirtualAllocEx(hprocess, None, 4096, MEM_COMMIT | MEM_RESERVE, PAGE_READWRITE)
        if not remote_mem:
            return []

        buffer_addr = remote_mem + 1024
        count = user32.SendMessageW(hwnd, LVM_GETITEMCOUNT, 0, 0)

        for i in range(count):
            # 1. Get position
            user32.SendMessageW(hwnd, LVM_GETITEMPOSITION, i, remote_mem)
            pt = POINT()
            kernel32.ReadProcessMemory(hprocess, remote_mem, ctypes.byref(pt), ctypes.sizeof(pt), None)

            # 2. Get text
            lv = LVITEMW()
            lv.mask = 0x0001  # LVIF_TEXT
            lv.iItem = i
            lv.iSubItem = 0
            lv.pszText = buffer_addr
            lv.cchTextMax = 260

            kernel32.WriteProcessMemory(hprocess, remote_mem, ctypes.byref(lv), ctypes.sizeof(lv), None)
            user32.SendMessageW(hwnd, LVM_GETITEMTEXTW, i, remote_mem)

            text_buff = ctypes.create_unicode_buffer(260)
            kernel32.ReadProcessMemory(hprocess, buffer_addr, ctypes.byref(text_buff), 520, None)

            name = text_buff.value.strip()
            if name:
                results.append({
                    'index': i,
                    'name': name,
                    'x': pt.x,
                    'y': pt.y
                })

        kernel32.VirtualFreeEx(hprocess, remote_mem, 0, MEM_RELEASE)
    finally:
        kernel32.CloseHandle(hprocess)

    return results


def safe_recycle_files(paths: list[str]) -> bool:
    """
    Send files to Windows Recycle Bin using SHFileOperation with undo support.
    User can undo anytime via Ctrl+Z in Explorer or restore from Recycle Bin!
    """
    if not paths:
        return True

    # Windows SHFileOperation expects double null-terminated multi-string: path1\0path2\0\0
    double_null_str = '\0'.join(os.path.abspath(p) for p in paths) + '\0\0'

    fileop = SHFILEOPSTRUCTW()
    fileop.hwnd = 0
    fileop.wFunc = FO_DELETE
    fileop.pFrom = double_null_str
    fileop.pTo = None
    fileop.fFlags = FOF_ALLOWUNDO | FOF_NOCONFIRMATION | FOF_SILENT | FOF_NOERRORUI
    fileop.fAnyOperationsAborted = False
    fileop.hNameMappings = None
    fileop.lpszProgressTitle = None

    ret = shell32.SHFileOperationW(ctypes.byref(fileop))
    return ret == 0


FILE_CATEGORIES = {
    'Documents': {'.pdf', '.docx', '.doc', '.txt', '.xlsx', '.xls', '.pptx', '.ppt', '.csv', '.md', '.rtf', '.odt'},
    'Media': {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp', '.mp4', '.mkv', '.mov', '.avi', '.mp3', '.flac', '.wav', '.m4a'},
    'Code & Scripts': {'.py', '.js', '.ts', '.html', '.css', '.json', '.kt', '.java', '.cpp', '.c', '.h', '.bat', '.cmd', '.ps1', '.sh', '.sql', '.php'},
    'Archives & Installers': {'.zip', '.rar', '.7z', '.tar', '.gz', '.iso', '.exe', '.msi'},
}


def get_file_category(path: str) -> str:
    if os.path.isdir(path):
        return 'Folders'
    ext = os.path.splitext(path)[1].lower()
    for cat_name, extensions in FILE_CATEGORIES.items():
        if ext in extensions:
            return cat_name
    return 'Miscellaneous'


def tidy_up_files_categorized(paths: list[str], root_target_folder: str) -> list[str]:
    """
    Tidy up desktop clutter by organizing files into categorized subfolders
    (Documents, Media, Code & Scripts, Archives, Folders, Miscellaneous).
    """
    os.makedirs(root_target_folder, exist_ok=True)
    moved = []
    for p in paths:
        if os.path.exists(p):
            category = get_file_category(p)
            dest_dir = os.path.join(root_target_folder, category)
            os.makedirs(dest_dir, exist_ok=True)

            base_name = os.path.basename(p)
            dest = os.path.join(dest_dir, base_name)
            counter = 1
            name, ext = os.path.splitext(base_name)
            while os.path.exists(dest):
                dest = os.path.join(dest_dir, f"{name}_{counter}{ext}")
                counter += 1
            shutil.move(p, dest)
            moved.append(dest)
    return moved


def permanent_delete_files(paths: list[str]) -> bool:
    """Permanently delete files from disk."""
    success = True
    for p in paths:
        try:
            if os.path.isdir(p):
                shutil.rmtree(p)
            elif os.path.exists(p):
                os.remove(p)
        except Exception:
            success = False
    return success


def organize_files_to_folder(paths: list[str], target_folder: str) -> list[str]:
    """Move list of files to an organized target folder on Desktop."""
    return tidy_up_files_categorized(paths, target_folder)
