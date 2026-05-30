import os
import discord
from discord.ext import commands
from dotenv import load_dotenv
from classes.database import wait_for_db
from classes.sync_manager import run_sync_if_needed

load_dotenv()

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID_TEST = int(os.getenv("GUILD_ID_TEST"))
GUILD_ID_PROD = int(os.getenv("GUILD_ID_PROD"))

intents = discord.Intents.default()
intents.scheduled_events = True

bot = discord.Bot(intents=intents)

bot.load_extension("cogs.review")
bot.load_extension("cogs.item")
bot.load_extension("cogs.priority")
bot.load_extension("cogs.events")

@bot.event
async def on_ready():
    await bot.sync_commands(force=True)
    print(f"Bot connected as {bot.user}")
    print(f"Serving {len(bot.guilds)} guild(s)")
    print("All cogs loaded")

    print("Running startup sync...")
    run_sync_if_needed()
    print("Startup sync complete - bot ready.")

    print("Syncing scheduled events from Discord...")
    events_cog = bot.cogs.get("EventsCog")
    if events_cog:
        for guild_id in [GUILD_ID_TEST, GUILD_ID_PROD]:
            guild = bot.get_guild(guild_id)
            if not guild:
                print(f"  Guild {guild_id} not found - bot may not be a member")
                continue
            events = guild.scheduled_events
            print(f"  Found {len(events)} events in {guild.name}")
            for event in events:
                await events_cog.save_event(event)
    print("Scheduled event sync complete.")

if __name__ == "__main__":
    if wait_for_db():
        bot.run(DISCORD_TOKEN)
    else:
        print("Could not connect to database - exiting.")