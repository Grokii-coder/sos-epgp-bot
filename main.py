import os
import discord
from discord.ext import commands
from dotenv import load_dotenv

load_dotenv()

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")

intents = discord.Intents.default()
intents.message_content = True

bot = discord.Bot(intents=intents)

@bot.event
async def on_ready():
    print(f"Bot connected as {bot.user}")
    print(f"Serving {len(bot.guilds)} guild(s)")

@bot.event
async def on_connect():
    await bot.load_extension("cogs.review")
    await bot.load_extension("cogs.item")
    await bot.load_extension("cogs.priority")
    print("All cogs loaded")

if __name__ == "__main__":
    bot.run(DISCORD_TOKEN)