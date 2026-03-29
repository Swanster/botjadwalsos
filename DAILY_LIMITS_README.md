# Daily Assignment Limits Feature

## Overview
This feature allows administrators to set flexible daily assignment limits for the schedule system. You can now control how many people can be assigned to work on each specific day.

## Features

### 1. Flexible Daily Limits
- Set different limits for different dates (e.g., Day 1: 1 person, Day 2: 2 people)
- Default limit of 1 person per day when no specific limit is set
- Priority over group-based quotas (INFRA/CE settings)

### 2. Web Administration Interface
Access the Daily Limits management through the web dashboard:
- **Navigation**: Click "Daily Limits" in the sidebar
- **Add Limit**: Select date and set maximum assignments
- **View Limits**: See all configured daily limits
- **Delete Limits**: Remove specific date limitations

### 3. Automatic Enforcement
- Users cannot select dates that are already full
- Real-time validation in the Telegram bot interface
- Scheduler warnings respect daily limits

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
- `set_daily_limit(tanggal, max_assignments)`: Set limit for specific date
- `get_daily_limit(tanggal, default_limit)`: Get limit with fallback
- `is_date_full(tanggal, default_limit)`: Check if date reached capacity
- `get_all_daily_limits()`: Retrieve all configured limits

### Integration Points
- **User Handlers**: Validation when users select dates
- **Scheduler**: Warning systems respect daily limits
- **Web Interface**: CRUD operations for limit management

## Priority System
1. **Daily Limits** (Highest priority) - Specific date configurations
2. **Group Quotas** (Fallback) - INFRA/CE group-based limits
3. **Default** (Lowest) - 1 person per day when nothing else is set

## Testing
Run the test suite:
```bash
python3 test_daily_limits.py
```

This validates all functionality including setting limits, checking capacity, and cleanup operations.