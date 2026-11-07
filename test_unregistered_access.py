"""User grup yang belum terdaftar harus dapat penjelasan, bukan menu jadwal."""
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

import config
from core import database as db
from handlers import access, user_handlers
from fake_telebot import FakeBot, message

MEMBER = 500
OTHER = 999999  # tidak ada di user_groups


@pytest.fixture(autouse=True)
def _setup(tmp_path, monkeypatch):
    db_path = str(tmp_path / "unregistered.sqlite")
    monkeypatch.setattr(config, "DB_NAME", db_path)
    monkeypatch.setattr(db, "DB_NAME", db_path)
    monkeypatch.setattr(user_handlers, "ALLOWED_TOPIC_ID", None)

    db.create_tables()
    db.set_user_group(MEMBER, "Apps User", "apps_user", "APPS")
    db.buka_bulan_baru(2026, 11)
    db.add_jadwal_manual(MEMBER, "Apps User", "apps_user", "2026-11-10")
    yield


def _bot():
    bot = FakeBot()
    user_handlers.register_user_handlers(bot)
    return bot


def test_lihat_jadwal_menjelaskan_user_belum_terdaftar():
    bot = _bot()

    bot.handlers["lihat_jadwal"](message(OTHER, "/lihat_jadwal"))

    assert len(bot.sent) == 1
    assert bot.sent[0]["text"] == access.UNREGISTERED_TEXT
    assert "/lihat_jadwal" in bot.sent[0]["text"]


def test_lihat_jadwal_tetap_jalan_untuk_user_terdaftar():
    bot = _bot()

    bot.handlers["lihat_jadwal"](message(MEMBER, "/lihat_jadwal"))

    assert len(bot.sent) == 1
    assert bot.sent[0]["text"] != access.UNREGISTERED_TEXT


def test_tanya_user_belum_terdaftar_tidak_memanggil_llm(monkeypatch):
    from core import ai_query

    monkeypatch.setattr(
        ai_query, "_post_chat",
        lambda payload: (_ for _ in ()).throw(AssertionError("LLM tidak boleh dipanggil")),
    )
    bot = _bot()

    bot.handlers["tanya"](message(OTHER, "/tanya siapa yang SOS besok?"))

    assert bot.sent[0]["text"] == access.UNREGISTERED_TEXT


def test_callback_rekap_user_belum_terdaftar_ditolak():
    bot = _bot()

    handled = bot.fire("view_rekap_2026_11", OTHER, chat_type="supergroup")

    assert handled is True
    assert bot.edits == []
    assert bot.sent[0]["text"] == access.UNREGISTERED_TEXT