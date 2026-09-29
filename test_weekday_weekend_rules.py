#!/usr/bin/env python3
"""Regression tests for weekday/weekend schedule selection rules."""

import sys

import config
import pytest

from unittest.mock import patch

from core import database as db
from core.database import (
    is_weekend_fallback_active_for_user,
    validate_weekday_weekend_balance,
)


def _setup(tmp_path, monkeypatch):
    db_path = str(tmp_path / 'fallback.sqlite')
    monkeypatch.setattr(config, 'DB_NAME', db_path)
    monkeypatch.setattr(db, 'DB_NAME', db_path)
    db.create_tables()
    return db_path


def test_user_can_select_two_weekdays_without_weekend_full_fallback():
    """Normal rule: user may take up to 2 weekdays."""
    is_valid, error_message = validate_weekday_weekend_balance([
        "2026-07-06",  # Monday
        "2026-07-07",  # Tuesday
    ])

    assert is_valid is True
    assert error_message is None


def test_user_cannot_select_third_weekday_when_weekend_is_not_full():
    """Normal rule: 3rd weekday is blocked when weekend slots are still available."""
    is_valid, error_message = validate_weekday_weekend_balance([
        "2026-07-06",  # Monday
        "2026-07-07",  # Tuesday
        "2026-07-08",  # Wednesday
    ])

    assert is_valid is False
    assert error_message is not None
    assert "2 jadwal weekday" in error_message


def test_user_can_select_third_weekday_when_weekend_is_full():
    """Fallback rule: when weekend slots are full, user may take 3 weekdays."""
    is_valid, error_message = validate_weekday_weekend_balance([
        "2026-07-06",  # Monday
        "2026-07-07",  # Tuesday
        "2026-07-08",  # Wednesday
    ], weekend_full=True)

    assert is_valid is True
    assert error_message is None


def test_weekend_selection_does_not_unlock_extra_weekdays():
    """Weekend selected by the user must not allow more than 2 weekdays."""
    is_valid, error_message = validate_weekday_weekend_balance([
        "2026-07-04",  # Saturday
        "2026-07-06",  # Monday
        "2026-07-07",  # Tuesday
        "2026-07-08",  # Wednesday
    ])

    assert is_valid is False
    assert error_message is not None
    assert "2 jadwal weekday" in error_message


def test_user_cannot_select_fourth_weekday_when_weekend_is_full():
    """Fallback rule still caps weekday-only schedule at 3 when weekends are full."""
    is_valid, error_message = validate_weekday_weekend_balance([
        "2026-07-06",  # Monday
        "2026-07-07",  # Tuesday
        "2026-07-08",  # Wednesday
        "2026-07-09",  # Thursday
    ], weekend_full=True)

    assert is_valid is False
    assert error_message is not None
    assert "3 jadwal weekday" in error_message


def test_fallback_active_when_remaining_weekend_type_is_full(tmp_path, monkeypatch):
    """If user already has Saturday, fallback activates when every Sunday is taken by others."""
    _setup(tmp_path, monkeypatch)

    def fail_get_user_group(user_id):
        raise AssertionError("fallback availability must not depend on group quota")

    db.set_user_group(123, 'Infra Op', 'op123', 'INFRA_OPERATION')
    assert db.add_jadwal_manual(123, 'Infra Op', 'op123', '2026-07-04') is True  # Sabtu

    # Semua Minggu Juli (5, 12, 19, 26) sudah diambil user LAIN.
    for idx, tanggal in enumerate(['2026-07-05', '2026-07-12', '2026-07-19', '2026-07-26'], start=701):
        db.set_user_group(idx, f'Apps {idx}', f'apps{idx}', 'APPS')
        assert db.add_jadwal_manual(idx, f'Apps {idx}', f'apps{idx}', tanggal) is True

    with patch("core.database.get_user_group", side_effect=fail_get_user_group):
        assert is_weekend_fallback_active_for_user(123, 2026, 7) is True


def test_fallback_inactive_when_remaining_weekend_type_still_available(tmp_path, monkeypatch):
    """User has Saturday but one Sunday is still open: keep normal 2-weekday limit."""
    _setup(tmp_path, monkeypatch)

    def fail_get_user_group(user_id):
        raise AssertionError("fallback availability must not depend on group quota")

    db.set_user_group(123, 'Infra Op', 'op123', 'INFRA_OPERATION')
    assert db.add_jadwal_manual(123, 'Infra Op', 'op123', '2026-07-04') is True  # Sabtu

    # Minggu 5, 12, 19 diambil user lain; Minggu 26 masih kosong.
    for idx, tanggal in enumerate(['2026-07-05', '2026-07-12', '2026-07-19'], start=701):
        db.set_user_group(idx, f'Apps {idx}', f'apps{idx}', 'APPS')
        assert db.add_jadwal_manual(idx, f'Apps {idx}', f'apps{idx}', tanggal) is True

    with patch("core.database.get_user_group", side_effect=fail_get_user_group):
        assert is_weekend_fallback_active_for_user(123, 2026, 7) is False


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, '-q']))
