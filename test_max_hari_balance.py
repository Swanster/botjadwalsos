#!/usr/bin/env python3
"""Regression: Maksimal Hari/Bulan (setting webapps) harus menentukan jatah
weekday member, dan gerbang bot/web harus konsisten dengan aturan
satu-per-tanggal (one-per-date).

Regression background (repro 2026-09-29):
- Balance rules hard-coded 2 weekday + 1 Sabtu + 1 Minggu membatasi member
  maksimal 4 tanggal/bulan, sehingga max_hari_infra_operation=5 (default di
  webapps) tidak pernah bisa dicapai — member dicegat jauh sebelum gerbang
  bulanan.
- Kalender member menandai penuh memakai jumlah divisi vs fallback global 1,
  sehingga tanggal yang diambil anggota lain (divisi lain) tetap terlihat
  bisa dipilih lalu ditolak bot.
- Tambah jadwal web menolak di fallback global 1 padahal Kuota Harian
  divisi masih mengizinkan stacking.
"""
import calendar
import json
import os
import re
import sys

import pytest

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

import config
from core import database as db


def _setup(tmp_path, monkeypatch):
    db_path = str(tmp_path / 'max_hari.sqlite')
    monkeypatch.setattr(config, 'DB_NAME', db_path)
    monkeypatch.setattr(db, 'DB_NAME', db_path)
    db.create_tables()
    return db_path


# =============================================================================
# 1. ALLOWANCE DITURUNKAN DARI MAX_HARI
# =============================================================================


def test_weekday_allowance_follows_monthly_max(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)

    db.set_setting('max_hari_infra_operation', '5')
    assert db.get_weekday_allowance_for_group('INFRA_OPERATION') == 3

    db.set_setting('max_hari_infra_operation', '3')
    assert db.get_weekday_allowance_for_group('INFRA_OPERATION') == 2

    # APPS default 31, INFRA_DELIVERY tetap fixed 1 (exact-one) -> floor 2.
    assert db.get_weekday_allowance_for_group('APPS') == 29
    assert db.get_weekday_allowance_for_group('INFRA_DELIVERY') == 2


def test_validate_weekday_weekend_balance_honors_allowance(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)

    tiga_weekday = ['2026-10-01', '2026-10-02', '2026-10-05']  # Thu, Fri, Mon

    # Kontrak lama tetap berlaku: default weekday_limit=2 menolak weekday ke-3.
    valid, _ = db.validate_weekday_weekend_balance(tiga_weekday)
    assert valid is False

    # Allowance baru (max_hari=5 -> 3): weekday ke-3 SAH meski weekend belum penuh.
    valid, err = db.validate_weekday_weekend_balance(tiga_weekday, weekday_limit=3)
    assert valid is True, err

    # Fallback weekend penuh = +1 di atas allowance (bukan hard-coded 3).
    empat_weekday = tiga_weekday + ['2026-10-06']
    valid, _ = db.validate_weekday_weekend_balance(empat_weekday, weekday_limit=3, weekend_full=True)
    assert valid is True


def test_date_capacity_matches_one_per_date_gate(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    db.set_setting('kuota_infra', '1')
    db.set_setting('kuota_apps', '2')
    db.set_setting('kuota_monitoring', '1')

    # Tanpa Batasan Harian: kapasitas = 1 (satu-per-tanggal) — total kuota
    # divisi TIDAK dipakai, karena gerbang web/bot menolak anggota ke-2.
    cap = db.get_date_capacity('2026-11-05')
    assert cap == {'limit': 1, 'current': 0, 'is_full': False}, (
        'kapasitas tanpa Batasan Harian harus 1 (satu-per-tanggal), bukan total kuota'
    )

    # Tanggal yang sudah diambil anggota lain harus tampil FULL, supaya form
    # & badge tidak menawarkan slot yang ditolak backend saat disimpan.
    db.set_user_group(202, 'Apps User', 'apps_user', 'APPS')
    assert db.add_jadwal_manual(202, 'Apps User', 'apps_user', '2026-11-05') is True
    cap = db.get_date_capacity('2026-11-05')
    assert cap['current'] == 1 and cap['is_full'] is True, (
        'tanggal yang sudah diambil anggota lain harus ditandai penuh'
    )

    # Batasan Harian kini menjadi kapasitas nyata per tanggal (keputusan
    # 2026-11-07): tanggal dengan batas 3 orang menampilkan kapasitas 3.
    db.set_daily_limit('2026-11-06', 3)
    cap = db.get_date_capacity('2026-11-06')
    assert cap == {'limit': 3, 'current': 0, 'is_full': False}, (
        'Batasan Harian harus dipakai sebagai kapasitas tanggal'
    )

    # Sabtu terisi juga FULL (bot save satu-per-tanggal); pengecualian form
    # admin weekend ditangani di JS schedules.html, bukan di kapasitas.
    db.set_user_group(203, 'Apps Sat', 'apps203', 'APPS')
    assert db.add_jadwal_manual(203, 'Apps Sat', 'apps203', '2026-11-07') is True
    cap = db.get_date_capacity('2026-11-07')
    assert cap['current'] == 1 and cap['is_full'] is True, (
        'Sabtu terisi harus tampil FULL di tampilan member'
    )


# =============================================================================
# 2. SAVE: MAX_HARI=5 BISA DICAPAI, ATURAN SISANYA TETAP
# =============================================================================


def test_save_reaches_five_dates_when_max_hari_five(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    db.set_user_group(201, 'Op User', 'op_user', 'INFRA_OPERATION')
    db.set_setting('max_hari_infra_operation', '5')

    # 3 weekday + Sabtu + Minggu = 5 tanggal (Okt 2026: 1=Kam, 2=Jum, 3=Sab,
    # 4=Min, 5=Sen).
    lima = ['2026-10-01', '2026-10-02', '2026-10-03', '2026-10-04', '2026-10-05']
    result = db.update_user_jadwal_for_month(201, 'Op User', 'op_user', lima, 2026, 10)
    assert result.ok is True, result.message
    assert len(db.get_user_jadwal_for_month(201, 2026, 10)) == 5

    # 6 tanggal melebihi Maksimal Hari/Bulan -> monthly_limit.
    enam = lima + ['2026-10-06']
    result = db.update_user_jadwal_for_month(201, 'Op User', 'op_user', enam, 2026, 10)
    assert result.ok is False
    assert result.error_code == 'monthly_limit'
    assert len(db.get_user_jadwal_for_month(201, 2026, 10)) == 5  # roll back

    # 5 tanggal tapi 4 di antaranya weekday -> weekday_balance tetap menolak
    # (jatah weekday = max_hari - 2 slot weekend = 3).
    empat_weekday = ['2026-10-05', '2026-10-06', '2026-10-07', '2026-10-08', '2026-10-11']
    result = db.update_user_jadwal_for_month(201, 'Op User', 'op_user', empat_weekday, 2026, 10)
    assert result.ok is False
    assert result.error_code == 'weekday_balance'


# =============================================================================
# 3. KALENDER MEMBER: TAMPILAN SEJALAN DENGAN GERBANG BOT
# =============================================================================


def _callback_datas(markup):
    return [btn.callback_data for row in markup.keyboard for btn in row]


def test_calendar_allows_third_weekday_when_allowance_reaches_five(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    db.set_user_group(201, 'Op User', 'op_user', 'INFRA_OPERATION')
    db.set_setting('max_hari_infra_operation', '5')

    from handlers import user_handlers as uh

    uh.user_selections[201] = {'choices': {'2026-10-01', '2026-10-02'}}
    try:
        markup = uh.create_calendar('jadwal', 201, 2026, 10)
        datas = _callback_datas(markup)
    finally:
        uh.user_selections.pop(201, None)

    # Hari Senin pertama yang belum dipilih (2026-10-05) harus BISA dipilih:
    # jatah weekday utk max_hari=5 adalah 3, bukan hard-coded 2.
    assert f'jadwal_toggle_2026-10-05' in datas, (
        'weekday ke-3 ditandai terkunci di kalender meski Maksimal Hari/Bulan=5'
    )
    assert f'reason_weekdaybalance_2026-10-05' not in datas


def test_calendar_marks_date_taken_by_other_group_as_full(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    db.set_user_group(201, 'Op User', 'op_user', 'INFRA_OPERATION')
    db.set_user_group(202, 'Apps User', 'apps_user', 'APPS')

    # Tanggal sudah diambil anggota DIVISI LAIN lewat web (satu-per-tanggal):
    # kalender harus menandai penuh, bukan menawarkan toggle yang nantinya
    # ditolak backend.
    assert db.add_jadwal_manual(202, 'Apps User', 'apps_user', '2026-10-07') is True

    from handlers import user_handlers as uh

    uh.user_selections[201] = {'choices': set()}
    try:
        markup = uh.create_calendar('jadwal', 201, 2026, 10)
        datas = _callback_datas(markup)
    finally:
        uh.user_selections.pop(201, None)

    assert f'reason_full_2026-10-07' in datas, (
        'tanggal yang diambil anggota lain tidak ditandai penuh di kalender member'
    )
    assert f'jadwal_toggle_2026-10-07' not in datas


# =============================================================================
# 4. WEB: satu-user-per-tanggal (date_conflict) dengan pesan penolakan jelas
# =============================================================================


def test_web_add_enforces_one_user_per_date_with_clear_message(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    db.init_default_admin()
    db.set_user_group(201, 'Op User 1', 'op_user1', 'INFRA_OPERATION')
    db.set_user_group(202, 'Op User 2', 'op_user2', 'INFRA_OPERATION')
    db.set_setting('kuota_infra', '3')

    from web.app import create_app
    import web.app as web_app

    # Jangan sentuh Google Sheet produksi dari test.
    monkeypatch.setattr(web_app, 'sync_jadwal_to_sheets', lambda **kwargs: True)

    app = create_app()
    app.config['TESTING'] = True
    client = app.test_client()

    r = client.post('/login', data={'username': 'admin', 'password': 'admin123'})
    assert r.status_code in (200, 302)

    tanggal = '2026-11-02'  # Senin

    client.post('/schedules/add', data={'user_id': '201', 'tanggal': tanggal})
    rows201 = [x for x in db.get_user_jadwal_for_month(201, 2026, 11) if x['tanggal'] == tanggal]
    assert rows201, 'penambahan anggota pertama harus sukses'

    # Web tetap satu-user-per-tanggal: anggota ke-2 ditolak dengan pesan
    # jelas (sejalan date_conflict di save), barisnya tidak dibuat.
    r2 = client.post(
        '/schedules/add', data={'user_id': '202', 'tanggal': tanggal}, follow_redirects=True
    )
    rows202 = [x for x in db.get_user_jadwal_for_month(202, 2026, 11) if x['tanggal'] == tanggal]
    assert not rows202, 'anggota ke-2 pada tanggal yang sudah diambil lain harus ditolak'
    html = r2.get_data(as_text=True)
    assert 'sudah penuh (Batasan Harian tercapai)' in html, (
        'penolakan tanggal terisi harus menampilkan pesan jelas, bukan gagal generik'
    )

    # Re-add user yang barisnya sudah ada = idempoten, tetap 1 baris.
    client.post('/schedules/add', data={'user_id': '201', 'tanggal': tanggal})
    same = [x for x in db.get_user_jadwal_for_month(201, 2026, 11) if x['tanggal'] == tanggal]
    assert len(same) == 1, 're-add user yang sama tidak boleh menggandakan baris'


def test_web_calendar_marks_taken_date_full(tmp_path, monkeypatch):
    """Halaman /schedules harus menandai tanggal terisi FULL sejalan gerbang."""
    _setup(tmp_path, monkeypatch)
    db.init_default_admin()
    db.set_user_group(202, 'Apps User', 'apps_user', 'APPS')

    from web.app import create_app
    import web.app as web_app

    monkeypatch.setattr(web_app, 'sync_jadwal_to_sheets', lambda **kwargs: True)

    app = create_app()
    app.config['TESTING'] = True
    client = app.test_client()

    r = client.post('/login', data={'username': 'admin', 'password': 'admin123'})
    assert r.status_code in (200, 302)

    # Anggota lain mengambil tanggal ini lewat web (satu-per-tanggal).
    tanggal = '2026-11-04'
    assert db.add_jadwal_manual(202, 'Apps User', 'apps_user', tanggal) is True

    html = client.get('/schedules?year=2026&month=11').get_data(as_text=True)
    match = re.search(r'const dailyLimits = (\{.*?\});', html, re.S)
    assert match, 'dailyLimits tidak ditemukan di halaman /schedules'
    limits = json.loads(match.group(1))
    assert limits.get(tanggal, {}).get('is_full') is True, (
        'tanggal yang sudah diambil anggota lain harus tampil FULL di /schedules, '
        'bukan menawarkan form yang nantinya ditolak backend'
    )


if __name__ == '__main__':
    sys.exit(pytest.main([__file__, '-q']))
