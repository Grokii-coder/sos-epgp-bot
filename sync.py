import os
import csv
import requests
import io
import time
from datetime import datetime
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

load_dotenv()

# Database connection
DB_USER     = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_HOST     = os.getenv("DB_HOST")
DB_PORT     = os.getenv("DB_PORT")
DB_NAME     = os.getenv("DB_NAME")

CONNECTION_STRING = f"mysql+pymysql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

# Google Sheet config
SHEET_ID = os.getenv("SHEET_ID")
TABS = {
    "ep_log":  "264766085",
    "gp_log":  "116377915",
    "cycles":  "850187403",
}

def get_engine():
    return create_engine(CONNECTION_STRING)

def fetch_sheet_tab(tab_name):
    """Fetch a Google Sheet tab as a list of rows."""
    gid = TABS[tab_name]
    url = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/export?format=csv&gid={gid}"
    print(f"Fetching {tab_name} from Google Sheets...")
    response = requests.get(url)
    if response.status_code != 200:
        print(f"Failed to fetch {tab_name}: HTTP {response.status_code}")
        return []
    content = response.content.decode("utf-8")
    reader = csv.reader(io.StringIO(content))
    rows = list(reader)
    print(f"Fetched {len(rows)} rows from {tab_name}")
    return rows

def parse_date(date_str):
    """Parse various date formats into YYYY-MM-DD for MySQL."""
    if not date_str or date_str.strip() == '':
        return None
    date_str = date_str.strip()
    for fmt in ('%m/%d/%Y', '%m/%d/%y'):
        try:
            return datetime.strptime(date_str, fmt).date()
        except ValueError:
            continue
    return None

def parse_int(val):
    """Safely parse an integer, return None if empty or invalid."""
    try:
        return int(val.strip()) if val and val.strip() else None
    except (ValueError, AttributeError):
        return None

def get_last_sheet_row(conn, table):
    """Get the highest sheet_row already stored for a table."""
    result = conn.execute(text(f"SELECT MAX(sheet_row) FROM {table}"))
    val = result.scalar()
    return val if val is not None else 0

def sync_ep_log(conn, rows):
    """Insert new EP Log rows into the database."""
    last_row = get_last_sheet_row(conn, "ep_log")
    print(f"EP Log: last stored sheet_row = {last_row}")

    inserted = 0
    skipped  = 0

    for sheet_row, row in enumerate(rows, start=1):
        # Skip header row and rows we already have
        if sheet_row <= 1:
            continue
        if sheet_row <= last_row:
            skipped += 1
            continue

        # Skip rows where the clean side (col 12) is empty or is a header
        if len(row) < 23 or row[12].strip() == '' or row[12].strip() == 'Cycle':
            continue

        try:
            conn.execute(text("""
                INSERT IGNORE INTO ep_log
                    (cycle, date, name, class, level, point_type, pp_value,
                     ep_points, cycle_sum, points_earned, note, sheet_row)
                VALUES
                    (:cycle, :date, :name, :class, :level, :point_type, :pp_value,
                     :ep_points, :cycle_sum, :points_earned, :note, :sheet_row)
            """), {
                "cycle":         parse_int(row[12]),
                "date":          parse_date(row[13]),
                "name":          row[14].strip(),
                "class":         row[15].strip(),
                "level":         row[16].strip(),
                "point_type":    row[17].strip(),
                "pp_value":      row[18].strip() or None,
                "ep_points":     parse_int(row[19]),
                "cycle_sum":     parse_int(row[20]),
                "points_earned": parse_int(row[21]),
                "note":          row[22].strip() or None,
                "sheet_row":     sheet_row,
            })
            inserted += 1
        except Exception as e:
            print(f"  Error on EP row {sheet_row}: {e}")
            continue

    print(f"EP Log: {inserted} inserted, {skipped} skipped (already stored)")
    return inserted

def sync_gp_log(conn, rows):
    """Insert new GP Log rows into the database."""
    last_row = get_last_sheet_row(conn, "gp_log")
    print(f"GP Log: last stored sheet_row = {last_row}")

    inserted = 0
    skipped  = 0

    for sheet_row, row in enumerate(rows, start=1):
        # Row 1 is junk header, skip it and already-stored rows
        if sheet_row <= 1:
            continue
        if sheet_row <= last_row:
            skipped += 1
            continue

        # Skip empty rows or header rows
        if len(row) < 7 or row[2].strip() == '' or row[2].strip() == 'Date':
            continue

        try:
            conn.execute(text("""
                INSERT IGNORE INTO gp_log
                    (date, toon_name, loot, gear_level, gp_value, duplicate, sheet_row)
                VALUES
                    (:date, :toon_name, :loot, :gear_level, :gp_value, :duplicate, :sheet_row)
            """), {
                "date":       parse_date(row[2]),
                "toon_name":  row[3].strip(),
                "loot":       row[4].strip(),
                "gear_level": row[5].strip(),
                "gp_value":   parse_int(row[6]),
                "duplicate":  1 if row[7].strip().lower() == 'yes' else 0,
                "sheet_row":  sheet_row,
            })
            inserted += 1
        except Exception as e:
            print(f"  Error on GP row {sheet_row}: {e}")
            continue

    print(f"GP Log: {inserted} inserted, {skipped} skipped (already stored)")
    return inserted

def sync_cycles(conn, rows):
    """Sync the cycles table - small table, upsert all rows."""
    inserted = 0

    for sheet_row, row in enumerate(rows, start=1):
        # Row 1 is blank, row 2 is header, data starts at row 3
        if sheet_row <= 2:
            continue

        # Skip empty rows
        if len(row) < 4 or row[1].strip() == '':
            continue

        try:
            conn.execute(text("""
                INSERT INTO cycles (cycle_number, start_date, end_date)
                VALUES (:cycle_number, :start_date, :end_date)
                ON DUPLICATE KEY UPDATE
                    start_date = VALUES(start_date),
                    end_date   = VALUES(end_date)
            """), {
                "cycle_number": parse_int(row[3]),
                "start_date":   parse_date(row[1]),
                "end_date":     parse_date(row[2]),
            })
            inserted += 1
        except Exception as e:
            print(f"  Error on cycle row {sheet_row}: {e}")
            continue

    print(f"Cycles: {inserted} processed")
    return inserted

def wait_for_db(retries=10, delay=5):
    """Wait for MySQL to be ready before proceeding."""
    for attempt in range(retries):
        try:
            engine = get_engine()
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            print("Database ready!")
            return True
        except Exception as e:
            print(f"Database not ready (attempt {attempt + 1}/{retries}): {e}")
            time.sleep(delay)
    print("Could not connect to database after multiple attempts.")
    return False

def run_sync():
    """Main sync function - fetch all tabs and store in MySQL."""
    print(f"\n{'='*50}")
    print(f"Starting sync at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*50}")

    if not wait_for_db():
        return

    engine = get_engine()

    # Fetch all tabs first
    ep_rows    = fetch_sheet_tab("ep_log")
    gp_rows    = fetch_sheet_tab("gp_log")
    cycle_rows = fetch_sheet_tab("cycles")

    # Insert into database
    with engine.begin() as conn:
        sync_cycles(conn, cycle_rows)
        sync_ep_log(conn, ep_rows)
        sync_gp_log(conn, gp_rows)

    print(f"\nSync complete at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

if __name__ == "__main__":
    run_sync()
    print("\nDone - exiting.")