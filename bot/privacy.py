"""Ménage des données (RGPD) : serveurs quittés, vieilles données, données d'un membre.

- Serveur quitté : ses données sont gardées 30 jours (s'il réajoute le bot, tout est encore là), puis effacées.
  On garde seulement la trace des accès Premium offerts et de l'essai gratuit (pour qu'il ne serve qu'une fois).
- Vieilles données : statistiques, XP par jour, journaux techniques… effacés après leur durée utile.
- Membre : /mes-donnees permet de télécharger ses données, ou d'effacer celles qui ne servent qu'à lui.
"""
from __future__ import annotations

import json
import time
from datetime import date, timedelta
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from bot.db import Database

LEFT_KEY = "left_at"                 # table settings : date de départ du bot (horodatage)
GRACE_DAYS = 30
KEEP_TABLES = {"premium_grants"}     # accès offerts / essai : jamais effacés (anti-abus de l'essai)
KEEP_SETTING_PREFIXES = ("premium_trial",)
# Tables « enfants » rattachées à un serveur par leur parent (à effacer avant le parent)
CHILDREN = {
    "events": (("event_participants", "event_id"),),
    "giveaways": (("giveaway_entries", "giveaway_id"),),
    "polls": (("poll_votes", "poll_id"),),
    "suggestions": (("suggestion_votes", "suggestion_id"),),
    "tournaments": (("tournament_players", "tournament_id"), ("tournament_matches", "tournament_id")),
}
# Durées de conservation : (table, colonne, jours, colonne au format date « AAAA-MM-JJ » ?)
RETENTION = (
    ("stats_daily", "day", 120, True),       # graphiques : 90 jours max dans le panel
    ("xp_daily", "day", 62, True),            # classements de la semaine / du mois
    ("ai_usage", "day", 30, True),
    ("security_logs", "created_at", 180, False),
    ("panel_audit", "created_at", 365, False),
    ("bot_votes", "voted_at", 90, False),
)
# Données d'un membre : (table, colonne qui contient son ID)
USER_EXPORT = (
    ("levels", "user_id"), ("xp_daily", "user_id"), ("economy", "user_id"), ("inventory", "user_id"),
    ("achievements", "user_id"), ("quest_progress", "user_id"), ("activity_streaks", "user_id"),
    ("member_counters", "user_id"), ("birthdays", "user_id"), ("reminders", "user_id"),
    ("giveaway_entries", "user_id"), ("poll_votes", "user_id"), ("suggestion_votes", "user_id"),
    ("event_participants", "user_id"), ("tournament_players", "user_id"), ("suggestions", "author_id"),
    ("tickets", "user_id"), ("cases", "user_id"), ("invite_joins", "member_id"), ("bot_votes", "user_id"),
)
# Ce que le membre peut effacer lui-même. Restent : sanctions, tickets, signalements, suggestions publiées,
# invitations (anti-abus) et journaux du staff, qui servent aussi à la modération des serveurs.
USER_ERASABLE = (
    ("levels", "user_id"), ("xp_daily", "user_id"), ("economy", "user_id"), ("inventory", "user_id"),
    ("achievements", "user_id"), ("quest_progress", "user_id"), ("activity_streaks", "user_id"),
    ("member_counters", "user_id"), ("birthdays", "user_id"), ("reminders", "user_id"),
    ("giveaway_entries", "user_id"), ("poll_votes", "user_id"), ("suggestion_votes", "user_id"),
    ("event_participants", "user_id"), ("bot_votes", "user_id"), ("web_sessions", "user_id"),
)


async def _tables_with(db: "Database", column: str) -> list[str]:
    tables = [r["name"] for r in await db.fetchall(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
    out = []
    for table in tables:
        cols = {c["name"] for c in await db.fetchall(f"PRAGMA table_info({table})")}
        if column in cols:
            out.append(table)
    return out


# --------------------------------------------------------------------------- #
#  Serveurs quittés
# --------------------------------------------------------------------------- #
async def mark_left(db: "Database", guild_id: int, when: float | None = None) -> None:
    if not await db.get_setting(guild_id, LEFT_KEY):
        await db.set_setting(guild_id, LEFT_KEY, str(time.time() if when is None else when))


async def mark_back(db: "Database", guild_id: int) -> None:
    await db.execute("DELETE FROM settings WHERE guild_id=? AND key=?", (guild_id, LEFT_KEY))


async def known_guilds(db: "Database") -> set[int]:
    """Serveurs qui ont des données (configuration, niveaux, réglages…)."""
    ids: set[int] = set()
    for table in ("guild_config", "settings", "levels", "economy", "tickets", "cases", "stats_daily"):
        ids.update(r["guild_id"] for r in await db.fetchall(f"SELECT DISTINCT guild_id FROM {table}"))
    ids.discard(0)  # 0 = réglages du bot lui-même
    return ids


async def purge_guild(db: "Database", guild_id: int) -> int:
    """Efface toutes les données d'un serveur (sauf l'historique Premium/essai). Renvoie le nombre de lignes."""
    total = 0
    for parent, children in CHILDREN.items():
        for child, key in children:
            cur = await db.conn.execute(  # type: ignore[union-attr]
                f"DELETE FROM {child} WHERE {key} IN (SELECT id FROM {parent} WHERE guild_id=?)", (guild_id,))
            total += cur.rowcount or 0
    # Autorisations Twitch des chaînes de ce serveur
    cur = await db.conn.execute(  # type: ignore[union-attr]
        "DELETE FROM twitch_tokens WHERE kind='broadcaster' AND user_id IN "
        "(SELECT broadcaster_id FROM twitch_channels WHERE guild_id=?)", (guild_id,))
    total += cur.rowcount or 0
    for table in await _tables_with(db, "guild_id"):
        if table in KEEP_TABLES:
            continue
        if table == "settings":
            keep = " AND ".join("key NOT LIKE ?" for _ in KEEP_SETTING_PREFIXES)
            cur = await db.conn.execute(  # type: ignore[union-attr]
                f"DELETE FROM settings WHERE guild_id=? AND {keep}",
                (guild_id, *[p + "%" for p in KEEP_SETTING_PREFIXES]))
        else:
            cur = await db.conn.execute(f"DELETE FROM {table} WHERE guild_id=?", (guild_id,))  # type: ignore[union-attr]
        total += cur.rowcount or 0
    await db.conn.commit()  # type: ignore[union-attr]
    return total


async def due_for_purge(db: "Database", present: set[int], now: float | None = None) -> list[int]:
    """Serveurs quittés depuis plus de GRACE_DAYS. Note aussi le départ de ceux quittés pendant que le bot était éteint."""
    now = time.time() if now is None else now
    for gid in await known_guilds(db) - present:
        await mark_left(db, gid, now)
    rows = await db.fetchall("SELECT guild_id, value FROM settings WHERE key=?", (LEFT_KEY,))
    due = []
    for r in rows:
        if r["guild_id"] in present:
            await mark_back(db, r["guild_id"])  # revenu pendant que le bot était éteint
        elif now - float(r["value"] or now) >= GRACE_DAYS * 86400:
            due.append(r["guild_id"])
    return due


# --------------------------------------------------------------------------- #
#  Vieilles données
# --------------------------------------------------------------------------- #
async def purge_old(db: "Database", now: float | None = None, today: date | None = None) -> int:
    now = time.time() if now is None else now
    today = today or date.today()
    total = 0
    for table, column, days, is_day in RETENTION:
        cutoff: Any = (today - timedelta(days=days)).isoformat() if is_day else now - days * 86400
        cur = await db.conn.execute(f"DELETE FROM {table} WHERE {column} < ?", (cutoff,))  # type: ignore[union-attr]
        total += cur.rowcount or 0
    cur = await db.conn.execute("DELETE FROM web_sessions WHERE expires_at < ?", (now,))  # type: ignore[union-attr]
    total += cur.rowcount or 0
    await db.conn.commit()  # type: ignore[union-attr]
    return total


async def vacuum(db: "Database") -> None:
    """Rend la place libérée (la base et les sauvegardes deviennent plus légères)."""
    await db.conn.commit()  # type: ignore[union-attr]
    await db.conn.execute("VACUUM")  # type: ignore[union-attr]


# --------------------------------------------------------------------------- #
#  Données d'un membre
# --------------------------------------------------------------------------- #
async def export_user(db: "Database", user_id: int) -> dict:
    out: dict[str, list[dict]] = {}
    for table, column in USER_EXPORT:
        rows = await db.fetchall(f"SELECT * FROM {table} WHERE {column}=?", (user_id,))
        if rows:
            out[table] = [{k: (str(v) if isinstance(v, int) and abs(v) > 2**53 else v) for k, v in dict(r).items()}
                          for r in rows]
    return {"user_id": str(user_id), "exported_at": int(time.time()), "data": out,
            "note": "Les notes internes du staff et les journaux de modération ne sont pas inclus : "
                    "demande-les au staff du serveur concerné."}


def export_json(data: dict) -> bytes:
    return json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")


async def erase_user(db: "Database", user_id: int) -> int:
    total = 0
    for table, column in USER_ERASABLE:
        cur = await db.conn.execute(f"DELETE FROM {table} WHERE {column}=?", (user_id,))  # type: ignore[union-attr]
        total += cur.rowcount or 0
    await db.conn.commit()  # type: ignore[union-attr]
    return total
