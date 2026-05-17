import os
import discord
from discord.ext import commands
from dotenv import load_dotenv
from classes.sync_manager import run_sync_if_needed
from classes.attendance import build_attendance_report

load_dotenv()

DEFAULT_PLAYER = os.getenv("PLAYER_NAME")


class ReviewCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @discord.slash_command(
        name="review",
        description="Review EP progress and missing event credits for the current cycle"
    )
    async def review(
        self,
        ctx,
        player: discord.Option(str, "Player name to review (default: you)", required=False) = None,
        cycle: discord.Option(int, "Cycle number to review (default: current)", required=False) = None
    ):
        # Defer response while we fetch data - gives us 15 minutes instead of 3 seconds
        await ctx.defer()

        # Use default player if none specified
        player_name = player if player else DEFAULT_PLAYER

        # Sync if cache is expired
        run_sync_if_needed()

        # Build the report
        report = build_attendance_report(player_name, cycle)

        if "error" in report:
            await ctx.followup.send(f"Error: {report['error']}")
            return

        # Format the response
        lines = []
        lines.append(f"**{report['player']}** — Cycle {report['cycle']} ({report['start_date']} to {report['end_date']})")
        lines.append(f"EP: **{report['ep_earned']} / {report['ep_cap']}**")

        if not report['discrepancies']:
            lines.append("\n✅ You're all caught up — no missing credits found.")
        else:
            lines.append(f"\n⚠️ Found **{len(report['discrepancies'])}** event(s) with missing credits:\n")
            for d in report['discrepancies']:
                lines.append(f"📅 **{d['date']}** — {d['event_type']} — 📍 {d['location']}")
                lines.append(f"  Missing: {', '.join(d['missing'])}")
                lines.append("")

        await ctx.followup.send("\n".join(lines))


def setup(bot):
    bot.add_cog(ReviewCog(bot))