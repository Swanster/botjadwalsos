# 📋 Panduan Setup Google Sheets API

Panduan lengkap untuk mengintegrasikan bot jadwal dengan Google Sheets.

---

## 📺 Video Tutorial (Opsional)

Jika lebih suka video, Anda bisa cari di YouTube:
- "Google Sheets API Service Account Python"
- "gspread service account tutorial"

---

## 🔧 Langkah 1: Buat Project di Google Cloud Console

### 1.1 Buka Google Cloud Console
1. Buka https://console.cloud.google.com/
2. Login dengan akun Google Anda (gunakan akun yang punya akses ke Google Sheets)

### 1.2 Buat Project Baru
1. Klik dropdown project di bagian atas (sebelah "Google Cloud Platform")
2. Klik **"NEW PROJECT"** atau **"CREATE PROJECT"**
3. Isi nama project: `Jadwal Standby Bot` (atau nama lain yang Anda suka)
4. Klik **"CREATE"**
5. Tunggu beberapa detik sampai project selesai dibuat
6. **PENTING**: Pastikan project baru saja yang terpilih di dropdown

---

## 🔐 Langkah 2: Enable Google Sheets API

### 2.1 Buka Library API
1. Di sidebar kiri, klik **"APIs & Services"** → **"Library"**
2. Atau langsung buka: https://console.cloud.google.com/apis/library

### 2.2 Cari dan Enable Google Sheets API
1. Ketik **"Google Sheets API"** di kolom search
2. Klik **"Google Sheets API"** dari hasil pencarian
3. Klik tombol **"ENABLE"** (biru)
4. Tunggu sampai status berubah menjadi **"API enabled"**

### 2.3 (Opsional) Enable Google Drive API
Jika ingin fitur lebih advanced (seperti create sheet otomatis):
1. Cari **"Google Drive API"** di Library
2. Klik **"ENABLE"**

---

## 🤖 Langkah 3: Buat Service Account

### 3.1 Buka Credentials Page
1. Di sidebar kiri, klik **"APIs & Services"** → **"Credentials"**
2. Atau langsung: https://console.cloud.google.com/apis/credentials

### 3.2 Create Service Account
1. Klik **"+ CREATE CREDENTIALS"** di bagian atas
2. Pilih **"Service account"**
3. Isi form:
   - **Service account name**: `jadwal-bot-service`
   - **Service account ID**: (akan terisi otomatis)
   - **Description**: `Service account untuk bot jadwal standby`
4. Klik **"CREATE AND CONTINUE"**

### 3.2 Skip Grant Access (untuk saat ini)
1. Di halaman "Grant this service account access to projects"
2. **SKIP SAJA** - kita akan setup access di Google Sheets nanti
3. Klik **"DONE"**

---

## 🔑 Langkah 4: Generate dan Download JSON Key

### 4.1 Buka Service Account yang Dibuat
1. Masih di halaman **Credentials**
2. Scroll ke bawah ke bagian **"Service accounts"**
3. Klik email service account yang baru dibuat (berakhir dengan `@...iam.gserviceaccount.com`)

### 4.2 Buat Key
1. Di halaman detail service account, klik tab **"KEYS"**
2. Klik **"+ ADD KEY"** → **"Create new key"**
3. Pilih tipe key: **"JSON"**
4. Klik **"CREATE"**
5. **PENTING**: File JSON akan otomatis terdownload ke komputer Anda
6. Simpan file ini dengan aman! 🔒

### 4.3 Rename File Key
File yang terdownload biasanya bernama panjang seperti:
```
jadwal-bot-service-a1b2c3d4e5f6.json
```

Rename menjadi lebih sederhana:
```
google_credentials.json
```

---

## 📊 Langkah 5: Setup Google Sheets

### 5.1 Buat Google Sheet Baru
1. Buka https://sheets.google.com/
2. Klik **"+"** atau **"Blank"** untuk buat spreadsheet baru
3. Beri nama: `Jadwal Standby - [Nama Tim Anda]`
4. **PENTING**: Catat URL/ID spreadsheet ini

### 5.2 Dapatkan Spreadsheet ID
URL spreadsheet terlihat seperti ini:
```
https://docs.google.com/spreadsheets/d/1ABC123xyz456_DEF789ghi/edit
                                          ^^^^^^^^^^^^^^^^^^^^^^^^^^
                                          Ini adalah Spreadsheet ID
```

Copy ID ini (contoh: `1ABC123xyz456_DEF789ghi`)

### 5.3 Buat Sheet Tabs
Di spreadsheet yang baru dibuat, buat 3 tabs (di bawah):
1. **Jadwal** - Untuk semua jadwal standby
2. **Absensi** - Untuk data cuti/absen
3. **Audit** - Untuk log aktivitas

### 5.4 Setup Header Kolom

#### Tab "Jadwal":
| A | B | C | D | E | F |
|---|---|---|---|---|---|
| **Tanggal** | **Hari** | **Username** | **User ID** | **Group** | **Created At** |

#### Tab "Absensi":
| A | B | C | D |
|---|---|---|---|
| **Tanggal** | **Username** | **User ID** | **Recorded At** |

#### Tab "Audit":
| A | B | C | D |
|---|---|---|---|
| **Timestamp** | **User** | **Action** | **Description** |

---

## 🔗 Langkah 6: Share Sheet ke Service Account

### 6.1 Copy Email Service Account
1. Kembali ke Google Cloud Console
2. Buka halaman **Credentials**
3. Copy email service account (berakhir dengan `@...iam.gserviceaccount.com`)

Contoh: `jadwal-bot-service@my-project-12345.iam.gserviceaccount.com`

### 6.2 Share Google Sheet
1. Buka Google Sheet yang dibuat di Langkah 5
2. Klik tombol **"Share"** di pojok kanan atas
3. Di kolom "Add people and groups", paste email service account
4. Pilih permission: **"Editor"** (bisa edit)
5. **UNCHECK** "Notify people"
6. Klik **"Share"** atau **"Send"**

### 6.3 Verifikasi
Sekarang service account punya akses edit ke Google Sheet Anda! ✅

---

## 💾 Langkah 7: Setup di Server/Bot

### 7.1 Upload File Credentials
Upload file `google_credentials.json` ke folder project bot:

```
/home/swanster/project6661/jadwal sos varnion/
├── google_credentials.json  ← Upload file ini
├── core/
├── handlers/
└── ...
```

**⚠️ PENTING**: File ini sudah ditambahkan ke `.gitignore` untuk keamanan!

### 7.2 Install Dependencies
Di terminal, jalankan:

```bash
cd "/home/swanster/project6661/jadwal sos varnion"
source venv/bin/activate  # Jika pakai virtualenv
pip install -r requirements.txt
```

### 7.3 Buat File Konfigurasi
Buat file baru `config.py` atau tambahkan ke `config.py` yang sudah ada:

```python
# Google Sheets Configuration
GOOGLE_CREDENTIALS_FILE = "google_credentials.json"
GOOGLE_SHEET_ID = "1ABC123xyz456_DEF789ghi"  # Ganti dengan ID spreadsheet Anda
GOOGLE_SHEET_SYNC_ENABLED = True  # Set True untuk enable sync
```

---

## 🧪 Langkah 8: Test Koneksi

### 8.1 Jalankan Test Script
Saya sudah buatkan script test. Jalankan:

```bash
python test_google_sheets.py
```

Jika sukses, akan muncul:
```
✅ Connected to Google Sheets!
📊 Spreadsheet: Jadwal Standby - [Nama Tim]
📝 Found 3 sheets: Jadwal, Absensi, Audit
✅ Test write successful!
```

### 8.2 Cek Google Sheets
Buka Google Sheets Anda, seharusnya ada data test di tab "Jadwal".

---

## 🚀 Langkah 9: Enable Auto-Sync

Setelah test berhasil, auto-sync akan aktif otomatis untuk:

1. ✅ Setiap user input jadwal via Telegram
2. ✅ Setiap admin input jadwal via Web Dashboard
3. ✅ Setiap user input absensi/cuti
4. ✅ Command `/export` untuk manual sync

---

## 🔒 Keamanan

### File `google_credentials.json`:
- ✅ Sudah ditambahkan ke `.gitignore`
- ✅ Jangan commit ke Git
- ✅ Jangan share ke orang lain
- ✅ Backup di tempat aman

### Jika File Hilang/Bocor:
1. Buka Google Cloud Console
2. Buka halaman **Credentials**
3. Delete key yang compromised
4. Buat key baru
5. Update file di server

---

## ❓ Troubleshooting

### Error: "The caller does not have permission"
**Solusi**: Pastikan sudah share Google Sheet ke email service account (Langkah 6)

### Error: "File google_credentials.json not found"
**Solusi**: Pastikan file ada di folder yang benar (Langkah 7.1)

### Error: "Spreadsheet not found"
**Solusi**: Cek GOOGLE_SHEET_ID di config.py (Langkah 7.3)

### Error: "gspread module not found"
**Solusi**: Jalankan `pip install -r requirements.txt`

---

## 📞 Butuh Bantuan?

Jika ada masalah, screenshot error dan buka issue di repository.

---

## 📚 Referensi

- [gspread Documentation](https://docs.gspread.org/)
- [Google Sheets API Docs](https://developers.google.com/sheets/api)
- [Service Account Auth](https://gspread.readthedocs.io/en/latest/oauth2.html)
