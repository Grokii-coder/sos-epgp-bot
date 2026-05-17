from datetime import datetime
from classes.database import wait_for_db
from classes.sync_manager import run_sync_if_needed


def run_sync():
    """Main sync entry point - respects TTL cache."""
    print(f"\n{'='*50}")
    print(f"Starting sync at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*50}")

    if not wait_for_db():
        return

    run_sync_if_needed()
    print("\nDone - exiting.")


if __name__ == "__main__":
    run_sync()