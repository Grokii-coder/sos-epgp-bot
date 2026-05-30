"""
pytest configuration for sos-epgp-bot tests.

cogs/events.py calls int(os.getenv("GUILD_ID_TEST")) and
int(os.getenv("GUILD_ID_PROD")) at module level.  Without a .env file
those return None and crash on import.  We set dummy values in the
environment before any test module imports the cog.
"""

import os
import pytest

# Set dummy env vars before any test module is collected.
# These are module-level constants in cogs/events.py — they must exist
# as valid integers or the import itself raises TypeError.
os.environ.setdefault("GUILD_ID_TEST", "111111111111111111")
os.environ.setdefault("GUILD_ID_PROD", "222222222222222222")

# Dummy DB credentials so classes/database.py doesn't blow up if imported
os.environ.setdefault("DB_USER",     "test")
os.environ.setdefault("DB_PASSWORD", "test")
os.environ.setdefault("DB_HOST",     "localhost")
os.environ.setdefault("DB_PORT",     "3306")
os.environ.setdefault("DB_NAME",     "test")
