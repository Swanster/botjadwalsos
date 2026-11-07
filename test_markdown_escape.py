"""Prioritas 2 audit: nama pengguna tidak boleh menyuntik Markdown/link ke pesan bot.

Nama Telegram bisa diubah anggota menjadi `[Promo](https://jahat.example)`. Bot
mem-post nama itu ke grup dengan parse_mode='Markdown', jadi tanpa escape tautan
tersebut tampil sebagai link aktif yang dikirim oleh bot sendiri.
"""
import os
import re
import sys

import pytest

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

import config
from core import database as db
from core.schedule_recap import generate_rekap_text
from core.telegram_text import escape_markdown
from fake_telebot import FakeBot, message
from handlers import user_handlers

EVIL_NAME = "[Promo](https://jahat.example)"
MEMBER = 500


@pytest.fixture(autouse=True)
def _setup(tmp_path, monkeypatch):
    db_path = str(tmp_path / "markdown.sqlite")
    monkeypatch.setattr(config, "DB_NAME", db_path)
    monkeypatch.setattr(db, "DB_NAME", db_path)
    monkeypatch.setattr(user_handlers, "ALLOWED_TOPIC_ID", None)
    monkeypatch.setattr(config, "ADMIN_ID", 111222333)

    db.create_tables()
    db.set_user_group(MEMBER, EVIL_NAME, "evil_tg", "APPS")
    db.buka_bulan_baru(2026, 11)
    db.add_jadwal_manual(MEMBER, EVIL_NAME, "evil_tg", "2026-11-10")
    user_handlers.user_selections.clear()
    yield


# ---------------------------------------------------------------------------
# Unit: helper escape
# ---------------------------------------------------------------------------

def _has_unescaped_link(text):
    """True kalau ada penutup link Markdown yang tidak di-escape ke target non-Telegram.

    Link mention internal `](tg://user?id=...)` memang disengaja, jadi dikecualikan.
    """
    return re.search(r'(?<!\\)\]\((?!tg://)', text) is not None


def test_escape_markdown_neutralizes_link():
    escaped = escape_markdown(EVIL_NAME)

    assert not _has_unescaped_link(escaped), "kurung siku harus ter-escape supaya tidak jadi link"
    assert "\\[Promo\\]" in escaped


def test_escape_markdown_handles_none_and_plain():
    assert escape_markdown(None) == ""
    assert escape_markdown("Budi Santoso") == "Budi Santoso"


def test_escape_markdown_escapes_backslash_first():
    assert escape_markdown("a\\_b") == "a\\\\\\_b"


# ---------------------------------------------------------------------------
# End-to-end: pesan bot ke grup
# ---------------------------------------------------------------------------

def test_rekap_message_has_no_active_link():
    text = generate_rekap_text(2026, 11)

    assert not _has_unescaped_link(text)
    assert "\\[Promo\\]" in text


def test_cuti_list_has_no_active_link():
    db.set_user_absensi(MEMBER, ["2026-11-11"], 2026, 11)
    bot = FakeBot()
    user_handlers.register_user_handlers(bot)

    bot.handlers["lihat_cuti"](message(MEMBER, "/lihat_cuti"))
    bot.fire("pick_lihat_cuti_2026_11", MEMBER, chat_id=-100)

    assert bot.sent, "daftar cuti harus terkirim"
    teks = bot.sent[-1]["text"]
    assert not _has_unescaped_link(teks)
    assert "\\[Promo\\]" in teks


def test_admin_statistik_has_no_active_link(monkeypatch):
    from handlers import admin_handlers

    monkeypatch.setattr(admin_handlers, "ADMIN_ID", 111222333)
    bot = FakeBot()
    admin_handlers.register_admin_handlers(bot)

    bot.handlers["statistik"](message(111222333, "/statistik", chat_id=111222333, chat_type="private"))
    bot.fire("stats_2026_11", 111222333, chat_id=111222333, chat_type="private")

    assert bot.sent, "statistik harus terkirim"
    teks = bot.sent[-1]["text"]
    assert not _has_unescaped_link(teks)
    assert "\\[Promo\\]" in teks


def test_daily_reminder_has_no_active_link(monkeypatch):
    from core import scheduler

    monkeypatch.setattr(scheduler.time, "sleep", lambda *_: None)  # jangan tunggu retry 30 detik
    today = db.today_wita()
    tanggal = today.strftime("%Y-%m-%d")
    db.add_jadwal_manual(MEMBER, EVIL_NAME, "evil_tg", tanggal)
    db.set_user_absensi(MEMBER, [tanggal], today.year, today.month)

    bot = FakeBot()
    scheduler.kirim_pengingat_harian(bot)

    teks = bot.sent[-1]["text"]
    assert EVIL_NAME not in teks, "nama mentah tidak boleh muncul di reminder"
    assert not _has_unescaped_link(teks)


def test_monthly_report_has_no_active_link():
    from core.monthly_report import build_monthly_report, format_monthly_report_for_telegram

    teks = format_monthly_report_for_telegram(build_monthly_report(2026, 11))

    assert not _has_unescaped_link(teks)
    assert "\\[Promo\\]" in teks
