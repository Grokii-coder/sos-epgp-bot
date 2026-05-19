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
        ORDER BY date ASC
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
    return row[0] if row else None


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


def get_answered_events(conn, player_name):
    """Return set of (event_date, event_type) tuples already answered by player.
    These are skipped in the discrepancy list."""
    result = conn.execute(text("""
        SELECT event_date, event_type
        FROM attendance_responses
        WHERE player_name = :player_name
    """), {"player_name": player_name})
    return {(row[0], row[1]) for row in result.fetchall()}


def get_scheduled_event_for_date(conn, event_date):
    """Look up the Discord scheduled event for a given raid date.
    Matches on the date portion of start_time.
    Returns a dict with name, location, previous_names, creator_name or None."""
    result = conn.execute(text("""
        SELECT se.event_id, se.name, se.location, se.creator_name,
               se.creator_id
        FROM scheduled_events se
        WHERE DATE(se.start_time) = :event_date
        LIMIT 1
    """), {"event_date": event_date})
    row = result.mappings().fetchone()
    if not row:
        return None

    # Get name history for this event
    history = conn.execute(text("""
        SELECT previous_value, new_value, changed_at
        FROM event_history
        WHERE event_id = :event_id
        AND field_changed = 'name'
        ORDER BY changed_at ASC
    """), {"event_id": row['event_id']})
    name_changes = history.mappings().fetchall()

    # Build list of previous names in order
    previous_names = [h['previous_value'] for h in name_changes]

    return {
        "name":           row['name'],
        "location":       row['location'],
        "creator_name":   row['creator_name'],
        "previous_names": previous_names,
    }


def format_event_location(discord_event, sheet_note):
    """Build the rich location display string.
    Format: DISCORD_NAME (was: PREV) [sheet: NOTE] 👤 LEADER
    """
    if not discord_event:
        # No Discord event found - fall back to sheet note only
        return f"[sheet: {sheet_note}]" if sheet_note else "Unknown"

    parts = []

    # Current Discord event name
    parts.append(discord_event['name'])

    # Previous names if any
    if discord_event['previous_names']:
        was = ', '.join(discord_event['previous_names'])
        parts.append(f"(was: {was})")

    # Sheet note
    if sheet_note:
        parts.append(f"[sheet: {sheet_note}]")

    location = ' '.join(parts)

    # Add leader
    if discord_event['creator_name']:
        location += f" 👤 {discord_event['creator_name']}"

    return location


def get_event_statement(event_type, missing, got):
    """Generate the two-statement description for a discrepancy.
    Returns (statement1, statement2) tuple."""
    missing_set = set(missing)
    got_set     = set(got)

    if event_type == 'PQ Event':
        return (
            "You aren't in any logs for this PQ event.",
            "You likely did not attend."
        )

    # EPGP Raid - determine which check-ins were missing vs received
    miss_start = 'Raid - Start' in missing_set
    miss_mid   = 'Raid - Mid'   in missing_set
    miss_end   = 'Raid - End'   in missing_set

    # Missing everything
    if miss_start and miss_mid and miss_end:
        return (
            "You aren't in any logs for this event.",
            "You likely did not attend."
        )

    # Missing start only - joined late
    if miss_start and not miss_mid and not miss_end:
        return (
            "You were credited for Mid and End, but not Start.",
            "You likely joined late."
        )

    # Missing end only - left early
    if not miss_start and not miss_mid and miss_end:
        return (
            "You were credited for Start and Mid, but not End.",
            "You likely left early."
        )

    # Missing mid only - logging error
    if not miss_start and miss_mid and not miss_end:
        return (
            "You were credited for Start and End, but not Mid.",
            "This is likely a logging error."
        )

    # Missing start and mid - only have end
    if miss_start and miss_mid and not miss_end:
        return (
            "You were only credited for End.",
            "You likely joined late."
        )

    # Missing mid and end - only have start
    if not miss_start and miss_mid and miss_end:
        return (
            "You were only credited for Start.",
            "You likely left early."
        )

    # Missing start and end - only have mid
    if miss_start and not miss_mid and miss_end:
        return (
            "You were only credited for Mid.",
            "This is likely a logging error."
        )

    # Fallback
    return (
        f"You are missing credit for: {', '.join(sorted(missing_set))}.",
        "Please review your attendance."
    )


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
        all_events      = get_events_in_range(conn, start_date, end_date)
        player_checkins = get_player_checkins(conn, player_name, start_date, end_date)

        # Already answered events - skip these
        answered = get_answered_events(conn, player_name)

        # Build discrepancy list
        discrepancies = []
        for event_date, guild_checkins in sorted(all_events.items()):
            player_got = player_checkins.get(event_date, set())

            # Get Discord event and sheet note for location display
            discord_event = get_scheduled_event_for_date(conn, event_date)
            sheet_note    = get_event_location(conn, event_date)
            location      = format_event_location(discord_event, sheet_note)

            # Split PQ and raid check-ins into separate events if both exist
            raid_types = guild_checkins & {'Raid - Start', 'Raid - Mid', 'Raid - End'}
            pq_types   = guild_checkins & {'Event Attend'}

            for event_checkins, event_type in [
                (raid_types, 'EPGP Raid'),
                (pq_types,   'PQ Event'),
            ]:
                if not event_checkins:
                    continue

                # Skip if player already answered this event
                if (event_date, event_type) in answered:
                    continue

                player_got_this = player_got & event_checkins
                missing         = event_checkins - player_got_this

                if missing:
                    stmt1, stmt2 = get_event_statement(
                        event_type, missing, player_got_this
                    )
                    discrepancies.append({
                        "date":           event_date,
                        "location":       location,
                        "event_type":     event_type,
                        "guild_checkins": sorted(event_checkins),
                        "player_got":     sorted(player_got_this),
                        "missing":        sorted(missing),
                        "statement1":     stmt1,
                        "statement2":     stmt2,
                    })

    return {
        "player":        player_name,
        "cycle":         cycle_num,
        "start_date":    start_date,
        "end_date":      end_date,
        "ep_earned":     ep_earned,
        "ep_cap":        900,
        "discrepancies": discrepancies,
    }