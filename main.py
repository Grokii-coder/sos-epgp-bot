import os
import discord
from discord.ext import commands
from dotenv import load_dotenv

load_dotenv()

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")

# Slash commands only need default intents
# message_content is a privileged intent we don't need
intents = discord.Intents.default()

bot = discord.Bot(intents=intents)

# Load cogs before bot starts
bot.load_extension("cogs.review")
bot.load_extension("cogs.item")
bot.load_extension("cogs.priority")

@bot.event
async def on_ready():
    print(f"Bot connected as {bot.user}")
    print(f"Serving {len(bot.guilds)} guild(s)")
    print("All cogs loaded")

if __name__ == "__main__":
    bot.run(DISCORD_TOKEN)