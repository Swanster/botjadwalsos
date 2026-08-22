# Task 6 Report: Infra Division Split Web Dashboard

## Changed files

- `web/app.py`
  - Imported canonical `GROUP_NAMES` and `GROUP_LABELS`.
  - Added `load_member_groups()` inside `create_app()` to load all four canonical groups and flattened `all_members`.
  - Reused centralized loading in login, dashboard, members, schedules, and manual schedule member lookup.
  - Updated member add/edit defaults to `INFRA_OPERATION`.
  - Kept `set_user_group()` as the final validator/normalizer and changed success flashes to readable `GROUP_LABELS` values.
  - Updated settings POST allowlist to exactly `kuota_infra`, `kuota_apps`, `kuota_monitoring`, `max_hari_infra_operation`, `max_hari_apps`, and `max_hari_monitoring`.
  - Passed `GROUP_LABELS` to the schedule template.
  - Preserved `/schedules/add` weekend bypass and duplicate handling unchanged.
- `web/templates/members.html`
  - Replaced both group selects with canonical options in required order: Infra Delivery, Infra Operation, APPS, MONITORING.
  - Replaced the three-group card list with four canonical cards using `members_by_group`.
  - Kept canonical group IDs in edit modal `data-group` and options.
- `web/templates/settings.html`
  - Rendered four cards.
  - Added shared Infra daily quota explanation, Delivery fixed monthly value of 1, and exact-one-date `/start` copy.
  - Added editable `max_hari_infra_operation` with default 5 and max 31.
  - Kept APPS and MONITORING daily/monthly inputs editable and explicitly distinguished daily quota from monthly maximum.
  - Removed the obsolete `max_hari_infra` input.
- `web/templates/schedules.html`
  - Set canonical four-group order.
  - Rendered display labels through `groupLabels` while retaining canonical IDs in quota data and form state.

## Implementation decisions

- The existing database normalization remains authoritative for legacy `INFRA`; the web UI emits only canonical values.
- The shared Infra daily setting remains `kuota_infra` for both Infra groups.
- No server-side weekend override or exact duplicate logic was changed.
- `test_web_weekend_override.py` was staged as required by the brief but had no content changes.

## Focused commands and complete output summaries

### `python test_web_weekend_override.py`

Passed. The script reported login status 302, allowed the same user on Saturday and Sunday, allowed a second user on the same Saturday, rejected the exact same-user/same-date duplicate, verified one row for each expected database assignment, and printed `PASS`.

Notable output included:

```text
A) same user Sat+Sun statuses: 302 302
B) different user same Sat status: 302
C) same user same Sat again status: 302
DB: u1 on Sat=1 (expect 1), u1 on Sun=1 (expect 1), u2 on Sat=1 (expect 1)
RESULT: weekend override OK — admin can fill user >1x across weekend days & multiple users per weekend day; duplicates prevented.
PASS
```

### `pytest -q test_infra_division_split.py -k 'web or settings or group_input'`

Passed: `2 passed, 20 deselected in 0.22s`.

## Commit

`f0b7aa5` — `feat: update dashboard for infra division split`

## Concerns

- The focused weekend script emits the pre-existing warning that `google_credentials.json` is unavailable during its Google Sheets sync path; the test still passed and database assertions were successful.
- No formatter, linter, or project-wide test suite was run, per the brief.

## Follow-up runtime fix

Post-commit verification found that the schedule JavaScript used `groupQuotas` and `dailyLimits` without declarations. Restored both declarations from the route-provided `group_quotas` and `daily_limits` template variables, preserving canonical `groupOrder`.

### Follow-up verification

- `python test_web_weekend_override.py`: PASS; weekend assignments and exact duplicate rejection remained correct.
- `pytest -q test_infra_division_split.py -k 'web or settings or group_input'`: `2 passed, 20 deselected in 0.19s`.
- Focused template assertion: `schedule template declarations and canonical order passed`.

Follow-up fix commit: recorded after the original `f0b7aa5` commit.

## Follow-up markup fix

Restored the missing `flex flex-col` wrapper in each members group-card header so the existing heading, description, and closing tags are balanced. Removed the duplicated orphaned heading block introduced during the earlier template update.

### Markup fix verification

- `python test_web_weekend_override.py`: PASS; weekend assignments and exact duplicate rejection remained correct.
- `pytest -q test_infra_division_split.py -k 'web or settings or group_input'`: `2 passed, 20 deselected in 0.16s`.
- Deterministic members template assertion: `members card wrapper and canonical card assertions passed`.

Markup fix commit: recorded after `189fbc4`.
