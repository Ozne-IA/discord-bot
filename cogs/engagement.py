"""Engagement des membres : succès (badges), quêtes du jour / de la semaine, séries d'activité, profil.

Gratuit : succès, 3 quêtes par jour, série d'activité, /profil.
💎 Premium : quête de la semaine (grosse récompense).
Les autres modules signalent une activité avec  bot.dispatch("activity", guild, user, channel, kind, amount)
(kind : daily, work, game_play, game_win). Les messages sont suivis ici directement.
"""
from __future__ import annotations

import logging
import time
from datetime import date, datetime
from zoneinfo import ZoneInfo

import discord
from discord import app_commands
from discord.ext import commands

from bot import embeds
from bot.config import gconf
from bot.engagement_data import (ACHIEVEMENTS, day_key, newly_unlocked, next_activity_streak, next_reset,
                                 progress_bar, quest_target, quest_text, quests_for, week_key)
from bot.utils import reply_error

log = logging.getLogger("cogs.engagement")
CHECK_EVERY = 120  # secondes entre deux vérifications de succès déclenchées par des messages


def server_today(guild: discord.Guild | None) -> date:
    tz_name = gconf(guild).get("birthdays", "timezone", default="Europe/Paris") or "UTC"
    try:
        tz = ZoneInfo(tz_name)
    except Exception:
        tz = ZoneInfo("UTC")
    return datetime.now(tz).date()


class Engagement(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.seen_today: dict[tuple[int, int], str] = {}
        self.last_check: dict[tuple[int, int], float] = {}

    @property
    def db(self):
        return self.bot.db  # type: ignore[attr-defined]

    @property
    def economy(self):
        return self.bot.get_cog("Economy")

    @staticmethod
    def enabled(guild: discord.Guild | None, key: str = "enabled") -> bool:
        cfg = gconf(guild)
        return bool(guild and cfg.get("engagement", "enabled", default=True) and cfg.get("engagement", key, default=True))

    # --- compteurs -----------------------------------------------------------
    async def bump(self, guild_id: int, user_id: int, key: str, amount: int = 1) -> None:
        await self.db.execute(
            "INSERT INTO member_counters (guild_id, user_id, key, value) VALUES (?,?,?,?) "
            "ON CONFLICT(guild_id, user_id, key) DO UPDATE SET value = value + excluded.value",
            (guild_id, user_id, key, amount))

    async def counters(self, guild_id: int, user_id: int) -> dict[str, int]:
        rows = await self.db.fetchall("SELECT key, value FROM member_counters WHERE guild_id=? AND user_id=?",
                                      (guild_id, user_id))
        return {r["key"]: r["value"] for r in rows}

    async def stats(self, guild: discord.Guild, user_id: int) -> dict[str, int]:
        lvl = await self.db.fetchone("SELECT level, messages, xp FROM levels WHERE guild_id=? AND user_id=?",
                                     (guild.id, user_id))
        eco = await self.db.fetchone("SELECT balance, bank, streak FROM economy WHERE guild_id=? AND user_id=?",
                                     (guild.id, user_id))
        act = await self.db.fetchone("SELECT streak, best FROM activity_streaks WHERE guild_id=? AND user_id=?",
                                     (guild.id, user_id))
        inv = await self.db.fetchone(
            "SELECT COUNT(*) AS n FROM invite_joins WHERE guild_id=? AND inviter_id=? AND left_at IS NULL",
            (guild.id, user_id))
        counters = await self.counters(guild.id, user_id)
        return {
            "messages": lvl["messages"] if lvl else 0, "level": lvl["level"] if lvl else 0, "xp": lvl["xp"] if lvl else 0,
            "wealth": (eco["balance"] + eco["bank"]) if eco else 0, "balance": eco["balance"] if eco else 0,
            "bank": eco["bank"] if eco else 0, "daily_streak": eco["streak"] if eco else 0,
            "activity_streak": act["best"] if act else 0, "current_streak": act["streak"] if act else 0,
            "invites": inv["n"] if inv else 0, "quests": counters.get("quests", 0),
            "game_wins": counters.get("game_wins", 0),
        }

    # --- annonces --------------------------------------------------------------
    async def announce(self, guild: discord.Guild, channel: discord.abc.Messageable | None, embed: discord.Embed) -> None:
        cfg = gconf(guild)
        if not cfg.get("engagement", "announce", default=True):
            return
        target = guild.get_channel(int(cfg.get("engagement", "channel", default=0) or 0))
        delete_after = None
        if not isinstance(target, (discord.TextChannel, discord.Thread)):
            target, delete_after = channel, 60  # dans le salon de l'action : effacé après 1 minute
        if target is None:
            return
        try:
            await target.send(embed=embed, delete_after=delete_after)
        except (discord.HTTPException, AttributeError):
            pass

    async def reward(self, guild: discord.Guild, user_id: int, amount: int) -> int:
        if amount <= 0 or not self.economy or not gconf(guild).get("economy", "enabled", default=True):
            return 0
        await self.economy.add(guild.id, user_id, amount)
        return amount

    # --- succès ------------------------------------------------------------
    async def check_achievements(self, guild: discord.Guild, member: discord.abc.User,
                                 channel: discord.abc.Messageable | None) -> list[str]:
        if not self.enabled(guild, "achievements"):
            return []
        rows = await self.db.fetchall("SELECT achievement FROM achievements WHERE guild_id=? AND user_id=?",
                                      (guild.id, member.id))
        unlocked = newly_unlocked(await self.stats(guild, member.id), {r["achievement"] for r in rows})
        from cogs.economy import money
        for aid in unlocked:
            emoji, name, desc, _stat, _threshold, prize = ACHIEVEMENTS[aid]
            await self.db.execute(
                "INSERT OR IGNORE INTO achievements (guild_id, user_id, achievement, unlocked_at) VALUES (?,?,?,?)",
                (guild.id, member.id, aid, time.time()))
            gained = await self.reward(guild, member.id, prize)
            text = f"{member.mention} débloque le succès {emoji} **{name}** !\n*{desc}*"
            if gained:
                text += f"\nRécompense : {money(guild, gained)}"
            await self.announce(guild, channel, embeds.base("🏅 Succès débloqué", text, color=0xF1C40F, guild=guild))
        return unlocked

    # --- quêtes --------------------------------------------------------------
    def active_quests(self, guild: discord.Guild, today: date) -> list[tuple[str, str, bool]]:
        """[(période, quête, hebdo ?)] actives aujourd'hui."""
        if not self.enabled(guild, "quests"):
            return []
        cfg = gconf(guild)
        eco = bool(cfg.get("economy", "enabled", default=True))
        games = eco and bool(cfg.get("games", "enabled", default=True))
        out = [(day_key(today), q, False) for q in quests_for(guild.id, day_key(today), False, eco, games)]
        if cfg.get("engagement", "weekly_quests", default=False):  # 💎 (faux en version gratuite)
            out += [(week_key(today), q, True) for q in quests_for(guild.id, week_key(today), True, eco, games)]
        return out

    async def progress_quests(self, guild: discord.Guild, member: discord.abc.User, channel, kind: str,
                              amount: int) -> None:
        from bot.engagement_data import QUESTS
        from cogs.economy import money
        today = server_today(guild)
        for period, qid, weekly in self.active_quests(guild, today):
            if QUESTS[qid][0] != kind:
                continue
            target = quest_target(qid, weekly)
            await self.db.execute(
                "INSERT INTO quest_progress (guild_id, user_id, period, quest, progress) VALUES (?,?,?,?,?) "
                "ON CONFLICT(guild_id, user_id, period, quest) DO UPDATE SET progress = MIN(?, progress + excluded.progress)",
                (guild.id, member.id, period, qid, min(amount, target), target))
            row = await self.db.fetchone(
                "SELECT progress, done FROM quest_progress WHERE guild_id=? AND user_id=? AND period=? AND quest=?",
                (guild.id, member.id, period, qid))
            if not row or row["done"] or row["progress"] < target:
                continue
            await self.db.execute(
                "UPDATE quest_progress SET done=1 WHERE guild_id=? AND user_id=? AND period=? AND quest=?",
                (guild.id, member.id, period, qid))
            await self.bump(guild.id, member.id, "quests")
            cfg = gconf(guild)
            prize = int(cfg.get("engagement", "weekly_reward" if weekly else "quest_reward", default=0) or 0)
            gained = await self.reward(guild, member.id, prize)
            title = "🏆 Quête de la semaine terminée" if weekly else "📜 Quête terminée"
            text = f"{member.mention} a terminé : **{quest_text(qid, weekly)}**"
            if gained:
                text += f"\nRécompense : {money(guild, gained)}"
            await self.announce(guild, channel, embeds.base(title, text, color=0x2ECC71, guild=guild))

    # --- événements --------------------------------------------------------------
    @commands.Cog.listener()
    async def on_activity(self, guild: discord.Guild | None, member: discord.abc.User, channel, kind: str,
                          amount: int = 1) -> None:
        if not guild or member.bot or not self.enabled(guild):
            return
        try:
            if kind == "game_win":
                await self.bump(guild.id, member.id, "game_wins", amount)
            await self.progress_quests(guild, member, channel, kind, amount)
            await self.check_achievements(guild, member, channel)
        except Exception:
            log.exception("Activité %s de %s sur %s", kind, member.id, guild.id)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        guild = message.guild
        if guild is None or message.author.bot or not self.enabled(guild):
            return
        key = (guild.id, message.author.id)
        today = server_today(guild)
        try:
            if self.seen_today.get(key) != today.isoformat():
                self.seen_today[key] = today.isoformat()
                row = await self.db.fetchone("SELECT * FROM activity_streaks WHERE guild_id=? AND user_id=?", key)
                streak, best, changed = next_activity_streak(row["last_day"] if row else None,
                                                             row["streak"] if row else 0, row["best"] if row else 0, today)
                if changed:
                    await self.db.execute(
                        "INSERT INTO activity_streaks (guild_id, user_id, last_day, streak, best) VALUES (?,?,?,?,?) "
                        "ON CONFLICT(guild_id, user_id) DO UPDATE SET last_day=excluded.last_day, streak=excluded.streak, "
                        "best=excluded.best", (*key, today.isoformat(), streak, best))
            await self.progress_quests(guild, message.author, message.channel, "message", 1)
            if time.time() - self.last_check.get(key, 0) > CHECK_EVERY:
                self.last_check[key] = time.time()
                await self.check_achievements(guild, message.author, message.channel)
        except Exception:
            log.exception("Engagement (message) sur %s", guild.id)

    # --- commandes ------------------------------------------------------------------
    @app_commands.command(name="profil", description="Ton profil : niveau, argent, séries, badges (ou celui d'un membre)")
    @app_commands.guild_only()
    async def profile(self, interaction: discord.Interaction, membre: discord.Member | None = None) -> None:
        assert interaction.guild
        member = membre or interaction.user
        s = await self.stats(interaction.guild, member.id)
        rows = await self.db.fetchall(
            "SELECT achievement FROM achievements WHERE guild_id=? AND user_id=? ORDER BY unlocked_at",
            (interaction.guild.id, member.id))
        badges = " ".join(ACHIEVEMENTS[r["achievement"]][0] for r in rows if r["achievement"] in ACHIEVEMENTS)
        from cogs.economy import money
        embed = embeds.base(f"🪪 Profil de {member.display_name}", guild=interaction.guild)
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.add_field(name="Niveau", value=f"**{s['level']}** ({s['xp']:,} XP)".replace(",", " "))
        embed.add_field(name="Messages", value=f"{s['messages']:,}".replace(",", " "))
        embed.add_field(name="Fortune", value=money(interaction.guild, s["wealth"]))
        embed.add_field(name="Série d'activité", value=f"🔥 {s['current_streak']} jour(s) (record : {s['activity_streak']})")
        embed.add_field(name="Série /daily", value=f"📅 {s['daily_streak']} jour(s)")
        embed.add_field(name="Invitations", value=str(s["invites"]))
        embed.add_field(name="Quêtes terminées", value=str(s["quests"]))
        embed.add_field(name="Parties gagnées", value=str(s["game_wins"]))
        embed.add_field(name=f"Badges ({len(rows)}/{len(ACHIEVEMENTS)})", value=badges or "Aucun pour l'instant", inline=False)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="succes", description="Liste des succès : débloqués et à débloquer")
    @app_commands.guild_only()
    async def achievements(self, interaction: discord.Interaction, membre: discord.Member | None = None) -> None:
        assert interaction.guild
        if not self.enabled(interaction.guild, "achievements"):
            await reply_error(interaction, "Les succès sont désactivés sur ce serveur.")
            return
        member = membre or interaction.user
        s = await self.stats(interaction.guild, member.id)
        rows = await self.db.fetchall("SELECT achievement FROM achievements WHERE guild_id=? AND user_id=?",
                                      (interaction.guild.id, member.id))
        have = {r["achievement"] for r in rows}
        lines = []
        for aid, (emoji, name, desc, stat, threshold, _prize) in ACHIEVEMENTS.items():
            if aid in have:
                lines.append(f"{emoji} **{name}** — {desc} ✅")
            else:
                value = min(s.get(stat, 0), threshold)
                bar = progress_bar(value, threshold)
                lines.append(f"🔒 **{name}** — {desc}\n`{bar}` {value:,}/{threshold:,}".replace(",", " "))
        from bot.pagination import Paginator, chunk
        pages = [embeds.base(f"🏅 Succès de {member.display_name} ({len(have)}/{len(ACHIEVEMENTS)})", "\n".join(group),
                             guild=interaction.guild) for group in chunk(lines, 10)]
        await Paginator.send(interaction, pages)

    @app_commands.command(name="quetes", description="Tes quêtes du jour (et de la semaine 💎) avec ta progression")
    @app_commands.guild_only()
    async def quests(self, interaction: discord.Interaction) -> None:
        guild = interaction.guild
        assert guild
        if not self.enabled(guild, "quests"):
            await reply_error(interaction, "Les quêtes sont désactivées sur ce serveur.")
            return
        today = server_today(guild)
        active = self.active_quests(guild, today)
        rows = await self.db.fetchall(
            "SELECT period, quest, progress, done FROM quest_progress WHERE guild_id=? AND user_id=? AND period IN (?,?)",
            (guild.id, interaction.user.id, day_key(today), week_key(today)))
        state = {(r["period"], r["quest"]): r for r in rows}
        cfg = gconf(guild)
        from cogs.economy import money
        embed = embeds.base("📜 Tes quêtes", guild=guild)
        for weekly in (False, True):
            lines = []
            for period, qid, is_weekly in active:
                if is_weekly != weekly:
                    continue
                row = state.get((period, qid))
                target = quest_target(qid, weekly)
                value = row["progress"] if row else 0
                mark = "✅" if row and row["done"] else "▫️"
                lines.append(f"{mark} {quest_text(qid, weekly)}\n`{progress_bar(value, target)}` {value}/{target}")
            if not lines:
                continue
            prize = int(cfg.get("engagement", "weekly_reward" if weekly else "quest_reward", default=0) or 0)
            reset = next_reset(today, weekly)
            ts = int(datetime(reset.year, reset.month, reset.day).timestamp())
            title = "🏆 Quête de la semaine" if weekly else "☀️ Quêtes du jour"
            embed.add_field(name=f"{title} · {money(guild, prize)} chacune",
                            value="\n".join(lines) + f"\nNouvelles quêtes <t:{ts}:R>", inline=False)
        if not cfg.get("engagement", "weekly_quests", default=False):
            embed.set_footer(text="💎 Premium : une quête de la semaine avec une grosse récompense.")
        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Engagement(bot))
