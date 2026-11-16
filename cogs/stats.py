"""Collecte des statistiques quotidiennes (arrivées, départs, messages, minutes en vocal, membres).

Les compteurs sont gardés en mémoire et écrits en base une fois par minute (pas une écriture par message).
Les graphiques sont affichés dans le panel web : 7 jours en gratuit, 30 / 90 jours en 💎 Premium.
"""
from __future__ import annotations

import logging
from collections import defaultdict
from datetime import datetime, timezone

import discord
from discord.ext import commands, tasks

log = logging.getLogger("cogs.stats")
FIELDS = ("joins", "leaves", "messages", "voice_minutes")


def today_utc() -> str:
    return datetime.now(timezone.utc).date().isoformat()


class Stats(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.pending: dict[tuple[int, str], dict[str, int]] = defaultdict(lambda: dict.fromkeys(FIELDS, 0))

    @property
    def db(self):
        return self.bot.db  # type: ignore[attr-defined]

    async def cog_load(self) -> None:
        self.flush.start()

    async def cog_unload(self) -> None:
        self.flush.cancel()
        await self.write_pending()

    def bump(self, guild_id: int, field: str, amount: int = 1) -> None:
        self.pending[(guild_id, today_utc())][field] += amount

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        if not member.bot:
            self.bump(member.guild.id, "joins")

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member) -> None:
        if not member.bot:
            self.bump(member.guild.id, "leaves")

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if message.guild and not message.author.bot:
            self.bump(message.guild.id, "messages")

    async def write_pending(self) -> None:
        pending, self.pending = self.pending, defaultdict(lambda: dict.fromkeys(FIELDS, 0))
        for (guild_id, day), counts in pending.items():
            guild = self.bot.get_guild(guild_id)
            await self.db.execute(
                "INSERT INTO stats_daily (guild_id, day, joins, leaves, messages, voice_minutes, members) "
                "VALUES (?,?,?,?,?,?,?) ON CONFLICT(guild_id, day) DO UPDATE SET "
                "joins = joins + excluded.joins, leaves = leaves + excluded.leaves, "
                "messages = messages + excluded.messages, voice_minutes = voice_minutes + excluded.voice_minutes, "
                "members = COALESCE(excluded.members, members)",
                (guild_id, day, counts["joins"], counts["leaves"], counts["messages"], counts["voice_minutes"],
                 guild.member_count if guild else None))

    @tasks.loop(minutes=1)
    async def flush(self) -> None:
        # minutes passées en vocal (humains, hors salon AFK)
        for guild in self.bot.guilds:
            minutes = sum(1 for ch in guild.voice_channels + guild.stage_channels if ch != guild.afk_channel
                          for m in ch.members if not m.bot)
            if minutes:
                self.bump(guild.id, "voice_minutes", minutes)
            else:
                self.pending[(guild.id, today_utc())]  # crée la ligne du jour (nombre de membres)
        try:
            await self.write_pending()
        except Exception:
            log.exception("Écriture des statistiques impossible")

    @flush.before_loop
    async def _before(self) -> None:
        await self.bot.wait_until_ready()


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Stats(bot))
