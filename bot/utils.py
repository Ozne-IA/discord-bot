"""Petits helpers réutilisés par plusieurs modules."""
from __future__ import annotations

import logging
import os
import re
from datetime import timedelta

import discord

from bot import embeds
from bot.config import gconf

log = logging.getLogger("bot.utils")

_DURATION_RE = re.compile(r"(\d+)\s*([smhdj])", re.IGNORECASE)
_UNITS = {"s": 1, "m": 60, "h": 3600, "d": 86400, "j": 86400}


def parse_duration(text: str) -> timedelta | None:
    """'1h30m' -> 1h30, '7d' / '7j' -> 7 jours. Renvoie None si invalide."""
    matches = _DURATION_RE.findall(text or "")
    if not matches or _DURATION_RE.sub("", text).strip():
        return None
    seconds = sum(int(n) * _UNITS[u.lower()] for n, u in matches)
    return timedelta(seconds=seconds) if seconds > 0 else None


def format_duration(delta: timedelta) -> str:
    seconds = int(delta.total_seconds())
    parts = []
    for name, size in (("j", 86400), ("h", 3600), ("min", 60), ("s", 1)):
        if seconds >= size:
            value, seconds = divmod(seconds, size)
            parts.append(f"{value}{name}")
    return " ".join(parts) or "0s"


def fill_template(template: str, member: discord.Member) -> str:
    """Remplace {mention} {name} {server} {count}. Les accolades inconnues sont laissées telles quelles."""
    values = {"mention": member.mention, "name": member.display_name,
              "server": member.guild.name, "count": member.guild.member_count}
    return re.sub(r"\{(\w+)\}", lambda m: str(values.get(m.group(1), m.group(0))), template or "")


def dashboard_url(guild_id: int | None = None) -> str | None:
    base = os.getenv("PUBLIC_URL", "").rstrip("/")
    if not base:
        return None
    return f"{base}/dashboard#/guild/{guild_id}" if guild_id else f"{base}/dashboard"


async def send_log(guild: discord.Guild, embed: discord.Embed, channel: str = "logs") -> None:
    """Envoie un embed dans un salon de logs configuré (ignore silencieusement s'il manque)."""
    cfg = gconf(guild)
    ch = guild.get_channel(cfg.channel_id(channel) or cfg.channel_id("logs"))
    if isinstance(ch, discord.TextChannel):
        try:
            await ch.send(embed=embed)
        except discord.HTTPException as exc:
            log.warning("Impossible d'envoyer le log dans #%s : %s", ch.name, exc)


def is_staff(member: discord.Member) -> bool:
    staff_id = gconf(member.guild).role_id("staff")
    perms = member.guild_permissions
    return (
        perms.administrator
        or perms.manage_guild
        or perms.moderate_members
        or any(r.id == staff_id for r in member.roles)
    )


def can_act_on(moderator: discord.Member, target: discord.Member) -> str | None:
    """Renvoie un message d'erreur si le modérateur ne peut pas sanctionner la cible."""
    me = target.guild.me
    if target == moderator:
        return "Tu ne peux pas te sanctionner toi-même."
    if target == target.guild.owner:
        return "Impossible de sanctionner le propriétaire du serveur."
    if target.top_role >= moderator.top_role and moderator != target.guild.owner:
        return "Ce membre a un rôle supérieur ou égal au tien."
    if target.top_role >= me.top_role:
        return "Ce membre a un rôle supérieur ou égal au mien : place mon rôle plus haut."
    return None


async def reply_error(interaction: discord.Interaction, message: str) -> None:
    embed = embeds.error(message)
    if interaction.response.is_done():
        await interaction.followup.send(embed=embed, ephemeral=True)
    else:
        await interaction.response.send_message(embed=embed, ephemeral=True)
