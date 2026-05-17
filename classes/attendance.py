from datetime import date, timedelta
from sqlalchemy import text
from classes.database import get_engine

# Point types that represent raid/event check-ins
# Anything not in this list is a bonus (level up, donation, etc.) and ignored
EVENT_POINT_TYPES = {
    'Raid - Start',
    'Raid - Mid',
    'Raid - End',
    'Event Attend',
}


def get_current_cycle(conn):
    """Return the current cycle row based on today's date."""
    today = date.today()
    result = conn.execute(text("""
        SELECT cycle_number, start_date, end_date
        FROM cycles
        WHERE :today BETWEEN start_date AND end_date
        LIMIT 1
    """), {"today": today})
    return result.mappings().fetchone()


def get_cycle_by_number(conn, cycle_number):
    """Return a specific cycle row by cycle number."""
    result = conn.execute(text("""
        SELECT cycle_number, start_date, end_date
        FROM cycles
        WHERE cycle_number = :cycle_number
    """), {"cycle_number": cycle_number})
    return result.mappings().fetchone()


def get_events_in_range(conn, start_date, end_date):
    """Return all unique event dates and their available check-ins
    within a date range, based on what the guild received.
    Minimum 12 players required to count as a real guild event
    (matches the guild's PQ eligibility requirement)."""
    result = conn.execute(text("""
        SELECT date, point_type
        FROM ep_log
        WHERE date BETWEEN :start_date AND :end_date
        AND point_type IN :point_types
        GROUP BY date, point_type
        HAVING COUNT(DISTINCT name) >= 12
        ORDER BY date DESC
    """), {
        "start_date":  start_date,
        "end_date":    end_date,
        "point_types": tuple(EVENT_POINT_TYPES),
    })
    rows = result.mappings().fetchall()

    # Group by date -> set of point_types available that day
    events = {}
    for row in rows:
        d = row['date']
        if d not in events:
            events[d] = set()
        events[d].add(row['point_type'])

    return events


def get_player_checkins(conn, player_name, start_date, end_date):
    """Return all check-ins a player received within a date range."""
    result = conn.execute(text("""
        SELECT date, point_type
        FROM ep_log
        WHERE name = :name
        AND date BETWEEN :start_date AND :end_date
        AND point_type IN :point_types
    """), {
        "name":        player_name,
        "start_date":  start_date,
        "end_date":    end_date,
        "point_types": tuple(EVENT_POINT_TYPES),
    })
    rows = result.mappings().fetchall()

    # Group by date -> set of point_types the player received
    checkins = {}
    for row in rows:
        d = row['date']
        if d not in checkins:
            checkins[d] = set()
        checkins[d].add(row['point_type'])

    return checkins


def get_event_location(conn, event_date):
    """Return the event location for a given date.
    Location is stored in the note field of the first Raid - Start entry."""
    result = conn.execute(text("""
        SELECT note
        FROM ep_log
        WHERE date = :date
        AND point_type = 'Raid - Start'
        AND note IS NOT NULL
        AND note != ''
        LIMIT 1
    """), {"date": event_date})
    row = result.fetchone()
    return row[0] if row else "Unknown"


def get_event_type(point_types):
    """Determine event type from the set of point types."""
    if 'Event Attend' in point_types:
        return 'PQ Event'
    return 'EPGP Raid'


def get_player_ep_progress(conn, player_name, cycle_number):
    """Return the player's EP progress for a given cycle."""
    result = conn.execute(text("""
        SELECT MAX(cycle_sum) as cycle_sum
        FROM ep_log
        WHERE name = :name
        AND cycle = :cycle
    """), {
        "name":  player_name,
        "cycle": cycle_number,
    })
    row = result.fetchone()
    return row[0] if row and row[0] is not None else 0


def build_attendance_report(player_name, cycle_number=None):
    """Build the full attendance report for a player.
    Returns cycle info, EP progress, and list of discrepancies."""
    engine = get_engine()

    with engine.connect() as conn:
        # Get cycle
        if cycle_number:
            cycle = get_cycle_by_number(conn, cycle_number)
        else:
            cycle = get_current_cycle(conn)

        if not cycle:
            return {"error": "Cycle not found."}

        start_date = cycle['start_date']
        end_date   = cycle['end_date']
        cycle_num  = cycle['cycle_number']

        # EP progress
        ep_earned = get_player_ep_progress(conn, player_name, cycle_num)

        # Guild events vs player check-ins
        all_events     = get_events_in_range(conn, start_date, end_date)
        player_checkins = get_player_checkins(conn, player_name, start_date, end_date)

        # Build discrepancy list
        discrepancies = []
        for event_date, guild_checkins in sorted(all_events.items(), reverse=True):
            player_got = player_checkins.get(event_date, set())

            # Split PQ and raid check-ins into separate events if both exist
            raid_types = guild_checkins & {'Raid - Start', 'Raid - Mid', 'Raid - End'}
            pq_types   = guild_checkins & {'Event Attend'}

            for event_checkins, event_type in [
                (raid_types, 'EPGP Raid'),
                (pq_types,   'PQ Event'),
            ]:
                if not event_checkins:
                    continue

                player_got_this = player_got & event_checkins
                missing         = event_checkins - player_got_this
                location        = get_event_location(conn, event_date)

                if missing:
                    discrepancies.append({
                        "date":           event_date,
                        "location":       location,
                        "event_type":     event_type,
                        "guild_checkins": sorted(event_checkins),
                        "player_got":     sorted(player_got_this),
                        "missing":        sorted(missing),
                    })

    return {
        "player":       player_name,
        "cycle":        cycle_num,
        "start_date":   start_date,
        "end_date":     end_date,
        "ep_earned":    ep_earned,
        "ep_cap":       900,
        "discrepancies": discrepancies,
    }