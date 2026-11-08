"""Test agen ringan untuk isi jadwal via teks."""
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

import config
from core import database as db
from handlers import user_handlers, agent_handler
from fake_telebot import FakeBot, message
import core.schedule_agent as schedule_agent


def _setup(tmp_path, monkeypatch):
    db_path = str(tmp_path / "agent.sqlite")
    monkeypatch.setattr(config, "DB_NAME", db_path)
    monkeypatch.setattr(db, "DB_NAME", db_path)
    db.create_tables()
    db.buka_bulan_baru(2026, 11)
    db.set_user_group(500, "Apps User", "apps_user", "APPS")
    user_handlers.sync_jadwal_to_sheets = lambda **kwargs: None
    user_handlers.sync_absensi_to_sheets = lambda **kwargs: None
    user_handlers.user_selections.clear()
    user_handlers.user_cuti_selections.clear()
    user_handlers.user_batal_selections.clear()
    user_handlers.user_batal_cuti_selections.clear()
    schedule_agent._pending_fills.clear()
    return db_path


def test_help_question_is_detected():
    assert schedule_agent.is_help_question("bagaimana cara kerja mengisi jadwal?")


def test_fill_request_is_detected():
    assert schedule_agent.is_fill_request("tolong input jadwal saya tanggal 4, 5, dan 10")


def test_build_fill_plan_skips_existing_dates(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    db.add_jadwal_manual(500, "Apps User", "apps_user", "2026-11-05")

    plan = schedule_agent.build_fill_plan(
        "tolong input jadwal saya tanggal 4, 5, dan 10", 500, "Apps User", "apps_user"
    )

    assert isinstance(plan, dict)
    assert plan["available_new"] == ["2026-11-04", "2026-11-10"]
    assert plan["skipped"] == ["2026-11-05"]


def test_build_fill_plan_rejects_monthly_cap(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    # APPS default cap besar; paksa kecil lewat monkeypatch settings
    monkeypatch.setattr(db, "get_monthly_cap_for_group", lambda group: 1)
    db.add_jadwal_manual(500, "Apps User", "apps_user", "2026-11-01")

    result = schedule_agent.build_fill_plan(
        "tolong input jadwal saya tanggal 4, 5, dan 10", 500, "Apps User", "apps_user"
    )

    assert isinstance(result, str)
    assert "batas bulanan" in result.lower()


def test_handle_tanya_fill_flow_saves_after_confirmation(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    bot = FakeBot()
    user_handlers.register_user_handlers(bot)
    agent_handler.register_agent_handlers(bot)

    bot.handlers["tanya"](message(500, "/tanya tolong input jadwal saya tanggal 4, 5, dan 10"))
    assert "Rencana isi jadwal" in bot.sent[-1]["text"]

    assert bot.fire("agent_fill_confirm", 500)
    assert any("berhasil disimpan" in str(item).lower() for item in bot.edits + [m["text"] for m in bot.sent])

    rows = [r["tanggal"] for r in db.get_user_jadwal_for_month(500, 2026, 11)]
    assert rows == ["2026-11-04", "2026-11-05", "2026-11-10"]


def test_handle_tanya_help_returns_guide(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    bot = FakeBot()
    user_handlers.register_user_handlers(bot)

    bot.handlers["tanya"](message(500, "/tanya bagaimana cara kerja mengisi jadwal?"))

    assert "Panduan Cepat" in bot.sent[-1]["text"]


def test_build_fill_plan_replace_does_not_keep_old_dates(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    db.add_jadwal_manual(500, "Apps User", "apps_user", "2026-11-02")

    plan = schedule_agent.build_fill_plan(
        "ganti jadwal saya tanggal 4, 5", 500, "Apps User", "apps_user", "replace"
    )

    assert isinstance(plan, dict)
    assert plan["mode"] == "replace"
    assert plan["available_new"] == ["2026-11-04", "2026-11-05"]
    assert plan["skipped"] == []


def test_build_fill_plan_parses_slash_date(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)

    plan = schedule_agent.build_fill_plan(
        "tambah jadwal saya 4/11/2026", 500, "Apps User", "apps_user", "add"
    )

    assert isinstance(plan, dict)
    assert plan["year"] == 2026
    assert plan["month"] == 11
    assert plan["available_new"] == ["2026-11-04"]


def test_get_pending_expires(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    plan = schedule_agent.build_fill_plan(
        "tambah jadwal saya tanggal 4", 500, "Apps User", "apps_user", "add"
    )
    schedule_agent.store_pending(500, plan)
    schedule_agent._pending_fills[500]["created_at"] = 0

    assert schedule_agent.get_pending(500) is None


def test_handle_tambah_command_adds_after_confirmation(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    bot = FakeBot()
    user_handlers.register_user_handlers(bot)
    agent_handler.register_agent_handlers(bot)

    bot.handlers["tambah_jadwal"](message(500, "/tambah_jadwal 4, 5"))
    assert "Rencana isi jadwal" in bot.sent[-1]["text"]

    assert bot.fire("agent_fill_confirm", 500)
    rows = [r["tanggal"] for r in db.get_user_jadwal_for_month(500, 2026, 11)]
    assert rows == ["2026-11-04", "2026-11-05"]


def test_handle_ganti_command_replaces_after_confirmation(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    db.add_jadwal_manual(500, "Apps User", "apps_user", "2026-11-02")
    bot = FakeBot()
    user_handlers.register_user_handlers(bot)
    agent_handler.register_agent_handlers(bot)

    bot.handlers["ganti_jadwal"](message(500, "/ganti_jadwal 10"))
    assert "Rencana ganti jadwal" in bot.sent[-1]["text"]

    assert bot.fire("agent_fill_confirm", 500)
    rows = [r["tanggal"] for r in db.get_user_jadwal_for_month(500, 2026, 11)]
    assert rows == ["2026-11-10"]


def test_menu_contains_new_fill_buttons(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    bot = FakeBot()
    user_handlers.register_user_handlers(bot)

    bot.handlers["menu"](message(500, "/menu"))
    labels = [label for label, _ in __import__("fake_telebot").button_data(bot.sent[-1]["markup"])]
    assert "Tambah Jadwal" in labels
    assert "Ganti Jadwal" in labels
