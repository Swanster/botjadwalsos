# Perbaikan Alur Jadwal "Saat Periode Dibuka" — Implementation Plan

> **For Hermes:** eksekusi per task dengan `subagent-driven-development` (atau langsung bila task saling terkait). Satu wave = satu approval user.

**Goal:** Menutup 3 bug alur isi-jadwal (simpan ke bulan tutup, simpan lintas bulan, perintah yang hanya melihat bulan terbuka pertama), menjadikan Batasan Harian gate nyata (N orang/tanggal), lalu merapikan keamanan dashboard dan kode mati.

**Architecture:** Semua perubahan tetap di lapisan yang sudah ada: `handlers/user_handlers.py` (alur Telegram), `handlers/admin_handlers.py`, `handlers/swap_handler.py`, `core/database.py` (aturan + transaksi), `core/scheduler.py` (pesan), `core/monthly_report.py`, `web/app.py` (dashboard). Tidak ada framework, layer, atau dependency baru. Satu modul test-helper baru (`fake_telebot.py`) mengikuti pola `test_admin_blast.py`.

**Tech Stack:** Python 3.14, pyTelegramBotAPI (telebot), sqlite3, APScheduler, Flask + Flask-Login, pytest.

**Baseline terverifikasi (2026-11-07):** 47 test lulus (`python -m pytest -q`), `py_compile` bersih, dan 3 bug sudah direproduksi lewat fake bot + salinan DB (harness scratch di `~/.hermes/cache/scratch/bot_audit/`). `.venv` repo KOSONG (python 3.14 tanpa pip) — Wave 0 wajib lebih dulu.

---

## Global Constraints

- Jangan pernah menghapus/menimpa data `data/jadwal_pro.db` produksi. Semua test pakai DB temporer (`tmp_path`) dengan pola `_setup(tmp_path, monkeypatch)` yang sudah ada.
- Test lama tidak boleh diubah semantiknya kecuali disebut eksplisit di task (default Batasan Harian = 1, jadi perilaku lama tetap).
- Setiap perubahan perilaku: test RED dulu, baru implementasi (TDD). Satu task = satu commit.
- Semua escape Markdown memakai helper yang sudah ada (`_escape_markdown_text` di `core/scheduler.py`), bukan helper baru.
- Bahasa pesan user: Indonesia, gaya pesan bot yang sudah ada.
- Setelah tiap wave: `python -m pytest -q` harus hijau dan `python -m py_compile` bersih sebelum lanjut.
- Bot TIDAK dijalankan melawan Telegram asli selama pengerjaan (manipulasi DB produksi berisiko). Verifikasi Telegram nyata hanya setelah user setuju, di wave terakhir.

---

## Peta Perubahan File

| File | Wave | Perubahan |
|---|---|---|
| `fake_telebot.py` (baru) | 0 | FakeBot + helper message/button_data |
| `.venv/`, `requirements-dev.txt` (baru) | 0 | Environment test |
| `handlers/user_handlers.py` | 1,2,4 | Gate bulan dibuka, reset sesi saat nav, pemilih bulan, `today_wita`, batas bulanan DRY |
| `handlers/swap_handler.py` | 1 | Bulan dari pilihan user, bukan `get_bulan_dibuka()` |
| `handlers/admin_handlers.py` | 2,4 | `today_wita`, typo EMOJI_HARI, throttle blast |
| `core/database.py` | 2,4 | `date_is_taken`, konflik berbasis kapasitas, `get_date_capacity`, `today_wita`, `add_jadwal_manual` atomik |
| `core/scheduler.py` | 2,4 | Escape mention, hapus fungsi mati |
| `core/monthly_report.py` | 2 | `full_dates`/`under_quota` berbasis kapasitas tanggal |
| `web/app.py` | 2,3 | Gate kapasitas, login tanpa bocor jadwal, rate limit, host, secret key |
| `web/templates/login.html` | 3 | Hapus blok kalender/jadwal dari halaman login |
| `cookies.txt`, `.gitignore`, `config.py` | 3 | Hygiene repo |
| `test_*.py` (baru 6 file) | 1–3 | Regression per bug |
| `DAILY_LIMITS_README.md`, docs | 4 | Sesuaikan dengan gate N/tanggal |

---

# WAVE 0 — Workspace & Baseline (10 menit)

### Task 0.1: Siapkan venv test

**Objective:** Repo bisa menjalankan test di mesin ini.

**Files:** `.venv/` (gitignored), `requirements-dev.txt` (baru)

**Step 1: Buat file dev requirements**

```text
-r requirements.txt
pytest
```

**Step 2: Buat venv + install** (`.venv` sudah ada tapi kosong, jadi pakai `--allow-existing`)

```bash
cd /home/swanster/Projects/projects/botjadwalsos
uv venv .venv --python 3.14 --allow-existing
uv pip install --python .venv/bin/python -r requirements-dev.txt
```

Expected: `Installed … pytest … pyTelegramBotAPI …` tanpa error.

**Step 3: Verifikasi**

```bash
.venv/bin/python -c "import telebot, apscheduler, flask, pytest; print('deps ok')"
```

Expected: `deps ok`

**Step 4: Commit**

```bash
git add requirements-dev.txt && git commit -m "chore: add dev requirements for pytest runs"
```

### Task 0.2: Baseline hijau

**Objective:** Pastikan titik awal bersih sebelum menyentuh kode.

**Files:** —

**Step 1: Jalankan suite**

```bash
.venv/bin/python -m pytest -q
```

Expected: `47 passed` (warning `PytestReturnNotNoneWarning` dari `test_google_sheets.py` boleh ada).

**Step 2: Compile check**

```bash
.venv/bin/python -m py_compile main.py config.py core/*.py handlers/*.py web/*.py && echo "compile OK"
```

Expected: `compile OK`

**Step 3: Catat**, jangan commit apa pun. Kalau jumlah test ≠ 47, berhenti dan laporkan (lingkungan berbeda dari audit).

### Task 0.3: Branch kerja

```bash
git switch -c fix/jadwal-open-period
git status --short
```

Expected: branch baru; hanya `.codebase-memory/` dan `.superpowers/.../task-1-report.md` yang untracked (sudah ada sebelum kerja ini) — jangan di-commit.

### Task 0.4: Modul fake bot untuk test handler

**Objective:** Handler Telegram bisa dites tanpa jaringan.

**Files:** Create `fake_telebot.py`

**Step 1: Tulis helper** (lengkap, tanpa placeholder)

```python
"""Fake TeleBot untuk test handler: merekam pesan dan bisa memicu callback."""
from types import SimpleNamespace


class FakeBot:
    def __init__(self):
        self.handlers = {}
        self.callbacks = []
        self.sent = []
        self.replies = []
        self.edits = []
        self.answers = []
        self.deleted = []
        self.next_step = None

    def message_handler(self, **kwargs):
        def decorator(handler):
            for command in kwargs.get("commands", []):
                self.handlers[command] = handler
            return handler
        return decorator

    def callback_query_handler(self, func=None, **kwargs):
        def decorator(handler):
            self.callbacks.append((func, handler))
            return handler
        return decorator

    def register_next_step_handler(self, message, handler):
        self.next_step = handler

    def send_message(self, chat_id, text, **kwargs):
        self.sent.append({"chat_id": chat_id, "text": text, "markup": kwargs.get("reply_markup")})
        return SimpleNamespace(chat=SimpleNamespace(id=chat_id), message_id=len(self.sent))

    def reply_to(self, message, text, **kwargs):
        self.replies.append(text)

    def edit_message_reply_markup(self, chat_id, message_id, reply_markup=None, **kwargs):
        self.edits.append(reply_markup)

    def edit_message_text(self, text, chat_id, message_id, **kwargs):
        self.edits.append(text)

    def delete_message(self, chat_id, message_id):
        self.deleted.append((chat_id, message_id))

    def answer_callback_query(self, callback_id, text=None, show_alert=False):
        self.answers.append(text)

    def fire(self, data, user_id, chat_id=-100, message_id=1):
        call = SimpleNamespace(
            data=data,
            id="cb",
            from_user=SimpleNamespace(id=user_id, first_name="U", username="u"),
            message=SimpleNamespace(
                chat=SimpleNamespace(id=chat_id, type="supergroup"),
                message_thread_id=None,
                message_id=message_id,
                reply_markup=None,
            ),
        )
        for predicate, handler in self.callbacks:
            if predicate is None or predicate(call):
                handler(call)
                return True
        return False


def button_data(markup):
    """Ratakan InlineKeyboardMarkup jadi daftar (label, callback_data)."""
    return [(button.text, button.callback_data) for row in markup.keyboard for button in row]


def message(user_id, text="", chat_id=-100, thread_id=None, chat_type="supergroup"):
    return SimpleNamespace(
        text=text,
        from_user=SimpleNamespace(id=user_id, first_name="U", username="u"),
        chat=SimpleNamespace(id=chat_id, type=chat_type),
        message_thread_id=thread_id,
        message_id=1,
        document=None,
        entities=None,
    )
```

**Step 2: Verifikasi import**

```bash
.venv/bin/python -c "import fake_telebot; print('helper ok')"
```

Expected: `helper ok`

**Step 3: Commit**

```bash
git add fake_telebot.py && git commit -m "test: add fake telebot helper for handler tests"
```

---

# WAVE 1 — Bug alur isi jadwal (finding 1, 2, 3, 10)

**Acceptance wave 1:**
- Simpan ke bulan `DITUTUP` atau bulan tanpa baris status ditolak dengan pesan jelas; DB tidak berubah.
- Pilih tanggal di bulan A, geser ke bulan B, simpan → hanya tanggal bulan B yang tersimpan.
- Dengan 2 bulan terbuka, `/jadwal_saya`, `/batal_jadwal`, `/lihat_cuti`, `/tukar_jadwal` menanyakan bulan lalu menampilkan bulan itu.
- `/cuti` dan `/batal_cuti` membuka bulan periode aktif, bukan bulan kalender hari ini.

### Shared test setup (dipakai semua test Wave 1)

Buat `test_user_flow_gating.py`, isi header ini:

```python
"""Regression: alur isi jadwal saat periode dibuka.

Bug yang dikunci test ini (repro 2026-11-07):
- Kalender bisa digeser ke bulan yang DITUTUP dan Simpan tetap menulis baris.
- Pilihan dari dua bulan tercampur dalam satu sesi -> simpan gagal total.
- Perintah selain /start hanya memakai bulan terbuka paling awal.
"""
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

import config
from core import database as db
from handlers import user_handlers
from fake_telebot import FakeBot, button_data, message


@pytest.fixture(autouse=True)
def _clean_sessions():
    user_handlers.user_selections.clear()
    user_handlers.user_cuti_selections.clear()
    user_handlers.user_batal_selections.clear()
    user_handlers.user_batal_cuti_selections.clear()
    yield


def _setup(tmp_path, monkeypatch):
    db_path = str(tmp_path / "flow.sqlite")
    monkeypatch.setattr(config, "DB_NAME", db_path)
    monkeypatch.setattr(db, "DB_NAME", db_path)
    db.create_tables()
    db.init_default_settings()
    monkeypatch.setattr(user_handlers, "sync_jadwal_to_sheets", lambda **kwargs: None)
    monkeypatch.setattr(user_handlers, "sync_absensi_to_sheets", lambda **kwargs: None)
    db.set_user_group(500, "Apps User", "apps_user", "APPS")
    return db_path


def _register():
    bot = FakeBot()
    user_handlers.register_user_handlers(bot)
    return bot


def _calendar_dates(markup, prefix):
    return [data for _, data in button_data(markup) if data and data.startswith(prefix)]
```

### Task 1.1: Gate periode terbuka saat simpan jadwal (RED)

**Objective:** Simpan jadwal ke bulan tutup harus ditolak.

**Files:** Test `test_user_flow_gating.py`

**Step 1: Tulis test**

```python
def test_save_rejected_for_month_without_open_status(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    db.buka_bulan_baru(2026, 11)
    bot = _register()

    bot.handlers["start"](message(500, "/start"))
    bot.fire("jadwal_nav_2026_12", 500)          # Desember belum pernah dibuka
    december = _calendar_dates(bot.edits[-1], "jadwal_toggle_2026-12-")
    assert december, "kalender Desember harus tampil untuk reproduksi"
    bot.fire(december[0], 500)
    bot.fire("jadwal_save_2026_12", 500)

    assert db.get_user_jadwal_for_month(500, 2026, 12) == []
    assert any("dibuka" in (text or "").lower() for text in bot.answers)


def test_save_rejected_for_closed_month(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    db.buka_bulan_baru(2026, 11)
    db.tutup_bulan_aktif(2026, 11)
    bot = _register()

    bot.handlers["start"](message(500, "/start"))
    december = _calendar_dates(bot.edits[-1] if bot.edits else bot.sent[-1]["markup"], "jadwal_toggle_")
    # /start menolak karena tidak ada periode terbuka; pastikan tidak ada kalender.
    assert december == []
    assert not db.get_user_jadwal_for_month(500, 2026, 11)
```

**Step 2: Jalankan, harus GAGAL**

```bash
.venv/bin/python -m pytest test_user_flow_gating.py -k "save_rejected" -v
```

Expected: FAIL pada `assert db.get_user_jadwal_for_month(500, 2026, 12) == []` — bukti bug lama (`['2026-12-01']`).

### Task 1.2: Implementasi gate periode

**Objective:** Satu helper + dua pemakaian.

**Files:** Modify `handlers/user_handlers.py`

**Step 1: Tambah helper** setelah `get_weekday_limit_message` (~baris 67):

```python
def is_month_open(tahun, bulan):
    """True bila (tahun, bulan) ada di daftar periode yang dibuka admin."""
    return any(b['tahun'] == tahun and b['bulan'] == bulan for b in get_bulan_dibuka_list())
```

**Step 2: Pakai di cabang `save` mode jadwal/cuti** (baris ~649, sebelum `pilihan_final`):

```python
            elif action == 'save':
                year, month = int(parts[2]), int(parts[3])
                if not is_month_open(year, month):
                    bot.answer_callback_query(
                        call.id,
                        f"Periode jadwal {NAMA_BULAN[month]} {year} sedang tidak dibuka. Hubungi admin.",
                        show_alert=True,
                    )
                    if user_id in selection_dict:
                        del selection_dict[user_id]
                    return
```

**Step 3: Pakai juga di cabang `save` mode batal** (baris ~700, sebelum `pilihan_batal`):

```python
            elif action == 'save':
                year, month = int(parts[3]), int(parts[4])
                if not is_month_open(year, month):
                    bot.answer_callback_query(
                        call.id,
                        f"Periode jadwal {NAMA_BULAN[month]} {year} sedang tidak dibuka.",
                        show_alert=True,
                    )
                    if user_id in selection_dict:
                        del selection_dict[user_id]
                    return
```

**Step 4: Verifikasi**

```bash
.venv/bin/python -m pytest test_user_flow_gating.py -k "save_rejected" -v
```

Expected: PASS (2 test).

**Step 5: Commit**

```bash
git add handlers/user_handlers.py test_user_flow_gating.py
git commit -m "fix(bot): refuse schedule writes for months that are not open"
```

### Task 1.3: Reset sesi saat pindah bulan (RED)

**Objective:** Pilihan bulan A tidak boleh ikut tersimpan ke bulan B.

**Files:** Test `test_user_flow_gating.py`

**Step 1: Tulis test**

```python
def test_nav_to_other_month_does_not_mix_selections(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    db.buka_bulan_baru(2026, 11)
    db.buka_bulan_baru(2026, 12)
    bot = _register()

    bot.handlers["start"](message(500, "/start"))
    picker = button_data(bot.sent[-1]["markup"])
    pick_nov = [d for _, d in picker if d and d.endswith("_2026_11")][0]
    bot.fire(pick_nov, 500)

    november = _calendar_dates(bot.sent[-1]["markup"], "jadwal_toggle_2026-11-")
    bot.fire(november[9], 500)                    # 10 Nov
    bot.fire("jadwal_nav_2026_12", 500)
    december = _calendar_dates(bot.edits[-1], "jadwal_toggle_2026-12-")
    bot.fire(december[0], 500)                    # 1 Des
    bot.fire("jadwal_save_2026_12", 500)

    assert [row["tanggal"] for row in db.get_user_jadwal_for_month(500, 2026, 12)] == ["2026-12-01"]
    assert not any("di luar bulan target" in (text or "") for text in bot.answers)
```

**Step 2: Jalankan, harus GAGAL**

```bash
.venv/bin/python -m pytest test_user_flow_gating.py -k "mix_selections" -v
```

Expected: FAIL — `assert not any("di luar bulan target" ...)` gagal; DB Desember kosong.

### Task 1.4: Implementasi reset sesi

**Objective:** Sesi menyimpan bulan aktif; pindah bulan = reset pilihan.

**Files:** Modify `handlers/user_handlers.py`

**Step 1: `start_jadwal_flow`** — sertakan bulan di sesi (baris ~266):

```python
        user_selections[user_id] = {
            'choices': user_jadwal_lama,
            'tahun': tahun,
            'bulan': bulan,
            'timestamp': time.time(),
        }
```

**Step 2: `start_cuti_flow`** — sama (baris ~317):

```python
        user_cuti_selections[user_id] = {
            'choices': set(absensi_tersimpan),
            'tahun': today.year,
            'bulan': today.month,
            'timestamp': time.time(),
        }
```

**Step 3: `start_batal_jadwal_flow` / `start_batal_cuti_flow`** — tambahkan `'tahun': tahun, 'bulan': bulan` pada dict sesi.

**Step 4: Cabang `nav` mode jadwal/cuti** (baris ~644) — reset bila bulan berubah:

```python
            elif action == 'nav':
                year, month = int(parts[2]), int(parts[3])
                sesi = selection_dict[user_id]
                if (sesi.get('tahun'), sesi.get('bulan')) != (year, month):
                    sesi['tahun'], sesi['bulan'] = year, month
                    sesi['choices'] = _month_seed_choices(mode, user_id, year, month)
                markup = create_calendar(mode, user_id, year, month)
                bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=markup)
```

**Step 5: Tambah helper seed** dekat `create_calendar`:

```python
def _month_seed_choices(mode, user_id, year, month):
    """Pilihan awal untuk satu bulan: jadwal tersimpan (jadwal) atau cuti tersimpan (cuti)."""
    if mode == 'jadwal':
        return {row['tanggal'] for row in get_user_jadwal_for_month(user_id, year, month)}
    start = f"{year}-{month:02d}-01"
    end = f"{year}-{month:02d}-{calendar.monthrange(year, month)[1]}"
    return set(get_user_absensi_in_range(user_id, start, end))
```

**Step 6: Cabang `nav` mode batal** (baris ~695) — reset pilihan ke set kosong saat bulan berubah:

```python
            elif action == 'nav':
                year, month = int(parts[3]), int(parts[4])
                sesi = selection_dict[user_id]
                if (sesi.get('tahun'), sesi.get('bulan')) != (year, month):
                    sesi['tahun'], sesi['bulan'] = year, month
                    sesi['choices'] = set()
                markup = create_calendar(f"batal_{sub_mode}", user_id, year, month)
                bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=markup)
```

**Step 7: Verifikasi**

```bash
.venv/bin/python -m pytest test_user_flow_gating.py -v
.venv/bin/python -m pytest -q
```

Expected: semua PASS (47 + test baru).

**Step 8: Commit**

```bash
git add handlers/user_handlers.py test_user_flow_gating.py
git commit -m "fix(bot): reset calendar session when the user changes month"
```

### Task 1.4b: `today_wita()` (prasyarat default bulan cuti)

**Objective:** Keputusan "bulan ini" tidak bergantung zona mesin; dibutuhkan Task 1.5.

**Files:** Modify `core/database.py` (tambah fungsi dekat `makassar_tz`), `handlers/user_handlers.py` (import)

**Step 1: Implementasi di `core/database.py`** (setelah `makassar_tz = pytz.timezone("Asia/Makassar")`):

```python
def today_wita():
    """Tanggal hari ini menurut zona Asia/Makassar (zona yang dipakai scheduler)."""
    return datetime.now(makassar_tz).date()
```

**Step 2: `handlers/user_handlers.py`** — tambahkan `today_wita` ke daftar import `from core.database import (...)`.

**Step 3: Verifikasi**

```bash
.venv/bin/python -c "from core.database import today_wita; print(today_wita())"
.venv/bin/python -m pytest -q
```

Expected: tanggal hari ini (WITA), semua test lama PASS.

**Step 4: Commit** `git commit -am "feat(db): add today_wita helper"`

### Task 1.5: Pemilih bulan bersama untuk perintah non-/start

**Objective:** `/jadwal_saya`, `/batal_jadwal`, `/lihat_cuti`, `/cuti`, `/batal_cuti` memakai bulan yang sama dengan yang ditawarkan `/start`.

**Files:** Modify `handlers/user_handlers.py`

**Step 1: Tambah helper** setelah `show_open_month_choices`:

```python
    def pick_open_month(chat_id, thread_id, action, callback):
        """Panggil callback(tahun, bulan); minta user memilih bila bulan terbuka > 1."""
        bulan_terbuka_list = get_bulan_dibuka_list()
        if not bulan_terbuka_list:
            bot.send_message(chat_id, "Saat ini tidak ada periode jadwal yang sedang dibuka.", message_thread_id=thread_id)
            return
        if len(bulan_terbuka_list) == 1:
            b = bulan_terbuka_list[0]
            callback(b['tahun'], b['bulan'])
            return
        markup = InlineKeyboardMarkup()
        for b in bulan_terbuka_list:
            markup.add(InlineKeyboardButton(
                f"{NAMA_BULAN[b['bulan']]} {b['tahun']}",
                callback_data=f"pick_{action}_{b['tahun']}_{b['bulan']}",
            ))
        bot.send_message(chat_id, "Pilih bulan jadwal:", reply_markup=markup, message_thread_id=thread_id)
```

**Step 2: `send_jadwal_saya`** — tambah parameter bulan (ganti baris 275-283):

```python
    def send_jadwal_saya(chat_id, user, thread_id=None, tahun=None, bulan=None):
        user_id = user.id
        if tahun is None or bulan is None:
            pick_open_month(chat_id, thread_id, 'jadwal_saya',
                            lambda t, b: send_jadwal_saya(chat_id, user, thread_id, t, b))
            return
        jadwal_user = get_user_jadwal_for_month(user_id, tahun, bulan)
        # sisa badan fungsi tidak berubah: format pesan memakai NAMA_BULAN[bulan] dan tahun di atas
```

**Step 3: `send_lihat_cuti`** — tambah parameter `tahun=None, bulan=None`, dan pada awal fungsi:

```python
        if tahun is None or bulan is None:
            pick_open_month(chat_id, thread_id, 'lihat_cuti',
                            lambda t, b: send_lihat_cuti(chat_id, thread_id, t, b))
            return
```

Hapus pemakaian `get_bulan_dibuka()` di fungsi ini.

**Step 4: `start_batal_jadwal_flow`** — tambah parameter `tahun=None, bulan=None`:

```python
        if tahun is None or bulan is None:
            pick_open_month(chat_id, thread_id, 'batal_jadwal',
                            lambda t, b: start_batal_jadwal_flow(chat_id, user, thread_id, t, b))
            return
```

**Step 5: `start_cuti_flow` dan `start_batal_cuti_flow`** — default ke periode terbuka:

```python
        bulan_terbuka_list = get_bulan_dibuka_list()
        if tahun is None or bulan is None:
            if bulan_terbuka_list:
                pick_open_month(chat_id, thread_id, 'cuti',
                                lambda t, b: start_cuti_flow(chat_id, user, thread_id, t, b))
                return
            today = today_wita()
            tahun, bulan = today.year, today.month
```

(aksi `'cuti'` untuk /cuti, `'batal_cuti'` untuk /batal_cuti; panggil callback-nya masing-masing.)

**Step 6: Handler callback baru** — daftarkan **sebelum** `handle_all_callbacks`:

```python
    @bot.callback_query_handler(func=lambda call: call.data.startswith('pick_'))
    def handle_pick_month(call):
        parts = call.data.split('_')
        if len(parts) < 4:
            bot.answer_callback_query(call.id, "Pilihan bulan tidak valid.", show_alert=True)
            return
        action = '_'.join(parts[1:-2])
        tahun, bulan = int(parts[-2]), int(parts[-1])
        user = call.from_user
        chat_id = call.message.chat.id
        thread_id = call.message.message_thread_id
        routes = {
            'jadwal': lambda: start_jadwal_flow(chat_id, user, thread_id, tahun, bulan),
            'jadwal_saya': lambda: send_jadwal_saya(chat_id, user, thread_id, tahun, bulan),
            'batal_jadwal': lambda: start_batal_jadwal_flow(chat_id, user, thread_id, tahun, bulan),
            'lihat_cuti': lambda: send_lihat_cuti(chat_id, thread_id, tahun, bulan),
            'cuti': lambda: start_cuti_flow(chat_id, user, thread_id, tahun, bulan),
            'batal_cuti': lambda: start_batal_cuti_flow(chat_id, user, thread_id, tahun, bulan),
        }
        route = routes.get(action)
        if route is None:
            bot.answer_callback_query(call.id, "Pilihan bulan tidak valid.", show_alert=True)
            return
        try:
            bot.delete_message(chat_id, call.message.message_id)
        except Exception:
            pass
        route()
        bot.answer_callback_query(call.id)
```

**Step 7: Ganti `show_open_month_choices`** agar memakai helper yang sama (hindari dua jalur):

```python
    def show_open_month_choices(chat_id, thread_id=None):
        bulan_terbuka_list = get_bulan_dibuka_list()
        if not bulan_terbuka_list:
            bot.send_message(chat_id, "Saat ini tidak ada periode jadwal yang sedang dibuka untuk diisi.", message_thread_id=thread_id)
            return None
        if len(bulan_terbuka_list) == 1:
            return bulan_terbuka_list[0]
        markup = InlineKeyboardMarkup()
        for b in bulan_terbuka_list:
            markup.add(InlineKeyboardButton(
                f"{NAMA_BULAN[b['bulan']]} {b['tahun']}",
                callback_data=f"openmonth_{b['tahun']}_{b['bulan']}",
            ))
        bot.send_message(chat_id, "Pilih bulan jadwal yang ingin diisi:", reply_markup=markup, message_thread_id=thread_id)
        return None
```

`handle_open_month_callbacks` tetap seperti sekarang (callback `openmonth_`).

**Step 8: Verifikasi**

```bash
.venv/bin/python -m py_compile handlers/user_handlers.py && .venv/bin/python -m pytest -q
```

Expected: compile OK, 47 passed (test baru menyusul di 1.6–1.8).

**Step 9: Commit**

```bash
git add handlers/user_handlers.py
git commit -m "feat(bot): let users choose any open month for schedule views and cancel"
```

### Task 1.6: Test `/jadwal_saya` dan `/batal_jadwal` dua bulan terbuka

**Files:** Test `test_user_flow_gating.py`

**Step 1: Tulis test**

```python
def test_jadwal_saya_uses_chosen_open_month(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    db.buka_bulan_baru(2026, 11)
    db.buka_bulan_baru(2026, 12)
    db.add_jadwal_manual(500, "Apps User", "apps_user", "2026-12-05")
    bot = _register()

    bot.handlers["jadwal_saya"](message(500, "/jadwal_saya"))
    pick = [d for _, d in button_data(bot.sent[-1]["markup"]) if d and d.startswith("pick_jadwal_saya_2026_12")]
    assert pick, "harus ada tombol Desember 2026"
    bot.fire(pick[0], 500)

    assert any("5 Desember 2026" in sent["text"] for sent in bot.sent)


def test_batal_jadwal_uses_chosen_open_month(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    db.buka_bulan_baru(2026, 11)
    db.buka_bulan_baru(2026, 12)
    db.add_jadwal_manual(500, "Apps User", "apps_user", "2026-12-05")
    bot = _register()

    bot.handlers["batal_jadwal"](message(500, "/batal_jadwal"))
    pick = [d for _, d in button_data(bot.sent[-1]["markup"]) if d and d.startswith("pick_batal_jadwal_2026_12")]
    bot.fire(pick[0], 500)

    cancel_dates = _calendar_dates(bot.sent[-1]["markup"], "batal_jadwal_toggle_2026-12-")
    assert cancel_dates == ["batal_jadwal_toggle_2026-12-05"]
    bot.fire(cancel_dates[0], 500)
    bot.fire("batal_jadwal_save_2026_12", 500)
    assert db.get_user_jadwal_for_month(500, 2026, 12) == []
```

**Step 2: Jalankan**

```bash
.venv/bin/python -m pytest test_user_flow_gating.py -k "chosen_open_month" -v
```

Expected: PASS. (Sebelum Task 1.5: FAIL — tombol `pick_*` tidak ada, bukti bug lama.)

**Step 3: Commit**

```bash
git add test_user_flow_gating.py
git commit -m "test(bot): cover month choice for jadwal_saya and batal_jadwal"
```

### Task 1.7: Test `/cuti`, `/batal_cuti`, `/lihat_cuti`

**Files:** Test `test_user_flow_gating.py`

**Step 1: Tulis test**

```python
def test_cuti_opens_active_period_month_not_today(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    db.buka_bulan_baru(2026, 12)          # periode dibuka = Desember
    from datetime import date
    monkeypatch.setattr(user_handlers, "today_wita", lambda: date(2026, 11, 7))
    bot = _register()

    bot.handlers["cuti"](message(500, "/cuti"))
    dates = _calendar_dates(bot.sent[-1]["markup"], "cuti_toggle_2026-12-")
    assert dates, "kalender cuti harus membuka Desember 2026 (periode aktif)"


def test_lihat_cuti_uses_chosen_open_month(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    db.buka_bulan_baru(2026, 11)
    db.buka_bulan_baru(2026, 12)
    db.set_user_absensi(500, ["2026-12-20"], 2026, 12)
    bot = _register()

    bot.handlers["lihat_cuti"](message(500, "/lihat_cuti"))
    pick = [d for _, d in button_data(bot.sent[-1]["markup"]) if d and d.startswith("pick_lihat_cuti_2026_12")]
    bot.fire(pick[0], 500)
    assert any("20 Desember 2026" in sent["text"] for sent in bot.sent)
```

**Step 2: Jalankan, expected PASS** (Task 1.4b + 1.5 sudah memberi `today_wita` dan pemilih bulan):

```bash
.venv/bin/python -m pytest test_user_flow_gating.py -k "cuti" -v
```

Expected: 2 PASS.

**Step 3: Commit**

```bash
git add test_user_flow_gating.py
git commit -m "test(bot): cover cuti flows using the active period month"
```

### Task 1.8: `/tukar_jadwal` memakai bulan pilihan user

**Files:** Modify `handlers/swap_handler.py`

**Step 1: `handle_tukar_jadwal`** — pecah jadi picker + flow:

```python
    def start_tukar_flow(chat_id, user_id, thread_id, tahun, bulan):
        jadwal_user = get_user_jadwal_for_month(user_id, tahun, bulan)
        if not jadwal_user:
            bot.send_message(chat_id, f"Anda tidak memiliki jadwal standby di {NAMA_BULAN[bulan]} {tahun} untuk ditukar.", message_thread_id=thread_id)
            return
        markup = InlineKeyboardMarkup()
        for jadwal in jadwal_user:
            tgl_obj = datetime.strptime(jadwal['tanggal'], '%Y-%m-%d').date()
            markup.add(InlineKeyboardButton(format_tanggal_indonesia(tgl_obj), callback_data=f"swap_selectA_{jadwal['tanggal']}"))
        bot.send_message(chat_id, "Silakan pilih tanggal JADWAL ANDA yang ingin ditukar:", reply_markup=markup, message_thread_id=thread_id)

    @bot.message_handler(commands=['tukar_jadwal'])
    def handle_tukar_jadwal(message):
        user_id = message.from_user.id
        thread_id = message.message_thread_id
        bulan_terbuka_list = get_bulan_dibuka_list()
        if not bulan_terbuka_list:
            bot.reply_to(message, "Tidak ada jadwal yang aktif untuk ditukar.", message_thread_id=thread_id)
            return
        if len(bulan_terbuka_list) == 1:
            b = bulan_terbuka_list[0]
            start_tukar_flow(message.chat.id, user_id, thread_id, b['tahun'], b['bulan'])
            return
        markup = InlineKeyboardMarkup()
        for b in bulan_terbuka_list:
            markup.add(InlineKeyboardButton(
                f"{NAMA_BULAN[b['bulan']]} {b['tahun']}",
                callback_data=f"pick_tukar_{b['tahun']}_{b['bulan']}",
            ))
        bot.send_message(message.chat.id, "Pilih bulan jadwal yang ingin ditukar:", reply_markup=markup, message_thread_id=thread_id)

    @bot.callback_query_handler(func=lambda call: call.data.startswith('pick_tukar_'))
    def handle_pick_tukar(call):
        parts = call.data.split('_')
        tahun, bulan = int(parts[-2]), int(parts[-1])
        start_tukar_flow(call.message.chat.id, call.from_user.id, call.message.message_thread_id, tahun, bulan)
        bot.answer_callback_query(call.id)
```

Tambahkan `NAMA_BULAN` dan `get_bulan_dibuka_list` pada import modul (salin dari `core/database.py` / `NAMA_BULAN` yang sudah ada di `user_handlers.py`).

**Step 2: `swap_selectA`** — simpan bulan di `swap_data`:

```python
        if action == 'selectA':
            tanggal_a = parts[2]
            tgl_obj = datetime.strptime(tanggal_a, '%Y-%m-%d').date()
            swap_data[user_id] = {'tanggal_a': tanggal_a, 'tahun': tgl_obj.year, 'bulan': tgl_obj.month}
```

**Step 3: `process_mention_step`** — ganti `get_bulan_dibuka()` dengan sesi:

```python
        sesi = swap_data[user_id]
        jadwal_user_b = get_user_jadwal_for_month(user_b_id, sesi['tahun'], sesi['bulan'])
```

**Step 4: Verifikasi**

```bash
.venv/bin/python -m pytest -q && .venv/bin/python -m py_compile handlers/swap_handler.py
```

Expected: semua PASS.

**Step 5: Commit**

```bash
git add handlers/swap_handler.py && git commit -m "fix(swap): use the month the user picked instead of the first open month"
```

**Wave 1 selesai — STOP.** Laporkan hasil `pytest -q` + demo ulang skrip reproduksi (3 bug tidak muncul), lalu minta approval Wave 2.

---

# WAVE 2 — Gate kapasitas & konsistensi data (finding 5, 4, 7, 9, 11)

**Acceptance wave 2:**
- `Batasan Harian = 2` untuk satu tanggal benar-benar mengizinkan 2 orang (bot + web), default tetap 1.
- Badge kalender/laporan memakai angka kapasitas yang sama dengan gate simpan.
- Pesan pengingat tidak pernah gagal parse karena "_" di username Telegram.
- Semua keputusan "hari ini/bulan ini" memakai zona Asia/Makassar.

### Task 2.1: Kapasitas tanggal jadi satu sumber (database)

**Objective:** `date_is_taken()` dan konflik simpan memakai `daily_limits`.

**Files:** Modify `core/database.py` (`has_other_user_assignment` baris 801, `_find_bot_date_conflicts_with_conn` baris 1264, `get_date_capacity` baris 811)

**Step 1: Test (file baru `test_daily_limit_gate.py`)**

```python
import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

import config
from core import database as db


def _setup(tmp_path, monkeypatch):
    db_path = str(tmp_path / "gate.sqlite")
    monkeypatch.setattr(config, "DB_NAME", db_path)
    monkeypatch.setattr(db, "DB_NAME", db_path)
    db.create_tables()
    db.init_default_settings()
    db.set_user_group(1, "Op User", "op_user", "INFRA_OPERATION")
    db.set_user_group(2, "Apps User", "apps_user", "APPS")
    return db_path


def test_default_capacity_is_one_person_per_date(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    assert db.add_jadwal_manual(1, "Op User", "op_user", "2026-11-10")
    assert db.date_is_taken("2026-11-10", 2) is True
    assert db.date_is_taken("2026-11-10", 1) is False


def test_daily_limit_allows_second_person_on_same_date(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    db.set_daily_limit("2026-11-10", 2)
    assert db.add_jadwal_manual(1, "Op User", "op_user", "2026-11-10")
    assert db.date_is_taken("2026-11-10", 2) is False
    result = db.update_user_jadwal_for_month(2, "Apps User", "apps_user", ["2026-11-10"], 2026, 11)
    assert result.ok is True
    assert db.get_date_capacity("2026-11-10") == {"limit": 2, "current": 2, "is_full": True}


def test_third_person_rejected_when_limit_two(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    db.set_daily_limit("2026-11-10", 2)
    db.set_user_group(3, "Mon User", "mon_user", "MONITORING")
    assert db.add_jadwal_manual(1, "Op User", "op_user", "2026-11-10")
    assert db.add_jadwal_manual(2, "Apps User", "apps_user", "2026-11-10")
    result = db.update_user_jadwal_for_month(3, "Mon User", "mon_user", ["2026-11-10"], 2026, 11)
    assert result.ok is False
    assert result.error_code == "date_conflict"
```

**Step 2: Jalankan, expected FAIL**

```bash
.venv/bin/python -m pytest test_daily_limit_gate.py -v
```

Expected: FAIL `AttributeError: module 'core.database' has no attribute 'date_is_taken'`.

**Step 3: Implementasi** — ganti `has_other_user_assignment` (baris 801-809) dengan:

```python
def date_is_taken(tanggal, user_id):
    """True bila slot tanggal ini sudah penuh untuk user (kapasitas = Batasan Harian)."""
    with connect_db() as conn:
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) AS n FROM jadwal WHERE tanggal = ? AND user_id != ?", (tanggal, user_id))
        others = cur.fetchone()['n']
        return others >= _get_daily_limit_with_conn(conn, tanggal)


def _find_date_capacity_conflicts_with_conn(conn, user_id, dates):
    """Daftar tanggal yang slotnya sudah penuh oleh anggota lain (kapasitas Batasan Harian)."""
    if not dates:
        return []
    placeholders = ', '.join('?' for _ in dates)
    cur = conn.cursor()
    cur.execute(
        f"SELECT tanggal, COUNT(*) AS n FROM jadwal WHERE tanggal IN ({placeholders}) AND user_id != ? GROUP BY tanggal",
        list(dates) + [user_id],
    )
    others = {row['tanggal']: row['n'] for row in cur.fetchall()}
    return [tanggal for tanggal in dates if others.get(tanggal, 0) >= _get_daily_limit_with_conn(conn, tanggal)]
```

**Step 4: Ganti pemanggil** `_find_bot_date_conflicts_with_conn` → `_find_date_capacity_conflicts_with_conn` di `update_user_jadwal_for_month` (baris 338) dan ganti `has_other_user_assignment` → `date_is_taken` di:
- `handlers/user_handlers.py:173`
- `handlers/user_handlers.py:619`
- `web/app.py:25` (import) dan `web/app.py:436`

Hapus fungsi lama `_find_bot_date_conflicts_with_conn` (tidak dipakai lagi — cek `grep -rn "_find_bot_date_conflicts"`).

**Step 5: `get_date_capacity`** (baris 811-822) jadi:

```python
def get_date_capacity(tanggal):
    """Kapasitas tanggal untuk tampilan web/kalender: kapasitas = Batasan Harian (default 1)."""
    limit = get_daily_limit(tanggal)
    current = get_assignment_count_for_date(tanggal)
    return {'limit': limit, 'current': current, 'is_full': current >= limit}
```

**Step 6: Verifikasi**

```bash
.venv/bin/python -m pytest test_daily_limit_gate.py -v && .venv/bin/python -m pytest -q
```

Expected: 3 test baru PASS, total 50+ PASS. Test lama `test_date_capacity_matches_one_per_date_gate` tetap PASS karena default limit 1.

**Step 7: Commit**

```bash
git add core/database.py handlers/user_handlers.py web/app.py test_daily_limit_gate.py
git commit -m "feat(db): make Batasan Harian the real per-date capacity gate"
```

### Task 2.2: Docstring & label gerbang menyesuaikan kapasitas

**Files:** Modify `handlers/user_handlers.py` (pesan `❌ Tanggal ini sudah diambil anggota lain.` baris 620), `core/database.py` (docstring)

**Step 1:** Ganti pesan alert toggle (baris 620) dan `SAVE_ERROR_MESSAGES['date_conflict']` (baris 27) menjadi:

```python
    'date_conflict': 'Tanggal yang dipilih sudah penuh (Batasan Harian tercapai). Silakan pilih tanggal lain.',
```

dan

```python
                        bot.answer_callback_query(call.id, "❌ Tanggal ini sudah penuh. Silakan pilih tanggal lain.", show_alert=True)
```

**Step 2: Verifikasi** `.venv/bin/python -m pytest -q` → PASS.

**Step 3: Commit** `git commit -am "chore(bot): clarify date capacity messages"`

### Task 2.3: Laporan bulanan memakai kapasitas tanggal

**Objective:** "Hari Penuh" dan "Hari Kurang" tidak lagi selalu 31/0.

**Files:** Modify `core/monthly_report.py` (baris 97-129), `web/templates/monthly_report.html` (label), formatter Telegram (baris 197-210)

**Step 1: Test** (tambahkan ke `test_daily_limit_gate.py`)

```python
def test_monthly_report_full_days_follow_date_capacity(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    from core.monthly_report import build_monthly_report
    for day in range(1, 4):
        db.add_jadwal_manual(1, "Op User", "op_user", f"2026-11-0{day}")
    report = build_monthly_report(2026, 11)
    assert set(report["full_dates"]) == {"2026-11-01", "2026-11-02", "2026-11-03"}
    assert report["under_capacity_dates_count"] == 27
```

**Step 2: Jalankan** → FAIL (key belum ada).

**Step 3: Implementasi** — ganti blok loop (baris 97-129) dengan:

```python
    empty_dates = []
    full_dates = []
    under_capacity = []
    over_capacity = []
    for day in range(1, days_in_month + 1):
        tanggal = f'{tahun}-{bulan:02d}-{day:02d}'
        if not per_date.get(tanggal):
            empty_dates.append(tanggal)

        capacity = get_date_capacity(tanggal)
        if capacity['is_full']:
            full_dates.append(tanggal)
        elif capacity['current'] > capacity['limit']:
            over_capacity.append({'tanggal': tanggal, 'current': capacity['current'], 'limit': capacity['limit']})
        else:
            under_capacity.append({'tanggal': tanggal, 'current': capacity['current'], 'limit': capacity['limit']})
```

Import `get_date_capacity` di header. Pada dict return, ganti kunci:
- `'under_quota_dates_count': len(under_capacity)`
- `'under_quota': under_capacity`
- `'over_quota': over_capacity`
- tambah `'under_capacity_dates_count': len(under_capacity)`

Formatter Telegram (baris 197-210) menyesuaikan: label per item `_date` tanpa `group_label`:

```python
    lines.extend(["", "🗓️ *Tanggal Belum Penuh*"])
    if report['under_capacity_dates_count']:
        for item in report['under_quota'][:20]:
            tanggal_obj = datetime.strptime(item['tanggal'], '%Y-%m-%d').date()
            hari = HARI_MAP_ID[tanggal_obj.weekday()]
            lines.append(f"- {hari}, {tanggal_obj.day}: {item['current']}/{item['limit']}")
        if report['under_capacity_dates_count'] > 20:
            lines.append(f"- ...dan {report['under_capacity_dates_count'] - 20} tanggal lainnya.")
    else:
        lines.append("- Tidak ada")
```

**Step 4: Template** `monthly_report.html:33` ganti `report.under_quota_dates_count` → `report.under_capacity_dates_count`, dan baris 145 `report.over_quota` tetap (bentuk item sekarang punya `tanggal`, `current`, `limit`; hapus pemakaian `item.group_label` bila ada).

**Step 5: Verifikasi** `.venv/bin/python -m pytest -q` (test `test_monthly_report_includes_canonical_group_labels` tetap PASS karena `per_group` tidak berubah).

**Step 6: Commit** `git commit -am "fix(report): measure full days against per-date capacity"`

### Task 2.4: Escape handle Markdown di semua pesan pengingat

**Objective:** Handle dengan "_" tidak mematikan seluruh pesan.

**Files:** Modify `core/scheduler.py` (baris 79, 232-237, 361-364, 467-471)

**Step 1: Test** (`test_scheduler_markdown.py`)

```python
import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

import config
from core import database as db
from core import scheduler


def _setup(tmp_path, monkeypatch):
    db_path = str(tmp_path / "md.sqlite")
    monkeypatch.setattr(config, "DB_NAME", db_path)
    monkeypatch.setattr(db, "DB_NAME", db_path)
    db.create_tables()
    db.init_default_settings()
    db.set_user_group(1, "Op User", "op_user_x", "INFRA_OPERATION")
    db.buka_bulan_baru(2026, 11)
    return db_path


def test_unfilled_warning_escapes_underscore_in_handle(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    text = scheduler.build_pesan_peringatan_pengisian_jadwal()
    assert text is not None
    unescaped = [i for i, ch in enumerate(text) if ch == "_" and (i == 0 or text[i - 1] != "\\")]
    assert len(unescaped) % 2 == 0, "underscore ganjil bikin Telegram menolak Markdown"
    assert "op\\_user\\_x" in text
```

**Step 2: Jalankan** → FAIL pada assertion escape.

**Step 3: Implementasi** — tambah helper setelah `_escape_markdown_text`:

```python
def _mention_handle(handle):
    """@handle siap-Markdown: '@' plus handle yang di-escape."""
    return '@' + _escape_markdown_text(str(handle).lstrip('@'))
```

Terapkan:
- `_format_user_mention` (baris 233): `return _mention_handle(user['telegram_username'])`
- `format_mention` di `kirim_peringatan_slot_weekend_kosong` (baris 361-364): `return _mention_handle(user['telegram_username'])`
- `kirim_peringatan_h_minus_3` (baris 467-471): `mentions.append(_mention_handle(user['telegram_username']))`
- `kirim_pengingat_harian` (baris 79): `f"[{_escape_markdown_text(p['username'])}](tg://user?id={p['user_id']})"`

**Step 4: Verifikasi** `.venv/bin/python -m pytest test_scheduler_markdown.py -v` → PASS; lalu `-q` seluruh suite.

**Step 5: Commit** `git commit -am "fix(scheduler): escape Telegram handles in Markdown reminders"`

### Task 2.5: `today_wita()` sebagai satu-satunya sumber tanggal

**Files:** Modify `core/database.py` (tambah fungsi), `handlers/user_handlers.py` (baris 280, 293, 312, 381), `handlers/admin_handlers.py` (baris 76, 155, 319), `web/app.py` (baris 132, 231, 319)

**Step 1: Test** (tambahkan ke `test_daily_limit_gate.py`)

```python
def test_today_wita_uses_makassar_date(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    from datetime import datetime
    import pytz
    assert db.today_wita() == datetime.now(pytz.timezone("Asia/Makassar")).date()
```

**Step 2: Sapu sisa pemakaian** — `today_wita()` sudah ada dari Task 1.4b. Ganti `date.today()` dengan `today_wita()` di:
- `handlers/user_handlers.py` (baris 280, 293, 312, 381) bila belum ikut terganti di Wave 1
- `handlers/admin_handlers.py` (baris 76, 155, 319) — tambahkan `today_wita` ke import
- `web/app.py` (baris 132, 231, 319) — import `today_wita` dari `core.database`

**Step 3: Verifikasi** `.venv/bin/python -m pytest -q` → PASS.

**Step 4: Commit** `git commit -am "fix: use Asia/Makassar date for period decisions"`

### Task 2.6: `add_jadwal_manual` atomik

**Objective:** Cek kuota dan insert dalam satu transaksi (dua admin web tidak bisa dobel).

**Files:** Modify `core/database.py:998-1055`

**Step 1: Test** (tambahkan ke `test_daily_limit_gate.py`)

```python
def test_add_jadwal_manual_is_atomic_and_rejects_duplicate(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    assert db.add_jadwal_manual(1, "Op User", "op_user", "2026-11-10") is True
    assert db.add_jadwal_manual(1, "Op User", "op_user", "2026-11-10") is False
    assert len(db.get_jadwal_for_specific_date("2026-11-10")) == 1
```

**Step 2: Implementasi** — ubah badan fungsi menjadi pola `_run_mutation_with_retry`:

```python
def add_jadwal_manual(user_id, username, telegram_username, tanggal):
    """Tambah jadwal manual (web). Weekend bebas; weekday ikut gate kapasitas & balance."""
    is_weekend = datetime.strptime(tanggal, '%Y-%m-%d').date().weekday() in (5, 6)

    def operation(conn):
        cur = conn.cursor()
        cur.execute("SELECT 1 FROM jadwal WHERE user_id = ? AND tanggal = ?", (user_id, tanggal))
        if cur.fetchone():
            return MutationResult(False, 'duplicate')

        if not is_weekend:
            group_name = _get_user_group_with_conn(conn, user_id)
            if not group_name:
                return MutationResult(False, 'invalid_group')
            limit = _get_group_quota_with_conn(conn, group_name)
            current = _get_group_assignment_count_for_date_with_conn(conn, tanggal, group_name, exclude_user_id=user_id)
            if current >= limit:
                return MutationResult(False, 'quota_full')

            target_date = datetime.strptime(tanggal, '%Y-%m-%d').date()
            existing = [row['tanggal'] for row in _get_user_jadwal_for_month_with_conn(conn, user_id, target_date.year, target_date.month)]
            if tanggal not in existing:
                existing.append(tanggal)
            weekend_full = _is_weekend_fallback_active_for_user_with_conn(conn, user_id, target_date.year, target_date.month)
            balance_valid, _ = validate_weekday_weekend_balance(
                existing,
                weekday_limit=_get_weekday_allowance_with_conn(conn, group_name),
                weekend_full=weekend_full,
            )
            if not balance_valid:
                return MutationResult(False, 'weekday_balance')

        cur.execute(
            "INSERT INTO jadwal (user_id, username, telegram_username, tanggal) VALUES (?, ?, ?, ?)",
            (user_id, username, telegram_username, tanggal),
        )
        return MutationResult(True, rows_affected=1)

    return _run_mutation_with_retry(operation).ok
```

**Step 3: Verifikasi** `.venv/bin/python -m pytest -q` — `test_web_weekend_override.py` dan `test_max_hari_balance.py` wajib tetap PASS.

**Step 4: Commit** `git commit -am "fix(db): make manual schedule insert atomic"`

**Wave 2 selesai — STOP.** Laporkan diff ringkas + hasil test, minta approval Wave 3.

---

# WAVE 3 — Keamanan dashboard (finding 6, 12)

**Acceptance wave 3:**
- GET `/login` tidak memuat nama anggota maupun jadwal.
- Tanpa `DEFAULT_ADMIN_PASSWORD`, tidak ada akun admin default yang dibuat.
- Login salah 5x dari IP yang sama ditahan sementara.
- Server default bind 127.0.0.1; secret key stabil antar restart.
- `cookies.txt` keluar dari git; `config.py` masuk git.

### Task 3.1: Halaman login tanpa data jadwal

**Files:** Modify `web/app.py:130-181`, `web/templates/login.html`

**Step 1: Test** (`test_web_login_privacy.py`)

```python
import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

import config
from core import database as db


def _setup(tmp_path, monkeypatch):
    db_path = str(tmp_path / "web.sqlite")
    monkeypatch.setattr(config, "DB_NAME", db_path)
    monkeypatch.setattr(db, "DB_NAME", db_path)
    db.create_tables()
    db.init_default_settings()
    db.set_user_group(777, "Rahasia User", "rahasia_user", "APPS")
    db.add_jadwal_manual(777, "Rahasia User", "rahasia_user", "2026-11-10")


def test_login_page_does_not_expose_schedule(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    from web.app import create_app
    client = create_app().test_client()
    body = client.get("/login").get_data(as_text=True)
    assert "Rahasia User" not in body
    assert "2026-11-10" not in body
```

**Step 2: Jalankan** → FAIL (nama muncul).

**Step 3: Implementasi** — di `web/app.py` route `login`, hapus blok pengambilan jadwal/member/limits (baris 130-171) dan render dengan flash yang benar-benar tampil:

```python
        return render_template('login.html', messages=get_flashed_messages(with_categories=True))
```

Tambahkan `get_flashed_messages` pada import Flask di header. (Sekarang `login.html` membaca variabel `messages` yang tidak pernah dikirim, jadi pesan error login tidak tampil — perbaikan ini sekaligus menutup itu.)

**Step 4: Template** — hapus blok kalender jadwal di `login.html` (sekitar baris 190-310: kartu statistik `jadwal_per_tanggal|length`, grid kalender, daftar nama). Ganti dengan gambar statis yang sudah ada di `web/static/images/landing-ops-command.png`.

**Step 5: Verifikasi** `.venv/bin/python -m pytest test_web_login_privacy.py -v` → PASS.

**Step 6: Commit** `git commit -am "fix(web): stop rendering schedule data on the public login page"`

### Task 3.2: Tidak ada admin default tanpa persetujuan eksplisit

**Files:** Modify `core/database.py:976-992`

**Step 1: Test** (tambahkan ke `test_web_login_privacy.py`)

```python
def test_no_default_admin_without_env(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    monkeypatch.delenv("DEFAULT_ADMIN_PASSWORD", raising=False)
    db.init_default_admin()
    assert db.get_all_admin_users() == []


def test_default_admin_created_from_env(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    monkeypatch.setenv("DEFAULT_ADMIN_PASSWORD", "ganti-sekarang")
    db.init_default_admin()
    admins = db.get_all_admin_users()
    assert [a["username"] for a in admins] == ["admin"]
    assert db.verify_admin("admin", "ganti-sekarang") is not None
```

**Step 2: Implementasi** — pada `init_default_admin`, ganti pembuatan `admin/admin123`:

```python
def init_default_admin():
    """Pastikan ada super admin; hanya buat akun default bila DEFAULT_ADMIN_PASSWORD di-set."""
    with connect_db() as conn:
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM admin_users")
        has_admin = cur.fetchone()[0] > 0

    if not has_admin:
        password = os.environ.get('DEFAULT_ADMIN_PASSWORD')
        if not password:
            print("⚠️  Belum ada admin dashboard. Set DEFAULT_ADMIN_PASSWORD lalu jalankan ulang untuk membuat akun 'admin'.")
            return
        add_admin_user('admin', password, 'super_admin')
        print("🔐 Admin default dibuat dari DEFAULT_ADMIN_PASSWORD.")
        return
    ... (blok pemastian super admin yang sudah ada, tanpa perubahan)
```

**Step 3: Verifikasi** `.venv/bin/python -m pytest test_web_login_privacy.py -v` → PASS. Catat di laporan: DB produksi sudah punya admin, jadi tidak terkunci.

**Step 4: Commit** `git commit -am "fix(web): create default admin only when a password is provided"`

### Task 3.3: Rate limit login

**Files:** Modify `web/app.py` (route `login`)

**Step 1: Test**

```python
def test_login_rate_limited_after_five_failures(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    monkeypatch.setenv("DEFAULT_ADMIN_PASSWORD", "benar-sekali")
    db.init_default_admin()
    from web.app import create_app
    app = create_app()
    client = app.test_client()
    for _ in range(5):
        client.post("/login", data={"username": "admin", "password": "salah"})
    body = client.post("/login", data={"username": "admin", "password": "benar-sekali"}).get_data(as_text=True)
    assert "Terlalu banyak percobaan" in body
```

**Step 2: Implementasi** — modul-level di `web/app.py`:

```python
LOGIN_ATTEMPTS = {}          # ip -> (count, first_attempt_ts)
LOGIN_WINDOW_SECONDS = 300
LOGIN_MAX_ATTEMPTS = 5


def _login_blocked(ip):
    entry = LOGIN_ATTEMPTS.get(ip)
    if not entry:
        return False
    count, first_ts = entry
    if time.time() - first_ts > LOGIN_WINDOW_SECONDS:
        LOGIN_ATTEMPTS.pop(ip, None)
        return False
    return count >= LOGIN_MAX_ATTEMPTS
```

Di route `login` POST, sebelum `verify_admin`:

```python
        ip = request.remote_addr or 'unknown'
        if _login_blocked(ip):
            flash('Terlalu banyak percobaan login. Coba lagi dalam 5 menit.', 'error')
            return render_template('login.html', messages=get_flashed_messages(with_categories=True)), 429
        admin = verify_admin(username, password)
        if admin:
            LOGIN_ATTEMPTS.pop(ip, None)
            # sisa cabang sukses tidak berubah: login_user, add_audit_log, flash, redirect
        else:
            count, first_ts = LOGIN_ATTEMPTS.get(ip, (0, time.time()))
            LOGIN_ATTEMPTS[ip] = (count + 1, first_ts)
```

Tambah `import time` di header `web/app.py`. Di test, kosongkan `web.app.LOGIN_ATTEMPTS` lebih dulu agar tidak tercemar test lain:

```python
    from web import app as web_app
    web_app.LOGIN_ATTEMPTS.clear()
```

**Step 3: Verifikasi** `.venv/bin/python -m pytest test_web_login_privacy.py -v` → PASS.

**Step 4: Commit** `git commit -am "feat(web): throttle repeated failed logins"`

### Task 3.4: Host dan secret key dari konfigurasi

**Files:** Modify `config.py`, `main.py:305-310`, `web/app.py:41`

**Step 1: `config.py`**

```python
WEB_HOST = os.environ.get('WEB_HOST', '127.0.0.1')
WEB_PORT = int(os.environ.get('WEB_PORT', '5050'))
SECRET_KEY = os.environ.get('SECRET_KEY', '')
```

**Step 2: `main.py`**

```python
    server = make_server(WEB_HOST, WEB_PORT, app, threaded=True)
```

dan log memakai `f"🌐 Web Dashboard running at http://{WEB_HOST}:{WEB_PORT}"`.

**Step 3: `web/app.py`**

```python
    app.secret_key = _load_secret_key()
```

dengan helper di modul:

```python
def _load_secret_key():
    """SECRET_KEY stabil: env, atau file data/.secret_key yang dibuat sekali."""
    if SECRET_KEY:
        return SECRET_KEY
    path = os.path.join(os.path.dirname(DB_NAME), '.secret_key')
    if os.path.exists(path):
        return open(path, 'rb').read()
    key = os.urandom(24)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'wb') as handle:
        handle.write(key)
    os.chmod(path, 0o600)
    return key
```

Import `SECRET_KEY`, `WEB_HOST`, `WEB_PORT`, `DB_NAME` dari config.

**Step 4: Verifikasi**

```bash
.venv/bin/python -c "import config; print(config.WEB_HOST)"
.venv/bin/python -m pytest -q
```

Expected: `127.0.0.1`, semua PASS.

**Step 5: Commit** `git commit -am "feat(web): bind localhost by default and persist the session secret"`

### Task 3.5: Hygiene repo (cookies.txt, config.py)

**Files:** `cookies.txt`, `.gitignore`

**Step 1:** `git rm --cached cookies.txt && rm cookies.txt`

**Step 2:** Hapus baris `config.py` dari `.gitignore`, lalu `git add config.py`.

**Step 3:** Pastikan tidak ada nilai rahasia di `config.py` (hanya `os.environ.get`). Bila ada, pindahkan ke `.env` lebih dulu.

**Step 4: Verifikasi**

```bash
git ls-files | grep -c cookies.txt   # expected: 0
git ls-files --error-unmatch config.py   # expected: config.py
.venv/bin/python -m pytest -q
```

**Step 5: Commit** `git commit -m "chore: drop tracked cookie file and version config.py"`

**Wave 3 selesai — STOP.** Laporkan, minta approval Wave 4.

---

# WAVE 4 — Cleanup & dokumentasi (finding 13, 14, 15, 16, 17)

### Task 4.1: Hapus kode mati

**Files:** `core/scheduler.py:159-226`, `core/database.py:741-746`, `core/database.py:918-924`

**Step 1:** Hapus `kirim_peringatan_jadwal_mingguan`, `init_default_settings`, `get_admin_by_id` (verifikasi dulu: `grep -rn "kirim_peringatan_jadwal_mingguan\|init_default_settings\|get_admin_by_id" --include=*.py .` harus kosong selain definisi + file test yang memakainya).

**Step 2:** `.venv/bin/python -m py_compile core/*.py && .venv/bin/python -m pytest -q` → PASS.

**Step 3: Commit** `git commit -am "chore: remove unreferenced scheduler and database helpers"`

### Task 4.2: Arsipkan script sekali-pakai

**Files:** `fix_jadwal_usernames.py`, `update_jadwal_usernames.py`, `demo_locking.py`, `demo_bulk_limits.py`, `migrate_monitoring.py`, `.worktrees/`

**Step 1:** Untuk `.worktrees/infra-division-split`: **jangan hapus** tanpa izin user — cukup catat di laporan akhir (worktree terdaftar di `git worktree list`).

**Step 2:** Pindahkan 5 script ke `scripts/archive/` (bukan delete, agar jejak migrasi lama tidak hilang):

```bash
mkdir -p scripts/archive
git mv fix_jadwal_usernames.py update_jadwal_usernames.py demo_locking.py demo_bulk_limits.py migrate_monitoring.py scripts/archive/
```

**Step 3:** Sesuaikan `sys.path` / import di script tersebut bila perlu (`sys.path.insert(0, ROOT)`), atau biarkan dan beri catatan di `scripts/archive/README.md` bahwa script arsip dijalankan dari root repo.

**Step 4: Commit** `git commit -m "chore: archive one-off migration and demo scripts"`

### Task 4.3: Typo emoji hari Rabu

**Files:** `handlers/admin_handlers.py:25`

**Step 1:** Ganti `'Rab':'📗'` → `'Rabu':'📗'`.

**Step 2:** `.venv/bin/python -m pytest -q` → PASS. **Commit** `git commit -am "fix(admin): restore Wednesday emoji in statistics"`

### Task 4.4: Google Sheets tidak memblokir simpan & absensi punya user_id

**Files:** `handlers/user_handlers.py` (baris 660-672), `core/database.py:619-637`, `web/app.py:796-807`

**Step 1:** Bungkus sync di handler dengan try/except agar kegagalan Sheets tidak menghapus konfirmasi:

```python
                    try:
                        for tanggal in pilihan_final:
                            sync_jadwal_to_sheets(
                                tanggal=tanggal,
                                hari=get_hari_from_date(tanggal),
                                username=call.from_user.username or call.from_user.first_name,
                                group=user_group or 'UNKNOWN',
                            )
                    except Exception as exc:
                        print(f"Sinkronisasi Sheets dilewati: {exc}")
```

Lakukan hal sama untuk blok `sync_absensi_to_sheets`.

**Step 2:** `get_all_absensi_in_range` tambahkan `a.user_id` pada SELECT dan dict hasil; `web/app.py` memakai `a['user_id']` alih-alih `0`.

**Step 3:** `.venv/bin/python -m pytest -q` → PASS. **Commit** `git commit -am "fix(sheets): never block schedule save, keep user_id in absensi export"`

### Task 4.5: Throttle blast DM buka jadwal

**Files:** `handlers/admin_handlers.py:54-62`

**Step 1:**

```python
        for user in get_all_registered_users():
            try:
                bot.send_message(user['user_id'], pesan, parse_mode='Markdown')
                success_count += 1
            except Exception as exc:
                if '429' in str(exc):
                    time.sleep(1)
                    try:
                        bot.send_message(user['user_id'], pesan, parse_mode='Markdown')
                        success_count += 1
                        continue
                    except Exception:
                        pass
                username = user.get('telegram_username') or str(user['user_id'])
                failed_users.append(username)
            time.sleep(0.05)
```

Tambah `import time` di header.

**Step 2:** `test_admin_blast.py` tetap PASS (FakeBot raise RuntimeError, bukan 429).

**Step 3: Commit** `git commit -am "fix(admin): throttle opening-period DM blast"`

### Task 4.6: Satu sumber batas bulanan

**Files:** `handlers/user_handlers.py` (baris 174-183, 623-634), `core/database.py`

**Step 1:** Tambah di `core/database.py`:

```python
def get_monthly_cap_for_group(group_name):
    """Batas jumlah tanggal per bulan untuk satu divisi (sama dengan gate simpan)."""
    canonical = normalize_group_name(group_name)
    with connect_db() as conn:
        return 1 if canonical == 'INFRA_DELIVERY' else _get_monthly_limit_with_conn(conn, canonical)
```

Gunakan `_get_monthly_limit_with_conn` langsung di dalam `with connect_db()` agar tidak perlu helper tambahan.

**Step 2:** Ganti blok `max_hari_keys` di handler toggle (baris 623-634) dengan:

```python
                    max_hari = db.get_monthly_cap_for_group(user_group)
                    pilihan_bulan_ini = {s for s in selections if datetime.strptime(s, '%Y-%m-%d').month == dt_obj_toggle.month and datetime.strptime(s, '%Y-%m-%d').year == dt_obj_toggle.year}
                    if len(pilihan_bulan_ini) >= max_hari:
                        bot.answer_callback_query(call.id, f"❌ Kuota maksimal {max_hari} hari/bulan untuk tim Anda telah tercapai.", show_alert=True)
                        return
```

Hapus dict `max_hari_keys` (tidak dipakai lagi; pastikan `get_setting` masih dipakai di tempat lain sebelum menghapus import).

**Step 3:** `.venv/bin/python -m pytest -q` → PASS. **Commit** `git commit -am "refactor(bot): single source for monthly day cap"`

### Task 4.7: Dokumentasi

**Files:** `DAILY_LIMITS_README.md`, `README` tambahan (buat `README.md` bila belum ada)

**Step 1:** `DAILY_LIMITS_README.md` — ubah klaim menjadi aturan nyata: "Batasan Harian = kapasitas slot per tanggal; default 1 orang. Pengaturan ini dipakai bot, web, dan laporan."

**Step 2:** Tambah bagian "Menjalankan" di `README.md`: venv + `requirements.txt`, isi `.env`, `python main.py`, dashboard di `WEB_HOST:WEB_PORT` (default 127.0.0.1:5050), `DEFAULT_ADMIN_PASSWORD` untuk akun admin pertama.

**Step 3: Commit** `git commit -am "docs: document capacity rule and local run steps"`

---

# Verifikasi Akhir (setelah semua wave disetujui)

**Step 1: Suite penuh**

```bash
.venv/bin/python -m pytest -q
.venv/bin/python -m py_compile main.py config.py core/*.py handlers/*.py web/*.py && echo "compile OK"
```

Expected: seluruh test PASS (>= 57), `compile OK`.

**Step 2: Reproduksi ulang 3 bug lama** dengan salinan DB baru + skrip harness Wave 1 (test `test_user_flow_gating.py` sudah mewakili; jalankan ulang dan tempel output).

**Step 3: Review akhir**

- `git log --oneline main..HEAD` — tidak ada commit di luar scope.
- `git diff main...HEAD --stat` — tidak ada file tak terduga.
- Review spec-compliance + code-quality per wave (delegate_task reviewer atau `requesting-code-review`).

**Step 4: Uji Telegram nyata (opsional, hanya dengan izin user)**

Jalankan bot dengan DB salinan (`DB_NAME=data/jadwal_test.db`), buka 2 bulan, ulangi skenario: /start bulan ke-2, simpan, /jadwal_saya, /batal_jadwal, /cuti. Laporkan hasil nyata.

**Step 5: Laporan penutup**

- Apa yang terverifikasi (command + output nyata).
- Apa yang belum / tidak bisa diverifikasi (Sheets tanpa kredensial, Telegram nyata bila tidak dijalankan).
- Opsi: merge ke main, buka PR, atau simpan branch.

---

## Risiko yang Harus Diingat

1. **Wave 2 mengubah aturan inti.** Setelah `date_is_taken` dipakai, admin yang set Batasan Harian > 1 membuka kemungkinan 2+ orang di satu tanggal yang sebelumnya ditolak. Ini keputusan user (dipilih di clarify 2026-11-07) — pastikan disosialisasikan sebelum deploy.
2. **Wave 3 mengunci super admin.** Bila deploy ke DB baru tanpa `DEFAULT_ADMIN_PASSWORD`, dashboard tidak bisa dipakai sampai env di-set. DB produksi sekarang sudah punya admin, jadi aman, tapi urutan deploy harus benar.
3. **Template login.html** menyimpan blok kalender yang cukup besar; hapus hati-hati agar tombol login & form tidak ikut terhapus (jalankan `client.get('/login')` dan cek form ada di body).
4. **Jangan menjalankan bot dengan DB produksi saat eksperimen.** Selalu `DB_NAME` salinan.
