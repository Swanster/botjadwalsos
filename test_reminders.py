"""Test pengingat proaktif jadwal kosong."""
import os
import sys
from datetime import date

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

import config
from core import database as db
from core import reminders


def _setup(tmp_path, monkeypatch):
    db_path = str(tmp_path / "rem.sqlite")
    monkeypatch.setattr(config, "DB_NAME", db_path)
    monkeypatch.setattr(db, "DB_NAME", db_path)
    db.create_tables()
    reminders._SENT_REMINDER_DAYS.clear()


def test_find_empty_dates_detects_days(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    dates = reminders.find_empty_dates(3)
    assert len(dates) == 3


def test_reminder_disabled_does_not_send(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    monkeypatch.setenv("REMINDER_ENABLED", "0")
    bot = type("Bot", (), {"send_message": lambda self, **kwargs: (_ for _ in ()).throw(AssertionError("dipanggil"))})()
    reminders.schedule_daily_reminder(bot)
    assert True


def test_reminder_does_not_spam_same_day(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    sent = []

    class Bot:
        def send_message(self, **kwargs):
            sent.append(kwargs)

    bot = Bot()
    reminders.schedule_daily_reminder(bot)
    reminders.schedule_daily_reminder(bot)
    assert len(sent) == 1
