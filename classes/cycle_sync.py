from sqlalchemy import text
from classes.helpers import parse_date, parse_int


def sync_cycles(conn, rows):
    """Sync the cycles table from the Cycles tab.
    Small table so we upsert all rows every sync.
    Row 1 is blank, row 2 is header, data starts at row 3.
    Column mapping: 1=start_date, 2=end_date, 3=cycle_number."""
    inserted = 0

    for sheet_row, row in enumerate(rows, start=1):
        # Row 1 is blank, row 2 is header
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