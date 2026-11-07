# Script arsip

Script sekali-pakai dari migrasi 2025–2026 (perbaikan username jadwal, demo
locking, pengaturan batas harian, migrasi grup monitoring). Disimpan sebagai
jejak historis, bukan bagian dari runtime bot/dashboard.

Jalankan dari root repo agar import `core`/`config` tetap bekerja:

    PYTHONPATH=. .venv/bin/python scripts/archive/<nama_script>.py

DB default mengikuti `DB_NAME` di `.env`; arahkan ke salinan bila ingin uji:
`DB_NAME=data/jadwal_test.db PYTHONPATH=. ...`
