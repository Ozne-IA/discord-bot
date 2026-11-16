"""Diagnostic de la configuration d'un serveur (utilisé par /check_config et le panel web)."""
from __future__ import annotations

import discord

from bot.config import gconf

REQUIRED_PERMISSIONS = ["manage_roles", "manage_channels", "manage_messages", "kick_members", "ban_members",
                        "moderate_members", "view_audit_log", "embed_links", "attach_files",
                        "read_message_history", "send_messages", "view_channel"]

LABELS = {
    "channels.welcome": "Salon de bienvenue", "channels.goodbye": "Salon d'au revoir",
    "channels.logs": "Salon de logs", "channels.mod_logs": "Logs de modération",
    "channels.level_up": "Annonces de niveau", "channels.ticket_category": "Catégorie des tickets",
    "channels.ticket_logs": "Logs des tickets", "panels.verify": "Salon des règles",
    "panels.notifications": "Salon des rôles", "panels.tickets": "Salon du support",
    "roles.unverified": "Rôle Non vérifié", "roles.member": "Rôle Membre", "roles.staff": "Rôle Staff",
}
OPTIONAL = {"channels.goodbye", "channels.level_up", "channels.mod_logs", "channels.ticket_logs"}


def run(guild: discord.Guild) -> list[dict]:
    """Renvoie une liste de {status: ok|warn|error, text}."""
    cfg = gconf(guild)
    results: list[dict] = []
    me = guild.me

    for section in ("channels", "panels"):
        for name in (cfg.get(section, default={}) or {}):
            key = f"{section}.{name}"
            label = LABELS.get(key, key)
            cid = int(cfg.get(section, name, default=0) or 0)
            ch = guild.get_channel(cid)
            if not cid:
                results.append({"status": "warn" if key in OPTIONAL else "error", "text": f"{label} : non défini"})
            elif ch is None:
                results.append({"status": "error", "text": f"{label} : salon introuvable (supprimé ?)"})
            elif isinstance(ch, discord.TextChannel) and not ch.permissions_for(me).send_messages:
                results.append({"status": "error", "text": f"{label} : je ne peux pas écrire dans #{ch.name}"})
            else:
                results.append({"status": "ok", "text": f"{label} : #{ch.name}"})

    roles = {f"roles.{k}": cfg.role_id(k) for k in ("unverified", "member", "staff")}
    for group in ("notifications", "level_roles"):
        for label, rid in (cfg.get("roles", group, default={}) or {}).items():
            roles[f"roles.{group}.{label}"] = int(rid or 0)
    for key, rid in roles.items():
        label = LABELS.get(key) or ("Notification " + key.split(".")[-1] if "notifications" in key
                                    else "Rôle niveau " + key.split(".")[-1])
        role = guild.get_role(rid)
        if not rid:
            results.append({"status": "error", "text": f"{label} : non défini"})
        elif role is None:
            results.append({"status": "error", "text": f"{label} : rôle introuvable (supprimé ?)"})
        elif role >= me.top_role:
            results.append({"status": "error",
                            "text": f"{label} : @{role.name} est au-dessus de mon rôle, monte mon rôle plus haut"})
        else:
            results.append({"status": "ok", "text": f"{label} : @{role.name}"})

    perms = me.guild_permissions
    missing = [p for p in REQUIRED_PERMISSIONS if not getattr(perms, p)]
    if missing:
        results.append({"status": "error", "text": "Permissions manquantes : " + ", ".join(missing)})
    else:
        results.append({"status": "ok", "text": "Toutes mes permissions sont présentes"})
    return results
