# Bot Jadwal SOS (Varnion)

Bot Telegram + dashboard web untuk jadwal standby tim: 4 divisi
(INFRA_DELIVERY, INFRA_OPERATION, APPS, MONITORING). Anggota mengisi jadwal
lewat kalender inline di Telegram; admin membuka/menutup periode bulanan dan
memakai dashboard untuk pengaturan kuota, input manual, dan export Sheets.

## Menjalankan

```bash
uv venv .venv --python 3.14 --allow-existing
uv pip install --python .venv/bin/python -r requirements-dev.txt

# buat file .env (lihat tabel di bawah; .env tidak di-commit)
.venv/bin/python main.py
```

Bot berjalan lewat long polling, dashboard ikut distart sebagai thread di
proses yang sama.

## Konfigurasi (`.env`)

| Variabel | Wajib | Keterangan |
|---|---|---|
| `API_TOKEN` | ya | Token bot dari @BotFather |
| `ADMIN_ID` | ya | Telegram user id admin (perintah admin hanya dari sini, di private chat) |
| `GROUP_CHAT_ID` | ya | Chat id grup tujuan pengumuman/pengingat |
| `ALLOWED_TOPIC_ID` | tidak | Id topik forum; kosong = semua topic grup boleh |
| `DB_NAME` | tidak | Default `data/jadwal_pro.db` |
| `WEB_HOST` / `WEB_PORT` | tidak | Default `127.0.0.1:5050` — jangan buka ke publik tanpa HTTPS |
| `SECRET_KEY` | tidak | Bila kosong, dibuat sekali di `data/.secret_key` |
| `DEFAULT_ADMIN_PASSWORD` | sekali | Membuat akun dashboard `admin` saat start pertama bila belum ada admin |
| `GOOGLE_SHEET_*` | tidak | Sync Sheets; tanpa kredensial fitur ini otomatis nonaktif |
| `AI_BASE_URL` | tidak | Default `http://127.0.0.1:20128/v1` (9Router lokal) |
| `AI_API_KEY` | tidak | API key 9Router; kosong = `/tanya` hanya bisa jawab jadwal via parser deterministik |
| `AI_MODEL` | tidak | Default `oc/deepseek-v4.1-flash-free` |

## Perintah bot

Anggota: `/start`, `/menu`, `/jadwal_saya`, `/lihat_jadwal`, `/cuti`,
`/lihat_cuti`, `/batal_jadwal`, `/batal_cuti`, `/tukar_jadwal`,
`/tanya <pertanyaan>` (tanya bot AI), `/panduan`.

`/tanya` juga bisa dipakai untuk aksi cepat, contoh:
- `tolong input jadwal saya tanggal 4, 5, dan 10`
- `ganti jadwal saya tanggal 4, 5`
- `batal jadwal saya tanggal 4`
- `cuti tanggal 4`

Admin (private chat): `/buka_jadwal_bulan [bulan tahun]`,
`/tutup_jadwal_bulan <bulan> <tahun>`, `/statistik`, `/ringkasan_kuota`,
`/tanggal_penuh`, `/upload_grup_csv`, `/export`.

## Reminder

Reminder harian jadwal kosong aktif setiap 09:00 WITA. Matikan dengan env:

```bash
REMINDER_ENABLED=0
```


## Aturan jadwal

- Periode harus dibuka admin; simpan ke bulan yang belum/tidak dibuka ditolak.
- Kapasitas tanggal = **Batasan Harian** (default 1 orang); lihat
  `DAILY_LIMITS_README.md`.
- Maksimal 1 Sabtu dan 1 Minggu per anggota per bulan.
- Jatah weekday mengikuti Maksimal Hari/Bulan divisi (lihat Settings).
- Tukar jadwal hanya boleh antar tipe hari yang sama.

## Test

```bash
.venv/bin/python -m pytest -q
```

Test memakai database temporer (`tmp_path`), tidak pernah menyentuh
`data/jadwal_pro.db`. Bila ingin uji manual, salin DB dulu:
`DB_NAME=data/jadwal_test.db .venv/bin/python main.py`.

## Dokumen lain

- `DAILY_LIMITS_README.md` — aturan kapasitas per tanggal
- `GOOGLE_SHEETS_SETUP.md` — setup integrasi Sheets
- `docs/superpowers/plans/` — rencana implementasi per fitur
- `scripts/archive/README.md` — script migrasi lama (arsip)
