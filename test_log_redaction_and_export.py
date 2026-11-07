"""Prioritas 1 audit: token bot tidak boleh masuk log, dan /export tidak boleh NameError.

Latar (audit 2026-11-07): requests menaruh URL penuh di pesan exception
(`... with url: /bot<TOKEN>/getMe`), dan main.check_api_connection mencatat `{e}`
apa adanya ke log_bot.txt (permission 664). Siapa pun yang membaca log bisa
mengambil alih bot. Selain itu handlers/admin_handlers.py memakai
sync_jadwal_to_sheets tanpa mengimpor -> /export selalu gagal.
"""
import io
import logging
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

import config
import main
from core import database as db
from fake_telebot import FakeBot, message

ADMIN = 111222333
FAKE_TOKEN = "123456789:FAKE-SECRET-TOKEN"


# ---------------------------------------------------------------------------
# Redaksi token di log
# ---------------------------------------------------------------------------

def test_redact_secrets_removes_token_from_url(monkeypatch):
    monkeypatch.setattr(main, "API_TOKEN", FAKE_TOKEN)

    cleaned = main.redact_secrets(f"Max retries exceeded with url: /bot{FAKE_TOKEN}/getMe")

    assert "FAKE-SECRET-TOKEN" not in cleaned
    assert "/bot<redacted>" in cleaned


def test_redact_secrets_removes_bare_token(monkeypatch):
    monkeypatch.setattr(main, "API_TOKEN", FAKE_TOKEN)

    assert "FAKE-SECRET-TOKEN" not in main.redact_secrets(f"token={FAKE_TOKEN} dipakai")


def test_formatter_scrubs_message_and_traceback(monkeypatch):
    monkeypatch.setattr(main, "API_TOKEN", FAKE_TOKEN)
    logger = logging.getLogger("uji-redaksi")
    logger.propagate = False
    logger.setLevel(logging.INFO)
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(main.RedactSecretsFormatter("%(message)s"))
    logger.addHandler(handler)

    try:
        raise RuntimeError(f"HTTPConnectionPool: url: /bot{FAKE_TOKEN}/getMe")
    except RuntimeError:
        logger.error("Error cek koneksi (attempt 1/3): %s", f"/bot{FAKE_TOKEN}/getMe", exc_info=True)
    finally:
        logger.removeHandler(handler)

    out = stream.getvalue()
    assert "FAKE-SECRET-TOKEN" not in out
    assert "Error cek koneksi" in out


def test_real_requests_error_is_redacted(monkeypatch):
    """Pesan exception requests asli (loopback tertutup, tanpa jaringan luar)."""
    import requests

    monkeypatch.setattr(main, "API_TOKEN", FAKE_TOKEN)
    try:
        requests.get(f"http://127.0.0.1:1/bot{FAKE_TOKEN}/getMe", timeout=2)
    except Exception as exc:  # ConnectionError
        raw = str(exc)
        cleaned = main.redact_secrets(exc)
    else:  # pragma: no cover - port 1 tidak mungkin melayani
        pytest.fail("koneksi 127.0.0.1:1 seharusnya gagal")

    assert "FAKE-SECRET-TOKEN" in raw, "prasyarat: pesan asli memang memuat token"
    assert "FAKE-SECRET-TOKEN" not in cleaned


def test_check_api_connection_log_written_without_token(tmp_path, monkeypatch):
    """Jalur nyata: check_api_connection gagal -> log_bot.txt tidak memuat token."""
    monkeypatch.setattr(main, "API_TOKEN", FAKE_TOKEN)
    monkeypatch.chdir(tmp_path)

    def _boom(*args, **kwargs):
        raise ConnectionError(f"Max retries exceeded with url: /bot{FAKE_TOKEN}/getMe")

    monkeypatch.setattr(main.requests, "get", _boom)
    monkeypatch.setattr(main.time, "sleep", lambda *_: None)

    manager = main.BotManager()
    manager.setup_logging()
    try:
        assert manager.check_api_connection() is False
    finally:
        for handler in logging.getLogger().handlers[:]:
            handler.close()
            logging.getLogger().removeHandler(handler)

    log_text = (tmp_path / "log_bot.txt").read_text(encoding="utf-8")
    assert "Error cek koneksi" in log_text
    assert "FAKE-SECRET-TOKEN" not in log_text


# ---------------------------------------------------------------------------
# /export benar-benar memanggil sync_jadwal_to_sheets
# ---------------------------------------------------------------------------

def test_export_reaches_sheets_sync(tmp_path, monkeypatch):
    db_path = str(tmp_path / "export.sqlite")
    monkeypatch.setattr(config, "DB_NAME", db_path)
    monkeypatch.setattr(db, "DB_NAME", db_path)
    from handlers import admin_handlers

    monkeypatch.setattr(admin_handlers, "ADMIN_ID", ADMIN)

    db.create_tables()
    db.set_user_group(500, "Apps User", "apps_user", "APPS")
    today = db.today_wita().strftime("%Y-%m-%d")
    db.add_jadwal_manual(500, "Apps User", "apps_user", today)

    calls = []

    class FakeClient:
        def is_enabled(self):
            return True

        def get_sheet_url(self):
            return "https://docs.google.com/spreadsheets/d/uji"

    monkeypatch.setattr(admin_handlers, "get_google_sheets_client", lambda: FakeClient())
    monkeypatch.setattr(admin_handlers, "sync_jadwal_to_sheets", lambda **kwargs: calls.append(kwargs))

    bot = FakeBot()
    admin_handlers.register_admin_handlers(bot)
    bot.handlers["export"](message(ADMIN, "/export", chat_id=ADMIN, chat_type="private"))

    assert len(calls) == 1, "sync_jadwal_to_sheets harus terpanggil, bukan NameError"
    assert calls[0]["tanggal"] == today
    assert "Error" not in bot.replies[-1]
    assert "Berhasil" in bot.replies[-1]
