from sqlalchemy import text
from classes.helpers import parse_date, parse_int
from classes.database import get_last_sheet_row


def sync_ep_log(conn, rows):
    """Insert new EP Log rows into the database.
    Skips rows already stored using sheet_row as the incremental marker.
    Reads from the clean side of the sheet (columns 12-22).
    Column 18 (pp_value) is a hidden field - stored but purpose unknown."""
    last_row = get_last_sheet_row(conn, "ep_log")
    print(f"EP Log: last stored sheet_row = {last_row}")

    inserted = 0
    skipped  = 0

    for sheet_row, row in enumerate(rows, start=1):
        # Skip header row
        if sheet_row <= 1:
            continue
        # Skip rows we already have
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