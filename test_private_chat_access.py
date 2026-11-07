"""Regression: chat pribadi bot hanya untuk admin (config.ADMIN_ID).

Bug yang dikunci (audit keamanan 2026-11-07): is_allowed() mengembalikan True
untuk SEMUA chat pribadi, dan jalur baca (/lihat_jadwal, /lihat_cuti, callback
view_rekap) tidak pernah mengecek registrasi. Akibatnya pengguna Telegram mana pun
yang menemukan bot bisa membaca roster dan daftar cuti seluruh tim lewat DM.
"""
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

import config
from core import database as db
from handlers import access, swap_handler, user_handlers
from fake_telebot import FakeBot, message

ADMIN = 111222333
MEMBER = 500
OTHER = 999999  # tidak terdaftar di user_groups


@pytest.fixture(autouse=True)
def _setup(tmp_path, monkeypatch):
    db_path = str(tmp_path / "private_chat.sqlite")
    monkeypatch.setattr(config, "DB_NAME", db_path)
    monkeypatch.setattr(db, "DB_NAME", db_path)
    monkeypatch.setattr(config, "ADMIN_ID", ADMIN)
    monkeypatch.setattr(user_handlers, "ALLOWED_TOPIC_ID", None)
    monkeypatch.setattr(user_handlers, "sync_jadwal_to_sheets", lambda **kwargs: None)
    monkeypatch.setattr(user_handlers, "sync_absensi_to_sheets", lambda **kwargs: None)

    db.create_tables()
    db.set_user_group(MEMBER, "Apps User", "apps_user", "APPS")
    db.buka_bulan_baru(2026, 11)
    db.add_jadwal_manual(MEMBER, "Apps User", "apps_user", "2026-11-10")

    user_handlers.user_selections.clear()
    yield


def _register():
    bot = FakeBot()
    user_handlers.register_user_handlers(bot)
    swap_handler.register_swap_handlers(bot)
    return bot


def _private(user_id, text, command):
    return message(user_id, text, chat_id=user_id, chat_type="private"), command


# ---------------------------------------------------------------------------
# Perintah lewat chat pribadi: hanya admin
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("command", ["menu", "start", "lihat_jadwal", "lihat_cuti", "jadwal_saya"])
def test_private_command_ignored_for_non_admin(command):
    bot = _register()
    msg, cmd = _private(MEMBER, f"/{command}", command)

    bot.handlers[cmd](msg)

    assert bot.sent == [], f"/{command} dari chat pribadi non-admin tidak boleh memicu balasan"
    assert bot.replies == []


def test_private_command_ignored_for_unregistered_stranger():
    bot = _register()
    msg, cmd = _private(OTHER, "/lihat_jadwal", "lihat_jadwal")

    bot.handlers[cmd](msg)

    assert bot.sent == []


def test_private_read_command_works_for_admin():
    bot = _register()
    msg, cmd = _private(ADMIN, "/lihat_jadwal", "lihat_jadwal")

    bot.handlers[cmd](msg)

    assert len(bot.sent) == 1, "admin harus tetap bisa memakai chat pribadi"


def test_private_swap_command_ignored_for_member():
    bot = _register()
    msg, cmd = _private(MEMBER, "/tukar_jadwal", "tukar_jadwal")

    bot.handlers[cmd](msg)

    assert bot.sent == []


# ---------------------------------------------------------------------------
# Grup/topik tetap terbuka untuk anggota
# ---------------------------------------------------------------------------

def test_group_command_still_works_for_member():
    bot = _register()

    bot.handlers["lihat_jadwal"](message(MEMBER, "/lihat_jadwal"))

    assert len(bot.sent) == 1, "chat grup tidak boleh ikut terkunci"


def test_group_swap_command_still_works_for_member():
    bot = _register()

    bot.handlers["tukar_jadwal"](message(MEMBER, "/tukar_jadwal"))

    assert len(bot.sent) == 1


# ---------------------------------------------------------------------------
# Callback (tombol lama / client kustom) juga ditolak di chat pribadi non-admin
# ---------------------------------------------------------------------------

def test_private_view_callback_denied_for_member():
    bot = _register()
    db.set_user_group(MEMBER, "Apps User", "apps_user", "APPS")

    handled = bot.fire("view_rekap_2026_11", MEMBER, chat_id=MEMBER, chat_type="private")

    assert handled is True
    assert bot.edits == [] and bot.sent == []
    assert bot.answers[-1] == access.DENIED_PRIVATE_TEXT


def test_private_view_callback_allowed_for_admin():
    bot = _register()

    bot.fire("view_rekap_2026_11", ADMIN, chat_id=ADMIN, chat_type="private")

    assert bot.edits, "admin harus mendapat rekap di chat pribadi"


def test_private_swap_callback_denied_for_member():
    bot = _register()

    bot.fire("swap_selectA_2026-11-10", MEMBER, chat_id=MEMBER, chat_type="private")

    assert bot.sent == [] and bot.edits == []
    assert bot.answers[-1] == access.DENIED_PRIVATE_TEXT


def test_group_callback_still_works_for_member():
    bot = _register()

    bot.fire("view_rekap_2026_11", MEMBER, chat_id=-100, chat_type="supergroup")

    assert bot.edits, "callback dari grup tidak boleh ikut terkunci"
