"""Publication des panneaux (règles, notifications, tickets) — utilisé par les commandes et le panel web.

Le message publié est mémorisé : republier le met à jour au lieu d'en créer un nouveau.
"""
from __future__ import annotations

import discord

PANELS = ("verify", "notifications", "tickets")


def _builder(name: str):
    # Import tardif pour éviter les imports circulaires avec les cogs
    if name == "verify":
        from cogs.verification import build_panel
    elif name == "notifications":
        from cogs.roles import build_panel
    elif name == "tickets":
        from cogs.tickets import build_panel
    else:
        raise ValueError(name)
    return build_panel


async def publish_panel(bot, guild: discord.Guild, name: str,
                        channel: discord.TextChannel) -> discord.Message:
    embed, view = _builder(name)(guild)
    key = f"panel_message:{name}"
    previous = await bot.db.get_setting(guild.id, key)
    if previous and ":" in previous:
        ch_id, msg_id = previous.split(":", 1)
        if int(ch_id) == channel.id:
            try:
                message = await channel.fetch_message(int(msg_id))
                await message.edit(embed=embed, view=view)
                return message
            except discord.HTTPException:
                pass  # supprimé entre-temps : on en renvoie un
        else:
            old_channel = guild.get_channel(int(ch_id))
            if isinstance(old_channel, discord.TextChannel):
                try:
                    old = await old_channel.fetch_message(int(msg_id))
                    await old.delete()
                except discord.HTTPException:
                    pass
    message = await channel.send(embed=embed, view=view)
    await bot.db.set_setting(guild.id, key, f"{channel.id}:{message.id}")
    return message
