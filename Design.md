# SoS EPGP Discord Bot — Design Document
*Last updated: 2026-05-15*

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
| Character | Who received the item |
| Loot | Item name |
| Gear Level | Bid type (High Bid, Medium Bid, Low Bid, Epic Drop, Alt Loot, Rot, etc.) |
| Notes | GP value |
| Duplicate Loot Found | Boolean flag |

#### Cycles (tab not yet fetched)
Cycle number, start date, end date. Small table, grows ~2 rows per month.
Must be synced to determine current cycle boundaries.

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

**Our additions will follow the same structure:**
- New cog: `cogs/epgp.py` — slash commands (`/review`, `/item`, `/priority`)
- New class: `classes/epgp_sync.py` — Google Sheets fetch and sync logic
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
| class | VARCHAR | Character class |
| level | VARCHAR | Character level (VARCHAR due to "ANONYMOUS") |
| point_type | VARCHAR | Type of EP earned |
| ep_points | INT | Point value |
| cycle_sum | INT | Running cycle total at time of entry |
| points_earned | INT | Actual points earned |
| note | VARCHAR | Event location if present |
| sheet_row | INT UNIQUE | Source row number in Google Sheet (for incremental sync) |

### gp_log
Mirrors the GP Log tab.

| Column | Type | Description |
|--------|------|-------------|
| id | INT PK AUTO | Internal row ID |
| date | DATE | Date of loot |
| character | VARCHAR | Who received the item |
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

---

## Sync Strategy

### Incremental Sync
- `sheet_row` column in `ep_log` and `gp_log` tracks which Google Sheets row each
  record came from
- On sync: find the highest `sheet_row` already stored, fetch only rows after it
- First run fetches entire history; subsequent runs fetch only new rows
- Cycles table is small enough to re-fetch entirely each sync

### Sync Triggers (Standalone)
- Runs automatically on a schedule (interval TBD)
- After each sync, checks for new EP Log entries matching the player's name and
  sends a DM notification if new credits are found (see DM Notifications below)

### Sync Triggers (PR / Existing Bot)
- Automatic scheduled sync
- Officer-triggered `/sync` command (out of scope for this developer — not an officer)

### Data Integrity
- Historical rows never change — only new rows are appended
- Late credit additions appear at the bottom of the sheet with their original event
  date — the `date` column is the source of truth for grouping, never row order
- Duplicate protection via `UNIQUE` constraint on `sheet_row`

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

### Alt Attendance — Deferred
Some players attend raids on approved alts and receive EP credit. Whether that
credit is logged under the alt's name or the main's name in the EP Log has **not
been confirmed** with real data. Do not design around this until verified.

---

## Commands

### `/review [cycle]`
**Purpose:** Shows EP cap progress for the current (or specified) cycle, then
walks through any events where the player may be missing credit, one at a time.

**Default:** Current cycle. Optional cycle number override (e.g. `/review 58`).

**Flow:**
```
/review

Grokenspiel — Cycle 59 (5/10/26 – 5/23/26)
EP: 586 / 900

I found 2 events where you may be missing credit.

Event 1 of 2:
📅 05/10/2026  ⚔️ EPGP Raid  📍 Kael Drakkel
Missing: Mid

Were you there? (yes / no)

> yes

Got it — flagged for officer review.

Event 2 of 2:
📅 04/28/2026  ⚔️ EPGP Raid  📍 Vex Thal
Missing: Start, Mid, End

Were you there? (yes / no)

> no

Noted — marking you as absent.

All done! No more discrepancies for Cycle 59.
```

**If no discrepancies:**
```
Grokenspiel — Cycle 59 (5/10/26 – 5/23/26)
EP: 586 / 900

✅ You're all caught up — no missing credits for Cycle 59.
```

**Discrepancy detection logic:**
1. Find all events (raids + PQ) within the cycle date range
2. For each event date, determine the guild baseline — all unique check-in types
   any member received on that date
3. Compare player's check-ins to the baseline
4. Skip events already responded to (stored in `attendance_responses`)
5. Surface only unreviewed discrepancies

**Response persistence:**
- `yes` → stored with `resolved = false`, awaits officer action, never asked again
- `no` → stored with `resolved = true`, closed permanently, never asked again

---

### `/item <partial name>`
**Purpose:** Shows loot history for a specific item — total drop count and the
last 3 drops with date, recipient, bid type, and GP cost. Designed for mid-raid use.

**Partial name search:** Case-insensitive. If multiple items match, bot lists them
and asks for clarification.

**All drop types shown:** High Bid, Medium Bid, Low Bid, Alt Loot, Rot, Epic Drop
(historical only) — full picture including rots.

**Example — consistent history:**
```
/item rod of mal

Rod of Malisement — 8 total drops

Recent history:
  01/30/24  Babee      High Bid    100 GP
  01/27/24  Wolfx      High Bid    100 GP
  01/17/24  Koramak    High Bid    100 GP
```

**Example — mixed history including rot:**
```
/item silky whip

Silky Whip of Replication — 5 total drops

Recent history:
  04/28/26  (rotted)   Rot           0 GP
  03/15/26  Crowshot   Low Bid      10 GP
  02/02/26  Ammaru     Medium Bid   50 GP
```

**Example — multiple matches:**
```
/item rod

Multiple items found:
  1. Rod of Malisement
  2. Rod of the Oracle
  3. Rod of Bone

Which item? (reply with number)
```

---

### `/priority`
**Purpose:** Shows the player's PR rank among their own class and among all
classes sharing their armor type. No arguments needed — class is looked up
automatically from the Overview tab.

**Class title → base class → armor type mapping:**
| Armor Type | EQ Titles in Sheet |
|------------|-------------------|
| Plate | Warrior, Warlord, Paladin, Crusader, Shadow Knight, Grave Lord, Cleric, High Priest |
| Chain | Ranger, Warder, Rogue, Bard, Virtuoso, Shaman, Hierophant, Beastlord |
| Leather | Monk, Grandmaster, Druid, Oracle |
| Cloth | Wizard, Arch Mage, Magician, Animist, Enchanter, Phantasmist, Necromancer |

**Example output (Grokenspiel = Virtuoso = Bard = Chain):**
```
/priority

Grokenspiel — PR: 9.2559

Among Bards (Virtuosos):        Rank 1 of 3
  1. Grokenspiel    9.2559  ← you
  2. Allrin         4.2333
  3. Ieaini         3.4795

Among Chain wearers:            Rank 3 of 12
  1. Darkclaw       9.0381
  2. Katrinka       8.4268
  3. Grokenspiel    9.2559  ← you
  4. Krayziefoo     5.9457
  ...
```

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

**Example DM:**
```
📋 New credits recorded — Cycle 59:

05/13/2026  VT - Day 2  EPGP Raid
  ✅ Raid - Start   50 EP
  ✅ Raid - Mid     50 EP
  ✅ Raid - End     50 EP
  Total: 150 EP  |  Cycle total: 586 / 900
```

**Future enhancement (Phase 3+):** If the bot that writes to the Google Sheet
fires a webhook or triggers a sync event on write, DMs could arrive within seconds
of credit being logged rather than waiting for the next scheduled sync.

---

## Development Phases

### Phase 0 — Docker Setup
Get the containerized development environment running before writing any
application code. MySQL will live entirely inside Docker — no local install needed.

**Deliverables:**
- `Dockerfile` — Python container built from `python:3.11-slim`, installs all
  pip dependencies from `requirements.txt`
- `docker-compose.yml` — defines two services:
  - `db` — MySQL 8 container with a named volume for data persistence
  - `bot` — Python container, depends on `db`, mounts project directory
- `.env` — credentials and config (never committed to git):
  ```
  PLAYER_NAME=Grokenspiel
  DISCORD_USER_ID=your_discord_id_here
  DISCORD_TOKEN=your_token_here
  DB_HOST=db
  DB_PORT=3306
  DB_NAME=sosbot
  DB_USER=botuser
  DB_PASSWORD=your_password_here
  SHEET_ID=1pu43LSErcxSaaAkaaTrvMi8GfZYV-dRf1qaWyKiveAA
  ```
- `.env.example` — safe template committed to git with placeholder values
- `.gitignore` — excludes `.env` and other sensitive files
- `requirements.txt` — pinned dependencies:
  ```
  py-cord
  sqlalchemy
  pymysql
  requests
  python-dotenv
  ```

**Project directory structure:**
```
sos-epgp-bot/
├── docker-compose.yml
├── Dockerfile
├── requirements.txt
├── .env                  # never committed
├── .env.example          # committed, safe template
├── .gitignore
├── main.py               # bot entry point (Phase 2)
├── sync.py               # standalone sync script (Phase 1)
├── classes/
│   ├── database.py       # SQLAlchemy setup, table definitions
│   └── epgp_sync.py      # Google Sheets fetch and sync logic
└── cogs/
    └── epgp.py           # slash commands (Phase 2)
```

**Verification:** MySQL is reachable from the Python container, tables can be
created, and a test row can be inserted and queried before moving to Phase 1.

**Key Docker concepts used:**
- **Image** — the blueprint for a container (e.g. `mysql:8`, `python:3.11-slim`)
- **Container** — a running instance of an image
- **Volume** — persistent storage that survives container restarts (MySQL data)
- **Compose** — tool that manages multiple containers as one application
- `docker compose up` — starts everything
- `docker compose down` — stops everything
- `docker compose logs bot` — view Python container output

**Note on PR integration:** The `docker-compose.yml` is a development convenience,
not a deployment requirement. When submitting the PR to the existing bot, only the
Python source files (`classes/`, `cogs/`, any new dependencies in their
`requirements.txt`) will be included. Docker setup stays in your personal repo.

---

### Phase 1 — Data Validation (runs inside Docker)
- Write `sync.py`: fetch EP Log, GP Log, Cycles tab via HTTP, store in MySQL
- Confirm incremental sync works correctly (append-only, date-based grouping)
- Write and test attendance query logic (baseline comparison, discrepancy detection)
- Print results to console — no Discord yet
- Validate output against known data before any bot work

---

### Phase 2 — Standalone Personal Bot
- Write `main.py` bot entry point with py-cord
- Implement `/review` with conversational flow and MySQL persistence
- Implement DM notifications triggered after each sync
- Implement `/item` with partial name search
- Implement `/priority` with class/armor type lookup table
- Test thoroughly as a personal tool

---

### Phase 3 — PR into Existing Bot
- Fork https://github.com/khandyman/SOS-Bot
- Port Phase 2 code into existing structure (`cogs/epgp.py`, `classes/`)
- Replace hard-coded player name with Discord ID → character lookup
- Handle main/alt relationships using existing bot's database
- Investigate and resolve alt attendance edge case with real data
- Submit PR

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

## Open Items & Deferred Decisions

| Item | Status | Notes |
|------|--------|-------|
| Alt attendance in EP Log | Deferred | Need to confirm whether alt credit is logged under alt name or main name. Do not design around this until confirmed with real data. |
| Cycles tab column layout | Not yet fetched | Confirm exact structure before syncing |
| Sync schedule interval | TBD | Determine appropriate polling frequency |
| Additional commands | Pending | `/pr`, `/standings`, `/loot`, `/decay`, `/whowas`, `/keys`, `/unresolved` — not committed to, evaluate after core features are working |
| Voice channel priority | Phase 3+ | Requires existing bot integration for Discord voice membership |
| Webhook-triggered sync | Phase 3+ | Requires coordination with the bot that writes to Google Sheets |