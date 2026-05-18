import os
import discord
from discord.ext import commands
from datetime import datetime
from dotenv import load_dotenv
from classes.database import get_engine
from sqlalchemy import text

load_dotenv()

GUILD_ID_TEST = int(os.getenv("GUILD_ID_TEST"))
GUILD_ID_PROD = int(os.getenv("GUILD_ID_PROD"))


class EventsCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    def save_event(self, event):
        """Insert or update a scheduled event in the database."""
        # Safely extract location string
        location = None
        if event.location:
            loc = event.location
            if hasattr(loc, 'value'):
                val = loc.value
                if isinstance(val, str):
                    location = val
                elif hasattr(val, 'name'):
                    location = val.name
                else:
                    location = None  # Channel-based event, no useful text location
            else:
                location = str(loc)

        # Safely extract creator name
        creator_name = None
        if event.creator:
            creator_name = event.creator.name

        # Convert status enum to string
        status = event.status.name if hasattr(event.status, 'name') else str(event.status)

        engine = get_engine()
        with engine.begin() as conn:
            conn.execute(text("""
                INSERT INTO scheduled_events
                    (event_id, guild_id, name, location, start_time, end_time,
                     creator_id, creator_name, status, description, created_at, updated_at)
                VALUES
                    (:event_id, :guild_id, :name, :location, :start_time, :end_time,
                     :creator_id, :creator_name, :status, :description, :created_at, :updated_at)
                ON DUPLICATE KEY UPDATE
                    name         = VALUES(name),
                    location     = VALUES(location),
                    start_time   = VALUES(start_time),
                    end_time     = VALUES(end_time),
                    status       = VALUES(status),
                    description  = VALUES(description),
                    updated_at   = VALUES(updated_at)
            """), {
                "event_id":     event.id,
                "guild_id":     event.guild.id,
                "name":         event.name,
                "location":     location,
                "start_time":   event.start_time.replace(tzinfo=None) if event.start_time else None,
                "end_time":     event.end_time.replace(tzinfo=None) if event.end_time else None,
                "creator_id":   event.creator_id,
                "creator_name": creator_name,
                "status":       status,
                "description":  event.description,
                "created_at":   datetime.utcnow(),
                "updated_at":   datetime.utcnow(),
            })
        print(f"Event saved: {event.name} (id={event.id})")

    def record_name_change(self, event_id, previous_name, new_name):
        """Record a name change in event_history for pivot detection."""
        engine = get_engine()
        with engine.begin() as conn:
            conn.execute(text("""
                INSERT INTO event_history
                    (event_id, field_changed, previous_value, new_value, changed_at)
                VALUES
                    (:event_id, :field_changed, :previous_value, :new_value, :changed_at)
            """), {
                "event_id":       event_id,
                "field_changed":  "name",
                "previous_value": previous_name,
                "new_value":      new_name,
                "changed_at":     datetime.utcnow(),
            })
        print(f"Name change recorded: {previous_name} → {new_name}")

    @commands.Cog.listener()
    async def on_scheduled_event_create(self, event):
        """Fired when a new scheduled event is created."""
        print(f"New event detected: {event.name}")
        self.save_event(event)

    @commands.Cog.listener()
    async def on_scheduled_event_update(self, before, after):
        """Fired when a scheduled event is modified.
        Detects name changes for pivot tracking."""
        print(f"Event updated: {after.name} (id={after.id})")

        # Detect name change
        if before.name != after.name:
            print(f"  Name changed: {before.name} → {after.name}")
            self.record_name_change(after.id, before.name, after.name)

        self.save_event(after)

    @commands.Cog.listener()
    async def on_scheduled_event_delete(self, event):
        """Fired when a scheduled event is deleted.
        We keep the record but mark it as cancelled."""
        print(f"Event deleted: {event.name} (id={event.id})")
        engine = get_engine()
        with engine.begin() as conn:
            conn.execute(text("""
                UPDATE scheduled_events
                SET status = 'cancelled', updated_at = :now
                WHERE event_id = :event_id
            """), {
                "event_id": event.id,
                "now":      datetime.utcnow(),
            })


def setup(bot):
    bot.add_cog(EventsCog(bot))