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


def test_nav_to_other_month_does_not_mix_selections(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    db.buka_bulan_baru(2026, 11)
    db.buka_bulan_baru(2026, 12)
    bot = _register()

    bot.handlers["start"](message(500, "/start"))
    picker = button_data(bot.sent[-1]["markup"])
    pick_nov = [data for _, data in picker if data and data.endswith("_2026_11")][0]
    bot.fire(pick_nov, 500)

    november = _calendar_dates(bot.sent[-1]["markup"], "jadwal_toggle_2026-11-")
    bot.fire(november[9], 500)                    # 10 Nov
    bot.fire("jadwal_nav_2026_12", 500)
    december = _calendar_dates(bot.edits[-1], "jadwal_toggle_2026-12-")
    bot.fire(december[0], 500)                    # 1 Des
    bot.fire("jadwal_save_2026_12", 500)

    assert [row["tanggal"] for row in db.get_user_jadwal_for_month(500, 2026, 12)] == ["2026-12-01"]
    assert not any("di luar bulan target" in (text or "") for text in bot.answers)


# ---------------------------------------------------------------------------
# Perintah non-/start memakai bulan yang dipilih
# ---------------------------------------------------------------------------


def test_jadwal_saya_uses_chosen_open_month(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    db.buka_bulan_baru(2026, 11)
    db.buka_bulan_baru(2026, 12)
    assert db.add_jadwal_manual(500, "Apps User", "apps_user", "2026-12-05")
    bot = _register()

    bot.handlers["jadwal_saya"](message(500, "/jadwal_saya"))
    pick = [data for _, data in button_data(bot.sent[-1]["markup"]) if data and data.startswith("pick_jadwal_saya_2026_12")]
    assert pick, "harus ada tombol Desember 2026"
    bot.fire(pick[0], 500)

    assert any("5 Desember 2026" in sent["text"] for sent in bot.sent)


def test_batal_jadwal_uses_chosen_open_month(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    db.buka_bulan_baru(2026, 11)
    db.buka_bulan_baru(2026, 12)
    assert db.add_jadwal_manual(500, "Apps User", "apps_user", "2026-12-05")
    bot = _register()

    bot.handlers["batal_jadwal"](message(500, "/batal_jadwal"))
    pick = [data for _, data in button_data(bot.sent[-1]["markup"]) if data and data.startswith("pick_batal_jadwal_2026_12")]
    bot.fire(pick[0], 500)

    cancel_dates = _calendar_dates(bot.sent[-1]["markup"], "batal_jadwal_toggle_2026-12-")
    assert cancel_dates == ["batal_jadwal_toggle_2026-12-05"]
    bot.fire(cancel_dates[0], 500)
    bot.fire("batal_jadwal_save_2026_12", 500)
    assert db.get_user_jadwal_for_month(500, 2026, 12) == []


def test_cuti_opens_active_period_month_not_today(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    db.buka_bulan_baru(2026, 12)
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
    pick = [data for _, data in button_data(bot.sent[-1]["markup"]) if data and data.startswith("pick_lihat_cuti_2026_12")]
    assert pick, "harus ada tombol Desember 2026"
    bot.fire(pick[0], 500)

    assert any("20 Desember 2026" in sent["text"] for sent in bot.sent)


def test_tukar_jadwal_uses_chosen_open_month(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    db.buka_bulan_baru(2026, 11)
    db.buka_bulan_baru(2026, 12)
    assert db.add_jadwal_manual(500, "Apps User", "apps_user", "2026-12-05")
    bot = FakeBot()
    user_handlers.register_user_handlers(bot)
    from handlers import swap_handler
    swap_handler.register_swap_handlers(bot)
    swap_handler.swap_data.clear()

    bot.handlers["tukar_jadwal"](message(500, "/tukar_jadwal"))
    pick = [data for _, data in button_data(bot.sent[-1]["markup"]) if data and data.startswith("pick_tukar_2026_12")]
    assert pick, "harus ada tombol Desember 2026"
    bot.fire(pick[0], 500)

    swap_dates = _calendar_dates(bot.sent[-1]["markup"], "swap_selectA_2026-12-")
    assert swap_dates == ["swap_selectA_2026-12-05"]


def test_save_confirmation_survives_sheets_failure(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    db.buka_bulan_baru(2026, 11)
    bot = _register()

    def boom(**kwargs):
        raise RuntimeError("sheets down")

    monkeypatch.setattr(user_handlers, "sync_jadwal_to_sheets", boom)

    bot.handlers["start"](message(500, "/start"))
    weekday = _calendar_dates(bot.sent[-1]["markup"], "jadwal_toggle_2026-11-")[0]
    bot.fire(weekday, 500)
    bot.fire("jadwal_save_2026_11", 500)

    saved = [row["tanggal"] for row in db.get_user_jadwal_for_month(500, 2026, 11)]
    assert saved == [weekday.replace("jadwal_toggle_", "")]
    assert any("telah disimpan" in (sent["text"] or "") for sent in bot.sent)
