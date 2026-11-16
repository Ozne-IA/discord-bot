"""Journal du serveur : messages supprimés/édités, pseudos, rôles, vocal, salons."""
from __future__ import annotations

import discord
from discord.ext import commands

from bot import embeds
from bot.utils import send_log


def _clip(text: str, limit: int = 1000) -> str:
    text = discord.utils.escape_markdown(text or "")
    return text if len(text) <= limit else text[:limit] + "…"


class Logs(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message) -> None:
        if not message.guild or message.author.bot:
            return
        embed = embeds.error(f"**Auteur** : {message.author.mention}\n**Salon** : {message.channel.mention}\n\n"
                             f"{_clip(message.content) or '*(pas de texte)*'}", "🗑️ Message supprimé")
        if message.attachments:
            embed.add_field(name="Pièces jointes", value="\n".join(a.filename for a in message.attachments))
        await send_log(message.guild, embed)

    @commands.Cog.listener()
    async def on_bulk_message_delete(self, messages: list[discord.Message]) -> None:
        if messages and messages[0].guild:
            await send_log(messages[0].guild, embeds.error(
                f"{len(messages)} messages supprimés dans {messages[0].channel.mention}", "🗑️ Suppression en masse"))

    @commands.Cog.listener()
    async def on_message_edit(self, before: discord.Message, after: discord.Message) -> None:
        if not before.guild or before.author.bot or before.content == after.content:
            return
        embed = embeds.warning(f"**Auteur** : {before.author.mention}\n**Salon** : {before.channel.mention} "
                               f"[aller au message]({after.jump_url})", "✏️ Message modifié")
        embed.add_field(name="Avant", value=_clip(before.content, 1000) or "-", inline=False)
        embed.add_field(name="Après", value=_clip(after.content, 1000) or "-", inline=False)
        await send_log(before.guild, embed)

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member) -> None:
        if before.nick != after.nick:
            await send_log(after.guild, embeds.info(
                f"{after.mention} : `{before.nick or before.name}` → `{after.nick or after.name}`", "🏷️ Pseudo modifié"))
        added = set(after.roles) - set(before.roles)
        removed = set(before.roles) - set(after.roles)
        if added or removed:
            parts = []
            if added:
                parts.append("➕ " + ", ".join(r.mention for r in added))
            if removed:
                parts.append("➖ " + ", ".join(r.mention for r in removed))
            await send_log(after.guild, embeds.info(f"{after.mention}\n" + "\n".join(parts), "🎭 Rôles modifiés"))
        if before.timed_out_until != after.timed_out_until and after.timed_out_until:
            await send_log(after.guild, embeds.warning(
                f"{after.mention} muet jusqu'à {discord.utils.format_dt(after.timed_out_until)}", "🔇 Timeout"))

    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState,
                                    after: discord.VoiceState) -> None:
        if before.channel == after.channel:
            return
        if before.channel is None and after.channel:
            text = f"{member.mention} a rejoint 🔊 {after.channel.mention}"
        elif after.channel is None and before.channel:
            text = f"{member.mention} a quitté 🔇 {before.channel.mention}"
        else:
            text = f"{member.mention} : {before.channel.mention} → {after.channel.mention}"  # type: ignore[union-attr]
        await send_log(member.guild, embeds.info(text, "🎙️ Vocal"))

    @commands.Cog.listener()
    async def on_guild_channel_create(self, channel: discord.abc.GuildChannel) -> None:
        await send_log(channel.guild, embeds.success(f"{channel.mention} (`{channel.name}`)", "📁 Salon créé"))

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel: discord.abc.GuildChannel) -> None:
        await send_log(channel.guild, embeds.error(f"`#{channel.name}`", "📁 Salon supprimé"))

    @commands.Cog.listener()
    async def on_guild_role_create(self, role: discord.Role) -> None:
        await send_log(role.guild, embeds.success(f"{role.mention}", "🎭 Rôle créé"))

    @commands.Cog.listener()
    async def on_guild_role_delete(self, role: discord.Role) -> None:
        await send_log(role.guild, embeds.error(f"`@{role.name}`", "🎭 Rôle supprimé"))

    @commands.Cog.listener()
    async def on_member_ban(self, guild: discord.Guild, user: discord.User) -> None:
        await send_log(guild, embeds.error(f"{user} (`{user.id}`)", "🔨 Bannissement"))

    @commands.Cog.listener()
    async def on_member_unban(self, guild: discord.Guild, user: discord.User) -> None:
        await send_log(guild, embeds.success(f"{user} (`{user.id}`)", "🕊️ Débannissement"))


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Logs(bot))
