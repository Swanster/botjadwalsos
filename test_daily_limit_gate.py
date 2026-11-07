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


def test_today_wita_uses_makassar_date(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    from datetime import datetime
    import pytz

    assert db.today_wita() == datetime.now(pytz.timezone("Asia/Makassar")).date()


def test_monthly_report_keeps_group_labels(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    from core.monthly_report import build_monthly_report

    report = build_monthly_report(2026, 11)

    labels = {group["group_name"]: group["group_label"] for group in report["per_group"]}
    assert labels["INFRA_DELIVERY"] == "Infra Delivery"
    assert labels["INFRA_OPERATION"] == "Infra Operation"


def test_add_jadwal_manual_runs_one_atomic_mutation(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    calls = {"n": 0}
    original = db._run_mutation_with_retry

    def counting(operation):
        calls["n"] += 1
        return original(operation)

    monkeypatch.setattr(db, "_run_mutation_with_retry", counting)

    assert db.add_jadwal_manual(1, "Op User", "op_user", "2026-11-10") is True
    assert calls["n"] == 1, "cek kuota dan insert harus dalam satu transaksi"
    assert db.add_jadwal_manual(1, "Op User", "op_user", "2026-11-10") is False
    assert len(db.get_jadwal_for_specific_date("2026-11-10")) == 1


def test_absensi_range_includes_user_id(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    db.set_user_absensi(1, ["2026-11-10"], 2026, 11)

    rows = db.get_all_absensi_in_range("2026-11-01", "2026-11-30")

    assert rows and rows[0]["user_id"] == 1
