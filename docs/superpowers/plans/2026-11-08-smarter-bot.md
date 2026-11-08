# Plan: Bot Jadwal SOS Lebih Pintar

Tanggal: 2026-11-08
Status: Plan only (belum implementasi)

## Tujuan
Membuat bot Telegram jadwal SOS lebih pintar secara bertahap, tetap aman dan mudah diuji.

## Asumsi & batasan
- Default arah: **deterministic-first**. LLM hanya membantu memahami niat dan menjawab, bukan memutuskan aksi tanpa gate.
- Fokus awal: pemahaman bahasa natural + konteks jadwal. Aksi lebih luas menyusul. Fitur admin opsional.
- Tidak menghapus alur kalender inline yang sudah ada.
- Tidak mengaktifkan Google Sheets.
- Semua aksi tulis tetap lewat fungsi database yang sudah ada dan tetap butuh konfirmasi user.

## Kondisi sekarang
- Branch utama: `main`.
- Test saat ini: `155 passed, 4 warnings`.
- Fitur baru sudah ada: `/tambah_jadwal`, `/ganti_jadwal`, `/tanya`, menu panduan, agent ringan di `core/schedule_agent.py` dan `handlers/agent_handler.py`.

## Roadmap singkat
1. Router niat lebih jelas.
2. Konteks jadwal lebih kaya untuk AI.
3. Aksi teks lebih luas.
4. Kemampuan proaktif.
5. Admin opsional.

---

## Fase 1 — Router niat deterministik
**Goal:** Semua input user masuk jalur yang jelas: panduan, isi/ganti jadwal, pertanyaan jadwal, atau pertanyaan umum.

### Files
- New: `core/intent.py`
- Modify: `handlers/user_handlers.py`
- New test: `test_intent.py`

### Interface
```python
def classify_intent(text: str) -> dict:
    # return {"kind": "help" | "fill" | "replace" | "cancel" | "leave" | "swap" | "query" | "unknown"}
```

### Behavior
- `help` jika ada kata cara/bagaimana/panduan dan kata penggunaan.
- `fill` untuk tambah/input/isi jadwal.
- `replace` untuk ganti/ubah/timpa jadwal.
- `cancel` untuk batal jadwal/cuti.
- `leave` untuk cuti.
- `swap` untuk tukar jadwal.
- `query` untuk pertanyaan jadwal seperti “siapa yang SOS besok?”.
- `unknown` jika tidak yakin.

### Tests
- `test_intent.py` memetakan contoh nyata ke intent.
- Contoh harus mencakup kalimat sama tapi beda konteks: “tambah jadwal 4, 5”, “ganti jadwal 4”, “cara batal jadwal”, “siapa SOS besok”.

### Command
```bash
.venv/bin/python -m pytest -q test_intent.py
```

### Commit point
`feat: add deterministic intent router for schedule bot`

---

## Fase 2 — Konteks jadwal lebih kaya
**Goal:** `/tanya` menjawab lebih tepat karena konteks AI bukan hanya 30 hari jadwal.

### Files
- New: `core/schedule_context.py`
- Modify: `core/ai_query.py`
- New test: `test_schedule_context.py`

### Interface
```python
def build_rich_context(today=None) -> str:
    # Ringkas:
    # - hari ini
    # - minggu ini
    # - bulan aktif
    # - tanggal kosong 14 hari
    # - cuti aktif
```

### Behavior
- Semua data diambil dari database existing, bukan dari LLM.
- Konteks tetap ringkas agar prompt tidak bengkak.
- Jika pertanyaan bukan soal jadwal, kirim konteks minimal seperti sekarang.

### Tests
- `test_schedule_context.py` memastikan konteks berisi hari ini, tanggal kosong, dan cuti.
- `test_ai_query.py` tetap lulus.

### Command
```bash
.venv/bin/python -m pytest -q test_schedule_context.py test_ai_query.py
```

### Commit point
`feat: enrich AI schedule context`

---

## Fase 3 — Aksi teks lebih luas
**Goal:** User bisa batal jadwal, cuti, dan lihat jadwal dengan teks pendek tanpa menghapus kalender inline.

### Files
- Modify: `core/schedule_agent.py`
- Modify: `handlers/user_handlers.py`
- Modify: `handlers/agent_handler.py`
- Modify: `test_schedule_agent.py`

### Interface
Perluas `build_fill_plan` menjadi plan aksi:
```python
def build_action_plan(text, user_id, first_name, username, mode) -> dict | str
```

### Behavior
- `add`: union jadwal lama + tanggal baru.
- `replace`: ganti jadwal bulan aktif.
- `cancel_jadwal`: hapus tanggal yang dipilih.
- `leave`: set tanggal cuti.
- Semua aksi tulis wajib tombol konfirmasi.
- Simpan `created_at` dan TTL seperti sekarang.

### Tests
- Tambah, ganti, batal, dan cuti punya test terpisah.
- Test user tidak terdaftar.
- Test bulan tidak dibuka.
- Test tanggal penuh.
- Test konfirmasi batal.

### Command
```bash
.venv/bin/python -m pytest -q test_schedule_agent.py
```

### Commit point
`feat: extend text actions for schedule management`

---

## Fase 4 — Proaktif
**Goal:** Bot memberi informasi berguna tanpa user bertanya dulu.

### Files
- New: `core/reminders.py`
- Modify: `core/scheduler.py`
- Modify: `handlers/user_handlers.py`
- New test: `test_reminders.py`

### Interface
```python
def find_empty_dates(days: int = 14) -> list[date]
def build_empty_schedule_warning() -> str
def schedule_daily_reminder(bot) -> None
```

### Behavior
- Deteksi tanggal kosong 14 hari ke depan.
- Kirim peringatan ke grup/topik aktif sekali per hari.
- Bisa dimatikan lewat env `REMINDER_ENABLED=0`.
- Default tetap non-intrusive.

### Tests
- Tanggal kosong terdeteksi.
- Reminder tidak dikirim jika dimatikan.
- Reminder tidak spam berulang di hari sama.

### Command
```bash
.venv/bin/python -m pytest -q test_reminders.py
```

### Commit point
`feat: add proactive empty schedule reminder`

---

## Fase 5 — Admin opsional
**Goal:** Admin bisa mengelola lebih cepat lewat bot.

### Files
- Modify: `handlers/admin_handlers.py`
- Modify: `main.py`
- Modify: test admin terkait.

### Behavior
- Buka/tutup bulan lewat teks.
- Lihat ringkasan kuota.
- Lihat tanggal penuh.
- Aksi admin tetap dibatasi hanya dari private chat admin.

### Tests
- Non-admin ditolak.
- Admin bisa buka/tutup bulan.
- Ringkasan kuota sesuai database.

### Commit point
`feat: add admin shortcuts for schedule management`

---

## Urutan pengerjaan
1. Fase 1.
2. Fase 2.
3. Fase 3.
4. Fase 4.
5. Fase 5 hanya jika user minta.

## Acceptance
- Semua test lulus.
- Fitur baru tidak merusak kalender inline.
- Aksi tulis tidak bisa terjadi tanpa konfirmasi.
- Tidak ada kredensial atau data sensitif di log/prompt.
- Perubahan kecil dan teruji per fase.
