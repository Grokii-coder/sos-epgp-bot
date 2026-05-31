# Changelog

All notable changes to this project are documented here, newest first.
Each entry corresponds to a scope creep item (SC-N) or development phase.

See `TODO.md` for current next steps.

---

## SC-7 — Docs Restructure (2026-05-30)
- Split Design.md into three files: static `Design.md`, `CHANGELOG.md`, `TODO.md`
- Added SC-N naming convention to project: next available number, permanent, no reuse
- Added annotated project directory tree to Design.md Architecture section

## SC-6 — `/item` Too-Many-Matches UX (2026-05-30)
- 6+ matches now show paginated buttons (3/page, sorted by most recent drop date)
  with Prev/Next navigation instead of dead-end "try a more specific name" message
- All `/item` outcomes are now ephemeral — visible only to the invoking user
- Added `_search_items_by_recency()` query (MAX(date) GROUP BY, ORDER BY DESC)
- Added `ItemPagedView` class with page state, nav button management, wrong-user guard
- 29 unit tests in `tests/test_sc6_item_ux.py`

## SC-5 — Discord Scheduled Events Integration (2026-05-28)
- Gateway listeners: `on_scheduled_event_create`, `on_scheduled_event_update`,
  `on_scheduled_event_delete` write to `scheduled_events` and `event_history` tables
- Startup sync saves all pre-existing guild events on `on_ready`
- `creator_name` populated via `guild.fetch_member(creator_id)`
- `get_scheduled_event_for_date()` and `format_event_location()` in `attendance.py`
- Event location display: `📍 NAME (was: PREV) [sheet: NOTE] 👤 LEADER`
- End-to-end `/review` enrichment confirmed live
- Known limitation: same-date double events — `LIMIT 1` returns earliest `start_time`
- SC-5 test gaps closed 2026-05-30: 15 unit tests in `tests/test_sc5_gaps.py`
  covering TTL cache isolation (T5), voice-channel location branch (T1), LIMIT 1
  same-date behavior (T2-5)

## SC-4 — Yes/No Button Flow in `/review` (2026-05-21)
- `/review` walks discrepancies one at a time using Discord UI buttons
- Responses persisted in `attendance_responses` table
- `yes` → flagged for officer follow-up, never asked again
- `no` → closed permanently, never asked again
- `skip` → deferred to next `/review` run

## SC-3 — TTL Cache for Google Sheets Sync (2026-05-21)
- 5-minute TTL cache prevents syncing on every command
- Cache state stored in `sync_state` MySQL table
- Startup sync runs automatically on bot connect

## SC-2 — Same-Day PQ + Raid Split (2026-05-21)
- PQ event and EPGP raid on the same date shown as two separate events
- Event type determined by check-in type: `Event Attend` = PQ, `Raid - *` = EPGP Raid

## SC-1 — 12-Player Minimum Threshold (2026-05-21)
- Single-player EP log entries (data errors, test entries) were appearing as guild events
- Added minimum of 12 players per check-in to qualify as a real event, matching the
  guild's PQ eligibility requirement

## Phase 2 — Standalone Personal Bot (2026-05-21)
- `/review`, `/item`, `/priority` commands live and tested
- Docker + MySQL dev environment confirmed working end-to-end

## Phase 1 — Data Validation (2026-05-21)
- Sync logic confirmed against live Google Sheets data
- Incremental sync, date-based grouping, attendance query logic all validated

## Phase 0 — Docker Setup (2026-05-21)
- MySQL + Python containers, volumes, .env, .gitignore complete
