from datetime import datetime, timedelta
from sqlalchemy import text
from classes.database import get_engine
from classes.sheets import fetch_sheet_tab
from classes.ep_sync import sync_ep_log
from classes.gp_sync import sync_gp_log
from classes.cycle_sync import sync_cycles

SYNC_TTL_MINUTES = 5


def get_last_sync(conn):
    """Return the last sync datetime or None if never synced."""
    result = conn.execute(text("SELECT last_sync FROM sync_state WHERE id = 1"))
    row = result.fetchone()
    return row[0] if row and row[0] else None


def update_last_sync(conn):
    """Update the last sync timestamp to now."""
    conn.execute(text("""
        UPDATE sync_state SET last_sync = :now WHERE id = 1
    """), {"now": datetime.utcnow()})


def is_sync_needed():
    """Return True if more than SYNC_TTL_MINUTES have passed since last sync."""
    engine = get_engine()
    with engine.connect() as conn:
        last_sync = get_last_sync(conn)
    if last_sync is None:
        return True
    age = datetime.utcnow() - last_sync
    return age > timedelta(minutes=SYNC_TTL_MINUTES)


def run_sync_if_needed():
    """Run a full sync only if the TTL has expired.
    Called before any bot command that needs fresh data.
    Returns True if a sync was run, False if cache was used."""
    if not is_sync_needed():
        print("Sync skipped - cache is fresh (under 5 minutes old)")
        return False

    print("Cache expired - running sync...")
    engine = get_engine()

    ep_rows    = fetch_sheet_tab("ep_log")
    gp_rows    = fetch_sheet_tab("gp_log")
    cycle_rows = fetch_sheet_tab("cycles")

    with engine.begin() as conn:
        sync_cycles(conn, cycle_rows)
        sync_ep_log(conn, ep_rows)
        sync_gp_log(conn, gp_rows)
        update_last_sync(conn)

    print(f"Sync complete at {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC")
    return True