import discord
from discord.ext import commands


class PriorityCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @discord.slash_command(
        name="priority",
        description="Show your loot priority rank by class and armor type"
    )
    async def priority(self, ctx):
        await ctx.respond("Priority command coming soon...")


def setup(bot):
    bot.add_cog(PriorityCog(bot))