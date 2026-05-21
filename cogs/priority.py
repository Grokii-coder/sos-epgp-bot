import io
import csv
import json
import os
import requests
import discord
from discord.ext import commands
from dotenv import load_dotenv
from sqlalchemy import text
from classes.database import get_engine

load_dotenv()

# ---------------------------------------------------------------------------
# Class alias map — loaded once at module import time.
# Maps any title string that might appear in the Totals tab's Class column
# to { base_class, armor_type }.  Built from data/eq_class_aliases.json.
# See that file for full source citations and per-entry notes.
# ---------------------------------------------------------------------------
_ALIAS_MAP: dict[str, dict] = {}


def _load_aliases() -> None:
    """Load eq_class_aliases.json into _ALIAS_MAP at startup."""
    path = os.path.join(os.path.dirname(__file__), "..", "data", "eq_class_aliases.json")
    path = os.path.normpath(path)
    with open(path, "r", encoding="utf-8") as f:
        raw = json.load(f)
    for title, entry in raw["aliases"].items():
        if not entry.get("_ambiguous"):
            _ALIAS_MAP[title.lower()] = entry


_load_aliases()

# ---------------------------------------------------------------------------
# Totals tab column indices (0-based), confirmed from live sheet inspection.
# gid=0.  Layout:
#   A(0): empty  B(1): Date  C(2): Name  D(3): Class  E(4): Level
#   F(5): Effort Points  G(6): Gear Points  H(7): Loot Priority
#   I(8): EP Decay  J(9): GP Decay
# Two header rows — row 0 and row 1 — are skipped on fetch.
# ---------------------------------------------------------------------------
COL_NAME  = 2
COL_CLASS = 3
COL_EP    = 5
COL_GP    = 6

# PR formula constants — must match the sheet formula
BASE_EP = 150
BASE_GP = 100

# Armor type display labels — edit here if different phrasing is preferred
ARMOR_LABELS = {
    "Plate":   "Plate wearers",
    "Chain":   "Chain wearers",
    "Leather": "Leather wearers",
    "Cloth":   "Cloth wearers",
}


# ---------------------------------------------------------------------------
# Data helpers
# ---------------------------------------------------------------------------

def _parse_float(value: str) -> float:
    """Return float from a sheet cell, or 0.0 on failure."""
    try:
        return float(value.replace(",", "").strip())
    except (ValueError, AttributeError):
        return 0.0


def _calc_pr(ep: float, gp: float) -> float:
    """PR = (EP + BASE_EP) / (GP + BASE_GP)."""
    return (ep + BASE_EP) / (gp + BASE_GP)


def _resolve_class(class_str: str) -> dict | None:
    """
    Look up a class string in the alias map.
    Returns { base_class, armor_type } or None if unresolvable.
    Case-insensitive, strips whitespace.
    """
    return _ALIAS_MAP.get(class_str.strip().lower())


def _lookup_class_from_ep_log(player_name: str) -> str | None:
    """
    Fall back to the EP log when a player's class shows as ANON or is
    unresolvable from the Totals tab.

    Returns the most recent non-ANON, non-empty class string for this
    player, or None if no usable entry exists.

    Background: players with /anon set in-game show as ANON in the EP log
    and occasionally in the Totals tab.  Their name is always recorded
    correctly, so we can recover their class from their most recent
    non-anonymous EP log entry.  Confirmed as ongoing behaviour May 2026.
    """
    engine = get_engine()
    with engine.connect() as conn:
        result = conn.execute(
            text("""
                SELECT class
                FROM ep_log
                WHERE name = :name
                  AND class != 'ANON'
                  AND class != ''
                ORDER BY date DESC
                LIMIT 1
            """),
            {"name": player_name}
        )
        row = result.fetchone()
    return row[0] if row else None


def _fetch_totals_tab() -> list[dict]:
    """
    Fetch the Totals tab (gid=0) fresh from Google Sheets and return a
    list of player dicts.  Skips the two header rows and any row without
    a name.

    For players whose class is ANON or unresolvable, falls back to the
    EP log via _lookup_class_from_ep_log().

    Each returned dict has: name, class_str, ep, gp, pr
    """
    sheet_id = os.getenv("SHEET_ID")
    url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv&gid=0"
    response = requests.get(url, timeout=15)
    if response.status_code != 200:
        raise RuntimeError(f"Failed to fetch Totals tab: HTTP {response.status_code}")

    content = response.content.decode("utf-8")
    reader = csv.reader(io.StringIO(content))
    rows = list(reader)

    players = []
    for i, row in enumerate(rows):
        # Row 0: "Last Attended / ..."  Row 1: "Date / Name / Class / ..."
        if i < 2 or len(row) <= COL_GP:
            continue
        name = row[COL_NAME].strip()
        if not name:
            continue

        class_str = row[COL_CLASS].strip()
        ep = _parse_float(row[COL_EP])
        gp = _parse_float(row[COL_GP])
        pr = _calc_pr(ep, gp)

        # --- ANON fallback ---
        # If the Totals tab shows ANON (or a class we can't resolve),
        # try to recover the real class from the EP log.
        if class_str.upper() == "ANON" or class_str.upper() == "ANONYMOUS":
            recovered = _lookup_class_from_ep_log(name)
            if recovered:
                class_str = recovered

        players.append({
            "name":      name,
            "class_str": class_str,
            "ep":        ep,
            "gp":        gp,
            "pr":        pr,
        })

    return players


def _format_ranked_list(
    player_name: str,
    ranked: list[dict],
    label: str,
    player_rank: int,
    window: int = 10,
) -> str:
    """
    Format a ranked list section for one group (class or armor type).
    Always shows the player's rank in the header (e.g. Rank 7 of 45).

    Windowing rules (window=10 by default):
      - List has <= window entries: show all.
      - Player in top <window>: show top <window>.
      - Player in bottom <window>: show bottom <window>.
      - Otherwise: show 4 above and 4 below the player, with ellipsis gaps.
    """
    total = len(ranked)
    header = f"Among {label}:  Rank {player_rank} of {total}"
    lines = [header]

    # Determine slice of ranks to display (0-based indices)
    if total <= window:
        start_idx = 0
        end_idx   = total
    elif player_rank <= window:
        start_idx = 0
        end_idx   = window
    elif player_rank > total - window:
        start_idx = total - window
        end_idx   = total
    else:
        # Middle: 4 above and 4 below the player
        start_idx = player_rank - 5   # 0-based: (player_rank-1) - 4
        end_idx   = player_rank + 4   # 0-based: (player_rank-1) + 4 + 1

    if start_idx > 0:
        lines.append("  ...")

    for i in range(start_idx, end_idx):
        p        = ranked[i]
        rank_num = i + 1
        rank_str = f"{rank_num}."
        name_str = p["name"]
        pr_str   = f"{p['pr']:.4f}"
        arrow    = "  ← you" if p["name"].lower() == player_name.lower() else ""
        lines.append(f"  {rank_str:<4}{name_str:<16}{pr_str}{arrow}")

    if end_idx < total:
        lines.append("  ...")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Cog
# ---------------------------------------------------------------------------

class PriorityCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @discord.slash_command(
        name="priority",
        description="Show your loot priority rank by class and armor type"
    )
    async def priority(self, ctx):
        # TODO (Phase 3): When integrated with the full guild bot, filter the
        # ranked lists to players currently in the raid voice channel rather
        # than the full guild roster from the Totals tab.  The voice channel
        # member list will be available via ctx.guild and the existing bot's
        # voice state tracking.

        await ctx.defer()

        player_name = os.getenv("PLAYER_NAME", "").strip()
        if not player_name:
            await ctx.followup.send(
                "❌ `PLAYER_NAME` is not set in `.env`. Cannot look up your character."
            )
            return

        # --- Fetch Totals tab fresh from Google Sheets ---
        try:
            players = _fetch_totals_tab()
        except Exception as e:
            await ctx.followup.send(f"❌ Failed to fetch Totals tab: {e}")
            return

        if not players:
            await ctx.followup.send("❌ Totals tab returned no data.")
            return

        # --- Find the calling player ---
        me = next(
            (p for p in players if p["name"].lower() == player_name.lower()),
            None
        )
        if me is None:
            await ctx.followup.send(
                f"❌ **{player_name}** not found in the Totals tab. "
                f"Check that `PLAYER_NAME` in `.env` matches your character name exactly."
            )
            return

        # --- Resolve class → base_class + armor_type ---
        class_info = _resolve_class(me["class_str"])
        if class_info is None:
            await ctx.followup.send(
                f"❌ Could not identify class from **{me['class_str']}**. "
                f"This title may not be in the alias map yet — "
                f"update `data/eq_class_aliases.json`."
            )
            return

        base_class  = class_info["base_class"]
        armor_type  = class_info["armor_type"]
        armor_label = ARMOR_LABELS.get(armor_type, f"{armor_type} wearers")

        # --- Build ranked lists ---
        # All players whose class resolves to the same base_class
        same_class = [
            p for p in players
            if _resolve_class(p["class_str"]) is not None
            and _resolve_class(p["class_str"])["base_class"] == base_class
        ]
        same_class.sort(key=lambda p: p["pr"], reverse=True)

        # All players whose class resolves to the same armor_type
        same_armor = [
            p for p in players
            if _resolve_class(p["class_str"]) is not None
            and _resolve_class(p["class_str"])["armor_type"] == armor_type
        ]
        same_armor.sort(key=lambda p: p["pr"], reverse=True)

        # Player's rank in each list (1-based)
        class_rank = next(
            (i + 1 for i, p in enumerate(same_class)
             if p["name"].lower() == player_name.lower()),
            None
        )
        armor_rank = next(
            (i + 1 for i, p in enumerate(same_armor)
             if p["name"].lower() == player_name.lower()),
            None
        )

        if class_rank is None or armor_rank is None:
            await ctx.followup.send(
                f"❌ Could not determine rank for **{player_name}**. "
                f"Their class may be unresolvable — check `data/eq_class_aliases.json`."
            )
            return

        # --- Build class label ---
        # Show both base name and current title if they differ:
        # "Bards (Virtuosos)" vs just "Warriors"
        if me["class_str"] and me["class_str"].lower() != base_class.lower():
            class_label = f"{base_class}s ({me['class_str']}s)"
        else:
            class_label = f"{base_class}s"

        # --- Format and send ---
        pr_str = f"{me['pr']:.4f}"
        class_section = _format_ranked_list(
            player_name, same_class, class_label, class_rank
        )
        armor_section = _format_ranked_list(
            player_name, same_armor, armor_label, armor_rank
        )

        output = (
            f"**{player_name}** — PR: {pr_str}\n\n"
            f"```\n{class_section}\n\n{armor_section}\n```"
        )

        await ctx.followup.send(output)


def setup(bot):
    bot.add_cog(PriorityCog(bot))