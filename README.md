# SoS EPGP Bot

A Discord bot for the **Seekers of Souls** guild on Project Quarm. Queries the
guild's EPGP tracking spreadsheet and provides attendance auditing, loot history,
and priority ranking via Discord slash commands.

---

## Features

- `/review` — Review EP cap progress and missing event credits for a cycle.
  Walks through discrepancies one at a time with Yes/No/Skip buttons.
- `/item` — Look up loot history for any item (partial name search supported).
- `/priority` — Show your loot priority rank by class and armor type.
- **Real-time Discord event tracking** — Listens for guild scheduled event
  changes and records pivot history (e.g. Kael → VT).
- **Incremental sync** — Only fetches new rows from Google Sheets, with a
  5-minute TTL cache to avoid unnecessary API calls.

---

## Prerequisites

- [Docker Desktop](https://www.docker.com/products/docker-desktop) installed and running
- A Discord bot token ([Discord Developer Portal](https://discord.com/developers/applications))
- Access to the guild's Google Spreadsheet (public, no credentials needed)

---

## Setup

### 1. Clone the repo

```bash
git clone https://github.com/Grokii-coder/sos-epgp-bot.git
cd sos-epgp-bot
```

### 2. Create your `.env` file

Copy the example and fill in your values:

```bash
cp .env.example .env
```

Edit `.env`:

```env
# Player identity
PLAYER_NAME=YourCharacterName
DISCORD_USER_ID=YourDiscordUserID

# Discord bot token (from Discord Developer Portal → Bot → Token)
DISCORD_TOKEN=your_token_here

# Google Sheet ID (already filled in - the guild sheet)
SHEET_ID=1pu43LSErcxSaaAkaaTrvMi8GfZYV-dRf1qaWyKiveAA

# Discord guild IDs
GUILD_ID_PROD=1155966759694778454
GUILD_ID_TEST=your_test_server_id

# Database credentials (choose your own passwords)
DB_HOST=db
DB_PORT=3306
DB_NAME=sosbot
DB_USER=botuser
DB_PASSWORD=choose_a_password
DB_ROOT_PASSWORD=choose_a_root_password
```

**Important:** Never commit `.env` to git. It is listed in `.gitignore`.

### 3. Start the bot

```bash
docker compose up -d
```

On first run this will:
- Pull the MySQL and Python Docker images
- Create the database and all tables from `init.sql`
- Fetch the full EP Log, GP Log, and Cycles history from Google Sheets
- Connect to Discord and register slash commands

View logs:
```bash
docker logs sos-epgp-bot-bot-1 --follow
```

---

## Restarting — What Gets Reloaded

Different restart commands reload different things. Use the right one for your situation.

| Command | Python Code | .env Variables | DB Schema | DB Data |
|---------|:-----------:|:--------------:|:---------:|:-------:|
| `docker compose restart bot` | ✅ | ❌ | ❌ | ✅ |
| `docker compose down && docker compose up -d` | ✅ | ✅ | ❌ | ✅ |
| `docker compose up --build -d` | ✅ | ✅ | ❌ | ✅ |
| `docker compose down -v && docker compose up -d` | ✅ | ✅ | ✅ fresh | ❌ wiped |

### When to use each

**Changed a Python file (`.py`)?**
```bash
docker compose restart bot
```
Fastest option. Bind mount means the container sees your changes immediately.

**Changed `.env` (added a variable, changed a password)?**
```bash
docker compose down && docker compose up -d
```
Full restart loads the new environment variables.

**Changed `requirements.txt` (added a pip package)?**
```bash
docker compose up --build -d
```
Rebuilds the Python Docker image with the new packages installed.

**Changed `init.sql` (modified the database schema)?**
```bash
docker compose down -v && docker compose up -d
```
⚠️ **This wipes all MySQL data.** The `-v` flag removes the named volume.
MySQL will re-run `init.sql` on fresh start. All Google Sheets data will be
re-synced automatically, but any `attendance_responses` you've recorded will
be lost.

### Decision tree

```
Changed requirements.txt?  →  docker compose up --build -d
Changed .env?              →  docker compose down && docker compose up -d
Changed init.sql schema?   →  docker compose down -v && docker compose up -d
Changed Python code only?  →  docker compose restart bot
```

---

### Read logs after a restart

```
docker logs sos-epgp-bot-bot-1 --follow
```


---

## Database Queries

Run a one-off MySQL query without opening an interactive session.

**Bash (Linux/Mac/Git Bash):**
```bash
docker compose exec db mysql -u botuser -p"${DB_PASSWORD}" sosbot -e "YOUR QUERY HERE;"
```

**PowerShell (Windows):**
```powershell
$pw = (Get-Content .env | Select-String 'DB_PASSWORD' | ForEach-Object { $_.ToString().Split('=')[1] })
docker compose exec db mysql -u botuser -p"$pw" sosbot -e "YOUR QUERY HERE;"
```

> **Why not `$env:DB_PASSWORD`?** Docker Compose loads `.env` into the
> container but does not export those values into your host PowerShell session.
> Reading directly from the `.env` file is the reliable cross-platform approach.

### Useful one-liners

```powershell
# See every distinct class name that has ever appeared in the EP log
# (use this to verify class alias mappings and catch unexpected title strings)
$pw = (Get-Content .env | Select-String 'DB_PASSWORD' | ForEach-Object { $_.ToString().Split('=')[1] })
docker compose exec db mysql -u botuser -p"$pw" sosbot -e "SELECT DISTINCT class FROM ep_log ORDER BY class;"
```

---

## Project Structure

```
sos-epgp-bot/
├── main.py                  # Bot entry point - loads cogs, handles startup sync
├── sync.py                  # Manual sync utility (run on demand)
├── test_attendance.py       # Console test for attendance query logic
├── classes/
│   ├── database.py          # SQLAlchemy engine, DB connection helpers
│   ├── sheets.py            # Google Sheets CSV fetch
│   ├── ep_sync.py           # EP Log incremental insert
│   ├── gp_sync.py           # GP Log incremental insert
│   ├── cycle_sync.py        # Cycles table upsert
│   ├── sync_manager.py      # TTL cache - run_sync_if_needed()
│   ├── attendance.py        # Attendance query and report builder
│   └── helpers.py           # parse_date(), parse_int() utilities
├── cogs/
│   ├── review.py            # /review command
│   ├── item.py              # /item command
│   ├── priority.py          # /priority command
│   └── events.py            # Discord scheduled event listeners
├── init.sql                 # Database schema - runs once on first MySQL boot
├── Dockerfile               # Python container definition
├── docker-compose.yml       # MySQL + Python container orchestration
├── requirements.txt         # Python dependencies (pinned versions)
├── .env                     # Your credentials - never committed
├── .env.example             # Safe template - committed to git
└── Design.md                # Full design document with all decisions
```

---

## Database Schema

| Table | Purpose |
|-------|---------|
| `ep_log` | All EP transactions from the Google Sheet |
| `gp_log` | All loot/GP transactions from the Google Sheet |
| `cycles` | Raid cycle boundaries (start date, end date, cycle number) |
| `attendance_responses` | Player yes/no/skip responses from `/review` |
| `scheduled_events` | Discord guild scheduled events (current state) |
| `event_history` | Change log for scheduled events (name, location, time changes) |
| `sync_state` | Tracks last sync timestamp for TTL cache |

---

## Commands

### `/review [player] [cycle]`
Reviews EP cap progress and missing event credits.

- `player` — optional, defaults to `PLAYER_NAME` in `.env`
- `cycle` — optional, defaults to current cycle

Shows a summary of all discrepancies, then walks through each one with:
- Two-statement description of what the log shows
- **✅ Yes, the EPGP sheet is correct** — marks resolved
- **❌ No, the EPGP sheet is wrong** — flags as disputed
- **⏭️ Skip for now** — deferred, appears again next time

### `/item <name>`
Shows loot history for an item. Partial name search supported.
If multiple items match, bot asks for clarification.
Shows total drop count and last 3 drops with date, recipient, bid type, GP cost.

### `/priority`
Shows your PR rank among your class and armor type group.
Class is looked up automatically from the Overview tab.

---

## Tech Stack

| Component | Choice |
|-----------|--------|
| Language | Python 3.11 |
| Discord library | py-cord |
| Database | MySQL 8.0 |
| ORM | SQLAlchemy |
| DB driver | PyMySQL |
| HTTP | requests |
| Config | python-dotenv |
| Dev environment | Docker + Docker Compose |

---

## Design Document

See `Design.md` for the full planning document including all design decisions,
data source analysis, scope creep items, and open questions.

---

## Related

- Guild's existing bot: [khandyman/SOS-Bot](https://github.com/khandyman/SOS-Bot)
- Guild's EPGP spreadsheet: [Google Sheets](https://docs.google.com/spreadsheets/d/1pu43LSErcxSaaAkaaTrvMi8GfZYV-dRf1qaWyKiveAA)