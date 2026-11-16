"""Statistiques d'activité du staff (sanctions par type, tickets pris en charge, notes)."""
from __future__ import annotations

PERIODS = {"7": 7, "30": 30, "90": 90, "all": 0}


async def build_staff_stats(db, guild_id: int, since: float = 0) -> list[dict]:
    """Une ligne par membre du staff, triée par activité totale."""
    staff: dict[int, dict] = {}

    def entry(uid: int) -> dict:
        return staff.setdefault(uid, {"user_id": uid, "actions": {}, "cases": 0, "tickets": 0, "notes": 0, "total": 0})

    for r in await db.fetchall(
            "SELECT mod_id, action, COUNT(*) AS n FROM cases WHERE guild_id=? AND created_at >= ? GROUP BY mod_id, action",
            (guild_id, since)):
        e = entry(r["mod_id"])
        e["actions"][r["action"]] = r["n"]
        e["cases"] += r["n"]
    for r in await db.fetchall(
            "SELECT claimed_by, COUNT(*) AS n FROM tickets WHERE guild_id=? AND claimed_by IS NOT NULL AND opened_at >= ? "
            "GROUP BY claimed_by", (guild_id, since)):
        entry(r["claimed_by"])["tickets"] = r["n"]
    for r in await db.fetchall(
            "SELECT mod_id, COUNT(*) AS n FROM notes WHERE guild_id=? AND created_at >= ? GROUP BY mod_id",
            (guild_id, since)):
        entry(r["mod_id"])["notes"] = r["n"]
    for e in staff.values():
        e["total"] = e["cases"] + e["tickets"] + e["notes"]
    return sorted(staff.values(), key=lambda e: (-e["total"], e["user_id"]))
