import sqlite3
from types import SimpleNamespace

from core import database
from handlers import admin_handlers


class FakeBot:
    def __init__(self):
        self.handlers = {}
        self.replies = []
        self.sent_messages = []

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

    def send_message(self, *args, **kwargs):
        self.sent_messages.append((args, kwargs))
        if args:
            raise RuntimeError("DM blocked")

    def reply_to(self, message, text, **kwargs):
        self.replies.append(text)


def test_open_month_reports_failed_dm_without_sqlite_row_error(tmp_path, monkeypatch):
    db_path = tmp_path / "jadwal.db"
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE user_groups (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                telegram_username TEXT,
                group_name TEXT
            )
            """
        )
        conn.execute(
            "INSERT INTO user_groups (user_id, username, telegram_username, group_name) "
            "VALUES (?, ?, ?, ?)",
            (123, "Alice", "alice", "APPS"),
        )

    monkeypatch.setattr(database, "DB_NAME", str(db_path))
    monkeypatch.setattr(admin_handlers, "buka_bulan_baru", lambda tahun, bulan: 1)

    bot = FakeBot()
    admin_handlers.register_admin_handlers(bot)
    message = SimpleNamespace(
        text="/buka_jadwal_bulan 9 2026",
        from_user=SimpleNamespace(id=admin_handlers.ADMIN_ID),
        chat=SimpleNamespace(type="private", id=999),
    )

    bot.handlers["buka_jadwal_bulan"](message)

    assert len(bot.replies) == 1
    assert "Terjadi kesalahan saat mengirim pengumuman" not in bot.replies[0]
    assert "Gagal DM: @alice" in bot.replies[0]
