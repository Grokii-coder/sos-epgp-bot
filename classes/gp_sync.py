from sqlalchemy import text
from classes.helpers import parse_date, parse_int
from classes.database import get_last_sheet_row


def sync_gp_log(conn, rows):
    """Insert new GP Log rows into the database.
    Skips rows already stored using sheet_row as the incremental marker.
    Row 1 is a junk header and is skipped.
    Column mapping: 2=date, 3=toon_name, 4=loot, 5=gear_level, 6=gp_value, 7=duplicate."""
    last_row = get_last_sheet_row(conn, "gp_log")
    print(f"GP Log: last stored sheet_row = {last_row}")

    inserted = 0
    skipped  = 0

    for sheet_row, row in enumerate(rows, start=1):
        # Row 1 is junk header
        if sheet_row <= 1:
            continue
        # Skip rows we already have
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