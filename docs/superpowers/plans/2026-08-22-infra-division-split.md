# Infra Division Split Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Split the legacy `INFRA` division into `INFRA_DELIVERY` and `INFRA_OPERATION`, enforce the approved monthly and transactional Bot rules, preserve the dashboard weekend override, and migrate old databases without losing members, schedules, or settings.

**Architecture:** `core/database.py` remains the single source of truth for canonical groups, migration, settings, and Bot mutations. Public read helpers continue to open their own connection for ordinary callers, while each Bot mutation runs through one fresh SQLite connection per retry attempt and passes that connection to private transaction-aware helpers. Web, scheduler, report, CSV, and Telegram presentation code consume the canonical four-group set and never write legacy values.

**Tech Stack:** Python 3.12, `sqlite3`, Flask 3, Flask-Login, pyTelegramBotAPI, APScheduler, pytest/unittest-style repository tests, temporary SQLite databases.

## Global Constraints

- The only canonical groups are, in this order: `INFRA_DELIVERY`, `INFRA_OPERATION`, `APPS`, `MONITORING`.
- `CE` and input `INFRA` normalize to `INFRA_OPERATION`; canonical values are used for all new writes and UI options.
- `user_groups` must have the exact four-value CHECK constraint; migration must rebuild any non-exact existing constraint, including an old three-group constraint whose SQL does not contain `CE`.
- `create_tables()` must create the canonical table on a fresh database, rebuild an old table before any canonical writes, and never run the obsolete `UPDATE ... = 'INFRA'` against the new constraint.
- `INFRA_DELIVERY` has exactly one Bot `/start` schedule per target month and a fixed monthly maximum of 1; `/batal_jadwal` may leave zero schedules.
- `INFRA_OPERATION` defaults to `max_hari_infra_operation = 5`; `APPS` and `MONITORING` retain `max_hari_apps = 31` and `max_hari_monitoring = 31`.
- The old `max_hari_infra` setting is deleted after migration and is not read by new code. The existing `kuota_infra` daily setting remains the shared Infra daily-quota setting for both canonical Infra groups; web daily-limit and weekend override behavior remains intact.
- A swap request with `tanggal_a == tanggal_b` is rejected before source-row validation and mutation. It is not a no-op: web weekend override may create multiple users on one date, and `UNIQUE(user_id, tanggal)` makes sequential same-date row updates unsafe.
- Every Bot schedule save rejects a date occupied by any other `jadwal` row, regardless of whether the row was created by Bot or web. A user's own existing rows are excluded while that user edits their month.
- Save, swap, and cancellation use `BEGIN IMMEDIATE` before decision-making reads, one connection for all reads/writes, at most three retries only for lock errors, rollback on every failure, and no external side effect before commit.
- Lock exhaustion returns a structured failure with the exact user-facing retry text: `Jadwal belum tersimpan karena sistem sedang dipakai. Silakan coba lagi.`
- No mutation helper used inside a transaction may call a public helper that opens another connection.

## File Map

- Modify `core/database.py`: canonical constants, schema rebuild, settings migration, connection-aware read helpers, mutation result type, retry runner, save/swap/cancellation implementations, monthly-limit validation.
- Modify `migrate_monitoring.py`: delegate to the canonical idempotent database initialization instead of maintaining a contradictory three-group schema.
- Modify `handlers/user_handlers.py`: canonical group guidance, dynamic monthly-limit UI hints, authoritative save result handling, and atomic cancellation result handling.
- Modify `handlers/swap_handler.py`: consume structured swap results and keep pending requests actionable on lock/validation failure.
- Modify `handlers/admin_handlers.py`: canonical CSV examples and member-rule announcement text.
- Modify `web/app.py`: load all four canonical groups, canonical member assignment defaults, settings keys, and four-group schedule contexts while preserving the weekend override path.
- Modify `web/templates/members.html`: four canonical options and group cards with user-facing labels.
- Modify `web/templates/settings.html`: separate Delivery and Operation cards, fixed Delivery monthly maximum, editable Operation maximum, and unambiguous daily/monthly copy.
- Modify `web/templates/schedules.html`: four-group order and labels in the schedule assignment modal.
- Modify `core/scheduler.py`: four-group iteration, division-specific labels, and monthly reminder targets.
- Modify `core/monthly_report.py` and `web/templates/monthly_report.html`: four-group report data and readable division labels.
- Modify `test_web_weekend_override.py` and `test_google_sheets.py`: canonical test inputs while retaining the existing web override assertions.
- Create `test_infra_division_split.py`: migration, canonical input, Bot save, swap, cancellation, lock, conflict, and nested-connection regression coverage.
- Run `test_startup_dependencies.py` and the existing weekday/weekend tests unchanged unless an assertion must be extended for the new canonical labels.

---

### Task 1: Add failing migration and mutation contract tests

**Files:**
- Create: `test_infra_division_split.py`
- Modify: `test_web_weekend_override.py`
- Modify: `test_google_sheets.py`

**Interfaces:**
- Consumes the current public functions in `core.database`; the first test run is expected to fail because the canonical constants, migration, `MutationResult`, and transaction behavior do not exist yet.
- Produces the observable contract that later tasks must satisfy: exact schema migration, canonical normalization, atomic mutations, lock result reporting, and preserved web override.

- [ ] **Step 1: Create isolated SQLite helpers and migration tests**

Use a temporary database for every test and patch both `core.database.DB_NAME` and `config.DB_NAME`, because `core.database` currently imports the configured path at module load time. Include these concrete tests:

```python
import sqlite3
from contextlib import closing

from core import database as db

CANONICAL_CHECK = "CHECK(group_name IN ('INFRA_DELIVERY', 'INFRA_OPERATION', 'APPS', 'MONITORING'))"


def _schema_sql(path):
    with closing(sqlite3.connect(path)) as conn:
        row = conn.execute(
            "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'user_groups'"
        ).fetchone()
    return row[0]


def test_old_three_group_schema_without_ce_is_rebuilt(tmp_path, monkeypatch):
    path = str(tmp_path / 'old-no-ce.sqlite')
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
```

The old-with-`CE` fixture is deliberately separate from the old three-value/no-`CE` fixture: SQLite cannot insert a `CE` row into a CHECK constraint that does not permit `CE`, while the migration must still prove both cases.

- [ ] **Step 2: Add canonical input and daily-quota contract tests**

Add exact assertions for legacy normalization and the shared existing daily quota:

```python
def test_group_input_normalizes_legacy_infra_and_ce(tmp_path, monkeypatch):
    monkeypatch.setattr(db, 'DB_NAME', str(tmp_path / 'groups.sqlite'))
    db.create_tables()

    db.set_user_group(1, 'Legacy Infra', 'legacy_infra', 'INFRA')
    db.set_user_group(2, 'Legacy CE', 'legacy_ce', 'CE')
    db.set_user_group(3, 'Delivery', 'delivery', 'INFRA_DELIVERY')

    assert db.get_user_group(1) == 'INFRA_OPERATION'
    assert db.get_user_group(2) == 'INFRA_OPERATION'
    assert db.get_user_group(3) == 'INFRA_DELIVERY'


def test_both_infra_groups_use_existing_daily_quota_setting(tmp_path, monkeypatch):
    monkeypatch.setattr(db, 'DB_NAME', str(tmp_path / 'quota.sqlite'))
    db.create_tables()
    db.set_setting('kuota_infra', '2')

    assert db.get_group_quota('INFRA_DELIVERY') == 2
    assert db.get_group_quota('INFRA_OPERATION') == 2
```

- [ ] **Step 3: Add Bot save, conflict, and atomicity tests**

Use helpers that register users, then assert `result.ok`, `result.error_code`, and unchanged rows. Cover these exact cases: Delivery zero dates fails; Delivery one free date succeeds; Delivery two dates fails; Operation rejects three dates when its setting is 2; APPS and MONITORING reject values above their settings; another user's row blocks a selected date; the current user's own row can be retained while replacing the rest; invalid dates outside the target month fail before deletion; every validation failure preserves the old monthly rows.

- [ ] **Step 4: Add web-created weekend conflict coverage**

Create two canonical users, add a weekend row for user A through `add_jadwal_manual`, then call the Bot save function for user B on that date. Assert a date-conflict failure, assert the weekend row still exists, and keep the existing `test_web_weekend_override.py` scenario proving the web route still permits multiple users and weekend dates while rejecting an exact duplicate.

- [ ] **Step 5: Add swap, cancellation, retry, and nested-connection tests**

The new file must cover:

1. A valid swap updates both source rows and marks the request `APPROVED`.
2. A request with `tanggal_a == tanggal_b` is rejected before source-row validation and leaves both schedules and the request `PENDING`; this explicitly handles same-date rows created through the web weekend override.
3. A missing or re-owned source row rejects the swap and leaves the request `PENDING`.
4. An unrelated row on either source date rejects the swap; only the exact two expected `(user_id, tanggal)` rows may be excluded.
5. Delivery post-state zero or two schedules rejects a swap; Operation/APPS/MONITORING post-state over-limit rejects it.
6. A valid multi-date cancellation deletes all requested rows atomically, a stale multi-date cancellation deletes none, and deleting a Delivery member's last schedule succeeds.
7. Lock exhaustion returns `error_code == 'database_locked'`, performs exactly three attempts, and leaves schedules/request status unchanged. Patch the retry-delay constant to zero in this test so the test is deterministic.
8. Wrap `db.connect_db` with a tracking context manager, execute one successful save, swap, and cancellation, and assert that each mutation opens exactly one connection. Also wrap each private transaction-aware helper to record `id(conn)` and assert every recorded ID equals the mutation connection ID.

Define the expected result surface in the test module before implementation:

```python
assert result.ok is False
assert result.error_code == 'database_locked'
assert result.message == db.LOCK_RETRY_MESSAGE
assert result.rows_affected == 0
```

- [ ] **Step 6: Run only the new tests and confirm they fail for missing behavior**

Run:

```bash
pytest -q test_infra_division_split.py
```

Expected: failures identify the old three-group schema, missing Operation setting, legacy normalization, non-transactional mutation results, and absent nested-connection protections. Do not change production code in this task; use the failure list to drive the following tasks.

- [ ] **Step 7: Commit the contract tests**

```bash
git add test_infra_division_split.py test_web_weekend_override.py test_google_sheets.py
git commit -m "test: define infra division split contracts"
```

---

### Task 2: Implement canonical schema rebuild and settings migration

**Files:**
- Modify: `core/database.py:12-205, 585-615`
- Modify: `migrate_monitoring.py:1-60`

**Interfaces:**
- Produces `GROUP_NAMES`, `GROUP_LABELS`, `normalize_group_name`, canonical `create_tables()`, idempotent old-schema rebuild, `get_monthly_limit_for_group`, and settings defaults used by later tasks.
- Preserves the existing public `set_user_group`, `get_user_group`, `get_all_users_in_group`, daily quota, and web helper behavior.

- [ ] **Step 1: Replace the old constants and normalization map**

Set the constants exactly as follows:

```python
GROUP_NAMES = (
    'INFRA_DELIVERY',
    'INFRA_OPERATION',
    'APPS',
    'MONITORING',
)
GROUP_LABELS = {
    'INFRA_DELIVERY': 'Infra Delivery',
    'INFRA_OPERATION': 'Infra Operation',
    'APPS': 'APPS',
    'MONITORING': 'MONITORING',
}
LEGACY_GROUP_ALIASES = {
    'CE': 'INFRA_OPERATION',
    'INFRA': 'INFRA_OPERATION',
}
GROUP_QUOTA_SETTING_KEYS = {
    'INFRA_DELIVERY': 'kuota_infra',
    'INFRA_OPERATION': 'kuota_infra',
    'APPS': 'kuota_apps',
    'MONITORING': 'kuota_monitoring',
}
GROUP_DEFAULT_QUOTAS = {
    'INFRA_DELIVERY': 1,
    'INFRA_OPERATION': 1,
    'APPS': 1,
    'MONITORING': 1,
}
MONTHLY_LIMIT_SETTING_KEYS = {
    'INFRA_OPERATION': 'max_hari_infra_operation',
    'APPS': 'max_hari_apps',
    'MONITORING': 'max_hari_monitoring',
}
MONTHLY_DEFAULT_LIMITS = {
    'INFRA_DELIVERY': 1,
    'INFRA_OPERATION': 5,
    'APPS': 31,
    'MONITORING': 31,
}
```

`normalize_group_name()` must uppercase/strip first and return the alias target, so all legacy writes become `INFRA_OPERATION`.

- [ ] **Step 2: Make fresh table creation canonical before migration runs**

Change every `CREATE TABLE user_groups` definition in `create_tables()` and the temporary rebuild table to use exactly:

```sql
 group_name TEXT NOT NULL CHECK(group_name IN ('INFRA_DELIVERY', 'INFRA_OPERATION', 'APPS', 'MONITORING'))
```

Do not leave the old three-value CHECK in the fresh-create path. Keep the single `conn.commit()` at the end of `create_tables()` so schema rebuild, data copy, and settings migration commit together.

- [ ] **Step 3: Replace string-based CE detection with exact-constraint detection**

Rewrite `_ensure_user_groups_schema(cur)` so it:

1. Reads `sqlite_master.sql` for `user_groups`.
2. Extracts the `group_name IN (...)` values while tolerating SQLite-added whitespace/casing.
3. Compares the ordered extracted values to `GROUP_NAMES`; a table is canonical only when all four values and their order match.
4. Returns without rebuilding only for that exact canonical set.
5. Otherwise creates `user_groups_new` with the canonical CHECK, reads all old rows, applies `normalize_group_name()` to each group, verifies the normalized value is in `GROUP_NAMES`, inserts `user_id`, `username`, `telegram_username`, and normalized group, then drops/renames the table.

The old/no-`CE` table must rebuild even though its SQL contains no `CE`. An invalid unknown legacy value must raise and let the surrounding `create_tables()` transaction roll back instead of silently dropping or inventing a group.

- [ ] **Step 4: Remove the obsolete legacy update path**

Delete `_migrate_ce_to_infra()` and its call, or replace it with a settings-only migration that never executes `UPDATE user_groups SET group_name = 'INFRA'`. After `_ensure_user_groups_schema()` returns, every row is already canonical. This directly prevents the fresh-database failure where a four-value CHECK rejects the old `INFRA` update.

- [ ] **Step 5: Migrate settings in the same initialization transaction**

Add a private cursor-based settings initializer called from `create_tables()` after the `settings` table exists:

```python
DEFAULT_SETTINGS = (
    ('kuota_infra', '1', 'Jumlah orang Infra per hari untuk setiap divisi Infra'),
    ('max_hari_infra_operation', '5', 'Maksimal hari standby per bulan untuk Infra Operation'),
    ('kuota_apps', '1', 'Jumlah orang APPS per hari'),
    ('max_hari_apps', '31', 'Maksimal hari standby per bulan untuk APPS'),
    ('kuota_monitoring', '1', 'Jumlah orang Monitoring per hari'),
    ('max_hari_monitoring', '31', 'Maksimal hari standby per bulan untuk Monitoring'),
)
```

Insert each missing key without overwriting an administrator's current canonical value, then delete `max_hari_infra`, `kuota_ce`, and `max_hari_ce`. The Operation default must always be 5 when the new key is absent; never copy the old combined Infra value. Keep `init_default_settings()` as an idempotent public wrapper around the same cursor helper for callers that still invoke it.

- [ ] **Step 6: Update normalization-aware public group helpers**

Make `set_user_group()` validate against the new `GROUP_NAMES` after normalization. Make `get_group_quota()`, `get_group_assignment_count_for_date()`, and `get_group_quota_status_for_date()` normalize input and iterate the four canonical groups. Add:

```python
def get_monthly_limit_for_group(group_name):
    canonical = normalize_group_name(group_name)
    if canonical == 'INFRA_DELIVERY':
        return 1
    key = MONTHLY_LIMIT_SETTING_KEYS.get(canonical)
    default = MONTHLY_DEFAULT_LIMITS.get(canonical, 31)
    try:
        return max(0, int(get_setting(key, default))) if key else default
    except (TypeError, ValueError):
        return default
```

Later transaction code will use a private connection variant rather than this public wrapper.

- [ ] **Step 7: Make the standalone migration safe and non-contradictory**

Replace the hand-written old three-group SQL in `migrate_monitoring.py` with an import of `create_tables()` and a small `migrate_user_groups()` function that prints the configured path, calls `create_tables()`, and reports success or the exception. It must not create `user_groups_new` with the old CHECK or perform a legacy `INFRA` update.

- [ ] **Step 8: Run migration and canonical-input tests**

Run:

```bash
pytest -q test_infra_division_split.py -k 'schema or group_input or daily_quota'
```

Expected: all migration, idempotence, setting, alias, and daily-quota tests pass. Then commit:

```bash
git add core/database.py migrate_monitoring.py
git commit -m "feat: migrate user groups to canonical infra divisions"
```

---

### Task 3: Add the shared transaction runner and connection-aware validators

**Files:**
- Modify: `core/database.py:49-60, 217-290, 369-478, 538-665, 865-1033`

**Interfaces:**
- Produces `MutationResult`, `LOCK_RETRY_MESSAGE`, `_run_mutation_with_retry`, and private helpers suffixed `_with_conn`.
- Required private helpers include `_get_setting_with_conn`, `_get_user_group_with_conn`, `_get_user_jadwal_for_month_with_conn`, `_get_tukar_request_by_id_with_conn`, `_get_daily_limit_with_conn`, `_get_assignment_count_for_date_with_conn`, `_get_group_quota_with_conn`, `_get_group_assignment_count_for_date_with_conn`, and `_is_weekend_fallback_active_for_user_with_conn`.
- Public helpers remain wrappers for non-transaction callers; later Bot mutations call private helpers directly.

- [ ] **Step 1: Define the result and retry contract**

Add:

```python
from dataclasses import dataclass
import time

LOCK_RETRY_MESSAGE = 'Jadwal belum tersimpan karena sistem sedang dipakai. Silakan coba lagi.'
MUTATION_MAX_ATTEMPTS = 3
MUTATION_RETRY_DELAYS = (0.05, 0.10)
MUTATION_BUSY_TIMEOUT_MS = 1000

@dataclass(frozen=True)
class MutationResult:
    ok: bool
    error_code: str | None = None
    message: str | None = None
    rows_affected: int = 0
```

Use `rows_affected` for cancellation and zero for save/swap.

- [ ] **Step 2: Implement one-connection-per-attempt retry execution**

Implement `_run_mutation_with_retry(operation)` with this behavior:

```python
for attempt in range(MUTATION_MAX_ATTEMPTS):
    with connect_db() as conn:
        conn.execute(f'PRAGMA busy_timeout = {MUTATION_BUSY_TIMEOUT_MS}')
        try:
            conn.execute('BEGIN IMMEDIATE')
            result = operation(conn)
            if result.ok:
                conn.commit()
            else:
                conn.rollback()
            return result
        except sqlite3.OperationalError as exc:
            conn.rollback()
            if 'database is locked' not in str(exc).lower():
                return MutationResult(False, 'database_error', str(exc))
            if attempt == MUTATION_MAX_ATTEMPTS - 1:
                return MutationResult(False, 'database_locked', LOCK_RETRY_MESSAGE)
    time.sleep(MUTATION_RETRY_DELAYS[attempt])
```

Use a fresh `connect_db()` invocation on every iteration. Rollback before every return after a begun transaction. Domain validation must return a failed `MutationResult`, not raise, so it is never retried. Do not perform Telegram, Google Sheets, or other external work in `operation`.

- [ ] **Step 3: Add same-connection read helpers**

Each helper accepts `conn` as its first argument and returns the same shape as its public counterpart. Implement SQL directly on `conn`, not by calling a public helper. The setting and group helpers must normalize group names. The monthly-limit helper returns Delivery `1`, Operation setting/default `5`, APPS setting/default `31`, and Monitoring setting/default `31`.

- [ ] **Step 4: Make weekend fallback transaction-aware**

Implement `_is_weekend_fallback_active_for_user_with_conn(conn, user_id, tahun, bulan, candidate_dates=None, excluded_rows=())`:

1. If `candidate_dates` is supplied, derive the user's already-selected weekend types from that final list; otherwise read the user's rows through `conn`.
2. Determine remaining weekend types (`5` and `6` minus selected types); if none remain, return `False`.
3. For every Saturday/Sunday in the month, read the daily limit and assignment count through `conn`, excluding only the `excluded_rows` `(user_id, tanggal)` pairs that will disappear during the mutation.
4. Return `True` only when every date for each remaining type is at or above its limit.

The public `is_weekend_fallback_active_for_user()` remains a wrapper that opens one connection and calls this helper. No connection-aware path may call `get_daily_limit()`, `get_assignment_count_for_date()`, or another public wrapper.

- [ ] **Step 5: Add pure candidate validation helpers**

Add private validators with explicit results:

- `_normalize_month_dates(list_of_tanggal, tahun, bulan)` parses `%Y-%m-%d`, rejects duplicates, rejects dates outside the target month, and returns sorted unique strings.
- `_validate_month_candidate(...)` checks Delivery exact-one, other monthly limits, weekend monthly limits, weekday/weekend balance using the connection-aware fallback, and returns the first specific `MutationResult` failure.
- `_find_bot_date_conflicts_with_conn(conn, user_id, dates)` selects every `jadwal` row on the selected dates where `user_id != ?`; it must not consult provenance because the table has none.

Use error codes `invalid_dates`, `delivery_exact_one`, `monthly_limit`, `weekend_limit`, `weekday_balance`, and `date_conflict` so handlers can show specific callback alerts.

- [ ] **Step 6: Run nested-connection tests after helper extraction**

Run:

```bash
pytest -q test_infra_division_split.py -k 'nested or fallback'
```

At this point the mutation functions may still fail their result assertions, but helper instrumentation must show that the new private helpers accept and use the same connection. Commit:

```bash
git add core/database.py
git commit -m "feat: add transaction-aware database primitives"
```

---

### Task 4: Implement authoritative Bot monthly save

**Files:**
- Modify: `core/database.py:271-291`
- Modify: `handlers/user_handlers.py:578-660`

**Interfaces:**
- Changes `update_user_jadwal_for_month(...)` to return `MutationResult`.
- The Bot save callback consumes `result.ok`, `result.error_code`, `result.message`, and only clears its session or syncs Google Sheets after `result.ok`.

- [ ] **Step 1: Replace `update_user_jadwal_for_month` with a transaction operation**

The operation passed to `_run_mutation_with_retry` must execute in this order:

1. Read the user's canonical group with `_get_user_group_with_conn`.
2. Read the current monthly limit with `_get_monthly_limit_with_conn`.
3. Normalize and validate every selected date, including the target month and Delivery exact-one rule.
4. Validate weekend limits, weekday/weekend balance, and fallback using the same `conn` and excluding the current user's existing target-month rows from availability counts.
5. Query every selected date for any other user's row; reject all conflicts, including web-created weekend rows.
6. Delete the current user's target-month rows only after all validation passes.
7. Insert the final dates with the supplied name and Telegram username.
8. Return `MutationResult(True)`.

The function must never delete old rows before validation. A failed result rolls back, and a lock result leaves the old schedule unchanged.

- [ ] **Step 2: Remove stale pre-save authority from the callback**

Keep calendar checks as guidance, but make the save callback call the database mutation even when the UI selection is empty or appears valid. Do not use the callback's earlier `get_setting()` or fallback result as the authority. Map failures as follows:

```python
SAVE_ERROR_MESSAGES = {
    'delivery_exact_one': 'Infra Delivery harus memiliki tepat 1 jadwal pada bulan ini.',
    'monthly_limit': 'Jumlah jadwal melebihi batas bulanan divisi Anda.',
    'date_conflict': 'Salah satu tanggal sudah diambil anggota lain.',
    'weekend_limit': 'Batas jadwal Sabtu/Minggu per bulan terlampaui.',
    'weekday_balance': 'Batas keseimbangan weekday/weekend terlampaui.',
    'database_locked': db.LOCK_RETRY_MESSAGE,
}
```

Use `result.message` when present, otherwise the map, and retain the session on failure. Delete the Telegram calendar session only after a successful commit.

- [ ] **Step 3: Move Google Sheets synchronization after commit**

Leave `sync_jadwal_to_sheets()` outside `update_user_jadwal_for_month`; call it only in the success branch after the database result is committed. Read the canonical group after commit for the side effect. A failed or locked save must not send any sync entry.

- [ ] **Step 4: Update monthly UI guidance for all four groups**

In the toggle path, use `INFRA_DELIVERY: 1`, `INFRA_OPERATION: max_hari_infra_operation/default 5`, `APPS: max_hari_apps/default 31`, and `MONITORING: max_hari_monitoring/default 31`. Use exact labels `Infra Delivery`, `Infra Operation`, `APPS`, and `MONITORING`. The UI may disable an apparently full date, but it must not be treated as backend authorization.

- [ ] **Step 5: Run save tests**

Run:

```bash
pytest -q test_infra_division_split.py -k 'save or conflict or web_created'
```

Expected: Delivery exact-one, Operation/APPS/Monitoring limits, own-row replacement, global conflict, validation rollback, and post-web-override conflict tests pass. Commit:

```bash
git add core/database.py handlers/user_handlers.py
git commit -m "feat: enforce transactional monthly schedule saves"
```

---

### Task 5: Implement atomic swap and cancellation mutations

**Files:**
- Modify: `core/database.py:403-478, 538-554`
- Modify: `handlers/swap_handler.py:134-163`
- Modify: `handlers/user_handlers.py:676-723`

**Interfaces:**
- `execute_swap(request_id)` returns `MutationResult` and re-reads the request inside the mutation connection.
- `delete_user_jadwal_on_dates(user_id, list_of_tanggal_to_delete)` returns `MutationResult` with `rows_affected`.
- The two handlers retain pending/session state on failure and report actual committed outcomes.

- [ ] **Step 1: Rebuild `execute_swap` around one transaction snapshot**

Inside `_run_mutation_with_retry`, implement this exact sequence:

1. Read the pending request using `_get_tukar_request_by_id_with_conn`; reject missing/non-`PENDING` requests without changing anything.
2. Parse both dates, reject malformed dates and reject `tanggal_a == tanggal_b` before source-row validation; verify same-day-type rules with the pure validator only after the dates differ.
3. Read both source rows by exact `(user_id, tanggal)` and require one expected row for each. A same-date request must never reach sequential row updates because `UNIQUE(user_id, tanggal)` permits only one row per owner/date.
4. For each source date, select all `jadwal` rows and remove only the one expected source tuple from the in-memory result. Reject if anything remains, including a web-created row.
5. Read both users' canonical group/name data through `conn`.
6. Build final monthly date lists grouped by `(year, month)` for every affected month: remove each source date from its owner and add the other date to the recipient. Reject a duplicate date already owned by a recipient.
7. Revalidate each user's final list with the same connection: Delivery exact-one, configured monthly maximum, weekend limits, weekday/weekend balance, and fallback with only the two source rows excluded from occupancy counts.
8. Update each source row with exact `WHERE user_id = ? AND tanggal = ?` predicates and require `rowcount == 1` for both updates.
9. Mark the request `APPROVED` only after both row updates succeed and require one updated request row.
10. Return success; commit is performed only by the retry runner.

Any stale row, conflict, invalid post-state, or lock failure must leave both schedules and request status unchanged. Do not fetch the request before `BEGIN IMMEDIATE`.

- [ ] **Step 2: Update swap callback handling**

Call `execute_swap()` once on approval. On failure, map `database_locked`, `stale_request`, `swap_conflict`, `delivery_exact_one`, `monthly_limit`, and validation errors to a callback alert/message. Do not mark the request rejected merely because the operation was locked or transiently invalid; the approved request remains `PENDING` for a later retry unless the user explicitly rejects it. Keep Telegram side effects after the database result.

- [ ] **Step 3: Replace cancellation with all-or-nothing ownership validation**

Implement `delete_user_jadwal_on_dates()` through `_run_mutation_with_retry`:

1. Return a successful zero-row result for an empty list only when called directly; the Bot UI still blocks an empty selection.
2. Parse every requested date and reject malformed/duplicate values.
3. Select all requested rows for the user through `conn` and require every requested date to be present. If one is missing, return `stale_schedule` and delete nothing.
4. Delete only `WHERE user_id = ? AND tanggal IN (...)`, require the row count to equal the requested count, and commit atomically.
5. Do not enforce Delivery's exact-one minimum; deleting its last schedule is the approved exception.

- [ ] **Step 4: Update Bot cancellation UX**

Use `result.rows_affected` in the confirmation: `✅ Berhasil membatalkan {rows_affected} jadwal.` Delete the cancellation session only after success. On stale or lock failure, keep the session and show a retryable alert; never claim rows were deleted.

- [ ] **Step 5: Run swap and cancellation tests**

Run:

```bash
pytest -q test_infra_division_split.py -k 'swap or cancellation or lock'
```

Expected: all valid, stale, conflict, Delivery post-state, configured-limit, lock, and nested-connection assertions pass. Commit:

```bash
git add core/database.py handlers/swap_handler.py handlers/user_handlers.py
git commit -m "feat: make swap and cancellation atomic"
```

---

### Task 6: Update web member management, settings, and schedule views

**Files:**
- Modify: `web/app.py:15-30,119-340,394-492,633-653`
- Modify: `web/templates/members.html:45-157`
- Modify: `web/templates/settings.html:14-140`
- Modify: `web/templates/schedules.html:209-260`

**Interfaces:**
- Web routes accept canonical group options and legacy `INFRA` through database normalization.
- Web weekend override behavior in `/schedules/add` remains exactly as before: weekend additions bypass daily/group/monthly balance checks but exact duplicate `(user_id, tanggal)` is rejected.
- Templates receive canonical group IDs and display labels without reintroducing `INFRA` as a selectable value.

- [ ] **Step 1: Centralize four-group member loading in `web/app.py`**

Import `GROUP_NAMES` and `GROUP_LABELS`, then define a local helper inside `create_app()`:

```python
def load_member_groups():
    groups = {
        group_name: [dict(member) for member in get_all_users_in_group(group_name)]
        for group_name in GROUP_NAMES
    }
    all_members = [member for group in groups.values() for member in group]
    return groups, all_members
```

Use it in login, dashboard, members, and schedules routes. Pass `members_by_group` and `all_members`; preserve any existing individual template variables only where an existing template still requires them. Ensure the schedule `group_quotas` object contains all four canonical keys.

- [ ] **Step 2: Update add/edit route defaults and messages**

Change `request.form.get('group_name', 'INFRA')` to default to `INFRA_OPERATION`. `set_user_group()` remains the final validator and continues to normalize legacy imports. Flash messages should use `GROUP_LABELS.get(canonical_group, canonical_group)` rather than exposing the legacy alias.

- [ ] **Step 3: Update the members template**

Replace both select lists with these four options in canonical order:

```html
<option value="INFRA_DELIVERY">Infra Delivery</option>
<option value="INFRA_OPERATION">Infra Operation</option>
<option value="APPS">APPS</option>
<option value="MONITORING">MONITORING</option>
```

Replace the group-card list with four entries using `members_by_group['INFRA_DELIVERY']` and `members_by_group['INFRA_OPERATION']`. Use readable headings `Infra Delivery` and `Infra Operation`, retain APPS/Monitoring cards, and keep the edit modal's `data-group` canonical.

- [ ] **Step 4: Update settings route and template**

The POST route must write exactly:

```python
keys = [
    'kuota_infra',
    'kuota_apps',
    'kuota_monitoring',
    'max_hari_infra_operation',
    'max_hari_apps',
    'max_hari_monitoring',
]
```

Do not accept or write `max_hari_infra`. Render four cards:

- Infra Delivery: editable shared `kuota_infra` daily slot setting, fixed text `Maksimal Hari / Bulan: 1`, and no monthly input.
- Infra Operation: text explaining the shared `kuota_infra` daily slot setting and editable `max_hari_infra_operation`, default `5`, max `31`.
- APPS and MONITORING: unchanged editable daily and monthly settings.

Use copy that explicitly distinguishes `Kuota Harian` from `Maksimal Hari / Bulan` and states that Delivery's `/start` save requires exactly one date.

- [ ] **Step 5: Update schedule view group order and labels**

Set the JavaScript order to:

```javascript
const groupOrder = ['INFRA_DELIVERY', 'INFRA_OPERATION', 'APPS', 'MONITORING'];
```

Render `GROUP_LABELS`-equivalent display text in the quota panel while retaining canonical IDs in form data. Do not change the server-side weekend override logic or its duplicate check.

- [ ] **Step 6: Run web behavior tests and template smoke checks**

Run:

```bash
python test_web_weekend_override.py
pytest -q test_infra_division_split.py -k 'web or settings or group_input'
```

Expected: the existing weekend override still permits two users on a weekend date and one user on Saturday plus Sunday, rejects the exact duplicate, and the new route/template checks expose four groups and the new Operation setting. Commit:

```bash
git add web/app.py web/templates/members.html web/templates/settings.html web/templates/schedules.html test_web_weekend_override.py
git commit -m "feat: update dashboard for infra division split"
```

---

### Task 7: Update Telegram admin UX, scheduler, reports, and Sheets consumers

**Files:**
- Modify: `handlers/admin_handlers.py:38-49,231-289`
- Modify: `handlers/user_handlers.py:250-255,382-402,725-748`
- Modify: `core/scheduler.py:11-256,301-355`
- Modify: `core/monthly_report.py:5-219`
- Modify: `web/templates/monthly_report.html:45-155`
- Modify: `test_google_sheets.py:44-70`

**Interfaces:**
- All group iterations use `GROUP_NAMES`; all display text uses `GROUP_LABELS` or explicit readable labels.
- Google Sheets receives canonical group values from database rows; no legacy `INFRA` value is emitted by new writes.
- Reminder targets use the actual current monthly rule per group instead of hardcoded three-schedule advice.

- [ ] **Step 1: Update admin announcements, CSV examples, and validation copy**

Change announcement/help text to state:

```text
- Infra Delivery wajib memilih tepat 1 jadwal per bulan saat menyimpan melalui /start.
- Infra Operation mengikuti maksimal hari/bulan yang diatur Admin (default 5).
- APPS dan MONITORING mengikuti maksimal hari/bulan pada Settings.
- Setiap orang maksimal 1 Sabtu dan 1 Minggu setiap bulan.
- Tukar jadwal harus tipe hari yang sama.
```

Show CSV examples using `INFRA_DELIVERY` and `INFRA_OPERATION`, while explicitly stating that legacy input `INFRA` is accepted and mapped to Infra Operation. Keep `normalize_group_name(row[3])` before `GROUP_NAMES` validation.

- [ ] **Step 2: Update Bot guide and no-group messages**

Replace `(INFRA/APPS/MONITORING)` with `(INFRA_DELIVERY/INFRA_OPERATION/APPS/MONITORING)` and include the Delivery exact-one and Operation default-five rules in both guide locations in `handlers/user_handlers.py`.

- [ ] **Step 3: Refactor scheduler group loops without changing unrelated scheduling**

Replace hardcoded three-group tuples and `jadwal_infra`/`users_infra` branches with dictionaries keyed by `GROUP_NAMES`. For each canonical group, use `get_jadwal_by_group`, `get_all_users_in_group`, `get_group_quota`, and `GROUP_LABELS`. Keep daily-limit checks and Telegram timing unchanged. Error messages and headings must display `Infra Delivery` or `Infra Operation` rather than the old combined `INFRA`.

- [ ] **Step 4: Make the unfilled-month reminder division-specific**

In `build_pesan_peringatan_pengisian_jadwal()`, compute each member's target with `get_monthly_limit_for_group(user['group_name'])`. Include members whose count is below that target; Delivery members with zero schedules are called out as needing one, and Operation members use the configured current setting. Replace the hardcoded `total in (1, 2)`, `3 - total`, and `Target ... 3x` text with the actual target in each line.

- [ ] **Step 5: Update monthly report data and template labels**

Keep canonical `group_name` fields for machine-readable data, add `group_label` fields from `GROUP_LABELS` to per-group, per-user, under-quota, and over-quota entries, and iterate all four groups. Render `group_label` in `monthly_report.html` and Telegram text. Quota status must include both Infra groups independently while using the shared daily quota setting.

- [ ] **Step 6: Keep Sheets values canonical and update its test input**

Ensure every schedule passed to `sync_jadwal_to_sheets` uses the canonical `group_name` returned by the database. Change the integration test fixture's sample group from `INFRA` to `INFRA_OPERATION`; retain the disabled-sync behavior when credentials are unavailable.

- [ ] **Step 7: Run consumer regression tests**

Run:

```bash
pytest -q test_google_sheets.py test_weekday_weekend_rules.py
pytest -q test_infra_division_split.py -k 'report or scheduler or csv'
```

Commit:

```bash
git add handlers/admin_handlers.py handlers/user_handlers.py core/scheduler.py core/monthly_report.py web/templates/monthly_report.html test_google_sheets.py
git commit -m "feat: propagate canonical infra divisions"
```

---

### Task 8: Run full verification and review the complete cutover

**Files:**
- Modify only files identified by failing verification; do not add compatibility aliases or leave old settings/group paths in place.

**Interfaces:**
- The repository starts with a fresh database and with representative old databases.
- The web route, Bot mutation functions, scheduler/report imports, and startup dependency checks all work together.

- [ ] **Step 1: Search for obsolete group and setting consumers**

Run:

```bash
python -c "from pathlib import Path; import re; roots=[Path('core'),Path('handlers'),Path('web'),Path('templates')]; patterns=[r\"['\\\"]INFRA['\\\"]\", r\"['\\\"]CE['\\\"]\", r'max_hari_infra(?!_operation)', r'kuota_ce']; hits=[]; [hits.extend((str(p), i, line.rstrip()) for i,line in enumerate(p.read_text(encoding='utf-8').splitlines(),1) if any(re.search(pattern,line) for pattern in patterns)) for root in roots if root.exists() for p in root.rglob('*.py') if p.is_file()]; print(*hits, sep='\\n')"
```

The only permitted legacy `INFRA`/`CE` references are explicit normalization/compatibility tests and explanatory CSV/help text. No production code may read `max_hari_infra` or write a legacy group.

- [ ] **Step 2: Run all focused and regression tests**

Run the complete existing verification set:

```bash
pytest -q test_infra_division_split.py test_weekday_weekend_rules.py test_startup_dependencies.py
python test_web_weekend_override.py
python -m py_compile main.py config.py core/database.py core/scheduler.py core/monthly_report.py handlers/admin_handlers.py handlers/user_handlers.py handlers/swap_handler.py web/app.py
```

Then run the full test command used by the repository:

```bash
pytest -q
```

- [ ] **Step 3: Smoke-test fresh initialization and web app creation**

Use a temporary `DB_NAME` and run:

```bash
python -c "import tempfile; from pathlib import Path; import config; from core import database as db; path=str(Path(tempfile.mkdtemp())/'fresh.sqlite'); config.DB_NAME=path; db.DB_NAME=path; db.create_tables(); assert db.get_setting('max_hari_infra_operation') == '5'; assert db.get_setting('max_hari_infra') is None; assert db.GROUP_NAMES == ('INFRA_DELIVERY','INFRA_OPERATION','APPS','MONITORING'); from web.app import create_app; create_app(); print('fresh initialization and Flask app smoke test passed')"
```

This must complete without a CHECK-constraint error, nested legacy migration error, missing settings error, or import error.

- [ ] **Step 4: Exercise the actual dashboard surface**

Start the Flask app against the temporary database, log in with the seeded admin, and inspect `/members`, `/settings`, and `/schedules` in a browser or Flask test client. Verify the four member options, separate Delivery/Operation cards, fixed Delivery monthly value `1`, editable Operation value `5`, and four schedule quota entries. Submit a weekend schedule through the web route and confirm its row remains available to the Bot conflict test.

- [ ] **Step 5: Review migration and transaction evidence**

Confirm the focused test output contains evidence for: old-schema rebuild without `CE`, both legacy mappings, preserved schedule rows, idempotent second initialization, `BEGIN IMMEDIATE` lock retries, no nested connection in save/swap/cancellation, global date conflicts, atomic rollback, Delivery cancellation exception, and unchanged web weekend override.

- [ ] **Step 6: Commit only after verification is green**

```bash
git diff --check
git status --short
git add core handlers web migrate_monitoring.py test_infra_division_split.py test_web_weekend_override.py test_google_sheets.py
git commit -m "feat: split infra delivery and operation divisions"
```

Do not claim completion until the full test output and startup/web smoke output are available.

## Self-Review Against the Approved Specification

- **Canonical divisions/member assignment:** Tasks 2 and 6 change constants, normalization, CSV, member forms, edit modal, and all group contexts.
- **Migration:** Task 2 creates the new table on fresh DBs, rebuilds every non-exact constraint, maps both `CE` and `INFRA`, preserves all member fields and schedules, migrates settings, and removes the invalid legacy update path.
- **Daily assignment invariant:** Tasks 3 and 4 begin `BEGIN IMMEDIATE` before conflict reads, exclude only the editing user's own rows, and reject every other `jadwal` row.
- **Delivery/Operation/APPS/Monitoring monthly rules:** Tasks 3–5 implement current-settings reads, exact-one Delivery, Operation default/configured maximum, and APPS/Monitoring limits in the authoritative save and swap paths.
- **Cancellation exception:** Task 5 deliberately validates ownership but does not enforce a Delivery minimum.
- **Swap:** Task 5 re-reads the request, verifies exact source ownership, rejects unrelated rows, validates post-state across affected months, and marks approval only after both updates.
- **Locking/connection boundary:** Task 3 defines fresh connections, busy timeout, bounded lock-only retry, rollback behavior, and connection-aware helpers; Tasks 1 and 5 verify no nested connection.
- **External side effects:** Task 4 keeps Sheets synchronization after commit; swap/cancellation handlers report only committed database results.
- **Web override and UX:** Task 6 preserves weekend bypass behavior; Tasks 4, 5, and 7 update callback, cancellation, guide, announcement, report, and settings copy.
- **Tests and regressions:** Tasks 1 and 8 cover migration, save, swap, cancellation, locks, UI behavior, weekend override, weekday/weekend rules, startup imports, and full-suite verification.

Plan complete and saved to `docs/superpowers/plans/2026-08-22-infra-division-split.md`. Two execution options:

1. **Subagent-Driven (recommended)** — dispatch a fresh worker per task, review between tasks, and integrate with checkpoints.
2. **Inline Execution** — execute this plan in the current session with staged checkpoints.

Which approach should be used?
