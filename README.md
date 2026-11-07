# 🤖 KumaCleaner LDS Pro (Windows Edition)

> **Versi Windows dari [muhraufan/robodust](https://github.com/muhraufan/robodust)**.  
> Robot vacuum virtual realistis (gaya flagship modern seperti Roborock / Roomba) yang membersihkan desktop Windows Anda dengan animasi LiDAR sweep, side-brush berputar, laser obstacle avoidance, dan eksekusi file yang aman!

---

## ✨ Tampilan & Fitur Realistis Baru

- 🛸 **Model Robot Vacuum Realistis**:
  - Tampilan *top-down* premium dengan bodi matte obsidian black, gunmetal titanium rim, dan seam lid dustbin.
  - **LDS LiDAR Turret**: Kubah sensor laser berputar dengan pantulan optik dan diode ruby/cyan dinamis.
  - **Spinning Side-Brush**: Sikat 3-lengan yang berputar aktif di sudut depan untuk menyapu debu ke corong hisap.
  - **3D Structured Light Cross-Laser**: Memproyeksikan garis laser pemindai rintangan di lantai desktop di depan bumper.
  - **Roda Suspensi Interaktif**: Saat Anda mengangkat robot dengan mouse, roda karetnya akan turun menjulur dengan per suspensi dan berputar di udara disertai peringatan sensor jatuh (*drop sensor*).
  - **Realistic Ambient Ground Shadow**: Bayangan kontak multi-layer directional membuat robot terasa benar-benar mengambang di atas wallpaper desktop Anda.

- 🏠 **Auto-Empty Charging Dock Station**:
  - Stasiun dok pengisian daya realistis dengan ramp pendaratan, pin kontak emas, dan lampu indikator status bernapas.
  - Robot keluar dari dok saat mulai dan mundur parkir secara presisi saat selesai.

- 🛡️ **100% Aman & Bergaransi Anti Hilang**:
  - Selama robot bekerja, file fisik asli **TIDAK disentuh**.
  - Di akhir pembersihan, muncul dialog konfirmasi:
    1. **🗑️ Buang ke Recycle Bin** (Resmi Windows, bisa di-*restore* via `Ctrl + Z` di Desktop!).
    2. **📁 Rapikan ke Folder** (Memindahkan file ke `Desktop/Kuma_Cleaned_YYYY-MM-DD`).
    3. **↩️ Batal / Kembalikan** (Icon kembali seperti sedia kala).
  - Dilengkapi proteksi otomatis: mengabaikan file yang baru diedit (< 15 menit), repository `.git`, dan icon sistem seperti *Recycle Bin* / *This PC*.

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
