"""Fabrique d'embeds pour garder un style uniforme partout."""
from __future__ import annotations

import discord

from bot.config import gconf

SUCCESS = 0x57F287
ERROR = 0xED4245
WARNING = 0xFEE75C
INFO = 0x5865F2


def base(title: str | None = None, description: str | None = None, color: int | None = None,
         guild: discord.Guild | None = None) -> discord.Embed:
    """Embed aux couleurs du serveur (couleur et pied de page réglables dans le panel)."""
    cfg = gconf(guild)
    embed = discord.Embed(title=title, description=description, color=cfg.color if color is None else color)
    footer = cfg.get("brand", "footer")
    if footer and guild is not None:
        embed.set_footer(text=footer)
    embed.timestamp = discord.utils.utcnow()
    return embed


def success(message: str, title: str = "✅ Succès") -> discord.Embed:
    return base(title, message, SUCCESS)


def error(message: str, title: str = "❌ Erreur") -> discord.Embed:
    return base(title, message, ERROR)


def warning(message: str, title: str = "⚠️ Attention") -> discord.Embed:
    return base(title, message, WARNING)


def info(message: str, title: str = "ℹ️ Information") -> discord.Embed:
    return base(title, message, INFO)
