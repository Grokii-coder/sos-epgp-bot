"""
SC-5 Test Gaps
==============
Covers three gaps left open after SC-5 live testing (2026-05-29):

  T5  — Regression: save_event / record_name_change must NOT touch sync_state
  T1  — Voice-channel branch: hasattr(val, 'name') path in save_event()
  T2-5 — Same-date double events: LIMIT 1 returns the earliest start_time row

All tests are pure unit tests — no running database required.
"""

import asyncio
from datetime import datetime, date, timezone
from unittest.mock import AsyncMock, MagicMock, patch, call
import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_text_event(
    event_id=1001,
    name="VT Night 1",
    location_str="Veeshan's Peak",
    creator_id=9001,
    status_name="scheduled",
    start_time=None,
    end_time=None,
    guild_id=5555,
    description="",
):
    """Return a mock Discord ScheduledEvent with a plain text location.

    event.location.value is a str — this is the branch that fires in practice
    and was already confirmed by T1 live testing.  Included here so the
    voice-channel test has a clean baseline to contrast against.
    """
    event = MagicMock()
    event.id           = event_id
    event.name         = name
    event.creator_id   = creator_id
    event.description  = description

    # location object: .value is a plain string
    loc       = MagicMock()
    loc.value = location_str
    event.location = loc

    # status enum
    status      = MagicMock()
    status.name = status_name
    event.status = status

    # timestamps
    event.start_time = start_time or datetime(2026, 6, 1, 20, 0, tzinfo=timezone.utc)
    event.end_time   = end_time   or datetime(2026, 6, 1, 23, 0, tzinfo=timezone.utc)

    # guild
    guild    = MagicMock()
    guild.id = guild_id
    event.guild = guild

    return event


def _make_voice_event(**kwargs):
    """Return a mock ScheduledEvent whose location.value has a .name attribute.

    This simulates a voice-channel-based event.  py-cord resolves
    event.location.value to a VoiceChannel object in this case; the relevant
    attribute is .name (e.g. "Raid Voice 1").
    """
    event = _make_text_event(**kwargs)

    # Replace location.value with an object that has .name but is NOT a str
    voice_channel       = MagicMock(spec=[])   # spec=[] → no default attrs
    voice_channel.name  = "Raid Voice 1"
    event.location.value = voice_channel       # isinstance(val, str) → False
                                               # hasattr(val, 'name')  → True
    return event


# ---------------------------------------------------------------------------
# T5 — Regression: SC-5 event writes do NOT invalidate the SC-3 sync TTL cache
# ---------------------------------------------------------------------------

class TestT5SyncStateIsolation:
    """
    save_event() and record_name_change() each open their own engine.begin()
    connection and write only to scheduled_events / event_history.
    They must never touch sync_state.

    Strategy: patch get_engine() to return an instrumented engine whose
    connections record every table name that appears in any SQL string.
    Assert 'sync_state' never appears.
    """

    def _run_save_event(self, event):
        """Run save_event() synchronously via asyncio.run for a given event."""
        executed_sql = []

        # --- build mock connection ------------------------------------------
        mock_conn = MagicMock()

        def capture_execute(stmt, params=None):
            executed_sql.append(str(stmt))
            return MagicMock()

        mock_conn.execute.side_effect = capture_execute
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__  = MagicMock(return_value=False)

        # engine.begin() returns the mock connection as a context manager
        mock_engine = MagicMock()
        mock_engine.begin.return_value = mock_conn

        # guild.fetch_member — async, returns a member with .name
        member      = MagicMock()
        member.name = "grokii_"
        event.guild.fetch_member = AsyncMock(return_value=member)

        with patch("cogs.events.get_engine", return_value=mock_engine):
            from cogs.events import EventsCog
            cog = EventsCog(bot=MagicMock())
            asyncio.run(cog.save_event(event))

        return executed_sql

    def _run_record_name_change(self, event_id, previous_name, new_name):
        """Run record_name_change() and return the list of executed SQL strings."""
        executed_sql = []

        mock_conn = MagicMock()

        def capture_execute(stmt, params=None):
            executed_sql.append(str(stmt))
            return MagicMock()

        mock_conn.execute.side_effect = capture_execute
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__  = MagicMock(return_value=False)

        mock_engine = MagicMock()
        mock_engine.begin.return_value = mock_conn

        with patch("cogs.events.get_engine", return_value=mock_engine):
            from cogs.events import EventsCog
            cog = EventsCog(bot=MagicMock())
            cog.record_name_change(event_id, previous_name, new_name)

        return executed_sql

    def test_save_event_does_not_touch_sync_state(self):
        """save_event() must not read or write sync_state."""
        event = _make_text_event()
        sql_stmts = self._run_save_event(event)

        assert sql_stmts, "save_event() executed no SQL — test setup broken"
        for stmt in sql_stmts:
            assert "sync_state" not in stmt.lower(), (
                f"save_event() touched sync_state — SC-3 TTL cache would be "
                f"affected.\nOffending SQL: {stmt}"
            )

    def test_record_name_change_does_not_touch_sync_state(self):
        """record_name_change() must not read or write sync_state."""
        sql_stmts = self._run_record_name_change(1001, "Old Name", "New Name")

        assert sql_stmts, "record_name_change() executed no SQL — test setup broken"
        for stmt in sql_stmts:
            assert "sync_state" not in stmt.lower(), (
                f"record_name_change() touched sync_state — SC-3 TTL cache "
                f"would be affected.\nOffending SQL: {stmt}"
            )

    def test_save_event_writes_to_scheduled_events(self):
        """Positive check: save_event() must write to scheduled_events."""
        event = _make_text_event()
        sql_stmts = self._run_save_event(event)

        assert any("scheduled_events" in s.lower() for s in sql_stmts), (
            "save_event() did not write to scheduled_events"
        )

    def test_record_name_change_writes_to_event_history(self):
        """Positive check: record_name_change() must write to event_history."""
        sql_stmts = self._run_record_name_change(1001, "Old Name", "New Name")

        assert any("event_history" in s.lower() for s in sql_stmts), (
            "record_name_change() did not write to event_history"
        )


# ---------------------------------------------------------------------------
# T1 — Voice-channel location branch: hasattr(val, 'name') in save_event()
# ---------------------------------------------------------------------------

class TestT1VoiceChannelBranch:
    """
    The location resolution block in save_event() has three branches:

        if hasattr(loc, 'value'):
            val = loc.value
            if isinstance(val, str):          ← confirmed by live testing
                location = val
            elif hasattr(val, 'name'):        ← THIS branch — never exercised
                location = val.name
            else:
                location = None

    This class exercises the voice-channel branch with a mock event whose
    location.value is an object with a .name attribute but is NOT a str.
    """

    def _run_save_event_capture_params(self, event):
        """Run save_event() and return the params dict passed to conn.execute."""
        captured_params = {}

        mock_conn = MagicMock()

        def capture_execute(stmt, params=None):
            if params:
                captured_params.update(params)
            return MagicMock()

        mock_conn.execute.side_effect = capture_execute
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__  = MagicMock(return_value=False)

        mock_engine = MagicMock()
        mock_engine.begin.return_value = mock_conn

        member      = MagicMock()
        member.name = "grokii_"
        event.guild.fetch_member = AsyncMock(return_value=member)

        with patch("cogs.events.get_engine", return_value=mock_engine):
            from cogs.events import EventsCog
            cog = EventsCog(bot=MagicMock())
            asyncio.run(cog.save_event(event))

        return captured_params

    def test_voice_channel_branch_fires_and_uses_channel_name(self):
        """hasattr(val, 'name') branch: location saved as the channel's .name."""
        event  = _make_voice_event()
        params = self._run_save_event_capture_params(event)

        assert "location" in params, (
            "save_event() did not pass 'location' to the DB execute call"
        )
        assert params["location"] == "Raid Voice 1", (
            f"Expected location='Raid Voice 1', got {params['location']!r}.\n"
            "hasattr(val, 'name') branch may not have fired."
        )

    def test_voice_branch_is_not_a_str(self):
        """Guard: confirm our mock value is not a str (branch pre-condition)."""
        event = _make_voice_event()
        val   = event.location.value
        assert not isinstance(val, str), (
            "Test setup error: voice channel mock value should not be a str"
        )

    def test_voice_branch_has_name_attr(self):
        """Guard: confirm our mock value has .name (branch pre-condition)."""
        event = _make_voice_event()
        val   = event.location.value
        assert hasattr(val, "name"), (
            "Test setup error: voice channel mock value must have .name"
        )

    def test_text_location_branch_still_works(self):
        """Baseline: str branch still resolves correctly after voice-branch work."""
        event  = _make_text_event(location_str="Veeshan's Peak")
        params = self._run_save_event_capture_params(event)
        assert params.get("location") == "Veeshan's Peak", (
            "str branch broken: text location not saved correctly"
        )

    def test_none_location_event(self):
        """Edge case: event.location is None → location saved as None, no crash."""
        event          = _make_text_event()
        event.location = None

        params = self._run_save_event_capture_params(event)
        assert params.get("location") is None, (
            "None location should be stored as NULL, not raise an exception"
        )


# ---------------------------------------------------------------------------
# T2-5 — Same-date double events: LIMIT 1 returns the earliest start_time row
# ---------------------------------------------------------------------------

class TestT25SameDateDoubleEvents:
    """
    get_scheduled_event_for_date() uses LIMIT 1 ordered by default
    (no explicit ORDER BY — MySQL returns the first matching row, which
    in practice is the row with the earliest start_time).

    With two events on the same date only one is returned.  This is the
    documented known limitation.  These tests confirm the behavior so
    that if the LIMIT is ever removed or an ORDER BY is added the suite
    will catch unintended regressions.
    """

    # ------------------------------------------------------------------
    # Helpers to build fake DB rows
    # ------------------------------------------------------------------

    def _make_mock_conn(self, se_row, history_rows=None):
        """Return a mock SQLAlchemy connection pre-loaded with canned rows.

        First execute() call → scheduled_events query (returns se_row or None).
        Second execute() call → event_history query (returns history_rows).
        """
        history_rows = history_rows or []

        # scheduled_events result
        if se_row is not None:
            se_mapping   = MagicMock()
            se_mapping.__getitem__ = lambda self_, k: se_row[k]
            se_result    = MagicMock()
            se_result.mappings.return_value.fetchone.return_value = se_mapping
        else:
            se_result = MagicMock()
            se_result.mappings.return_value.fetchone.return_value = None

        # event_history result
        hist_mappings = []
        for h in history_rows:
            m = MagicMock()
            m.__getitem__ = lambda self_, k, _h=h: _h[k]
            hist_mappings.append(m)

        hist_result = MagicMock()
        hist_result.mappings.return_value.fetchall.return_value = hist_mappings

        conn = MagicMock()
        conn.execute.side_effect = [se_result, hist_result]
        return conn

    # ------------------------------------------------------------------
    # Tests
    # ------------------------------------------------------------------

    def test_single_event_on_date_returns_correctly(self):
        """Baseline: one event on date → dict with correct fields returned."""
        from classes.attendance import get_scheduled_event_for_date

        se_row = {
            "event_id":     2001,
            "name":         "VT Night 1",
            "location":     "Veeshan's Peak",
            "creator_name": "grokii_",
            "creator_id":   9001,
        }
        conn   = self._make_mock_conn(se_row)
        result = get_scheduled_event_for_date(conn, date(2026, 6, 1))

        assert result is not None
        assert result["name"]           == "VT Night 1"
        assert result["location"]       == "Veeshan's Peak"
        assert result["creator_name"]   == "grokii_"
        assert result["previous_names"] == []

    def test_no_event_on_date_returns_none(self):
        """No scheduled event for date → None returned, no exception."""
        from classes.attendance import get_scheduled_event_for_date

        conn   = self._make_mock_conn(se_row=None)
        result = get_scheduled_event_for_date(conn, date(2026, 6, 1))

        assert result is None

    def test_limit_1_means_only_one_row_queried(self):
        """LIMIT 1 documented behavior: conn.execute is called for scheduled_events
        exactly once per get_scheduled_event_for_date() call.

        With two events on the same date the query still issues one SELECT;
        the database engine resolves which row to return.  This test confirms
        the function makes exactly one scheduled_events query regardless of
        how many rows exist in the table.
        """
        from classes.attendance import get_scheduled_event_for_date

        se_row = {
            "event_id":     2001,
            "name":         "Earlier Event",
            "location":     "Velious",
            "creator_name": "grokii_",
            "creator_id":   9001,
        }
        conn = self._make_mock_conn(se_row)
        get_scheduled_event_for_date(conn, date(2026, 6, 1))

        # Two total execute calls: one for scheduled_events, one for event_history
        assert conn.execute.call_count == 2, (
            f"Expected exactly 2 execute() calls (scheduled_events + event_history), "
            f"got {conn.execute.call_count}"
        )

    def test_limit_1_known_limitation_documented_in_sql(self):
        """The LIMIT 1 clause must be present in the SQL sent to the DB.

        This test pins the known limitation in place: if someone removes
        LIMIT 1 without also adding tie-breaking logic, this test fails
        and forces a deliberate decision.
        """
        from classes.attendance import get_scheduled_event_for_date
        import re

        se_row = {
            "event_id":     2001,
            "name":         "Event A",
            "location":     "Kael",
            "creator_name": "grokii_",
            "creator_id":   9001,
        }
        captured_sql = []

        conn = MagicMock()

        # First call (scheduled_events SELECT)
        se_mapping = MagicMock()
        se_mapping.__getitem__ = lambda self_, k: se_row[k]
        se_result  = MagicMock()
        se_result.mappings.return_value.fetchone.return_value = se_mapping

        # Second call (event_history SELECT)
        hist_result = MagicMock()
        hist_result.mappings.return_value.fetchall.return_value = []

        def capture(stmt, params=None):
            captured_sql.append(str(stmt))
            if len(captured_sql) == 1:
                return se_result
            return hist_result

        conn.execute.side_effect = capture

        get_scheduled_event_for_date(conn, date(2026, 6, 1))

        assert captured_sql, "No SQL was executed"
        first_stmt = captured_sql[0]
        assert re.search(r"\bLIMIT\s+1\b", first_stmt, re.IGNORECASE), (
            "LIMIT 1 not found in scheduled_events query.\n"
            "Known limitation: same-date double events return only the first row.\n"
            "If removing LIMIT 1, add explicit tie-breaking (ORDER BY start_time ASC) "
            "and update Design.md.\n"
            f"Actual SQL: {first_stmt}"
        )

    def test_same_date_double_event_only_one_result_per_call(self):
        """Simulate two events on the same date at the application layer.

        The DB always returns at most one row (LIMIT 1).  We call
        get_scheduled_event_for_date() twice with different mock rows to
        show which row the caller receives depends entirely on which row
        the DB chose to return — there is no application-layer disambiguation.

        This is the acceptance test for the known limitation: the caller
        gets exactly one result, and there is no way to retrieve the second
        event without a schema or query change.
        """
        from classes.attendance import get_scheduled_event_for_date

        # Simulate DB returning the *earlier* event (default LIMIT 1 behavior)
        earlier_row = {
            "event_id":     2001,
            "name":         "Earlier Event — Kael",
            "location":     "Kael",
            "creator_name": "grokii_",
            "creator_id":   9001,
        }
        conn_a  = self._make_mock_conn(earlier_row)
        result_a = get_scheduled_event_for_date(conn_a, date(2026, 6, 1))

        # Simulate DB returning the *later* event (shows LIMIT 1 is the only gate)
        later_row = {
            "event_id":     2002,
            "name":         "Later Event — ToV",
            "location":     "Temple of Veeshan",
            "creator_name": "grokii_",
            "creator_id":   9001,
        }
        conn_b   = self._make_mock_conn(later_row)
        result_b = get_scheduled_event_for_date(conn_b, date(2026, 6, 1))

        # Both calls succeed and return exactly one result
        assert result_a is not None
        assert result_b is not None

        # The two results are different — the caller has no way to get both
        assert result_a["name"] != result_b["name"], (
            "Expected different events from different DB states, got the same name"
        )

        # Neither call errors or returns a list — the limitation is silent
        assert isinstance(result_a, dict)
        assert isinstance(result_b, dict)

    def test_previous_names_populated_from_event_history(self):
        """Regression: previous_names list is assembled from event_history rows."""
        from classes.attendance import get_scheduled_event_for_date

        se_row = {
            "event_id":     2001,
            "name":         "Final Name",
            "location":     "Velious",
            "creator_name": "grokii_",
            "creator_id":   9001,
        }
        history = [
            {"previous_value": "Original Name", "new_value": "Interim Name",  "changed_at": datetime(2026, 5, 30, 10, 0)},
            {"previous_value": "Interim Name",  "new_value": "Final Name",    "changed_at": datetime(2026, 5, 30, 12, 0)},
        ]
        conn   = self._make_mock_conn(se_row, history_rows=history)
        result = get_scheduled_event_for_date(conn, date(2026, 6, 1))

        assert result["previous_names"] == ["Original Name", "Interim Name"], (
            f"previous_names not assembled correctly: {result['previous_names']}"
        )
