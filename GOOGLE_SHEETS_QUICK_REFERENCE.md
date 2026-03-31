# 📊 Google Sheets Integration - Quick Reference

## ✅ Yang Sudah Diimplementasikan

### 1. **Auto-Sync Real-time**
- ✅ Setiap user input jadwal via Telegram → otomatis sync ke Google Sheets
- ✅ Setiap user input cuti/absensi → otomatis sync ke Google Sheets
- ✅ Setiap admin input jadwal via Web Dashboard → otomatis sync ke Google Sheets

### 2. **Manual Sync Commands**
- ✅ Command `/export` untuk admin - sync manual semua data bulan ini
- ✅ Web Dashboard: tombol "Sync Semua Data" di halaman Google Sheets

### 3. **Struktur Google Sheets**
- **Tab Jadwal**: Tanggal, Hari, Username, User ID, Group, Created At
- **Tab Absensi**: Tanggal, Username, User ID, Recorded At
- **Tab Audit**: Timestamp, User, Action, Description

---

## 🚀 Langkah Setup (Ringkasan)

### Step 1: Install Dependencies
```bash
cd "/home/swanster/project6661/jadwal sos varnion"
source venv/bin/activate
pip install -r requirements.txt
```

### Step 2: Setup Google Cloud Console
Ikuti panduan lengkap di **`GOOGLE_SHEETS_SETUP.md`**:
1. ✅ Buat project di Google Cloud Console
2. ✅ Enable Google Sheets API
3. ✅ Buat Service Account
4. ✅ Download JSON key
5. ✅ Buat Google Sheet baru
6. ✅ Share sheet ke email service account

### Step 3: Upload Credentials
Upload file JSON key yang sudah didownload ke folder project:
```
/home/swanster/project6661/jadwal sos varnion/google_credentials.json
```

### Step 4: Update config.py
Edit file `config.py`:
```python
GOOGLE_SHEET_ID = '1ABC123xyz456_DEF789ghi'  # Ganti dengan ID spreadsheet Anda
GOOGLE_SHEET_SYNC_ENABLED = True  # Enable sync
```

### Step 5: Test Koneksi
```bash
python test_google_sheets.py
```

### Step 6: Restart Bot
```bash
python main.py
```

---

## 📋 File yang Dibuat/Diubah

### File Baru:
1. `core/google_sheets.py` - Modul utama Google Sheets integration
2. `test_google_sheets.py` - Script testing koneksi
3. `GOOGLE_SHEETS_SETUP.md` - Panduan lengkap setup
4. `web/templates/google_sheets.html` - Halaman status Google Sheets di web dashboard
5. `GOOGLE_SHEETS_QUICK_REFERENCE.md` - File ini

### File yang Diubah:
1. `requirements.txt` - Tambah gspread & google-auth
2. `config.py` - Tambah konfigurasi Google Sheets
3. `.gitignore` - Ignore file google_credentials.json
4. `handlers/user_handlers.py` - Auto-sync saat user input jadwal/cuti
5. `handlers/admin_handlers.py` - Command /export untuk manual sync
6. `web/app.py` - Auto-sync di web dashboard + halaman Google Sheets
7. `web/templates/base.html` - Tambah menu Google Sheets di sidebar

---

## 🎯 Fitur yang Tersedia

### Via Telegram Bot:
| Command | Deskripsi |
|---------|-----------|
| `/start` | Input jadwal → auto-sync ke Google Sheets |
| `/cuti` | Input cuti → auto-sync ke Google Sheets |
| `/export` | Manual sync semua data bulan ini ke Google Sheets |

### Via Web Dashboard:
| Menu | Deskripsi |
|------|-----------|
| Jadwal Manual | Input jadwal → auto-sync ke Google Sheets |
| Google Sheets | Lihat status & full sync manual |

---

## 🔧 Troubleshooting

### Error: "File google_credentials.json not found"
**Solusi**: Upload file credentials ke folder project.

### Error: "Spreadsheet not found"
**Solusi**: Cek GOOGLE_SHEET_ID di config.py. Pastikan ID benar.

### Error: "The caller does not have permission"
**Solusi**: Share Google Sheet ke email service account (berakhir dengan `@...iam.gserviceaccount.com`).

### Sync tidak jalan
**Solusi**: 
1. Cek `GOOGLE_SHEET_SYNC_ENABLED = True` di config.py
2. Restart bot setelah ubah config
3. Jalankan `test_google_sheets.py` untuk debug

---

## 📊 Monitoring

### Cek Log Bot
Setiap sync akan muncul log seperti:
```
📝 [Google Sheets] Jadwal added: @username @ 2026-04-01
```

### Cek Google Sheets
- Tab "Jadwal" → data jadwal real-time
- Tab "Absensi" → data cuti real-time
- Tab "Audit" → log aktivitas

---

## 🔐 Keamanan

- ✅ File `google_credentials.json` sudah di `.gitignore`
- ✅ Jangan commit credentials ke Git
- ✅ Jangan share file JSON ke orang lain
- ✅ Backup credentials di tempat aman

---

## 📞 Butuh Bantuan?

1. Baca `GOOGLE_SHEETS_SETUP.md` untuk panduan detail
2. Jalankan `test_google_sheets.py` untuk diagnosa
3. Cek log bot untuk error messages

---

**Last Updated**: 2026-03-31
**Version**: 1.0.0
