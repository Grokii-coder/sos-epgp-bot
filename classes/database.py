import os
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

load_dotenv()

DB_USER     = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_HOST     = os.getenv("DB_HOST")
DB_PORT     = os.getenv("DB_PORT")
DB_NAME     = os.getenv("DB_NAME")

CONNECTION_STRING = f"mysql+pymysql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"


def get_engine():
    """Return a SQLAlchemy engine using credentials from .env"""
    return create_engine(CONNECTION_STRING)


def get_last_sheet_row(conn, table):
    """Get the highest sheet_row already stored for a table.
    Used by sync functions to determine where to resume."""
    result = conn.execute(text(f"SELECT MAX(sheet_row) FROM {table}"))
    val = result.scalar()
    return val if val is not None else 0


def wait_for_db(retries=10, delay=5):
    """Wait for MySQL to be ready before proceeding.
    Retries on failure to handle container startup timing."""
    import time
    for attempt in range(retries):
        try:
            engine = get_engine()
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            print("Database ready!")
            return True
        except Exception as e:
            print(f"Database not ready (attempt {attempt + 1}/{retries}): {e}")
            time.sleep(delay)
    print("Could not connect to database after multiple attempts.")
    return False