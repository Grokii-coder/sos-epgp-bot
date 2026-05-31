# SoS EPGP Discord Bot — Design Document

> **This document is static architecture reference.**
> For current work status see `TODO.md`. For shipped history see `CHANGELOG.md`.

---

## Overview

A Discord bot for the *Seekers of Souls* guild on Project Quarm that queries their
EPGP tracking spreadsheet and returns information to guild members. The primary use
case is attendance auditing — allowing players to verify they received correct credit
for raid and PQ events, understand their EP cap progress, and check loot and priority
information.

Development happens in four phases:
1. **Docker setup** — establish the containerized development environment (MySQL + Python)
2. **Data validation** — personal script confirming sync and query logic works correctly
3. **Standalone bot** — personal Discord bot for one player (Grokenspiel)
4. **PR into existing bot** — port the feature into the guild's existing SOS-Bot
   repository at https://github.com/khandyman/SOS-Bot

Docker is used as the **development environment only**. The existing guild bot's
production deployment is out of scope.

---

## Repository

| Item | Value |
|------|-------|
| GitHub account | https://github.com/Grokii-coder |
| Repository name | sos-epgp-bot |
| GitHub URL | https://github.com/Grokii-coder/sos-epgp-bot |
| Local path | E:\\winflat\\github\\Grokii-coder\\sos-epgp-bot |
| Upstream reference | https://github.com/khandyman/SOS-Bot |

---

## Background & Context

### EPGP System
- **EP (Effort Points)** — earned by attending raids, PQ events, donating items,
  reaching level milestones, completing epics, leading events, etc.
- **GP (Gear Points)** — accumulated by looting gear during EPGP (raid) events
- **PR (Priority Rating)** — calculated as `(EP + 150) / (GP + 100)`; determines
  loot priority. Higher is better.
- Base EP: 150, Base GP: 100 (prevents divide-by-zero and low decimal values)
- 20% decay on both EP and GP at the end of every raid cycle
- EP cap: 900 per cycle

### Event Types
| Type | Description | EP Structure |
|------|-------------|-------------|
| EPGP Raid | Full raid event, GP spent on loot | Raid - Start, Raid - Mid, Raid - End (3 check-ins) |
| PQ Event | Player Quest, no GP/loot | Single check-in (Event Attend) |
| Bonus EP | Level milestones, epic completion, donations, event leads | One-time entries |

### Raid Cycles
Cycles run approximately 2 weeks each. Each cycle has a number, start date, and
end date. The current cycle as of this document is **59** (5/10/26 – 5/23/26).

| Start | End | Cycle |
|-------|-----|-------|
| 11/2/25 | 11/15/25 | 45 |
| 11/16/25 | 11/30/25 | 46 |
| ... | ... | ... |
| 5/10/26 | 5/23/26 | 59 |
| 5/24/26 | 6/6/26 | 60 |

---

## Data Source

### Google Spreadsheet
- **Sheet ID:** `1pu43LSErcxSaaAkaaTrvMi8GfZYV-dRf1qaWyKiveAA`
- **Access:** Publicly readable, no authentication required
- **Fetching:** Plain HTTP requests (`requests` library), no Google API needed
- **Trade-off:** If the sheet is ever made private, a service account would be required.

### Key Tabs

#### Overview (gid=0)
Current standings for all members. One row per member.

| Column | Description |
|--------|-------------|
| Date | Last attended date |
| Name | Character name |
| Class | Character class (EQ progression titles, e.g. "Virtuoso" not "Bard") |
| Level | Character level (may be "ANONYMOUS") |
| Effort Points | Current EP |
| Gear Points | Current GP |
| Loot Priority | Calculated PR = (EP+150)/(GP+100) |
| EP Decay | EP decay amount for current cycle |
| GP Decay | GP decay amount for current cycle |

#### EP Log (gid=264766085)
Every EP transaction ever recorded. Use **columns M onward only** (clean side).
Columns A-J are raw app data and must be ignored.

| Column | Field Name | Description |
|--------|-----------|-------------|
| M | Cycle | Cycle number |
| N | Date | Transaction date |
| O | Name | Character name |
| P | Class | Character class |
| Q | Level | Character level |
| R | Point Type | Type of EP earned |
| S | EP Points | Point value |
| T | Cycle Sum | Running EP total for this player in this cycle |
| U | Points Earned | Actual points earned (may differ due to cap) |
| V | Note | Event location (e.g. "VT - Day 2") |

**Point Type values:**
- `Raid - Start` / `Raid - Mid` / `Raid - End` — EPGP raid check-ins
- `Event Attend` — PQ event attendance
- `Hitting lvl 40/45/50/55/60` — level milestone bonus
- `Epic Completion` — epic weapon bonus
- `Bank Donation` — item donation bonus
- `Event Lead` — event leadership bonus
- `Meeting` — guild meeting attendance

**Critical data quirk — append-only log:**
The EP Log is append-only. Late credit additions appear at the next available row,
NOT inline with the original event block. All grouping must be done by **date value
in column N**, never by row proximity.

#### GP Log (gid=116377915)
Every loot event.

| Column | Description |
|--------|-------------|
| Date | Date of loot |
| Character | Who received the item (stored as `toon_name` — `character` is reserved in MySQL) |
| Loot | Item name |
| Gear Level | Bid type (High Bid, Medium Bid, Low Bid, Epic Drop, Alt Loot, Rot, etc.) |
| Notes | GP value |
| Duplicate Loot Found | Boolean flag |

#### Cycles
Cycle number, start date, end date. Small table, grows ~2 rows per month.
Re-fetched entirely each sync.

---

## Player Identity

### Standalone Version
```
# .env
PLAYER_NAME=Grokenspiel
DISCORD_USER_ID=your_discord_id_here
```

### PR / Existing Bot Version
Replace hard-coded name with lookup: `get_character_for_discord_user(interaction.user.id)`

### Alt Attendance
Alt attendance is logged under the **player's main name** with the **alt's class title**.
There is no separate alt character name in the EP log. Bot logic is unaffected — all
queries group by player name only.

### Main Switches
When a player switches mains, all historical EP log entries are retroactively renamed
to the new main's name. The old character name disappears entirely from the database.
The `class` column reflects the class at the time of entry — cosmetic only, no impact
on bot logic.

---

## Architecture

### Project Directory Structure

```
sos-epgp-bot/
├── Design.md                        # Static architecture reference (this file)
├── CHANGELOG.md                     # Shipped features by SC-N, newest first
├── TODO.md                          # Current next steps, known issues, tabled items
├── Dockerfile                       # Python container definition
├── README.md                        # Repo overview
├── docker-compose.yml               # MySQL + Python containers
├── init.sql                         # DB schema — run once on first container start
├── main.py                          # Bot entry point — loads cogs, handles on_ready sync
├── requirements.txt                 # Python dependencies
├── sync.py                          # Standalone sync script (Phase 1 validation tool)
├── test_attendance.py               # Legacy Phase 1 integration script (not pytest)
├── .env.example                     # Template for .env — copy and fill in secrets
├── cogs/
│   ├── events.py                    # SC-5: Discord scheduled event gateway listeners
│   ├── item.py                      # SC-6: /item command — loot history search
│   ├── priority.py                  # /priority command — PR rank by class/armor type
│   └── review.py                    # /review command — EP discrepancy review flow
├── classes/
│   ├── attendance.py                # Query helpers: event lookup, location formatting
│   ├── cycle_sync.py                # Syncs cycles tab from Google Sheets
│   ├── database.py                  # SQLAlchemy engine factory (get_engine())
│   ├── ep_sync.py                   # Incremental sync of EP log from Google Sheets
│   ├── gp_sync.py                   # Incremental sync of GP log from Google Sheets
│   ├── helpers.py                   # Shared utilities (date parsing, formatting, etc.)
│   ├── sheets.py                    # Google Sheets HTTP fetch helpers
│   └── sync_manager.py              # SC-3: TTL cache logic, orchestrates all syncs
├── data/
│   └── eq_class_aliases.json        # EQ title → base class → armor type mapping
└── tests/
    ├── __init__.py
    ├── conftest.py                  # Env var patches so cogs import cleanly without .env
    ├── test_sc5_gaps.py             # SC-5 unit tests: TTL isolation, voice branch, LIMIT 1
    └── test_sc6_item_ux.py          # SC-6 unit tests: pagination, ephemeral, routing
```

### Tech Stack
| Component | Library | Reason |
|-----------|---------|--------|
| Discord | py-cord | Matches existing bot |
| Database ORM | SQLAlchemy | Matches existing bot |
| Database driver | PyMySQL (MySQL) | Matches existing bot |
| HTTP | requests | Public sheet, no auth needed |
| Config | python-dotenv | Matches existing bot |
| Dev environment | Docker + Docker Compose | No local MySQL, reproducible |

### Confirmed Architecture Decisions

| Decision | Choice | Reason |
|----------|--------|--------|
| Sheets access | `requests` plain HTTP | Public sheet, no auth needed |
| Class mapping | eq_class_aliases.json | Source of truth — EQ title → base class → armor type |
| Deployment | Local machine (standalone) | Existing bot handles guild deployment |
| Test runner | pytest + pytest-asyncio | Standard, runs cleanly in Docker container |

---

## Database Schema

### ep_log
Mirrors the clean side (columns M-V) of the EP Log tab.

| Column | Type | Description |
|--------|------|-------------|
| id | INT PK AUTO | Internal row ID |
| cycle | INT | Cycle number |
| date | DATE | Transaction date |
| name | VARCHAR | Character name |
| class | VARCHAR | Character class (EQ progression title) |
| level | VARCHAR | Character level (VARCHAR due to "ANONYMOUS") |
| point_type | VARCHAR | Type of EP earned |
| ep_points | INT | Point value |
| cycle_sum | INT | Running cycle total at time of entry |
| points_earned | INT | Actual points earned |
| note | VARCHAR | Event location if present |
| sheet_row | INT UNIQUE | Source row number in Google Sheet (incremental sync) |

### gp_log
Mirrors the GP Log tab.

| Column | Type | Description |
|--------|------|-------------|
| id | INT PK AUTO | Internal row ID |
| date | DATE | Date of loot |
| toon_name | VARCHAR | Who received the item |
| loot | VARCHAR | Item name |
| gear_level | VARCHAR | Bid type |
| gp_value | INT | GP cost |
| duplicate | BOOLEAN | Duplicate loot flag |
| sheet_row | INT UNIQUE | Source row number in Google Sheet |

### cycles
| Column | Type | Description |
|--------|------|-------------|
| cycle_number | INT PK | Cycle number |
| start_date | DATE | Cycle start |
| end_date | DATE | Cycle end |

### attendance_responses
Stores player responses to discrepancy questions from `/review`.

| Column | Type | Description |
|--------|------|-------------|
| id | INT PK AUTO | Internal row ID |
| player_name | VARCHAR | Character name |
| event_date | DATE | Date of the event |
| event_location | VARCHAR | Location of the event |
| event_type | VARCHAR | EPGP Raid or PQ Event |
| missing_checkins | VARCHAR | Which check-ins were missing (e.g. "Mid") |
| player_response | ENUM | 'yes' (was there) / 'no' (was not there) |
| response_date | DATE | When the player responded |
| resolved | BOOLEAN | Whether an officer has addressed a 'yes' response |

### sync_state
TTL cache state for Google Sheets sync (SC-3).

| Column | Type | Description |
|--------|------|-------------|
| id | INT PK AUTO | Internal row ID |
| last_sync | DATETIME | Timestamp of last completed sync |
| sync_type | VARCHAR | Which sync ran (ep_log, gp_log, cycles, full) |

### scheduled_events
Discord scheduled event data (SC-5).

| Column | Type | Description |
|--------|------|-------------|
| id | VARCHAR PK | Discord event ID |
| name | VARCHAR | Event name |
| scheduled_start | DATETIME | Scheduled start time |
| creator_id | VARCHAR | Discord user ID of event creator |
| status | VARCHAR | scheduled / active / completed / canceled |

### event_history
Discord event name changes for pivot detection (SC-5).

| Column | Type | Description |
|--------|------|-------------|
| id | INT PK AUTO | Internal row ID |
| event_id | VARCHAR | Discord event ID (FK to scheduled_events) |
| previous_name | VARCHAR | Name before change |
| changed_at | DATETIME | When the name change was detected |

---

## Class Title Mapping

**Source of truth: `data/eq_class_aliases.json`**

| Armor Type | Base Class | Sample Titles |
|------------|------------|---------------|
| Plate | Bard | Bard, Troubadour, Virtuoso, Maestro... |
| Plate | Cleric | Cleric, High Priest, Templar, Archon... |
| Plate | Paladin | Paladin, Crusader, Cavalier, Knight... |
| Plate | Shadow Knight | Shadow Knight, Grave Lord, Dread Lord... |
| Plate | Warrior | Warrior, Warlord, Champion, Myrmidon... |
| Chain | Ranger | Ranger, Warder, Pathfinder, Outrider... |
| Chain | Rogue | Rogue, Assassin, Blackguard, Swashbuckler... |
| Chain | Shaman | Shaman, Oracle, Luminary, Mystic... |
| Leather | Beastlord | Beastlord, Animist, Feral Lord, Wildblood... |
| Leather | Druid | Druid, Hierophant, Preserver, Wanderer... |
| Leather | Monk | Monk, Grandmaster, Disciple, Ascendant... |
| Cloth | Enchanter | Enchanter, Illusionist, Beguiler, Phantasmist... |
| Cloth | Magician | Magician, Arch Mage, Conjurer, Elementalist... |
| Cloth | Necromancer | Necromancer, Defiler, Lich, Arch Lich... |
| Cloth | Wizard | Wizard, Sorcerer, Evoker, Channeler, Arcanist... |

*"Unknown" category exists for guild rank titles or NPCs — not shown in `/priority` output.*

---

## Sync Strategy

### Incremental Sync
- `sheet_row` tracks which Google Sheets row each record came from
- On sync: find the highest `sheet_row` already stored, fetch only rows after it
- First run fetches entire history; subsequent runs fetch only new rows
- Cycles table is small enough to re-fetch entirely each sync

### Sync Triggers (Standalone)
- 5-minute TTL cache — sync only runs if more than 5 minutes have passed
- Cache state persisted in `sync_state` MySQL table
- Startup sync runs automatically when the bot connects

### Sync Triggers (PR / Existing Bot)
- Automatic scheduled sync
- Officer-triggered `/sync` command (out of scope — not an officer)

### Data Integrity
- Historical rows never change — only new rows appended
- Late credit additions appear at the bottom with their original event date
- `date` column is the source of truth for grouping, never row order
- Duplicate protection via `UNIQUE` constraint on `sheet_row`

---

## Commands

### `/review [cycle]`
Shows EP cap progress for the current (or specified) cycle, then walks through
events where the player may be missing credit one at a time.

**Discrepancy detection logic:**
1. Find all events (raids + PQ) within the cycle date range
2. For each event date, determine guild baseline — all unique check-in types any
   member received (minimum 12 players to qualify as real event)
3. Compare player's check-ins to baseline
4. Skip events already responded to (stored in `attendance_responses`)
5. Surface only unreviewed discrepancies

**Response persistence:**
- `yes` → stored with `resolved = false`, flagged for officer action, never asked again
- `no` → stored with `resolved = true`, closed permanently, never asked again
- `skip` → deferred, will reappear on next `/review` run

**Event location display format (SC-5):**
```
📍 DISCORD_EVENT_NAME (was: PREVIOUS_NAME) [sheet: EPGP_NOTE] 👤 LEADER
```

---

### `/item <partial name>`
Shows loot history for a specific item — total drop count and the last 3 drops
with date, recipient, bid type, and GP cost. Designed for mid-raid use.

- Case-insensitive partial name search
- 2–5 matches: alphabetical button selection
- 6+ matches: paginated buttons (3/page, sorted by most recent drop date) with Prev/Next
- All outcomes ephemeral — visible only to the invoking user (SC-6)

---

### `/priority`
Shows the player's PR rank among their own class and among all classes sharing
their armor type. Class looked up automatically from the Overview tab via
`data/eq_class_aliases.json`.

---

## DM Notifications

**Not implemented. Parked for future consideration.**

Original intent: notify the player after sync when new EP credits are recorded.
Superseded by ephemeral `/review` command — players can check on demand.

Future use case (better fit): proactively DM players who **opt in** when they
missed EP they could have earned — e.g. a raid happened and they were not credited.
This is distinct from the review flow and would require an opt-in roster.

---

## Development Phases

### Phase 0 — Docker Setup ✅
Containerized development environment. MySQL + Python containers, volumes, .env, .gitignore.

### Phase 1 — Data Validation ✅
Sync logic confirmed. Incremental sync, date-based grouping, attendance query logic
validated against live data.

### Phase 2 — Standalone Personal Bot ✅
All commands live and tested. See `CHANGELOG.md` for full SC-N history.

### Phase 3 — PR into Existing Bot 🔜 Ready
- Fork https://github.com/khandyman/SOS-Bot
- Port Phase 2 code into existing structure
- Replace hard-coded player name with Discord ID → character lookup
- Handle main/alt relationships using existing bot's database
- Submit PR

