import os
from datetime import datetime
from classes.database import get_engine, wait_for_db
from classes.sheets import fetch_sheet_tab
from classes.ep_sync import sync_ep_log
from classes.gp_sync import sync_gp_log
from classes.cycle_sync import sync_cycles


def run_sync():
    """Main sync orchestrator - fetch all tabs and store in MySQL."""
    print(f"\n{'='*50}")
    print(f"Starting sync at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*50}")

    if not wait_for_db():
        return

    engine = get_engine()

    # Fetch all tabs from Google Sheets
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