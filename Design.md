# SoS EPGP Discord Bot — Design Document
*Last updated: 2026-05-21*

---

## Project Status Snapshot

### ✅ Completed
| Item | Notes |
|------|-------|
| Phase 0 — Docker setup | MySQL + Python containers, volumes, .env, .gitignore |
| Phase 1 — Data validation | Sync logic, incremental sync, attendance query logic confirmed |
| Phase 2 — Standalone bot | All three commands live and tested |
| `/review` command | Button flow, persistence, skip, re-run behavior all confirmed ✅ |
| `/item` command | Partial search, no-match, too-many-match, single result all confirmed ✅ |
| `/priority` command | Class/armor ranking confirmed live ✅ |
| SC-1: 12-player threshold | Confirmed filtering noise correctly ✅ |
| SC-2: Same-day PQ + Raid split | Confirmed working ✅ |
| SC-3: TTL cache | 5-min cache via sync_state table confirmed ✅ |
| SC-4: Yes/No button flow | Persistence, skip, re-run all confirmed ✅ |
| pp_value column | Investigated — confirmed empty across all 37,496 rows, dropped from schema ✅ |
| Alt attendance confirmed | Logged under main name with alt's class title — no separate alt name ✅ |
| Main switch behavior confirmed | Old name retroactively replaced guild-wide — old name disappears entirely ✅ |
| eq_class_aliases.json | Source of truth for EQ title → base class → armor type mapping ✅ |

### 🔧 Known Issues / Wording Fix Needed
| Item | Notes |
|------|-------|
| `/review` wording — "logging error" | Soften: "Start and End are missing" instead of "this is likely a logging error" |

### 🔜 Next — Before PR
| Item | Notes |
|------|-------|
| SC-5: Discord Scheduled Events | Tables and cog exist (`cogs/events.py`) — not yet tested |
| SC-6: `/item` too-many-matches UX | Show 3 most-recent matching items as buttons, paginate in groups of 3 |
| Fix `/review` wording | See known issues above |
| Update project directory tree in this doc | Real structure has diverged significantly from Phase 0 plan |
| Fork + PR into khandyman/SOS-Bot | Phase 3 — table until bot is fully tested and doc is final |

### 🚫 Tabled (Phase 3+)
| Item | Notes |
|------|-------|
| Fork and PR into khandyman/SOS-Bot | After all testing complete and design doc final |
| Voice channel priority filter | Requires existing bot's Discord voice membership access |
| Webhook-triggered sync | Requires coordination with sheet-writing bot |
| Multi-player support | Standalone version is single-player by design |

---

## Overview
A Discord bot for the *Seekers of Souls* guild on Project Quarm that queries their
EPGP tracking spreadsheet and returns information to guild members. The primary use
case is attendance auditing — allowing players to verify they received correct credit
for raid and PQ events, understand their EP cap progress, and check loot and priority
information.

Development happens in four phases:
1. **Docker setup** — establish the containerized development environment (MySQL + Python) before writing any application code
2. **Data validation** — personal script confirming sync and query logic works correctly, no Discord yet
3. **Standalone bot** — personal Discord bot for one player (Grokenspiel)
4. **PR into existing bot** — port the feature into the guild's existing SOS-Bot
   repository at https://github.com/khandyman/SOS-Bot

Docker is used as the **development environment only**. It eliminates the need to
install MySQL locally and ensures a reproducible environment. The existing guild
bot's production deployment is out of scope.

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
| EPGP Raid | Full raid event, GP spent on loot | Raid - Start, Raid - Mid, Raid - End (3 separate check-ins) |
| PQ Event | Player Quest, no GP/loot | Single check-in (Event Attend) |
| Bonus EP | Level milestones, epic completion, donations, event leads | One-time entries, not events |

### Raid Cycles
Cycles run approximately 2 weeks each. Each cycle has a number, start date, and
end date. The current cycle as of this document is **59** (5/10/26 – 5/23/26).

Sample cycle data:
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
- **Fetching:** Plain HTTP requests (`requests` library), no Google API or service
  account needed
- **Trade-off accepted:** If the sheet is ever made private, a service account
  would be required. Known and acceptable risk.

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
Every EP transaction ever recorded. Has two sides — use **columns M onward only**
(the clean/processed side). Columns A-J are raw app data and must be ignored.

| Column | Field Name | Description |
|--------|-----------|-------------|
| M | Cycle | Cycle number |
| N | Date | Transaction date |
| O | Name | Character name |
| P | Class | Character class |
| Q | Level | Character level |
| R | Point Type | Type of EP earned (see below) |
| S | EP Points | Point value |
| T | Cycle Sum | Running EP total for this player in this cycle |
| U | Points Earned | Actual points earned (may differ from EP Points due to cap) |
| V | Note | Event location (e.g. "VT - Day 2") — see note below |

**Point Type values:**
- `Raid - Start` / `Raid - Mid` / `Raid - End` — EPGP raid check-ins
- `Event Attend` — PQ event attendance
- `Hitting lvl 40/45/50/55/60` — level milestone bonus
- `Epic Completion` — epic weapon bonus
- `Bank Donation` — item donation bonus
- `Event Lead` — event leadership bonus
- `Meeting` — guild meeting attendance

**Event location** is stored in column V (Note) on the first `Raid - Start` entry
for a given date. This convention was not followed in early data — older events may
have no location. Fallback: display "Unknown".

**Critical data quirk — append-only log:**
The EP Log is append-only. Late credit additions (e.g. an officer manually crediting
a missed check-in) are added at the next available row — NOT inserted inline with
the original event block. Row proximity is therefore meaningless for grouping.
All grouping must be done by **date value in column N**.

#### GP Log (gid=116377915)
Every loot event. Clean and straightforward.

| Column | Description |
|--------|-------------|
| Date | Date of loot |
| Character | Who received the item (stored as `toon_name` in DB — `character` is a reserved word in MySQL) |
| Loot | Item name |
| Gear Level | Bid type (High Bid, Medium Bid, Low Bid, Epic Drop, Alt Loot, Rot, etc.) |
| Notes | GP value |
| Duplicate Loot Found | Boolean flag |

#### Cycles (tab not yet fetched)
Cycle number, start date, end date. Small table, grows ~2 rows per month.
Must be synced to determine current cycle boundaries.

---

## Player Identity

### Standalone Version
```
# .env
PLAYER_NAME=Grokenspiel
DISCORD_USER_ID=your_discord_id_here
```

### PR / Existing Bot Version
- Existing bot already maps Discord user ID → character name
- Replace hard-coded name with lookup: `get_character_for_discord_user(interaction.user.id)`
- The existing main/alt relationship is already managed by the existing bot

### Alt Attendance — Confirmed ✅
*Investigated 2026-05-21 using live EP log data.*

Alt attendance is logged under the **player's main name** with the **alt's class title**.
There is no separate alt character name in the EP log. When a player attends on an
approved alt, the EP Log entry shows:
- `name` = main character's name (e.g. "Narya")
- `class` = alt's class title (e.g. "Troubadour" when Narya's main is a Wizard/Sorcerer)

**Evidence:** Narya shows 406 entries as Wizard-family titles (Sorcerer, Evoker, Channeler)
and 291 entries as Bard-family titles (Virtuoso, Troubadour, Bard) — two distinct armor
types under one name. Aransur shows similar pattern with Paladin as main and scattered
Enchanter/Cleric/Magician entries as alts.

**Impact on bot logic:** None. `/review` and `/priority` query by player name only.
The alt's class title may appear in the EP log but does not affect EP credit grouping,
discrepancy detection, or PR calculation. This is handled correctly as-built.

### Main Switches — Confirmed ✅
*Investigated 2026-05-21 using live EP log data.*

When a player switches mains, the guild officer **retroactively renames all historical
EP log entries** in the sheet to the new main's name. The old character name is removed
entirely — it does not appear anywhere in the database.

**Evidence:**
- Kess (Cleric) shows 483 entries as Shaman-family titles — she was previously a Shaman
  named Kelo. No rows exist under the name "Kelo".
- Winian (Warrior) shows ~20 entries as Necromancer-family titles. No separate
  necromancer character name exists.

The `class` column reflects whatever class the player was on *at the time of the entry*,
so old entries will show the previous class. This is cosmetic and does not affect any
bot logic — all queries group by name only.

---

## Architecture

### Existing Bot Reference
The guild has an existing Discord bot at https://github.com/khandyman/SOS-Bot.
Our code must match its architecture exactly for clean PR integration.

**Existing bot stack:**
| Component | Library |
|-----------|---------|
| Discord | py-cord |
| Database ORM | SQLAlchemy |
| Database driver | PyMySQL (MySQL backend) |
| HTTP | requests |
| Config | python-dotenv (.env file) |

**Existing bot structure:**
- `main.py` — bot entry point, loads cogs, handles connect/ready events
- `classes/` — `Database` and `Tracker` helper classes
- `cogs/` — slash command modules (`lookups.py`, `updates.py`)
- `.env` — environment variables (Discord token, guild name, DB credentials)

**Our additions follow the same structure:**
- New cogs: `cogs/priority.py`, `cogs/review.py`, `cogs/item.py`, `cogs/events.py`
- New classes: `classes/ep_sync.py`, `classes/gp_sync.py`, `classes/cycle_sync.py`,
  `classes/sync_manager.py`, `classes/attendance.py`, `classes/sheets.py`, `classes/helpers.py`
- New data: `data/eq_class_aliases.json` — source of truth for class title mapping
- New MySQL tables — see Database Schema below

### Confirmed Architecture Decisions

| Decision | Choice | Reason |
|----------|--------|--------|
| Language | Python | Familiarity + existing bot match |
| Sheets access | `requests` plain HTTP | Public sheet, no auth needed |
| Database | MySQL | Matches existing bot |
| ORM | SQLAlchemy | Matches existing bot |
| DB Driver | PyMySQL | Matches existing bot |
| Config | python-dotenv (.env) | Matches existing bot |
| Discord library | py-cord | Matches existing bot |
| Dev environment | Docker + Docker Compose | No local MySQL install, reproducible environment |
| Deployment | Local machine (standalone) | Existing bot handles guild deployment |
| Class mapping | eq_class_aliases.json | Source of truth — EQ title → base class → armor type |

---

## Database Schema

### ep_log
Mirrors the clean side (columns M-V) of the EP Log tab.
*Note: `pp_value` column was present in early builds — confirmed empty across all
37,496 rows on 2026-05-21 and removed from schema.*

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
| sheet_row | INT UNIQUE | Source row number in Google Sheet (for incremental sync) |

### gp_log
Mirrors the GP Log tab.
*Note: The sheet column is named "Character" but stored as `toon_name` in the DB
because `character` is a reserved word in MySQL.*

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
Stores TTL cache state for the Google Sheets sync (SC-3).

| Column | Type | Description |
|--------|------|-------------|
| id | INT PK AUTO | Internal row ID |
| last_sync | DATETIME | Timestamp of last completed sync |
| sync_type | VARCHAR | Which sync ran (ep_log, gp_log, cycles, full) |

### scheduled_events
Stores Discord scheduled event data for SC-5.

| Column | Type | Description |
|--------|------|-------------|
| id | VARCHAR PK | Discord event ID |
| name | VARCHAR | Event name |
| scheduled_start | DATETIME | Scheduled start time |
| creator_id | VARCHAR | Discord user ID of event creator |
| status | VARCHAR | scheduled / active / completed / canceled |

### event_history
Tracks Discord event name changes for pivot detection (SC-5).

| Column | Type | Description |
|--------|------|-------------|
| id | INT PK AUTO | Internal row ID |
| event_id | VARCHAR | Discord event ID (FK to scheduled_events) |
| previous_name | VARCHAR | Name before change |
| changed_at | DATETIME | When the name change was detected |

---

## Class Title Mapping

**Source of truth: `data/eq_class_aliases.json`**

The sheet stores EQ progression titles (e.g. "Virtuoso"), not base class names.
The alias file maps every known title to a base class and armor type.

| Armor Type | Base Class | Sample Titles |
|------------|------------|---------------|
| Plate | Bard | Bard, Troubadour, Virtuoso, Maestro, Minstrel, Lyricist... |
| Plate | Cleric | Cleric, High Priest, Templar, Archon, Exarch... |
| Plate | Paladin | Paladin, Crusader, Cavalier, Knight, Lightbringer... |
| Plate | Shadow Knight | Shadow Knight, Grave Lord, Dread Lord, Bloodreaver... |
| Plate | Warrior | Warrior, Warlord, Champion, Myrmidon, Overlord... |
| Chain | Ranger | Ranger, Warder, Pathfinder, Outrider, Farwarden... |
| Chain | Rogue | Rogue, Assassin, Blackguard, Swashbuckler... |
| Chain | Shaman | Shaman, Oracle, Luminary, Mystic, Spiritwalker... |
| Leather | Beastlord | Beastlord, Animist, Feral Lord, Wildblood... |
| Leather | Druid | Druid, Hierophant, Preserver, Wanderer... |
| Leather | Monk | Monk, Grandmaster, Disciple, Ascendant... |
| Cloth | Enchanter | Enchanter, Illusionist, Beguiler, Phantasmist... |
| Cloth | Magician | Magician, Arch Mage, Conjurer, Elementalist... |
| Cloth | Necromancer | Necromancer, Defiler, Lich, Arch Lich... |
| Cloth | Wizard | Wizard, Sorcerer, Evoker, Channeler, Arcanist... |

*Note: An "Unknown" category exists in the alias file for titles that don't map to
a playable class (Baron, Duchess, Elder, etc.). These are likely guild rank titles
or NPCs — they are not shown in `/priority` output.*

---

## Sync Strategy

### Incremental Sync
- `sheet_row` column in `ep_log` and `gp_log` tracks which Google Sheets row each
  record came from
- On sync: find the highest `sheet_row` already stored, fetch only rows after it
- First run fetches entire history; subsequent runs fetch only new rows
- Cycles table is small enough to re-fetch entirely each sync

### Sync Triggers (Standalone)
- 5-minute TTL cache — sync only runs if more than 5 minutes have passed since last sync
- Cache state persisted in `sync_state` MySQL table
- Startup sync runs automatically when the bot connects

### Sync Triggers (PR / Existing Bot)
- Automatic scheduled sync
- Officer-triggered `/sync` command (out of scope for this developer — not an officer)

### Data Integrity
- Historical rows never change — only new rows are appended
- Late credit additions appear at the bottom of the sheet with their original event
  date — the `date` column is the source of truth for grouping, never row order
- Duplicate protection via `UNIQUE` constraint on `sheet_row`

---

## Commands

### `/review [cycle]`
**Purpose:** Shows EP cap progress for the current (or specified) cycle, then
walks through any events where the player may be missing credit, one at a time.

**Default:** Current cycle. Optional cycle number override (e.g. `/review 58`).

**Discrepancy detection logic:**
1. Find all events (raids + PQ) within the cycle date range
2. For each event date, determine the guild baseline — all unique check-in types
   any member received on that date (minimum 12 players to qualify as real event)
3. Compare player's check-ins to the baseline
4. Skip events already responded to (stored in `attendance_responses`)
5. Surface only unreviewed discrepancies

**Response persistence:**
- `yes` → stored with `resolved = false`, flagged for officer action, never asked again
- `no` → stored with `resolved = true`, closed permanently, never asked again
- `skip` → deferred, will reappear on next `/review` run

**Known wording issue (pending fix):**
When only Mid credit is present and Start/End are missing, current output reads
"this is likely a logging error." This should be softened to "Start and End are missing."

---

### `/item <partial name>`
**Purpose:** Shows loot history for a specific item — total drop count and the
last 3 drops with date, recipient, bid type, and GP cost. Designed for mid-raid use.

**Partial name search:** Case-insensitive. If multiple items match, bot lists them
and asks for clarification.

**All drop types shown:** High Bid, Medium Bid, Low Bid, Alt Loot, Rot, Epic Drop
(historical only) — full picture including rots.

**Too-many-matches behavior (current):** If more than a threshold of items match,
returns "try a more specific name." See SC-6 for planned improvement.

---

### `/priority`
**Purpose:** Shows the player's PR rank among their own class and among all
classes sharing their armor type. No arguments needed — class is looked up
automatically from the Overview tab.

**Class resolution:** EQ title → base class → armor type via `data/eq_class_aliases.json`.

**Future enhancement (Phase 3+):**
When integrated with the existing bot, `/priority` will filter by who is currently
in the raid voice channel — showing rank only among characters actually present on
tonight's raid. Requires Discord voice channel membership access via the existing bot.

---

## DM Notifications

**Purpose:** Proactively notify the player when new EP credits are recorded after
a sync — no need to run `/review` to find out you were credited.

**Trigger:** After every sync, check for new `ep_log` rows where:
- `name = PLAYER_NAME`
- `point_type` is a raid or PQ check-in
- Row was added in this sync (new `sheet_row` values)

**Group by event date** — one DM per event, not one per check-in.

---

## Development Phases

### Phase 0 — Docker Setup ✅
Containerized development environment running. MySQL + Python containers, volumes,
.env, .gitignore all complete.

### Phase 1 — Data Validation ✅
Sync logic confirmed. Incremental sync, date-based grouping, attendance query logic
all validated against live data.

### Phase 2 — Standalone Personal Bot ✅
All commands live and tested. See Project Status Snapshot at top of document for
full testing status.

### Phase 3 — PR into Existing Bot 🚫 Tabled
- Fork https://github.com/khandyman/SOS-Bot
- Port Phase 2 code into existing structure
- Replace hard-coded player name with Discord ID → character lookup
- Handle main/alt relationships using existing bot's database
- Submit PR

*Tabled until bot is fully tested, all known issues resolved, and design doc is final.*

---

## Repository

| Item | Value |
|------|-------|
| GitHub account | https://github.com/Grokii-coder |
| Repository name | sos-epgp-bot |
| GitHub URL | https://github.com/Grokii-coder/sos-epgp-bot |
| Local path | E:\winflat\github\Grokii-coder\sos-epgp-bot |
| Upstream reference | https://github.com/khandyman/SOS-Bot |

---

## Scope Creep Log

### SC-1: 12-Player Minimum Threshold ✅
Single-player EP Log entries (data errors, test entries) were appearing as guild
events. Added a minimum of 12 players per check-in to qualify as a real event,
matching the guild's PQ eligibility requirement.

### SC-2: Same-Day PQ + Raid Split ✅
When a PQ event and EPGP raid occur on the same date, they are shown as two
separate events rather than one combined event. Event type determined by check-in
type (Event Attend = PQ, Raid - Start/Mid/End = EPGP Raid).

### SC-3: TTL Cache for Google Sheets Sync ✅
5-minute TTL cache prevents syncing on every command. Cache state stored in
`sync_state` MySQL table. Startup sync runs automatically on bot connect.

### SC-4: Yes/No Button Flow in /review ✅
`/review` walks through discrepancies one at a time using Discord UI buttons.
Responses persisted in `attendance_responses` table. Skip defers to next run.
"No" responses closed permanently. "Yes" responses flagged for officer follow-up.

### SC-5: Discord Scheduled Events Integration 🔜
Pull upcoming guild events from Discord's scheduled events API for event name
and raid leader enrichment. Tables (`scheduled_events`, `event_history`) and
cog (`cogs/events.py`) exist — **not yet tested**.

**Event location display format:**
```
📍 DISCORD_EVENT_NAME (was: PREVIOUS_NAME) [sheet: EPGP_NOTE] 👤 LEADER
```

### SC-6: `/item` Too-Many-Matches UX 🔜
Instead of dead-end "try a more specific name" message, show the 3 most recently
dropped matching items as buttons. Player can select one or page through in groups
of 3 (sorted by most recent drop date descending) until they find what they want.

---

## Open Items

| Item | Status | Notes |
|------|--------|-------|
| Alt attendance in EP Log | ✅ Resolved | Logged under main name with alt's class title. No separate alt name. See Player Identity section. |
| Main switch behavior | ✅ Resolved | Old name retroactively replaced guild-wide. Old name disappears entirely from DB. |
| pp_value column | ✅ Resolved | Confirmed empty across all 37,496 rows — dropped from schema. |
| gp_log column name | ✅ Resolved | Sheet says "Character" but DB uses `toon_name` — `character` is reserved in MySQL. |
| Bard armor type in design doc | ✅ Resolved | Bard is Plate, not Chain. Source of truth is eq_class_aliases.json. |
| `/review` wording "logging error" | 🔧 Fix needed | Soften to "Start and End are missing" |
| SC-5 testing | 🔜 Next | cogs/events.py and tables exist, not yet tested |
| SC-6 implementation | 🔜 Next | /item too-many-matches UX improvement |
| Project directory tree | 🔜 Update | Real structure has diverged from Phase 0 plan |
| Sync schedule interval | TBD | Currently 5-min TTL cache triggered by commands |
| Voice channel priority | Phase 3+ | Requires existing bot integration |
| Webhook-triggered sync | Phase 3+ | Requires coordination with sheet-writing bot |