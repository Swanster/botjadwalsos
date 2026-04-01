# 📅 Cara Mengaktifkan Calendar View di Google Sheets

Setelah sync Google Sheets aktif, Anda bisa menampilkan data jadwal dalam tampilan kalender yang lebih visual.

## 📋 Struktur Data Google Sheets

Sheet "Jadwal" sekarang memiliki format:
| Tanggal | Hari | Nama Anggota | Group |
|---------|------|--------------|-------|
| 2026-04-01 | Rabu | john_doe | INFRA |
| 2026-04-01 | Rabu | jane_smith | CE |
| 2026-04-02 | Kamis | bob_wilson | INFRA |

## 🗓️ Cara Membuat Calendar View

### Opsi 1: Menggunakan Filter View (Paling Mudah)

1. **Buka Google Sheets** Anda
2. Klik menu **Data** → **Create a filter** (atau tekan `Ctrl+Shift+L`)
3. Klik icon filter di header kolom
4. Sortir berdasarkan **Tanggal** (A→Z)
5. Data akan terurut berdasarkan tanggal

### Opsi 2: Menggunakan Google Sheets Calendar Template

1. **Buka Google Sheets baru**
2. Klik **Gallery** (template)
3. Pilih template **Calendar** atau **Annual Calendar**
4. Copy-paste data dari sheet "Jadwal" ke template calendar

### Opsi 3: Menggunakan Add-on Calendar (Rekomendasi)

1. **Install Add-on Calendar:**
   - Klik **Extensions** → **Add-ons** → **Get add-ons**
   - Search: "Calendar"
   - Install add-on seperti **"Calendar by AbleBits"** atau **"Sheet2Site"**

2. **Setup Calendar View:**
   - Buka add-on Calendar
   - Pilih sheet "Jadwal"
   - Map kolom:
     - **Date Column**: Tanggal (Kolom A)
     - **Title Column**: Nama Anggota (Kolom C)
     - **Description Column**: Group (Kolom D)
   - Klik **Create Calendar**

3. **Calendar view akan muncul** di sheet baru!

### Opsi 4: Menggunakan Google Data Studio (Paling Profesional)

1. **Buka [Google Data Studio](https://datastudio.google.com/)**
2. Klik **Create** → **Data Source**
3. Pilih **Google Sheets** sebagai connector
4. Pilih spreadsheet Anda
5. Pilih sheet "Jadwal"
6. Klik **Add to Report**
7. Tambahkan **Calendar Chart** dari visualisasi
8. Map field:
   - **Date**: Tanggal
   - **Dimension**: Nama Anggota, Group

## 🎨 Tips Formatting

### Format Tanggal agar Mudah Dibaca

1. **Pilih kolom Tanggal** (Kolom A)
2. Klik **Format** → **Number** → **Custom date and time**
3. Pilih format: `DD MMM YYYY` (contoh: 01 Apr 2026)

### Format Conditional untuk Group

1. **Pilih kolom Group** (Kolom D)
2. Klik **Format** → **Conditional formatting**
3. Buat rules:
   - **INFRA**: Background hijau
   - **CE**: Background biru
   - **APPS**: Background kuning
   - **MONITORING**: Background merah

### Freeze Header Row

1. **Klik row 2** (row setelah header)
2. Klik **View** → **Freeze** → **1 row**
3. Header akan tetap terlihat saat scroll

## 🔄 Auto-Sync

Data akan **otomatis terupdate** setiap:
- User input jadwal via Telegram (`/start`)
- Admin input jadwal via Web Dashboard
- Klik tombol "Sync Semua Data" di web

## 📊 Contoh Tampilan

```
┌─────────────┬─────────┬──────────────┬──────────┐
│  Tanggal    │  Hari   │ Nama Anggota │  Group   │
├─────────────┼─────────┼──────────────┼──────────┤
│ 01 Apr 2026 │ Rabu    │ john_doe     │ INFRA    │
│ 01 Apr 2026 │ Rabu    │ jane_smith   │ CE       │
│ 02 Apr 2026 │ Kamis   │ bob_wilson   │ INFRA    │
│ 03 Apr 2026 │ Jumat   │ alice_brown  │ APPS     │
└─────────────┴─────────┴──────────────┴──────────┘
```

## ⚠️ Troubleshooting

### Data tidak muncul di Calendar
- Pastikan format tanggal adalah **YYYY-MM-DD**
- Refresh Google Sheets (F5)
- Cek apakah sync sudah berhasil

### Calendar View tidak update
- Klik **File** → **Refresh**
- Hapus cache browser
- Re-sync dari web dashboard

### Format tanggal salah
- Pilih kolom Tanggal
- Format → Number → Date
- Pilih format yang sesuai

## 📞 Bantuan

Jika ada masalah, cek:
1. `GOOGLE_SHEET_SYNC_ENABLED = True` di config.py
2. Credentials Google Sheets sudah benar
3. Sheet ID sudah tepat
4. Log bot untuk error messages
