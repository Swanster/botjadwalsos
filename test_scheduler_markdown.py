"""Regression: mention ber-underscore tidak boleh mematikan pesan Markdown.

Telegram legacy Markdown menolak seluruh pesan bila ada satu karakter "_"
tanpa pasangan. Handle seperti @op_user_x disisipkan mentah sebelum perbaikan
2026-11-07, sehingga pengingat jadwal gagal terkirim untuk SEMUA anggota.
"""
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


def test_daily_reminder_escapes_display_name(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    assert db.add_jadwal_manual(1, "Op_User", "op_user_x", "2026-11-10")

    sent = {}

    class FakeBot:
        def send_message(self, chat_id, text, **kwargs):
            sent["text"] = text

    monkeypatch.setattr(scheduler, "datetime", _FrozenDatetime)
    scheduler.kirim_pengingat_harian.__wrapped__(FakeBot())

    unescaped = [i for i, ch in enumerate(sent["text"]) if ch == "_" and (i == 0 or sent["text"][i - 1] != "\\")]
    assert len(unescaped) % 2 == 0


class _FrozenDatetime(__import__("datetime").datetime):
    @classmethod
    def now(cls, tz=None):
        return cls(2026, 11, 10, 7, 0, tzinfo=tz)
