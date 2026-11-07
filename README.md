# KumaCleaner LDS (Windows Edition)

> Native desktop workspace & clutter organizer for Windows with precision LDS navigation, differential kinematics, and non-destructive file operations.

---

## Architecture & Design Principles

- **Precision Vector Hardware Rendering**:
  - Pure subpixel vector rendering (anti-aliased `QPainter`) matching contemporary industrial design.
  - Directional 45° key lighting, micro-beveled PBT composite chassis, recessed mechanical bumper seams, and dark acrylic optical windows.
  - Raised LDS LiDAR turret with rotating ruby optical diode and satin aluminum chamfer collar.
  - Active 3-arm industrial side-brush and differential suspension drive wheels with physical ground drop shadows.

- **Auto-Empty Charging Base**:
  - Geometric docking station with ramp taper, wheel guide grooves, satin brass charging contacts, and ambient status pinhole LED.

- **Acoustic Sound Design**:
  - Bandpass-filtered, acoustic micro-interactions (soft haptic clicks, damped cavity resonance, warm low-frequency motor hum).
  - Zero harsh raw synthesizer beeps.

- **Non-Destructive File Operations**:
  - Simulation preserves real desktop files untouched until user confirms.
  - Review screen with direct selection.
  - Safe recycling via Windows `SHFileOperationW` (`FOF_ALLOWUNDO`) allowing standard `Ctrl + Z` undo in Windows Explorer.
  - Global fail-safe hooks (`atexit` & `sys.excepthook`) guarantee desktop icon visibility is restored under all exit conditions.

---

## Quick Start

### Start Menu / Desktop Shortcut
Run `create_shortcut.py` or search for **KumaCleaner** in the Windows Start Menu.

### Terminal
```bash
python main.py
```

### Controls
- **Spacebar**: Launch cleaning sequence from dock.
- **Escape**: Immediately abort cleaning and restore all desktop icons.
- **Left Click + Drag**: Lift and inspect robot vacuum kinematics.

---

## 🚀 Cara Menjalankan

### Cara Cepat:
Cukup klik ganda (double-click) file **`start.bat`**.

### Atau via Terminal:
```bash
# Pastikan dependensi terpasang:
pip install -r requirements.txt

# Jalankan KumaCleaner:
python main.py
```

---

## 🎛️ Pintasan Tombol (Hotkeys)
- **ESC**: Batalkan pembersihan darurat dan pulihkan seluruh icon desktop secara instan.
- **Klik Kiri pada Kuma**: Angkat dan bawa Kuma jalan-jalan di layar.

---

## 🛠️ Tech Stack
- **Python 3.10+**
- **PyQt6**: Transparent frameless overlay, QPainter vector animation, authentic file thumbnails.
- **Win32 Shell API (pywin32 / ctypes)**: `SysListView32` remote memory inspection, `SHFileOperationW` (Recycle Bin with Undo).
- **Procedural Sound FX Engine**: Sintesis gelombang audio 8-bit in-memory (`wave` + `winsound`).
