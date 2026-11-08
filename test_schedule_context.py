"""Test konteks jadwal kaya."""
import os
import sys
from datetime import date

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

import config
from core import database as db
from core.schedule_context import build_rich_context


def _setup(tmp_path, monkeypatch):
    db_path = str(tmp_path / "ctx.sqlite")
    monkeypatch.setattr(config, "DB_NAME", db_path)
    monkeypatch.setattr(db, "DB_NAME", db_path)
    db.create_tables()
    db.set_user_group(1, "Budi", "budi", "INFRA_OPERATION")
    db.add_jadwal_manual(1, "Budi", "budi", "2026-11-08")


def test_build_rich_context_includes_schedule_and_empty_days(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    text = build_rich_context(today=date(2026, 11, 7))
    assert "2026-11-08" in text
    assert "Budi" in text
    assert "Hari kosong" in text
