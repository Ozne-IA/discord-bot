"""💎 Droits d'accès au panel par rôle.

Les admins (« Gérer le serveur ») ont toujours accès à tout. Avec Premium, ils peuvent donner à certains
rôles (ex. Modérateurs) un accès LIMITÉ à quelques groupes de réglages. Le serveur web ne garde, lors d'un
enregistrement, que les réglages des groupes autorisés : le reste est recopié depuis la config actuelle.
"""
from __future__ import annotations

import copy
from typing import Any

# groupe -> (nom affiché, chemins de config modifiables)
ACCESS_GROUPS: dict[str, tuple[str, tuple[str, ...]]] = {
    "community": ("Communauté", (
        "welcome", "channels.welcome", "channels.goodbye", "channels.level_up", "leveling", "roles.level_roles",
        "roles.notifications", "panels.notifications", "economy", "games", "birthdays", "reminders", "suggestions",
        "starboard", "temp_voice", "counters", "custom_commands", "role_menus", "engagement", "events", "ai")),
    "moderation": ("Modération", ("moderation", "automod", "anti_raid", "anti_nuke", "reports", "message_log",
                                  "twitch_mod")),
    "tickets": ("Tickets & modmail", (
        "tickets", "panels.tickets", "channels.ticket_category", "channels.ticket_logs", "modmail", "invites")),
    "alerts": ("Alertes & événements", ("alerts", "giveaways")),
    "messages": ("Messages", ("scheduled",)),
    "stats": ("Statistiques & historique", ()),
}
GROUP_IDS = tuple(ACCESS_GROUPS)


def _get(data: dict, path: str) -> tuple[bool, Any]:
    cur: Any = data
    for key in path.split("."):
        if not isinstance(cur, dict) or key not in cur:
            return False, None
        cur = cur[key]
    return True, cur


def _set(data: dict, path: str, value: Any) -> None:
    keys = path.split(".")
    cur = data
    for key in keys[:-1]:
        cur = cur.setdefault(key, {})
    cur[keys[-1]] = copy.deepcopy(value)


def apply_restricted(current: dict, incoming: dict, groups: set[str]) -> dict:
    """Config à enregistrer pour un membre à accès limité : seuls les chemins de ses groupes changent."""
    result = copy.deepcopy(current)
    for group in groups:
        for path in ACCESS_GROUPS.get(group, ("", ()))[1]:
            found, value = _get(incoming, path)
            if found:
                _set(result, path, value)
    return result


def groups_for_roles(role_ids: set[int], rules: list[dict]) -> set[str]:
    """Groupes autorisés pour un membre, d'après ses rôles et les règles d'accès du serveur."""
    allowed: set[str] = set()
    for rule in rules or []:
        if int(rule.get("role") or 0) in role_ids:
            allowed |= {g for g in GROUP_IDS if rule.get(g)}
    return allowed
