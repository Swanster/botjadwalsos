#!/usr/bin/env python3
"""Regression tests for weekday/weekend schedule selection rules."""

from unittest.mock import patch

from core.database import (
    is_weekend_fallback_active_for_user,
    validate_weekday_weekend_balance,
)


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


def test_fallback_active_when_remaining_weekend_type_is_full():
    """If user already has Saturday, fallback may activate when all Sundays are full."""
    def fail_get_user_group(user_id):
        raise AssertionError("fallback logic must use global daily capacity, not group quota")

    def fake_count(tanggal):
        return 1 if tanggal in {"2026-07-05", "2026-07-12", "2026-07-19", "2026-07-26"} else 0

    with patch("core.database.get_user_group", side_effect=fail_get_user_group), \
         patch("core.database.get_daily_limit", return_value=1), \
         patch("core.database.get_assignment_count_for_date", side_effect=fake_count), \
         patch("core.database.connect_db") as mock_connect:
        mock_connect.return_value.__enter__.return_value.cursor.return_value.fetchall.return_value = [
            {"tanggal": "2026-07-04"},  # User already has Saturday
        ]

        assert is_weekend_fallback_active_for_user(123, 2026, 7) is True


def test_fallback_inactive_when_remaining_weekend_type_still_available():
    """If user already has Saturday but a Sunday is still open, keep normal 2 weekday limit."""
    def fail_get_user_group(user_id):
        raise AssertionError("fallback logic must use global daily capacity, not group quota")

    def fake_count(tanggal):
        return 1 if tanggal in {"2026-07-05", "2026-07-12", "2026-07-19"} else 0

    with patch("core.database.get_user_group", side_effect=fail_get_user_group), \
         patch("core.database.get_daily_limit", return_value=1), \
         patch("core.database.get_assignment_count_for_date", side_effect=fake_count), \
         patch("core.database.connect_db") as mock_connect:
        mock_connect.return_value.__enter__.return_value.cursor.return_value.fetchall.return_value = [
            {"tanggal": "2026-07-04"},  # User already has Saturday; 2026-07-26 Sunday open
        ]

        assert is_weekend_fallback_active_for_user(123, 2026, 7) is False


if __name__ == "__main__":
    test_user_can_select_two_weekdays_without_weekend_full_fallback()
    test_user_cannot_select_third_weekday_when_weekend_is_not_full()
    test_user_can_select_third_weekday_when_weekend_is_full()
    test_weekend_selection_does_not_unlock_extra_weekdays()
    test_user_cannot_select_fourth_weekday_when_weekend_is_full()
    test_fallback_active_when_remaining_weekend_type_is_full()
    test_fallback_inactive_when_remaining_weekend_type_still_available()
    print("weekday/weekend rule tests passed")
