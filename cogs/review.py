import os
import discord
from discord.ext import commands
from dotenv import load_dotenv
from classes.sync_manager import run_sync_if_needed
from classes.attendance import build_attendance_report
from classes.database import get_engine
from sqlalchemy import text
from datetime import date

load_dotenv()

DEFAULT_PLAYER = os.getenv("PLAYER_NAME")


class AttendanceView(discord.ui.View):
    """Handles the Yes/No/Skip button interaction for a single discrepancy."""

    def __init__(self, player_name, discrepancies, current_index, report):
        super().__init__(timeout=300)
        self.player_name   = player_name
        self.discrepancies = discrepancies
        self.current_index = current_index
        self.report        = report

    def get_current_embed(self):
        """Build the embed for the current discrepancy."""
        d     = self.discrepancies[self.current_index]
        total = len(self.discrepancies)
        index = self.current_index + 1

        embed = discord.Embed(
            title=f"Event {index} of {total}",
            color=discord.Color.orange()
        )
        embed.add_field(name="Date",     value=str(d['date']),  inline=True)
        embed.add_field(name="Type",     value=d['event_type'], inline=True)
        embed.add_field(name="Location", value=d['location'],   inline=True)
        embed.add_field(name=d['statement1'], value=d['statement2'], inline=False)
        embed.set_footer(text=f"{self.player_name} — Cycle {self.report['cycle']}")
        return embed

    def save_response(self, event_date, event_type, location, missing, response):
        """Persist the player's response to the database."""
        engine = get_engine()
        with engine.begin() as conn:
            conn.execute(text("""
                INSERT INTO attendance_responses
                    (player_name, event_date, event_type, event_location,
                     missing_checkins, player_response, response_date, resolved)
                VALUES
                    (:player_name, :event_date, :event_type, :event_location,
                     :missing_checkins, :player_response, :response_date, :resolved)
                ON DUPLICATE KEY UPDATE
                    player_response  = VALUES(player_response),
                    missing_checkins = VALUES(missing_checkins),
                    response_date    = VALUES(response_date),
                    resolved         = VALUES(resolved)
            """), {
                "player_name":     self.player_name,
                "event_date":      event_date,
                "event_type":      event_type,
                "event_location":  location,
                "missing_checkins": ', '.join(missing),
                "player_response": response,
                "response_date":   date.today(),
                "resolved":        response == 'yes',
            })

    async def advance(self, interaction):
        """Move to the next discrepancy or finish if done."""
        self.current_index += 1
        if self.current_index >= len(self.discrepancies):
            await interaction.response.edit_message(
                content="✅ All done! No more discrepancies to review.",
                embed=None,
                view=None
            )
        else:
            await interaction.response.edit_message(
                content="Is this correct?",
                embed=self.get_current_embed(),
                view=self
            )

    @discord.ui.button(label="✅ Yes, the EPGP sheet is correct", style=discord.ButtonStyle.green)
    async def yes_button(self, button, interaction):
        d = self.discrepancies[self.current_index]
        self.save_response(
            d['date'], d['event_type'], d['location'], d['missing'], 'yes'
        )
        await self.advance(interaction)

    @discord.ui.button(label="❌ No, the EPGP sheet is wrong", style=discord.ButtonStyle.red)
    async def no_button(self, button, interaction):
        d = self.discrepancies[self.current_index]
        self.save_response(
            d['date'], d['event_type'], d['location'], d['missing'], 'no'
        )
        await self.advance(interaction)

    @discord.ui.button(label="⏭️ Skip for now", style=discord.ButtonStyle.grey)
    async def skip_button(self, button, interaction):
        # Don't save anything - will appear again next /review
        await self.advance(interaction)


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
        player: discord.Option(str, description="Player name to review (default: you)", required=False, default=None),
        cycle: discord.Option(int, description="Cycle number to review (default: current)", required=False, default=None)
    ):
        await ctx.defer()

        player_name = player if player else DEFAULT_PLAYER
        print(f"DEBUG: player arg={player}, DEFAULT_PLAYER={DEFAULT_PLAYER}, using={player_name}") 
        print(f"DEBUG review called: player={repr(player)}, cycle={repr(cycle)}, ctx.interaction={repr(ctx.interaction)}")
        print(f"DEBUG interaction data: {repr(ctx.interaction.data)}")
        run_sync_if_needed()
        report = build_attendance_report(player_name, cycle)

        if "error" in report:
            await ctx.followup.send(f"Error: {report['error']}")
            return

        # Header - EP progress
        header = (
            f"**{report['player']}** — Cycle {report['cycle']} "
            f"({report['start_date']} to {report['end_date']})\n"
            f"EP: **{report['ep_earned']} / {report['ep_cap']}**"
        )

        if not report['discrepancies']:
            await ctx.followup.send(
                header + "\n\n✅ You're all caught up — no missing credits found."
            )
            return

        # Build summary of all discrepancies
        summary_lines = [header, f"\nHere's what I found:\n"]
        for d in report['discrepancies']:
            summary_lines.append(
                f"📅 **{d['date']}**  {d['event_type']}  📍 {d['location']}\n"
                f"   {d['statement1']} {d['statement2']}\n"
            )

        summary_lines.append(
            f"\nReady to review **{len(report['discrepancies'])}** event(s). Let's go!"
        )

        await ctx.followup.send("\n".join(summary_lines))

        # Start the button flow with the first discrepancy
        view = AttendanceView(
            player_name   = player_name,
            discrepancies = report['discrepancies'],
            current_index = 0,
            report        = report
        )
        await ctx.followup.send(
            content="Is this correct?",
            embed=view.get_current_embed(),
            view=view
        )


def setup(bot):
    bot.add_cog(ReviewCog(bot))