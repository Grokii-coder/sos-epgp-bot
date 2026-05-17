import discord
from discord.ext import commands


class ItemCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @discord.slash_command(
        name="item",
        description="Look up loot history for an item"
    )
    async def item(self, ctx, name: str):
        await ctx.respond(f"Item lookup coming soon for: {name}")


def setup(bot):
    bot.add_cog(ItemCog(bot))