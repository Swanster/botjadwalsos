"""Peringatan khusus Infra Operation: minimal 2x isi jadwal per bulan."""
import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

import config
from core import database as db
from core.scheduler import build_pesan_peringatan_pengisian_jadwal

TITLE = "PERINGATAN KHUSUS INFRA OPERATION"


def _setup(tmp_path, monkeypatch):
    db_path = str(tmp_path / "infra_op.sqlite")
    monkeypatch.setattr(config, "DB_NAME", db_path)
    monkeypatch.setattr(db, "DB_NAME", db_path)
    db.create_tables()
    db.buka_bulan_baru(2026, 11)
    db.set_setting('max_hari_infra_operation', '5')
    db.set_user_group(1, 'Op Baru', 'op_baru', 'INFRA_OPERATION')
    db.set_user_group(2, 'Apps Baru', 'apps_baru', 'APPS')


def test_infra_operation_kurang_dari_2x_dapat_peringatan_khusus(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    db.add_jadwal_manual(1, 'Op Baru', 'op_baru', '2026-11-02')
    db.add_jadwal_manual(2, 'Apps Baru', 'apps_baru', '2026-11-03')

    text = build_pesan_peringatan_pengisian_jadwal()

    assert text is not None
    assert TITLE in text
    section = text.split(TITLE)[1].split("📅 *Tanggal")[0]
    assert "op\\_baru" in section
    assert "apps\\_baru" not in section
    assert "baru *1x*" in section


def test_infra_operation_2x_tidak_diperingatkan_khusus(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    db.add_jadwal_manual(1, 'Op Baru', 'op_baru', '2026-11-02')
    db.add_jadwal_manual(1, 'Op Baru', 'op_baru', '2026-11-04')

    text = build_pesan_peringatan_pengisian_jadwal()

    assert text is not None
    assert TITLE not in text