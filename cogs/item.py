import discord
from discord.ext import commands
from classes.database import get_engine
from sqlalchemy import text

PAGE_SIZE = 3  # items shown per page in the paginated too-many-matches view


def _format_results(item_name: str, total: int, rows: list) -> str:
    """Format the item history into a monospace code block."""
    lines = [
        f"{item_name} — {total} total drop{'s' if total != 1 else ''}",
        "",
        "Recent history:",
    ]
    for row in rows:
        date_str   = row.date.strftime("%m/%d/%y") if row.date else "??"
        toon       = row.toon_name or "Unknown"
        gear_level = row.gear_level or "Unknown"
        gp         = row.gp_value if row.gp_value is not None else 0
        lines.append(f"  {date_str:<10}  {toon:<12}  {gear_level:<12}  {gp} GP")
    return "```\n" + "\n".join(lines) + "\n```"


def _search_items(partial: str) -> list[str]:
    """Return distinct item names matching a partial name, alphabetically.
    Used for the 2–5 match case."""
    engine = get_engine()
    with engine.connect() as conn:
        result = conn.execute(
            text("SELECT DISTINCT loot FROM gp_log WHERE loot LIKE :pattern ORDER BY loot"),
            {"pattern": f"%{partial}%"}
        )
        return [row.loot for row in result]


def _search_items_by_recency(partial: str) -> list[str]:
    """Return distinct item names matching a partial name, sorted by most
    recent drop date descending. Used for the 6+ match paginated case."""
    engine = get_engine()
    with engine.connect() as conn:
        result = conn.execute(
            text("""
                SELECT loot, MAX(date) AS last_drop
                FROM gp_log
                WHERE loot LIKE :pattern
                GROUP BY loot
                ORDER BY last_drop DESC
            """),
            {"pattern": f"%{partial}%"}
        )
        return [row.loot for row in result]


def _get_item_detail(item_name: str) -> tuple[int, list]:
    """Return (total_count, last_3_rows) for an exact item name."""
    engine = get_engine()
    with engine.connect() as conn:
        total_result = conn.execute(
            text("SELECT COUNT(*) FROM gp_log WHERE loot = :name"),
            {"name": item_name}
        )
        total = total_result.scalar()

        rows_result = conn.execute(
            text("""
                SELECT date, toon_name, gear_level, gp_value
                FROM gp_log
                WHERE loot = :name
                ORDER BY date DESC
                LIMIT 3
            """),
            {"name": item_name}
        )
        rows = rows_result.fetchall()
    return total, rows


class ItemSelectView(discord.ui.View):
    """Numbered buttons for choosing among 2–5 matched item names (alphabetical)."""

    def __init__(self, ctx, matches: list[str]):
        super().__init__(timeout=60)
        self.ctx = ctx

        for i, name in enumerate(matches):
            button = discord.ui.Button(
                label=f"{i + 1}. {name}",
                style=discord.ButtonStyle.primary,
                custom_id=f"item_select_{i}"
            )
            button.callback = self._make_callback(name)
            self.add_item(button)

    def _make_callback(self, item_name: str):
        async def callback(interaction: discord.Interaction):
            if interaction.user != self.ctx.author:
                await interaction.response.send_message(
                    "Only the person who ran `/item` can pick.", ephemeral=True
                )
                return

            await interaction.response.defer(ephemeral=True)
            self.stop()

            try:
                total, rows = _get_item_detail(item_name)
            except Exception as e:
                await interaction.followup.send(f"Database error: {e}", ephemeral=True)
                return

            if not rows:
                await interaction.followup.send(
                    f"No drop history found for **{item_name}**.", ephemeral=True
                )
                return

            await interaction.followup.send(
                _format_results(item_name, total, rows), ephemeral=True
            )

        return callback

    async def on_timeout(self):
        for child in self.children:
            child.disabled = True


class ItemPagedView(discord.ui.View):
    """Paginated buttons for 6+ matches, sorted by most recent drop date.
    Shows PAGE_SIZE item buttons per page plus Prev / Next navigation."""

    def __init__(self, ctx, matches: list[str]):
        super().__init__(timeout=60)
        self.ctx      = ctx
        self.matches  = matches          # full list, sorted by recency
        self.page     = 0                # current page index (0-based)
        self.total_pages = (len(matches) + PAGE_SIZE - 1) // PAGE_SIZE
        self._build_buttons()

    def _page_matches(self) -> list[str]:
        """Return the slice of matches for the current page."""
        start = self.page * PAGE_SIZE
        return self.matches[start:start + PAGE_SIZE]

    def _build_buttons(self):
        """Clear and rebuild all buttons for the current page."""
        self.clear_items()

        # Item buttons for this page
        for i, name in enumerate(self._page_matches()):
            global_index = self.page * PAGE_SIZE + i
            button = discord.ui.Button(
                label=f"{global_index + 1}. {name}",
                style=discord.ButtonStyle.primary,
                custom_id=f"item_paged_{global_index}",
                row=i,
            )
            button.callback = self._make_item_callback(name)
            self.add_item(button)

        # Navigation row — always on row 3 so it sits below item buttons
        nav_row = PAGE_SIZE  # row index equal to page size keeps it below items

        prev_button = discord.ui.Button(
            label="← Prev",
            style=discord.ButtonStyle.secondary,
            custom_id="item_paged_prev",
            disabled=(self.page == 0),
            row=nav_row,
        )
        prev_button.callback = self._prev_callback
        self.add_item(prev_button)

        next_button = discord.ui.Button(
            label="Next →",
            style=discord.ButtonStyle.secondary,
            custom_id="item_paged_next",
            disabled=(self.page >= self.total_pages - 1),
            row=nav_row,
        )
        next_button.callback = self._next_callback
        self.add_item(next_button)

    def _page_header(self) -> str:
        return (
            f"**{len(self.matches)} items found — pick one "
            f"(page {self.page + 1}/{self.total_pages}, sorted by most recent drop):**"
        )

    def _make_item_callback(self, item_name: str):
        async def callback(interaction: discord.Interaction):
            if interaction.user != self.ctx.author:
                await interaction.response.send_message(
                    "Only the person who ran `/item` can pick.", ephemeral=True
                )
                return

            await interaction.response.defer(ephemeral=True)
            self.stop()

            try:
                total, rows = _get_item_detail(item_name)
            except Exception as e:
                await interaction.followup.send(f"Database error: {e}", ephemeral=True)
                return

            if not rows:
                await interaction.followup.send(
                    f"No drop history found for **{item_name}**.", ephemeral=True
                )
                return

            await interaction.followup.send(
                _format_results(item_name, total, rows), ephemeral=True
            )

        return callback

    async def _prev_callback(self, interaction: discord.Interaction):
        if interaction.user != self.ctx.author:
            await interaction.response.send_message(
                "Only the person who ran `/item` can navigate.", ephemeral=True
            )
            return
        self.page -= 1
        self._build_buttons()
        await interaction.response.edit_message(
            content=self._page_header(), view=self
        )

    async def _next_callback(self, interaction: discord.Interaction):
        if interaction.user != self.ctx.author:
            await interaction.response.send_message(
                "Only the person who ran `/item` can navigate.", ephemeral=True
            )
            return
        self.page += 1
        self._build_buttons()
        await interaction.response.edit_message(
            content=self._page_header(), view=self
        )

    async def on_timeout(self):
        for child in self.children:
            child.disabled = True


class ItemCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @discord.slash_command(
        name="item",
        description="Look up loot history for an item (partial name search)"
    )
    async def item(
        self,
        ctx,
        name: discord.Option(str, description="Partial item name to search for", required=True)
    ):
        await ctx.defer(ephemeral=True)

        try:
            matches = _search_items(name)
        except Exception as e:
            await ctx.followup.send(f"Database error: {e}")
            return

        # --- No matches ---
        if not matches:
            await ctx.followup.send(f"No items found matching **{name}**.")
            return

        # --- Exactly one match ---
        if len(matches) == 1:
            item_name = matches[0]
            try:
                total, rows = _get_item_detail(item_name)
            except Exception as e:
                await ctx.followup.send(f"Database error: {e}")
                return

            if not rows:
                await ctx.followup.send(f"No drop history found for **{item_name}**.")
                return

            await ctx.followup.send(_format_results(item_name, total, rows))
            return

        # --- 2–5 matches: alphabetical buttons (existing flow) ---
        if len(matches) <= 5:
            view  = ItemSelectView(ctx, matches)
            lines = ["**Multiple items found — pick one:**"]
            for i, m in enumerate(matches):
                lines.append(f"{i + 1}. {m}")
            await ctx.followup.send("\n".join(lines), view=view)
            return

        # --- 6+ matches: paginated by most recent drop date ---
        try:
            recent_matches = _search_items_by_recency(name)
        except Exception as e:
            await ctx.followup.send(f"Database error: {e}")
            return

        view = ItemPagedView(ctx, recent_matches)
        await ctx.followup.send(view._page_header(), view=view)


def setup(bot):
    bot.add_cog(ItemCog(bot))
