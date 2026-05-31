"""
SC-6 Tests — /item too-many-matches UX
=======================================
Covers:
  - _search_items_by_recency: returns names sorted by MAX(date) DESC
  - ItemPagedView: pagination logic, button state, page header text
  - Routing: 0 / 1 / 2-5 / 6+ match branches all reach the right path
  - Ephemeral: ctx.defer called with ephemeral=True in all outcomes

All tests are pure unit tests — no running database required.

Implementation notes
--------------------
discord.ui.View.__init__ calls asyncio.get_running_loop() in py-cord, so any
test that constructs a View directly must do so inside a running event loop.
The _make_view() helper uses asyncio.run() for this.

ItemCog.item is decorated as a SlashCommand by py-cord, so calling
`cog.item(ctx, ...)` goes through the slash command dispatcher, which
mangles `self`. The routing and ephemeral tests call the raw callback via
`cog.item.callback(cog, ctx, name=...)` to bypass the decorator.
"""

import asyncio
import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from datetime import date


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_ctx(author_id=42):
    ctx           = MagicMock()
    ctx.author    = MagicMock()
    ctx.author.id = author_id
    ctx.defer     = AsyncMock()
    ctx.followup  = MagicMock()
    ctx.followup.send = AsyncMock()
    return ctx


def _make_interaction(user=None):
    interaction                         = MagicMock()
    interaction.user                    = user or MagicMock()
    interaction.response                = MagicMock()
    interaction.response.defer          = AsyncMock()
    interaction.response.send_message   = AsyncMock()
    interaction.response.edit_message   = AsyncMock()
    interaction.followup                = MagicMock()
    interaction.followup.send           = AsyncMock()
    return interaction


def _make_db_rows(names_with_dates: list[tuple[str, str]]):
    """Return mock DB rows with .loot and .last_drop attributes."""
    rows = []
    for name, d in names_with_dates:
        row           = MagicMock()
        row.loot      = name
        row.last_drop = date.fromisoformat(d)
        rows.append(row)
    return rows


def _make_view(matches, page=0):
    """Construct an ItemPagedView inside a running event loop.

    py-cord's discord.ui.View.__init__ calls asyncio.get_running_loop(),
    so construction must happen inside an async context.
    """
    from cogs.item import ItemPagedView

    async def _build():
        view = ItemPagedView(_make_ctx(), matches)
        view.page = page
        view._build_buttons()
        return view

    return asyncio.run(_build())


# ---------------------------------------------------------------------------
# _search_items_by_recency
# ---------------------------------------------------------------------------

class TestSearchItemsByRecency:
    """_search_items_by_recency must return names ordered by MAX(date) DESC."""

    def _run(self, db_rows):
        mock_result = MagicMock()
        mock_result.__iter__ = MagicMock(return_value=iter(db_rows))

        mock_conn = MagicMock()
        mock_conn.execute.return_value = mock_result
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__  = MagicMock(return_value=False)

        mock_engine = MagicMock()
        mock_engine.connect.return_value = mock_conn

        with patch("cogs.item.get_engine", return_value=mock_engine):
            from cogs.item import _search_items_by_recency
            return _search_items_by_recency("sword")

    def test_returns_names_in_db_order(self):
        """Names come back in whatever order the DB returns — recency sort
        is done by the SQL ORDER BY, not in Python."""
        rows   = _make_db_rows([
            ("Sword of Runes",   "2026-05-20"),
            ("Sword of Shadows", "2026-04-10"),
            ("Shortsword",       "2026-03-01"),
        ])
        result = self._run(rows)
        assert result == ["Sword of Runes", "Sword of Shadows", "Shortsword"]

    def test_returns_empty_list_for_no_matches(self):
        result = self._run([])
        assert result == []

    def test_sql_contains_max_date_and_order_by(self):
        """The query must use MAX(date) and ORDER BY last_drop DESC."""
        captured_sql = []

        mock_result = MagicMock()
        mock_result.__iter__ = MagicMock(return_value=iter([]))

        mock_conn = MagicMock()

        def capture(stmt, params=None):
            captured_sql.append(str(stmt))
            return mock_result

        mock_conn.execute.side_effect = capture
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__  = MagicMock(return_value=False)

        mock_engine = MagicMock()
        mock_engine.connect.return_value = mock_conn

        with patch("cogs.item.get_engine", return_value=mock_engine):
            from cogs.item import _search_items_by_recency
            _search_items_by_recency("sword")

        assert captured_sql, "No SQL executed"
        sql = captured_sql[0].upper()
        assert "MAX(" in sql,     "Query must use MAX(date) for recency sort"
        assert "ORDER BY" in sql, "Query must have ORDER BY"
        assert "DESC" in sql,     "ORDER BY must be DESC (most recent first)"
        assert "GROUP BY" in sql, "Query must GROUP BY loot for distinct names"


# ---------------------------------------------------------------------------
# ItemPagedView — pagination logic
# ---------------------------------------------------------------------------

class TestItemPagedView:

    def _button_labels(self, view):
        return [c.label for c in view.children]

    def _nav_buttons(self, view):
        prev = next((c for c in view.children if c.label == "← Prev"), None)
        nxt  = next((c for c in view.children if c.label == "Next →"), None)
        return prev, nxt

    # --- page content ---

    def test_first_page_shows_first_three_items(self):
        matches = [f"Item {i}" for i in range(1, 10)]
        view    = _make_view(matches, page=0)
        labels  = self._button_labels(view)
        assert "1. Item 1" in labels
        assert "2. Item 2" in labels
        assert "3. Item 3" in labels
        assert not any("Item 4" in l for l in labels)

    def test_second_page_shows_next_three_items(self):
        matches = [f"Item {i}" for i in range(1, 10)]
        view    = _make_view(matches, page=1)
        labels  = self._button_labels(view)
        assert "4. Item 4" in labels
        assert "5. Item 5" in labels
        assert "6. Item 6" in labels
        assert not any("Item 3" in l for l in labels)
        assert not any("Item 7" in l for l in labels)

    def test_last_page_shows_remaining_items(self):
        """7 items → pages of 3, 3, 1. Last page has only one item button."""
        matches      = [f"Item {i}" for i in range(1, 8)]
        view         = _make_view(matches, page=2)
        item_buttons = [c for c in view.children
                        if c.label not in ("← Prev", "Next →")]
        assert len(item_buttons) == 1
        assert item_buttons[0].label == "7. Item 7"

    # --- nav button state ---

    def test_prev_disabled_on_first_page(self):
        view    = _make_view([f"Item {i}" for i in range(1, 10)], page=0)
        prev, _ = self._nav_buttons(view)
        assert prev.disabled is True

    def test_next_enabled_on_first_page(self):
        view     = _make_view([f"Item {i}" for i in range(1, 10)], page=0)
        _, nxt   = self._nav_buttons(view)
        assert nxt.disabled is False

    def test_next_disabled_on_last_page(self):
        view    = _make_view([f"Item {i}" for i in range(1, 10)], page=2)
        _, nxt  = self._nav_buttons(view)
        assert nxt.disabled is True

    def test_prev_enabled_on_last_page(self):
        view    = _make_view([f"Item {i}" for i in range(1, 10)], page=2)
        prev, _ = self._nav_buttons(view)
        assert prev.disabled is False

    def test_both_nav_enabled_on_middle_page(self):
        view      = _make_view([f"Item {i}" for i in range(1, 10)], page=1)
        prev, nxt = self._nav_buttons(view)
        assert prev.disabled is False
        assert nxt.disabled  is False

    # --- page header ---

    def test_page_header_shows_total_and_page_numbers(self):
        view   = _make_view([f"Item {i}" for i in range(1, 10)], page=0)
        header = view._page_header()
        assert "9 items found" in header
        assert "page 1/3"      in header

    def test_page_header_updates_on_page_change(self):
        view   = _make_view([f"Item {i}" for i in range(1, 10)], page=1)
        header = view._page_header()
        assert "page 2/3" in header

    def test_total_pages_exact_multiple(self):
        """6 items with PAGE_SIZE=3 → exactly 2 pages."""
        view = _make_view([f"Item {i}" for i in range(1, 7)], page=0)
        assert view.total_pages == 2

    def test_total_pages_with_remainder(self):
        """7 items with PAGE_SIZE=3 → 3 pages."""
        view = _make_view([f"Item {i}" for i in range(1, 8)], page=0)
        assert view.total_pages == 3

    # --- navigation callbacks ---

    @pytest.mark.asyncio
    async def test_next_callback_advances_page(self):
        from cogs.item import ItemPagedView
        ctx     = _make_ctx()
        view    = ItemPagedView(ctx, [f"Item {i}" for i in range(1, 10)])

        interaction = _make_interaction(user=ctx.author)
        await view._next_callback(interaction)

        assert view.page == 1
        interaction.response.edit_message.assert_called_once()

    @pytest.mark.asyncio
    async def test_prev_callback_decrements_page(self):
        from cogs.item import ItemPagedView
        ctx  = _make_ctx()
        view = ItemPagedView(ctx, [f"Item {i}" for i in range(1, 10)])
        view.page = 1
        view._build_buttons()

        interaction = _make_interaction(user=ctx.author)
        await view._prev_callback(interaction)

        assert view.page == 0
        interaction.response.edit_message.assert_called_once()

    @pytest.mark.asyncio
    async def test_wrong_user_cannot_navigate(self):
        from cogs.item import ItemPagedView
        ctx        = _make_ctx()
        other_user = MagicMock()
        view       = ItemPagedView(ctx, [f"Item {i}" for i in range(1, 10)])

        interaction = _make_interaction(user=other_user)
        await view._next_callback(interaction)

        assert view.page == 0   # must not advance
        interaction.response.send_message.assert_called_once()
        assert interaction.response.send_message.call_args.kwargs.get("ephemeral") is True


# ---------------------------------------------------------------------------
# Routing — correct branch chosen based on match count
# ---------------------------------------------------------------------------

class TestItemRouting:
    """Call cog.item.callback(cog, ctx, name=...) directly to bypass the
    py-cord SlashCommand wrapper, which would mangle `self`."""

    def _make_detail_row(self):
        row            = MagicMock()
        row.date       = date(2026, 5, 1)
        row.toon_name  = "Grokenspiel"
        row.gear_level = "High Bid"
        row.gp_value   = 10
        return row

    @pytest.mark.asyncio
    async def test_no_matches_sends_not_found(self):
        from cogs.item import ItemCog
        ctx = _make_ctx()
        cog = ItemCog(bot=MagicMock())

        with patch("cogs.item._search_items", return_value=[]):
            await cog.item.callback(cog, ctx, name="xyzzy")

        ctx.followup.send.assert_called_once()
        assert "No items found" in ctx.followup.send.call_args.args[0]

    @pytest.mark.asyncio
    async def test_single_match_sends_result_directly(self):
        from cogs.item import ItemCog
        ctx = _make_ctx()
        cog = ItemCog(bot=MagicMock())

        with patch("cogs.item._search_items", return_value=["Sword of Truth"]), \
             patch("cogs.item._get_item_detail", return_value=(1, [self._make_detail_row()])):
            await cog.item.callback(cog, ctx, name="sword")

        ctx.followup.send.assert_called_once()
        sent = ctx.followup.send.call_args.args[0]
        assert "Sword of Truth" in sent
        assert "pick one" not in sent.lower()

    @pytest.mark.asyncio
    async def test_two_to_five_matches_uses_item_select_view(self):
        from cogs.item import ItemCog, ItemSelectView
        ctx = _make_ctx()
        cog = ItemCog(bot=MagicMock())

        with patch("cogs.item._search_items", return_value=["Sword A", "Sword B", "Sword C"]):
            await cog.item.callback(cog, ctx, name="sword")

        ctx.followup.send.assert_called_once()
        _, kwargs = ctx.followup.send.call_args
        assert isinstance(kwargs.get("view"), ItemSelectView)

    @pytest.mark.asyncio
    async def test_six_plus_matches_uses_item_paged_view(self):
        from cogs.item import ItemCog, ItemPagedView
        ctx     = _make_ctx()
        cog     = ItemCog(bot=MagicMock())
        matches = [f"Sword {i}" for i in range(8)]

        with patch("cogs.item._search_items", return_value=matches), \
             patch("cogs.item._search_items_by_recency", return_value=matches):
            await cog.item.callback(cog, ctx, name="sword")

        ctx.followup.send.assert_called_once()
        _, kwargs = ctx.followup.send.call_args
        assert isinstance(kwargs.get("view"), ItemPagedView)

    @pytest.mark.asyncio
    async def test_six_plus_uses_recency_search_not_alpha(self):
        """For 6+ matches the paginated view must be built from
        _search_items_by_recency, not the alphabetical _search_items result."""
        from cogs.item import ItemCog
        ctx    = _make_ctx()
        cog    = ItemCog(bot=MagicMock())
        alpha  = [f"Sword {i}" for i in range(8)]
        recent = list(reversed(alpha))

        recency_mock = MagicMock(return_value=recent)

        with patch("cogs.item._search_items", return_value=alpha), \
             patch("cogs.item._search_items_by_recency", recency_mock):
            await cog.item.callback(cog, ctx, name="sword")

        recency_mock.assert_called_once_with("sword")


# ---------------------------------------------------------------------------
# Ephemeral — ctx.defer must always be called with ephemeral=True
# ---------------------------------------------------------------------------

class TestEphemeral:
    """All /item outcomes must be invisible to other Discord members."""

    @pytest.mark.asyncio
    async def test_defer_is_ephemeral_no_matches(self):
        from cogs.item import ItemCog
        ctx = _make_ctx()
        cog = ItemCog(bot=MagicMock())

        with patch("cogs.item._search_items", return_value=[]):
            await cog.item.callback(cog, ctx, name="xyzzy")

        ctx.defer.assert_called_once_with(ephemeral=True)

    @pytest.mark.asyncio
    async def test_defer_is_ephemeral_single_match(self):
        from cogs.item import ItemCog
        ctx = _make_ctx()
        cog = ItemCog(bot=MagicMock())
        row = MagicMock()
        row.date = date(2026, 5, 1); row.toon_name = "G"
        row.gear_level = "High Bid"; row.gp_value = 10

        with patch("cogs.item._search_items", return_value=["Sword"]), \
             patch("cogs.item._get_item_detail", return_value=(1, [row])):
            await cog.item.callback(cog, ctx, name="sword")

        ctx.defer.assert_called_once_with(ephemeral=True)

    @pytest.mark.asyncio
    async def test_defer_is_ephemeral_multi_match(self):
        from cogs.item import ItemCog
        ctx = _make_ctx()
        cog = ItemCog(bot=MagicMock())

        with patch("cogs.item._search_items", return_value=["A", "B", "C"]):
            await cog.item.callback(cog, ctx, name="sword")

        ctx.defer.assert_called_once_with(ephemeral=True)

    @pytest.mark.asyncio
    async def test_defer_is_ephemeral_paged_match(self):
        from cogs.item import ItemCog
        ctx     = _make_ctx()
        cog     = ItemCog(bot=MagicMock())
        matches = [f"Item {i}" for i in range(8)]

        with patch("cogs.item._search_items", return_value=matches), \
             patch("cogs.item._search_items_by_recency", return_value=matches):
            await cog.item.callback(cog, ctx, name="item")

        ctx.defer.assert_called_once_with(ephemeral=True)

    @pytest.mark.asyncio
    async def test_item_select_callback_defers_ephemeral(self):
        """Button callbacks in ItemSelectView must defer with ephemeral=True."""
        from cogs.item import ItemSelectView
        ctx  = _make_ctx()
        view = ItemSelectView(ctx, ["Sword A", "Sword B"])
        row  = MagicMock()
        row.date = date(2026, 5, 1); row.toon_name = "G"
        row.gear_level = "High Bid"; row.gp_value = 10

        interaction = _make_interaction(user=ctx.author)

        with patch("cogs.item._get_item_detail", return_value=(1, [row])):
            await view._make_callback("Sword A")(interaction)

        interaction.response.defer.assert_called_once_with(ephemeral=True)

    @pytest.mark.asyncio
    async def test_item_paged_callback_defers_ephemeral(self):
        """Item selection callbacks in ItemPagedView must defer with ephemeral=True."""
        from cogs.item import ItemPagedView
        ctx     = _make_ctx()
        view    = ItemPagedView(ctx, [f"Item {i}" for i in range(8)])
        row     = MagicMock()
        row.date = date(2026, 5, 1); row.toon_name = "G"
        row.gear_level = "High Bid"; row.gp_value = 10

        interaction = _make_interaction(user=ctx.author)

        with patch("cogs.item._get_item_detail", return_value=(1, [row])):
            await view._make_item_callback("Item 1")(interaction)

        interaction.response.defer.assert_called_once_with(ephemeral=True)
