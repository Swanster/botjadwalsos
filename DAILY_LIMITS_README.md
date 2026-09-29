# Daily Assignment Limits Feature

## Overview
This feature allows administrators to set flexible daily assignment limits for the schedule system. You can now control how many people can be assigned to work on each specific day.

## Features

### 1. Flexible Daily Limits
- Set different limits for different dates (e.g., Day 1: 1 person, Day 2: 2 people)
- **No specific limit set**: capacity = the sum of all group quotas (Pengaturan Kuota), so a free date is *not* wrongly shown as full
- Priority over group-based quotas (INFRA/APPS/MONITORING settings)

### 2. Web Administration Interface
Access the Daily Limits management through the web dashboard:
- **Navigation**: Click "Daily Limits" in the sidebar
- **Add Limit**: Select date and set maximum assignments
- **View Limits**: See all configured daily limits
- **Delete Limits**: Remove specific date limitations

### 3. Automatic Enforcement
- Users cannot select dates that are already full
- Real-time validation in the Telegram bot interface (calendar buttons + toggle gate)
- Scheduler warnings respect daily limits

### 4. Weekday allowance follows "Maksimal Hari / Bulan"
- Weekday allowance per user per month = `max_hari - 2` weekend slots (minimum 2)
- Fallback: when the user's weekend slots are full, they may take 1 extra weekday
  (allowance + 1), so the configured monthly maximum stays reachable
- Applied everywhere the weekday/weekend balance is validated: bot toggle,
  bot save, web "add schedule", and manual admin add

## How to Use

### Via Web Interface (Recommended)
1. Access the admin dashboard at `http://localhost:5050`
2. Login with admin credentials (default: admin/admin123)
3. Click "Daily Limits" in the navigation sidebar
4. Add new limits by selecting date and specifying maximum assignments
5. View and manage existing limits in the table below

### Example Configuration
```
2026-04-01: 1 person  (busy day - limited staff)
2026-04-02: 2 persons (normal day - standard staffing)
2026-04-03: 3 persons (high demand - extra staff)
```

## Technical Implementation

### Database Structure
New table `daily_limits` stores:
- `tanggal`: Date (YYYY-MM-DD format)
- `max_assignments`: Maximum people allowed
- `created_at/updated_at`: Timestamps

### Key Functions
- `set_daily_limit(tanggal, max_assignments)`: Set limit for specific date — in this
  tree it only feeds scheduler reminder thresholds (no fill gate reads it)
- `get_daily_limit(tanggal, default_limit)` / `is_date_full(...)`: retained for legacy
  call sites (scheduler reminders, demo scripts)
- `get_date_capacity(tanggal)`: Display/validation capacity — one-per-date member
  truth: limit 1, full when any member row exists (matches bot save and the web
  weekday gate; the weekend form stays open in the UI for the uncapped admin
  override)
- `get_weekday_allowance_for_group(group)`: Weekday allowance derived from Maksimal Hari/Bulan

### Integration Points
- **User Handlers**: calendar rendering, toggle gate, and save validation enforce
  one-per-date, weekend monthly limits, and the weekday allowance
- **Scheduler**: Warning systems respect daily limits
- **Web Interface**: CRUD operations for limit management + one-per-date capacity
  display on login/schedules calendars; division quota checked for weekday adds;
  weekend adds bypass limits (admin override)

## Priority System (this tree: INFRA_DELIVERY, INFRA_OPERATION, APPS, MONITORING)
1. **One-per-date (fill gates)** - calendar, bot toggle, and save reject a date
   already taken by another member
2. **Group Quotas (web weekday adds)** - INFRA_DELIVERY / INFRA_OPERATION / APPS /
   MONITORING division quota when adding a member to a weekday via web
   (no implicit "1 person per day" gate there)
3. **Weekend (admin override)** - web adds on Sat/Sun bypass every limit (uncapped)
4. **Daily Limits (scheduler reminders only)** - read by reminder thresholds, not by
   any fill gate or the capacity display in this tree

## Testing
Run the test suite:
```bash
python3 -m pytest -q   # full suite (fill-quota, weekday allowance, daily limits, ...)
```

This validates all functionality including setting limits, checking capacity, and cleanup operations.
