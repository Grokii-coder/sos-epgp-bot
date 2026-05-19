import discord
from discord.ext import commands
from classes.database import get_engine
from sqlalchemy import text


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
    """Return distinct item names matching a partial name (case-insensitive)."""
    engine = get_engine()
    with engine.connect() as conn:
        result = conn.execute(
            text("SELECT DISTINCT loot FROM gp_log WHERE loot LIKE :pattern ORDER BY loot"),
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
    """Numbered buttons for choosing among multiple matched item names."""

    def __init__(self, ctx, matches: list[str]):
        super().__init__(timeout=60)
        self.ctx = ctx

        for i, name in enumerate(matches):
            # Use a closure-captured default arg to bind `name` correctly
            button = discord.ui.Button(
                label=f"{i + 1}. {name}",
                style=discord.ButtonStyle.primary,
                custom_id=f"item_select_{i}"
            )
            button.callback = self._make_callback(name)
            self.add_item(button)

    def _make_callback(self, item_name: str):
        async def callback(interaction: discord.Interaction):
            # Only the original command user may respond
            if interaction.user != self.ctx.author:
                await interaction.response.send_message(
                    "Only the person who ran `/item` can pick.", ephemeral=True
                )
                return

            await interaction.response.defer()
            self.stop()

            try:
                total, rows = _get_item_detail(item_name)
            except Exception as e:
                await interaction.followup.send(f"Database error: {e}")
                return

            if not rows:
                await interaction.followup.send(f"No drop history found for **{item_name}**.")
                return

            await interaction.followup.send(_format_results(item_name, total, rows))

        return callback

    async def on_timeout(self):
        # Disable all buttons when the view expires
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
        await ctx.defer()

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

        # --- Too many matches ---
        if len(matches) > 5:
            await ctx.followup.send(
                f"**{len(matches)} items** found matching `{name}` — try a more specific name."
            )
            return

        # --- 2–5 matches: show buttons ---
        view = ItemSelectView(ctx, matches)
        lines = ["**Multiple items found — pick one:**"]
        for i, m in enumerate(matches):
            lines.append(f"{i + 1}. {m}")
        await ctx.followup.send("\n".join(lines), view=view)


def setup(bot):
    bot.add_cog(ItemCog(bot))