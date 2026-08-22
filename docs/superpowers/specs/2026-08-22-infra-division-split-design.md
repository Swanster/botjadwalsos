# Infra Division Split Design

**Date:** 2026-08-22
**Status:** Design approved for specification review
**Scope:** Split the existing `INFRA` member division into `Infra Delivery` and `Infra Operation`, while preserving `APPS` and `MONITORING` behavior.

## Goal

Allow administrators to assign members to `Infra Delivery` or `Infra Operation` from the Member tab, enforce the requested monthly rules in the Telegram Bot backend, and migrate existing `INFRA` data without losing members or schedules.

## Confirmed Business Rules

### Official divisions

The application will use exactly these four canonical group values:

- `INFRA_DELIVERY` — UI label: **Infra Delivery**
- `INFRA_OPERATION` — UI label: **Infra Operation**
- `APPS` — unchanged
- `MONITORING` — unchanged

The canonical group set is ordered as:

```python
GROUP_NAMES = (
    'INFRA_DELIVERY',
    'INFRA_OPERATION',
    'APPS',
    'MONITORING',
)
```

### Member assignment

- Administrators choose the division for each member in the Member tab.
- Existing members stored as `INFRA` are migrated automatically to `INFRA_OPERATION`.
- Existing members stored as legacy `CE` are also migrated to `INFRA_OPERATION`.
- Existing schedule rows are preserved; no schedule data is deleted by migration.
- The input alias `INFRA` remains accepted for legacy CSV imports and is normalized to `INFRA_OPERATION`.
- Canonical values are shown in the UI and used for new writes.

### Daily assignment behavior

- The Telegram Bot enforces one assignment per date across all divisions on its save path.
- The dashboard web keeps its current behavior, including the weekend admin override. The new Bot save invariant does not remove or alter that web override.
- Because `jadwal` currently has no Bot/web provenance field, the Bot conflict query treats every existing row for another user as occupied, including rows created through the web weekend override. The Bot never displaces such a row.
- A user editing their own monthly schedule is excluded from the conflict query for their own existing rows, so they can retain those rows while replacing the rest of their month.
- The Bot calendar's availability checks remain UI/session guidance only. The backend revalidates the rule at save time.

### Monthly member behavior

- `INFRA_DELIVERY`: when a member saves or edits their monthly schedule through the Bot `/start` flow, the final result must contain exactly one schedule in the target month. Zero schedules and more than one schedule are rejected.
- `INFRA_OPERATION`: the default maximum is 5 schedules per member per month. The administrator can change this value in Settings.
- `APPS`: continues to use `max_hari_apps`, default 31.
- `MONITORING`: continues to use `max_hari_monitoring`, default 31.
- `INFRA_DELIVERY` uses a fixed maximum of 1 and is not editable as a general setting.
- The Bot backend reads the current settings during every monthly save; stale UI/session state cannot bypass a changed limit.

### Cancellation exception

The exact-one Delivery rule applies to the `/start` save/edit operation. The user explicitly allows `/batal_jadwal` to cancel the last Delivery schedule, so cancellation may leave an `INFRA_DELIVERY` member with zero schedules for that month.

Cancellation remains atomic and lock-protected, but it does not require a minimum schedule count for Delivery. The member can use `/start` again later, and that save must produce exactly one schedule.

### Swap behavior

A Telegram schedule swap is a separate mutation and must preserve valid final state for both users:

- The swap is performed only if both source rows are still owned by the expected users.
- Because `jadwal` has no Bot/web provenance field, each affected date must contain exactly its expected source row and no other `jadwal` row. The conflict query excludes only the two source rows identified by `(user_id, tanggal)` for this request; every other row is a conflict, including a row created through the web weekend override.
- The swap never displaces or ignores an unrelated `jadwal` row, regardless of which interface created it.
- The resulting monthly schedules for both users are revalidated before mutation.
- `INFRA_DELIVERY` must remain exactly one schedule in every affected month for each Delivery user. A cross-month swap that would leave a Delivery user with zero or more than one schedule in an affected month is rejected.
- `INFRA_OPERATION`, `APPS`, and `MONITORING` must remain within their configured `max_hari` limits.
- Existing weekend/weekday and same-day-type swap rules remain enforced.

This preserves the approved exact-one invariant for swaps while keeping the explicit cancellation exception.

## Data Model and Migration

### Schema rebuild requirement

The current `user_groups` table has a SQLite `CHECK` constraint for the old three-group set. Updating rows in place would fail because the old constraint rejects `INFRA_OPERATION` and `INFRA_DELIVERY`.

Migration must rebuild `user_groups` whenever the existing table constraint is not exactly the canonical four-group set. It must not rely only on detecting the string `'CE'` in the table SQL.

Migration algorithm:

1. Inspect `sqlite_master.sql` for `user_groups` and determine whether its group constraint is exactly:

   ```sql
   CHECK(group_name IN ('INFRA_DELIVERY', 'INFRA_OPERATION', 'APPS', 'MONITORING'))
   ```

2. If it is not exact, create `user_groups_new` with the canonical four-group CHECK constraint.
3. Copy rows into `user_groups_new`, mapping:
   - `CE` → `INFRA_OPERATION`
   - `INFRA` → `INFRA_OPERATION`
   - canonical values unchanged
4. Drop the old `user_groups` table.
5. Rename `user_groups_new` to `user_groups`.
6. Preserve `user_id`, `username`, and `telegram_username`.
7. Commit the schema/data migration together.
8. Keep the migration idempotent: running initialization again must not rebuild or remap an already canonical table unnecessarily.

Settings migration/defaults:

- Create `max_hari_infra_operation` with value `5`; the confirmed new default is explicit and must not inherit a previous `max_hari_infra` value.
- Remove the obsolete `max_hari_infra` setting after the migration succeeds; no new code may read the old combined Infra key.
- Keep `max_hari_apps` and `max_hari_monitoring` unchanged.
- Keep existing daily quota settings and web daily-limit behavior unless directly required by the existing code path.

Migration verification must use a temporary SQLite database containing the tracked old schema and representative rows for `CE`, `INFRA`, `APPS`, and `MONITORING`. The test must verify:

- table creation succeeds under the new constraint;
- `CE` and `INFRA` rows become `INFRA_OPERATION`;
- existing `APPS` and `MONITORING` rows remain unchanged;
- usernames and Telegram usernames remain unchanged;
- existing `jadwal` rows remain present;
- settings remain present and the Operation default is initialized;
- a second initialization is idempotent.

## Backend Mutation Semantics

### Shared lock/retry policy

All Bot schedule mutations that can change ownership or counts use the following policy:

- Start the write transaction with `BEGIN IMMEDIATE` before any conflict or post-state SELECT.
- Use the same transaction snapshot for all validation reads and writes.
- Retry only `sqlite3.OperationalError` cases whose message indicates `database is locked`.
- Retry at most 3 times with a short increasing delay.
- On exhaustion, rollback and return a structured failure result that lets the Bot show: `Jadwal belum tersimpan karena sistem sedang dipakai. Silakan coba lagi.`
- Never partially delete, insert, swap, or mark a request approved after a lock failure.
- Non-lock validation failures rollback immediately without retry.

`BEGIN IMMEDIATE` serializes writers, but the implementation must not claim that a second session automatically reads the first commit. If the lock cannot be acquired within the configured SQLite timeout/retry policy, the operation fails clearly and the user retries.

### Transaction connection boundary

- Each retry attempt creates one fresh SQLite connection, configures its busy timeout, and begins `BEGIN IMMEDIATE` on that connection.
- After `BEGIN IMMEDIATE`, every read that can affect the mutation decision and every write must use that same `conn`/cursor until commit or rollback.
- Mutation code must not call public helpers that implicitly open another connection, including `get_setting()`, `get_user_group()`, `get_user_jadwal_for_month()`, `get_tukar_request_by_id()`, `get_assignment_count_for_date()`, or `is_weekend_fallback_active_for_user()`.
- Add transaction-aware private helper variants or connection parameters for these paths. At minimum, the transaction-aware forms must cover settings reads, member/group reads, jadwal reads and conflict counts, pending swap request reads, daily-limit reads, and weekend-fallback reads. Nested reads inside a weekend-fallback helper must use the same transaction connection as well.
- Public helpers may remain as wrappers for non-transaction callers, but the three Bot mutations must call the transaction-aware forms directly. Pure validators that only inspect supplied lists may remain connection-free.
- External side effects such as Google Sheets synchronization and Telegram notifications happen only after the database transaction commits; they are not part of the atomic database decision.
- Tests must verify that save, swap, and cancellation do not open a nested SQLite connection during an active mutation attempt and that a transaction-aware helper reads through the mutation connection.


### `update_user_jadwal_for_month`

This is the authoritative Bot `/start` save path.

For each attempt:

1. Open one database connection for the attempt, configure its busy timeout, and execute `BEGIN IMMEDIATE` on that connection.
2. Read the member's canonical group from `user_groups` through a transaction-aware helper using the same `conn`.
3. Read the relevant monthly limit from Settings through a transaction-aware helper using the same `conn`.
4. Validate the final selection list:
   - Delivery: exactly one date in the target month;
   - Operation/APPS/MONITORING: count does not exceed that division's `max_hari`;
   - existing weekend monthly limits;
   - existing weekday/weekend balance rules, including any database-backed weekend-fallback lookup through the same `conn`;
   - every selected date is in the target month and has valid date format;
   - every selected date has no existing `jadwal` row owned by another user, regardless of whether that row came from the Bot or the web.
5. The conflict query excludes rows belonging to the current `user_id`, so a user can keep their own existing dates while editing; all other `jadwal` rows are conflicts and the query uses the same `conn`.
6. Only after every validation passes, delete the current user's rows for the target month.
7. Insert the final selection list.
8. Commit.

If any validation fails, rollback before the old rows are deleted. This protects against stale sessions, direct save paths, and concurrent Bot saves.

### `execute_swap`

`execute_swap` is a separate Bot mutation and must not rely on checks performed when the request was created or displayed.

Inside a `BEGIN IMMEDIATE` retry attempt:

1. Re-read the pending request through a transaction-aware helper using the same `conn`.
2. Verify both source rows still exist and are owned by the expected users.
3. For each source date, query all `jadwal` rows for that date and exclude only its expected source row. Reject the swap if any row remains, including a row created through the web weekend override; no provenance distinction is available or allowed.
4. Build the post-swap monthly date lists for both users across every affected month through the same `conn`.
5. Revalidate Delivery exact-one, Operation/APPS/MONITORING `max_hari`, weekend monthly limits, weekday/weekend balance, and same-day-type rules; all settings and database-backed fallback reads use the same `conn`.
6. Perform both row ownership updates.
7. Mark the request `APPROVED` only after both updates succeed.
8. Commit atomically.

Any failed source/ownership/conflict/post-state validation rejects the swap and leaves both schedules and the request status unchanged. A lock exhaustion returns a retryable user-facing failure and does not approve the request.

### `delete_user_jadwal_on_dates`

This is the Bot `/batal_jadwal` mutation.

Inside a `BEGIN IMMEDIATE` retry attempt:

1. Normalize and validate the requested dates.
2. Verify every requested row is still owned by the requesting user in the target month(s) through the same `conn`; do not use a separate-connection jadwal helper.
3. If any requested row is stale or missing, rollback and reject the entire operation; do not partially delete other requested dates.
4. Delete only the verified rows owned by that user.
5. Commit atomically.

The operation intentionally does not require Delivery to retain one schedule because the user-approved cancellation exception allows Delivery to become zero. It must still never delete another user's schedule or partially apply a stale multi-date request. A lock exhaustion returns the same clear retry message and leaves all rows unchanged.

## Web UI and Settings

### Member tab

Update the add-member form, edit-member modal, and group cards to use the four canonical divisions:

- Infra Delivery
- Infra Operation
- APPS
- MONITORING

The administrator remains responsible for choosing which existing Infra member belongs to which new Infra division.

### Settings page

- Replace the combined Infra card with separate Delivery and Operation cards.
- Delivery shows a fixed monthly maximum of 1 and does not expose an editable maximum field.
- Operation shows editable `max_hari_infra_operation`, default 5.
- APPS and MONITORING retain their current editable monthly settings and behavior.
- Labels and help text must distinguish daily slot behavior from monthly per-member limits.

### Other consumers

Update group iteration, labels, reports, schedule views, CSV validation/normalization, scheduler messages, and Google Sheets group values to use the four canonical groups. Existing web weekend override behavior is intentionally preserved.

## Bot UX and Error Handling

- The Bot calendar may disable dates that appear full, but this is not authoritative.
- On save validation failure, show a specific callback alert for the violated rule where possible:
  - Delivery requires exactly one date;
  - monthly limit reached;
  - date already assigned;
  - existing weekend/weekday rule violation.
- On database lock exhaustion, show a clear retry message and leave the session available for another save attempt where the existing flow allows it.
- Update help/guide text so members understand the two Infra divisions and Delivery's one-schedule monthly rule.
- On cancellation, confirm the actual number of rows deleted; do not imply that Delivery still has a mandatory schedule after the explicit cancellation exception.

## Test Plan

Tests must cover observable behavior rather than implementation-only details.

### Migration and group behavior

- Rebuild an old three-group schema even when its SQL contains no `CE` value.
- Map both `CE` and `INFRA` to `INFRA_OPERATION` during rebuild.
- Preserve APPS/MONITORING rows, member fields, jadwal rows, and settings.
- Verify canonical four-group CHECK constraint.
- Verify initialization is idempotent.
- Verify add/edit/CSV input accepts canonical divisions and maps legacy `INFRA` to Operation.
- Verify a web-created weekend row is preserved and blocks a conflicting Bot save, while the web override itself remains available.

### Monthly save backend

- Delivery save with zero dates fails and preserves existing rows.
- Delivery save with one date succeeds if the date is free.
- Delivery save with two dates fails and preserves existing rows.
- Operation rejects more than the configured limit, including when the selection bypasses UI toggles.
- APPS and MONITORING continue enforcing their configured limits in the backend.
- A selected date already owned by another `jadwal` row is rejected, including a row created through the web weekend override.
- Validation failure leaves the previous monthly schedule unchanged.
- Concurrent/save-lock scenarios exercise `BEGIN IMMEDIATE`, bounded retry, rollback, and the clear lock failure result.
- The save test detects any nested connection opened after `BEGIN IMMEDIATE` and verifies settings, group, fallback, and conflict reads use the transaction connection.

### Swap mutation

- Swap rejects a stale request when either source row changed ownership or disappeared.
- Swap rejects a date containing any other `jadwal` row, including a row created through the web weekend override; only the two expected source rows may be excluded from the conflict check.
- Swap rejects a post-state Delivery 0/>1 result in an affected month.
- Swap rejects a post-state Operation/APPS/MONITORING max limit violation.
- Valid swap updates both rows and marks the request approved atomically when both dates contain only their expected source rows.
- Lock exhaustion leaves both schedules and request status unchanged.
- Swap tests detect nested connection attempts while re-reading the request and validating post-swap state.

### Cancellation mutation

- Cancellation deletes only rows still owned by the requesting user.
- A stale multi-date cancellation rejects the entire request and deletes nothing.
- Multiple valid dates delete atomically.
- Deleting the last Delivery schedule is allowed by the explicit cancellation exception.
- Lock exhaustion leaves all requested rows intact.
- Cancellation tests detect nested connection attempts during stale-row verification and deletion.

### Regression

- Existing weekday/weekend validation tests remain green.
- Existing web weekend override behavior remains green, and its rows are treated as occupied by Bot conflict validation.
- Existing startup and import checks remain green.

## Acceptance Criteria

The feature is complete only when all of the following are true:

1. Member tab exposes Infra Delivery and Infra Operation and administrators can assign members independently.
2. Old `INFRA` and `CE` rows migrate to Infra Operation under a rebuilt exact four-group constraint.
3. Existing schedule rows and unrelated group/member data survive migration.
4. Infra Delivery `/start` saves enforce exactly one schedule per month in backend code.
5. Infra Operation, APPS, and MONITORING `/start` saves enforce their configured monthly maxima in backend code.
6. Bot saves enforce one assignment per date against every existing `jadwal` row using `BEGIN IMMEDIATE` before conflict reads, bounded lock retry, and atomic rollback.
7. Swap revalidates source ownership, date conflicts, and post-state monthly rules atomically.
8. Cancellation revalidates ownership, is atomic, and explicitly permits Delivery to become zero.
9. Dashboard web weekend override remains unchanged.
10. Migration, save, swap, cancellation, lock handling, UI, and regression tests provide fresh evidence for the behavior above.
