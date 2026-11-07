"""Regression: Batasan Harian harus menjadi kapasitas nyata per tanggal.

Sebelum perbaikan (audit 2026-11-07): menu Batasan Harian bisa diset admin,
tapi tidak ada gate yang membacanya. Bot dan web memakai aturan hardcode
"satu orang per tanggal", jadi setting admin tidak berefek apa pun.
"""
import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

import config
from core import database as db


def _setup(tmp_path, monkeypatch):
    db_path = str(tmp_path / "gate.sqlite")
    monkeypatch.setattr(config, "DB_NAME", db_path)
    monkeypatch.setattr(db, "DB_NAME", db_path)
    db.create_tables()
    db.init_default_settings()
    db.set_user_group(1, "Op User", "op_user", "INFRA_OPERATION")
    db.set_user_group(2, "Apps User", "apps_user", "APPS")
    return db_path


def test_default_capacity_is_one_person_per_date(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    assert db.add_jadwal_manual(1, "Op User", "op_user", "2026-11-10")
    assert db.date_is_taken("2026-11-10", 2) is True
    assert db.date_is_taken("2026-11-10", 1) is False


def test_daily_limit_allows_second_person_on_same_date(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    db.set_daily_limit("2026-11-10", 2)
    assert db.add_jadwal_manual(1, "Op User", "op_user", "2026-11-10")
    assert db.date_is_taken("2026-11-10", 2) is False

    result = db.update_user_jadwal_for_month(2, "Apps User", "apps_user", ["2026-11-10"], 2026, 11)

    assert result.ok is True, result
    assert db.get_date_capacity("2026-11-10") == {"limit": 2, "current": 2, "is_full": True}


def test_third_person_rejected_when_limit_two(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    db.set_daily_limit("2026-11-10", 2)
    db.set_user_group(3, "Mon User", "mon_user", "MONITORING")
    assert db.add_jadwal_manual(1, "Op User", "op_user", "2026-11-10")
    assert db.add_jadwal_manual(2, "Apps User", "apps_user", "2026-11-10")

    result = db.update_user_jadwal_for_month(3, "Mon User", "mon_user", ["2026-11-10"], 2026, 11)

    assert result.ok is False
    assert result.error_code == "date_conflict"


def test_monthly_report_full_days_follow_date_capacity(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    from core.monthly_report import build_monthly_report

    for day in range(1, 4):
        assert db.add_jadwal_manual(1, "Op User", "op_user", f"2026-11-0{day}")

    report = build_monthly_report(2026, 11)

    assert set(report["full_dates"]) == {"2026-11-01", "2026-11-02", "2026-11-03"}
    assert report["under_capacity_dates_count"] == 27
    assert all(item["tanggal"] for item in report["under_quota"])
