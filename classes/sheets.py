import os
import csv
import io
import requests
from dotenv import load_dotenv

load_dotenv()

SHEET_ID = os.getenv("SHEET_ID")

TABS = {
    "ep_log":  "264766085",
    "gp_log":  "116377915",
    "cycles":  "850187403",
}


def fetch_sheet_tab(tab_name):
    """Fetch a Google Sheet tab as a list of rows via public CSV export.
    No authentication required - sheet must be publicly readable."""
    gid = TABS[tab_name]
    url = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/export?format=csv&gid={gid}"
    print(f"Fetching {tab_name} from Google Sheets...")
    response = requests.get(url)
    if response.status_code != 200:
        print(f"Failed to fetch {tab_name}: HTTP {response.status_code}")
        return []
    content = response.content.decode("utf-8")
    reader = csv.reader(io.StringIO(content))
    rows = list(reader)
    print(f"Fetched {len(rows)} rows from {tab_name}")
    return rows