import os
import discord
from discord.ext import commands
from dotenv import load_dotenv

load_dotenv()

PLAYER_NAME = os.getenv("PLAYER_NAME")


class ReviewCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @discord.slash_command(
        name="review",
        description="Review your EP progress and missing event credits for the current cycle"
    )
    async def review(self, ctx, cycle: int = None):
        await ctx.respond(f"Review command coming soon for {PLAYER_NAME}...")


def setup(bot):
    bot.add_cog(ReviewCog(bot))