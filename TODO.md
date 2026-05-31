# TODO

Current work status for sos-epgp-bot.
See `CHANGELOG.md` for shipped history. See `Design.md` for architecture.

**SC-N convention:** Any new scope item gets the next available number.
Current highest: **SC-9** (this restructure). Add new items below with the
next number before starting work.

---

## 🔜 Next Steps

| ID | Description | Notes |
|----|-------------|-------|
| — | Fork khandyman/SOS-Bot and begin Phase 3 PR | All pre-conditions met — tests green, doc final |

---

## 🚫 Tabled (Phase 3+)

| ID | Description | Notes |
|----|-------------|-------|
| — | Fork + PR into khandyman/SOS-Bot | After all testing complete and doc is final |
| — | Voice channel priority filter | Requires existing bot's Discord voice membership access |
| — | Webhook-triggered sync | Requires coordination with sheet-writing bot |
| — | Multi-player support | Standalone version is single-player by design |
| SC-9 | DM opt-in for missed EP notifications | Proactively DM players who opt in when they missed EP they could have earned. Requires opt-in roster. Better fit than original DM design. |

---

## 📋 SC-N Registry

| SC | Title | Status |
|----|-------|--------|
| SC-1 | 12-player minimum threshold | ✅ Shipped |
| SC-2 | Same-day PQ + Raid split | ✅ Shipped |
| SC-3 | TTL cache for Google Sheets sync | ✅ Shipped |
| SC-4 | Yes/No button flow in `/review` | ✅ Shipped |
| SC-5 | Discord scheduled events integration | ✅ Shipped |
| SC-6 | `/item` too-many-matches UX + ephemeral | ✅ Shipped |
| SC-7 | Design.md directory tree + SC-N convention | ✅ Shipped |
| SC-8 | Docs restructure (Design/Changelog/Todo split) | ✅ Shipped |
| SC-9 | DM opt-in for missed EP notifications | 🚫 Tabled (Phase 3+) |
