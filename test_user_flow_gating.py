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
    if markup is None or isinstance(markup, str):
        return []
    return [data for _, data in button_data(markup) if data and data.startswith(prefix)]


# ---------------------------------------------------------------------------
# Gate periode terbuka
# ---------------------------------------------------------------------------


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


def test_closed_period_offers_no_calendar(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    db.buka_bulan_baru(2026, 11)
    db.tutup_bulan_aktif(2026, 11)
    bot = _register()

    bot.handlers["start"](message(500, "/start"))

    assert bot.sent[-1]["markup"] is None
    assert not db.get_user_jadwal_for_month(500, 2026, 11)
