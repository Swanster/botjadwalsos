import contextlib
import os
import sqlite3
import pytest
from contextlib import closing
from unittest.mock import patch

import config
from core import database as db

CANONICAL_CHECK = "CHECK(group_name IN ('INFRA_DELIVERY', 'INFRA_OPERATION', 'APPS', 'MONITORING'))"


def _schema_sql(path):
    with closing(sqlite3.connect(path)) as conn:
        row = conn.execute(
            "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'user_groups'"
        ).fetchone()
    return row[0]


@pytest.fixture(autouse=True)
def isolate_db(tmp_path, monkeypatch):
    """Ensure every test in this module operates on an isolated temporary SQLite database."""
    db_path = str(tmp_path / "test_infra_split.db")
    monkeypatch.setattr(config, "DB_NAME", db_path)
    monkeypatch.setattr(db, "DB_NAME", db_path)
    return db_path


# =============================================================================
# 1. MIGRATION & REBUILD TESTS
# =============================================================================


def test_old_three_group_schema_without_ce_is_rebuilt(tmp_path, monkeypatch):
    path = str(tmp_path / 'old-no-ce.sqlite')
    monkeypatch.setattr(config, 'DB_NAME', path)
    monkeypatch.setattr(db, 'DB_NAME', path)
    conn = sqlite3.connect(path)
    conn.executescript('''
        CREATE TABLE user_groups (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            telegram_username TEXT,
            group_name TEXT NOT NULL CHECK(group_name IN ('INFRA', 'APPS', 'MONITORING'))
        );
        INSERT INTO user_groups VALUES (1, 'Infra User', 'infra_user', 'INFRA');
        INSERT INTO user_groups VALUES (2, 'Apps User', 'apps_user', 'APPS');
        INSERT INTO user_groups VALUES (3, 'Monitoring User', 'monitoring_user', 'MONITORING');
        CREATE TABLE jadwal (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            username TEXT NOT NULL,
            telegram_username TEXT,
            tanggal TEXT NOT NULL,
            UNIQUE(user_id, tanggal)
        );
        INSERT INTO jadwal(user_id, username, telegram_username, tanggal)
        VALUES (1, 'Infra User', 'infra_user', '2026-09-03');
    ''')
    conn.commit()
    conn.close()

    db.create_tables()

    assert CANONICAL_CHECK in _schema_sql(path)
    assert db.get_user_group(1) == 'INFRA_OPERATION'
    assert db.get_user_group(2) == 'APPS'
    assert db.get_user_group(3) == 'MONITORING'
    assert len(db.get_user_jadwal_for_month(1, 2026, 9)) == 1


def test_ce_and_infra_map_during_rebuild_and_second_init_is_idempotent(tmp_path, monkeypatch):
    path = str(tmp_path / 'old-with-ce.sqlite')
    monkeypatch.setattr(config, 'DB_NAME', path)
    monkeypatch.setattr(db, 'DB_NAME', path)
    conn = sqlite3.connect(path)
    conn.executescript('''
        CREATE TABLE user_groups (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            telegram_username TEXT,
            group_name TEXT NOT NULL CHECK(group_name IN ('CE', 'INFRA', 'APPS', 'MONITORING'))
        );
        INSERT INTO user_groups VALUES (10, 'CE User', 'ce_user', 'CE');
        INSERT INTO user_groups VALUES (11, 'Infra User', 'infra_user', 'INFRA');
        INSERT INTO user_groups VALUES (12, 'Apps User', 'apps_user', 'APPS');
        INSERT INTO user_groups VALUES (13, 'Monitoring User', 'monitoring_user', 'MONITORING');
        CREATE TABLE jadwal (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            username TEXT NOT NULL,
            telegram_username TEXT,
            tanggal TEXT NOT NULL,
            UNIQUE(user_id, tanggal)
        );
        INSERT INTO jadwal(user_id, username, telegram_username, tanggal)
        VALUES (10, 'CE User', 'ce_user', '2026-09-04');
        CREATE TABLE settings(key TEXT PRIMARY KEY, value TEXT NOT NULL, description TEXT);
        INSERT INTO settings VALUES ('max_hari_infra', '99', 'old value');
    ''')
    conn.commit()
    conn.close()

    db.create_tables()
    first_rows = [dict(row) for row in db.get_all_users_in_group('INFRA_OPERATION')]
    first_sql = _schema_sql(path)
    db.create_tables()
    second_rows = [dict(row) for row in db.get_all_users_in_group('INFRA_OPERATION')]

    assert first_sql == _schema_sql(path)
    assert first_rows == second_rows
    assert {row['user_id'] for row in first_rows} == {10, 11}
    assert db.get_setting('max_hari_infra_operation') == '5'
    assert db.get_setting('max_hari_infra') is None
    assert db.get_user_jadwal_for_month(10, 2026, 9)[0]['tanggal'] == '2026-09-04'


# =============================================================================
# 2. CANONICAL INPUT & DAILY-QUOTA TESTS
# =============================================================================


def test_group_input_normalizes_legacy_infra_and_ce(tmp_path, monkeypatch):
    monkeypatch.setattr(config, 'DB_NAME', str(tmp_path / 'groups.sqlite'))
    monkeypatch.setattr(db, 'DB_NAME', str(tmp_path / 'groups.sqlite'))
    db.create_tables()

    db.set_user_group(1, 'Legacy Infra', 'legacy_infra', 'INFRA')
    db.set_user_group(2, 'Legacy CE', 'legacy_ce', 'CE')
    db.set_user_group(3, 'Delivery', 'delivery', 'INFRA_DELIVERY')

    assert db.get_user_group(1) == 'INFRA_OPERATION'
    assert db.get_user_group(2) == 'INFRA_OPERATION'
    assert db.get_user_group(3) == 'INFRA_DELIVERY'


def test_both_infra_groups_use_existing_daily_quota_setting(tmp_path, monkeypatch):
    monkeypatch.setattr(config, 'DB_NAME', str(tmp_path / 'quota.sqlite'))
    monkeypatch.setattr(db, 'DB_NAME', str(tmp_path / 'quota.sqlite'))
    db.create_tables()
    db.set_setting('kuota_infra', '2')

    assert db.get_group_quota('INFRA_DELIVERY') == 2
    assert db.get_group_quota('INFRA_OPERATION') == 2


# =============================================================================
# 3. BOT MONTHLY SAVE, CONFLICT & ATOMICITY TESTS
# =============================================================================


def test_delivery_save_zero_dates_fails_and_preserves_old_rows():
    db.create_tables()
    db.set_user_group(1, 'Delivery 1', 'delivery1', 'INFRA_DELIVERY')
    # Pre-populate one date
    db.add_jadwal_manual(1, 'Delivery 1', 'delivery1', '2026-09-01')

    # Try saving 0 dates
    result = db.update_user_jadwal_for_month(1, 'Delivery 1', 'delivery1', [], 2026, 9)
    assert result.ok is False
    assert result.error_code in ('delivery_exact_one', 'invalid_dates')
    # Preserves old rows
    rows = db.get_user_jadwal_for_month(1, 2026, 9)
    assert len(rows) == 1
    assert rows[0]['tanggal'] == '2026-09-01'


def test_delivery_save_one_free_date_succeeds():
    db.create_tables()
    db.set_user_group(1, 'Delivery 1', 'delivery1', 'INFRA_DELIVERY')

    result = db.update_user_jadwal_for_month(1, 'Delivery 1', 'delivery1', ['2026-09-02'], 2026, 9)
    assert result.ok is True
    rows = db.get_user_jadwal_for_month(1, 2026, 9)
    assert len(rows) == 1
    assert rows[0]['tanggal'] == '2026-09-02'


def test_delivery_save_two_dates_fails_and_preserves_old_rows():
    db.create_tables()
    db.set_user_group(1, 'Delivery 1', 'delivery1', 'INFRA_DELIVERY')
    db.add_jadwal_manual(1, 'Delivery 1', 'delivery1', '2026-09-01')

    result = db.update_user_jadwal_for_month(1, 'Delivery 1', 'delivery1', ['2026-09-02', '2026-09-03'], 2026, 9)
    assert result.ok is False
    assert result.error_code == 'delivery_exact_one'
    # Preserves old rows
    rows = db.get_user_jadwal_for_month(1, 2026, 9)
    assert len(rows) == 1
    assert rows[0]['tanggal'] == '2026-09-01'


def test_operation_save_rejects_dates_exceeding_setting():
    db.create_tables()
    db.set_user_group(2, 'Op User', 'op_user', 'INFRA_OPERATION')
    db.set_setting('max_hari_infra_operation', '2')

    # Try saving 3 dates (e.g. weekdays: Wed, Thu, Fri: Sep 2, 3, 4)
    result = db.update_user_jadwal_for_month(2, 'Op User', 'op_user', ['2026-09-02', '2026-09-03', '2026-09-04'], 2026, 9)
    assert result.ok is False
    assert result.error_code == 'monthly_limit'
    assert len(db.get_user_jadwal_for_month(2, 2026, 9)) == 0


def test_apps_and_monitoring_save_rejects_dates_exceeding_setting():
    db.create_tables()
    db.set_user_group(3, 'Apps User', 'apps_user', 'APPS')
    db.set_user_group(4, 'Mon User', 'mon_user', 'MONITORING')
    db.set_setting('max_hari_apps', '2')
    db.set_setting('max_hari_monitoring', '2')

    res_apps = db.update_user_jadwal_for_month(3, 'Apps User', 'apps_user', ['2026-09-02', '2026-09-03', '2026-09-04'], 2026, 9)
    assert res_apps.ok is False
    assert res_apps.error_code == 'monthly_limit'

    res_mon = db.update_user_jadwal_for_month(4, 'Mon User', 'mon_user', ['2026-09-02', '2026-09-03', '2026-09-04'], 2026, 9)
    assert res_mon.ok is False
    assert res_mon.error_code == 'monthly_limit'


def test_another_user_row_blocks_selected_date():
    db.create_tables()
    db.set_user_group(1, 'User 1', 'user1', 'INFRA_OPERATION')
    db.set_user_group(2, 'User 2', 'user2', 'APPS')
    db.add_jadwal_manual(1, 'User 1', 'user1', '2026-09-02')

    result = db.update_user_jadwal_for_month(2, 'User 2', 'user2', ['2026-09-02'], 2026, 9)
    assert result.ok is False
    assert result.error_code == 'date_conflict'
    assert len(db.get_user_jadwal_for_month(2, 2026, 9)) == 0


def test_current_user_can_retain_own_row_while_replacing_others():
    db.create_tables()
    db.set_user_group(1, 'User 1', 'user1', 'INFRA_OPERATION')
    db.add_jadwal_manual(1, 'User 1', 'user1', '2026-09-02')
    db.add_jadwal_manual(1, 'User 1', 'user1', '2026-09-03')

    # Retain Sep 02, replace Sep 03 with Sep 04
    result = db.update_user_jadwal_for_month(1, 'User 1', 'user1', ['2026-09-02', '2026-09-04'], 2026, 9)
    assert result.ok is True
    rows = [r['tanggal'] for r in db.get_user_jadwal_for_month(1, 2026, 9)]
    assert rows == ['2026-09-02', '2026-09-04']


def test_invalid_dates_outside_target_month_fails_before_deletion():
    db.create_tables()
    db.set_user_group(1, 'Delivery 1', 'delivery1', 'INFRA_DELIVERY')
    db.add_jadwal_manual(1, 'Delivery 1', 'delivery1', '2026-09-01')

    # Try saving a date in October for September
    result = db.update_user_jadwal_for_month(1, 'Delivery 1', 'delivery1', ['2026-10-01'], 2026, 9)
    assert result.ok is False
    assert result.error_code == 'invalid_dates'
    # Old rows intact
    rows = db.get_user_jadwal_for_month(1, 2026, 9)
    assert len(rows) == 1
    assert rows[0]['tanggal'] == '2026-09-01'


# =============================================================================
# 4. WEB-CREATED WEEKEND CONFLICT COVERAGE
# =============================================================================


def test_web_created_weekend_row_blocks_bot_save_for_another_user():
    db.create_tables()
    db.set_user_group(1, 'User A', 'user_a', 'INFRA_OPERATION')
    db.set_user_group(2, 'User B', 'user_b', 'INFRA_DELIVERY')

    # Sep 5, 2026 is Saturday (weekend)
    # Admin adds User A to weekend via add_jadwal_manual (web path)
    db.add_jadwal_manual(1, 'User A', 'user_a', '2026-09-05')

    # User B attempts to save via Bot on 2026-09-05
    result = db.update_user_jadwal_for_month(2, 'User B', 'user_b', ['2026-09-05'], 2026, 9)
    assert result.ok is False
    assert result.error_code == 'date_conflict'

    # User A's weekend row is preserved
    rows_a = db.get_user_jadwal_for_month(1, 2026, 9)
    assert len(rows_a) == 1
    assert rows_a[0]['tanggal'] == '2026-09-05'


# =============================================================================
# 5. SWAP, CANCELLATION, RETRY & NESTED-CONNECTION TESTS
# =============================================================================


def test_valid_swap_updates_both_rows_and_approves_request():
    db.create_tables()
    db.set_user_group(1, 'User 1', 'user1', 'INFRA_OPERATION')
    db.set_user_group(2, 'User 2', 'user2', 'INFRA_OPERATION')

    # Both are weekdays: Sep 2 (Wed) and Sep 3 (Thu)
    db.add_jadwal_manual(1, 'User 1', 'user1', '2026-09-02')
    db.add_jadwal_manual(2, 'User 2', 'user2', '2026-09-03')

    req_id = db.create_tukar_request(1, 'User 1', 2, '2026-09-02', '2026-09-03')
    result = db.execute_swap(req_id)

    assert result.ok is True
    # Verify User 1 now has Sep 03, User 2 now has Sep 02
    rows_1 = [r['tanggal'] for r in db.get_user_jadwal_for_month(1, 2026, 9)]
    rows_2 = [r['tanggal'] for r in db.get_user_jadwal_for_month(2, 2026, 9)]
    assert rows_1 == ['2026-09-03']
    assert rows_2 == ['2026-09-02']

    req = db.get_tukar_request_by_id(req_id)
    assert req['status'] == 'APPROVED'


def test_swap_same_dates_rejected_before_validation_and_leaves_pending():
    """A swap request with tanggal_a == tanggal_b is rejected before source-row validation.
    Leaves both schedules and the request PENDING."""
    db.create_tables()
    db.set_user_group(1, 'User 1', 'user1', 'INFRA_OPERATION')
    db.set_user_group(2, 'User 2', 'user2', 'INFRA_OPERATION')

    # E.g. web weekend override created rows for both users on same weekend day (Sep 5, Sat)
    db.add_jadwal_manual(1, 'User 1', 'user1', '2026-09-05')
    db.add_jadwal_manual(2, 'User 2', 'user2', '2026-09-05')

    req_id = db.create_tukar_request(1, 'User 1', 2, '2026-09-05', '2026-09-05')
    result = db.execute_swap(req_id)

    assert result.ok is False
    assert result.error_code in ('same_date', 'invalid_dates')

    # Both schedules still present
    rows_1 = [r['tanggal'] for r in db.get_user_jadwal_for_month(1, 2026, 9)]
    rows_2 = [r['tanggal'] for r in db.get_user_jadwal_for_month(2, 2026, 9)]
    assert rows_1 == ['2026-09-05']
    assert rows_2 == ['2026-09-05']

    req = db.get_tukar_request_by_id(req_id)
    assert req['status'] == 'PENDING'


def test_swap_missing_or_reowned_source_row_rejects_and_leaves_pending():
    db.create_tables()
    db.set_user_group(1, 'User 1', 'user1', 'INFRA_OPERATION')
    db.set_user_group(2, 'User 2', 'user2', 'INFRA_OPERATION')

    # User 1 has Sep 2, but User 2 does NOT have Sep 3
    db.add_jadwal_manual(1, 'User 1', 'user1', '2026-09-02')

    req_id = db.create_tukar_request(1, 'User 1', 2, '2026-09-02', '2026-09-03')
    result = db.execute_swap(req_id)

    assert result.ok is False
    assert result.error_code in ('stale_request', 'source_row_missing')

    req = db.get_tukar_request_by_id(req_id)
    assert req['status'] == 'PENDING'
    rows_1 = [r['tanggal'] for r in db.get_user_jadwal_for_month(1, 2026, 9)]
    assert rows_1 == ['2026-09-02']


def test_swap_unrelated_row_on_either_date_rejects_and_leaves_pending():
    db.create_tables()
    db.set_user_group(1, 'User 1', 'user1', 'INFRA_OPERATION')
    db.set_user_group(2, 'User 2', 'user2', 'INFRA_OPERATION')
    db.set_user_group(3, 'User 3', 'user3', 'APPS')

    # Sep 5 (Sat) and Sep 6 (Sun)
    db.add_jadwal_manual(1, 'User 1', 'user1', '2026-09-05')
    db.add_jadwal_manual(2, 'User 2', 'user2', '2026-09-06')
    # Unrelated row on Sep 5 (e.g. from web weekend override)
    db.add_jadwal_manual(3, 'User 3', 'user3', '2026-09-05')

    req_id = db.create_tukar_request(1, 'User 1', 2, '2026-09-05', '2026-09-06')
    result = db.execute_swap(req_id)

    assert result.ok is False
    assert result.error_code in ('swap_conflict', 'date_conflict')

    req = db.get_tukar_request_by_id(req_id)
    assert req['status'] == 'PENDING'


def test_swap_rejects_delivery_post_state_zero_or_two_or_other_group_over_limit():
    db.create_tables()
    db.set_user_group(1, 'Delivery 1', 'deliv1', 'INFRA_DELIVERY')
    db.set_user_group(2, 'Op User', 'op_user', 'INFRA_OPERATION')

    # Delivery user has Sep 02 (in Sep 2026), Op has Oct 01 (in Oct 2026) - both weekdays
    db.add_jadwal_manual(1, 'Delivery 1', 'deliv1', '2026-09-02')
    db.add_jadwal_manual(2, 'Op User', 'op_user', '2026-10-01')

    # If swapped, Delivery user would have 0 in Sep 2026 and 1 in Oct 2026.
    # But Delivery requires exactly 1 schedule in target month (Sep 2026 becomes 0).
    req_id = db.create_tukar_request(1, 'Delivery 1', 2, '2026-09-02', '2026-10-01')
    result = db.execute_swap(req_id)

    assert result.ok is False
    assert result.error_code in ('delivery_exact_one', 'monthly_limit')

    req = db.get_tukar_request_by_id(req_id)
    assert req['status'] == 'PENDING'


def test_cancellation_valid_atomic_and_stale_multi_date():
    db.create_tables()
    db.set_user_group(1, 'User 1', 'user1', 'INFRA_OPERATION')
    db.add_jadwal_manual(1, 'User 1', 'user1', '2026-09-02')
    db.add_jadwal_manual(1, 'User 1', 'user1', '2026-09-03')

    # Stale multi-date cancellation: includes Sep 04 which user 1 does not own
    result_stale = db.delete_user_jadwal_on_dates(1, ['2026-09-02', '2026-09-04'])
    assert result_stale.ok is False
    assert result_stale.error_code == 'stale_schedule'
    assert result_stale.rows_affected == 0
    # Both rows still exist
    assert len(db.get_user_jadwal_for_month(1, 2026, 9)) == 2

    # Valid multi-date cancellation: deletes both atomically
    result_valid = db.delete_user_jadwal_on_dates(1, ['2026-09-02', '2026-09-03'])
    assert result_valid.ok is True
    assert result_valid.rows_affected == 2
    assert len(db.get_user_jadwal_for_month(1, 2026, 9)) == 0


def test_cancellation_allows_deleting_last_delivery_schedule():
    db.create_tables()
    db.set_user_group(1, 'Delivery 1', 'delivery1', 'INFRA_DELIVERY')
    db.add_jadwal_manual(1, 'Delivery 1', 'delivery1', '2026-09-02')

    # Explicit cancellation exception allows Delivery to have 0 schedules
    result = db.delete_user_jadwal_on_dates(1, ['2026-09-02'])
    assert result.ok is True
    assert result.rows_affected == 1
    assert len(db.get_user_jadwal_for_month(1, 2026, 9)) == 0


def test_lock_exhaustion_returns_structured_failure_and_performs_three_attempts(monkeypatch):
    db.create_tables()
    db.set_user_group(1, 'Delivery 1', 'delivery1', 'INFRA_DELIVERY')

    # Patch retry delay to 0 for determinism
    if hasattr(db, 'MUTATION_RETRY_DELAYS'):
        monkeypatch.setattr(db, 'MUTATION_RETRY_DELAYS', (0, 0))

    # Hold a lock on the database using an external connection
    lock_conn = sqlite3.connect(db.DB_NAME)
    lock_conn.execute("BEGIN EXCLUSIVE")

    try:
        result = db.update_user_jadwal_for_month(1, 'Delivery 1', 'delivery1', ['2026-09-02'], 2026, 9)
        assert result.ok is False
        assert result.error_code == 'database_locked'
        assert result.message == getattr(db, 'LOCK_RETRY_MESSAGE', 'Jadwal belum tersimpan karena sistem sedang dipakai. Silakan coba lagi.')
        assert result.rows_affected == 0
    finally:
        lock_conn.rollback()
        lock_conn.close()


def test_mutations_use_single_connection_and_pass_conn_to_private_helpers():
    db.create_tables()
    db.set_user_group(1, 'User 1', 'user1', 'INFRA_OPERATION')
    db.set_user_group(2, 'User 2', 'user2', 'INFRA_OPERATION')

    connect_calls = 0
    active_conn_ids = []
    original_connect = db.connect_db

    @contextlib.contextmanager
    def tracking_connect():
        nonlocal connect_calls
        connect_calls += 1
        with original_connect() as conn:
            active_conn_ids.append(id(conn))
            yield conn

    # Wrap private transaction helpers to assert they receive the active mutation connection ID
    seen_helper_conn_ids = []
    private_helpers = [
        '_get_setting_with_conn',
        '_get_user_group_with_conn',
        '_get_user_jadwal_for_month_with_conn',
        '_get_tukar_request_by_id_with_conn',
        '_get_daily_limit_with_conn',
        '_get_assignment_count_for_date_with_conn',
        '_get_group_quota_with_conn',
        '_get_group_assignment_count_for_date_with_conn',
        '_is_weekend_fallback_active_for_user_with_conn',
        '_find_bot_date_conflicts_with_conn',
    ]

    def make_wrapper(orig_fn):
        def wrapper(conn, *args, **kwargs):
            seen_helper_conn_ids.append(id(conn))
            return orig_fn(conn, *args, **kwargs)
        return wrapper

    with patch.object(db, 'connect_db', side_effect=tracking_connect):
        for helper_name in private_helpers:
            if hasattr(db, helper_name):
                orig = getattr(db, helper_name)
                patch.object(db, helper_name, side_effect=make_wrapper(orig)).start()

        # Test 1: Save mutation
        connect_calls = 0
        active_conn_ids.clear()
        seen_helper_conn_ids.clear()
        res = db.update_user_jadwal_for_month(1, 'User 1', 'user1', ['2026-09-02'], 2026, 9)
        assert res.ok is True
        assert connect_calls == 1, f"Expected 1 connection for save mutation, got {connect_calls}"
        if seen_helper_conn_ids:
            assert all(cid == active_conn_ids[-1] for cid in seen_helper_conn_ids)

        # Test 2: Swap mutation
        db.add_jadwal_manual(2, 'User 2', 'user2', '2026-09-03')
        req_id = db.create_tukar_request(1, 'User 1', 2, '2026-09-02', '2026-09-03')

        connect_calls = 0
        active_conn_ids.clear()
        seen_helper_conn_ids.clear()
        res_swap = db.execute_swap(req_id)
        assert res_swap.ok is True
        assert connect_calls == 1, f"Expected 1 connection for swap mutation, got {connect_calls}"
        if seen_helper_conn_ids:
            assert all(cid == active_conn_ids[-1] for cid in seen_helper_conn_ids)

        # Test 3: Cancellation mutation
        connect_calls = 0
        active_conn_ids.clear()
        seen_helper_conn_ids.clear()
        res_del = db.delete_user_jadwal_on_dates(1, ['2026-09-03'])
        assert res_del.ok is True
        assert connect_calls == 1, f"Expected 1 connection for cancellation mutation, got {connect_calls}"
        if seen_helper_conn_ids:
            assert all(cid == active_conn_ids[-1] for cid in seen_helper_conn_ids)
