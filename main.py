import os
import discord
from discord.ext import commands
from dotenv import load_dotenv
from classes.database import wait_for_db
from classes.sync_manager import run_sync_if_needed

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
    await bot.sync_commands()
    print(f"Bot connected as {bot.user}")
    print(f"Serving {len(bot.guilds)} guild(s)")
    print("All cogs loaded")
    print("Running startup sync...")
    run_sync_if_needed()
    print("Startup sync complete - bot ready.")

if __name__ == "__main__":
    if wait_for_db():
        bot.run(DISCORD_TOKEN)
    else:
        print("Could not connect to database - exiting.")