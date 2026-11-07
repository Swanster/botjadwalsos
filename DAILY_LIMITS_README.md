# Batasan Harian (Daily Assignment Limits)

## Ringkasan
Admin bisa menentukan berapa orang yang boleh mengambil satu tanggal. Nilai ini
adalah **kapasitas tanggal** yang dipakai bersama oleh bot dan dashboard. Bila
tidak ada baris `daily_limits` untuk tanggal tersebut, kapasitas = **1 orang**.

Perubahan 2026-11-07: sebelumnya menu ini hanya dibaca oleh teks pengingat
scheduler; sekarang ia benar-benar menjadi gerbang simpan (bot & web).

## Aturan kapasitas (satu sumber: `core/database.py`)
- `get_daily_limit(tanggal)` → kapasitas tanggal (default 1).
- `date_is_taken(tanggal, user_id)` → True bila jumlah anggota lain pada tanggal
  itu ≥ kapasitas.
- `get_date_capacity(tanggal)` → `{limit, current, is_full}` untuk kalender web.
- Gate simpan bot (`update_user_jadwal_for_month`) dan web
  (`add_jadwal_manual`) memakai angka yang sama.

Aturan lain yang tetap berlaku:
- Satu orang tidak bisa punya dua baris pada tanggal yang sama.
- Maksimal 1 Sabtu dan 1 Minggu per anggota per bulan.
- Jatah weekday per bulan = `Maksimal Hari/Bulan − 2` (minimum 2), dengan
  fallback +1 weekday bila slot weekend yang tersisa sudah penuh.
- Infra Delivery: tepat 1 tanggal per bulan.

## Cara memakai
1. Buka dashboard (`http://127.0.0.1:5050` secara default).
2. Login sebagai admin (akun dibuat dari `DEFAULT_ADMIN_PASSWORD` saat start
   pertama).
3. Menu **Batasan Harian** → pilih tanggal + jumlah orang, atau isi massal
   untuk satu bulan.

Contoh:
```
2026-04-01: 1 orang  (hari sibuk)
2026-04-02: 2 orang  (normal)
2026-04-03: 3 orang  (butuh tambahan)
```

## Catatan
- Menambah kapasitas menjadi >1 berarti dua anggota (bahkan beda divisi) bisa
  berdampingan pada tanggal itu; ini keputusan operasional admin.
- Input weekend lewat dashboard tetap berupa *admin override*: admin boleh
  menambah melebihi kapasitas, sama seperti sebelumnya.
- Laporan bulanan (`/monthly-report`) menghitung "Hari Penuh" dari kapasitas
  tanggal, bukan dari kuota per divisi.

## Test
```bash
.venv/bin/python -m pytest -q
```

`test_daily_limit_gate.py` mengunci perilaku: default 1 orang, batas 2
mengizinkan orang kedua, orang ketiga ditolak, dan laporan bulanan mengikuti
kapasitas.
