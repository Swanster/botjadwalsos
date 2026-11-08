"""Test shortcut admin jadwal."""
import os
import sys
from types import SimpleNamespace

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

import config
from core import database as db
from handlers import admin_handlers


class FakeBot:
    def __init__(self):
        self.handlers = {}
        self.replies = []

    def message_handler(self, **kwargs):
        def decorator(handler):
            for command in kwargs.get("commands", []):
                self.handlers[command] = handler
            return handler
        return decorator

    def callback_query_handler(self, **kwargs):
        def decorator(handler):
            return handler
        return decorator

    def reply_to(self, message, text, **kwargs):
        self.replies.append(text)

    def send_message(self, *args, **kwargs):
        return None


def _setup(tmp_path, monkeypatch):
    db_path = str(tmp_path / "admin.sqlite")
    monkeypatch.setattr(config, "DB_NAME", db_path)
    monkeypatch.setattr(db, "DB_NAME", db_path)
    db.create_tables()
    db.buka_bulan_baru(2026, 11)
    db.set_user_group(500, "Apps User", "apps_user", "APPS")


def test_admin_ringkasan_kuota_works(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    bot = FakeBot()
    admin_handlers.register_admin_handlers(bot)
    message = SimpleNamespace(
        text="/ringkasan_kuota 11 2026",
        from_user=SimpleNamespace(id=config.ADMIN_ID),
        chat=SimpleNamespace(type="private", id=999),
    )
    bot.handlers["ringkasan_kuota"](message)
    assert bot.replies
    assert "Ringkasan Kuota" in bot.replies[0]


def test_non_admin_ringkasan_kuota_denied(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    bot = FakeBot()
    admin_handlers.register_admin_handlers(bot)
    message = SimpleNamespace(
        text="/ringkasan_kuota 11 2026",
        from_user=SimpleNamespace(id=999),
        chat=SimpleNamespace(type="private", id=999),
    )
    bot.handlers["ringkasan_kuota"](message)
    assert bot.replies
    assert "hanya untuk Admin" in bot.replies[0]
