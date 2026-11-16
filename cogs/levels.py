"""Niveaux : XP par message, cooldown, bonus booster, rôles de niveau, /rank, /leaderboard.
💎 Premium : XP vocal, carte de rang en image, classements de la semaine et du mois."""
from __future__ import annotations

import io
import random
import time
from datetime import date, timedelta

import discord
from discord import app_commands
from discord.ext import commands, tasks

from bot import embeds
from bot.config import gconf
from bot.i18n import tr
from bot.images import rank_card
from bot.pagination import Paginator, chunk
from bot.premium import require


def xp_for_next(level: int) -> int:
    """XP nécessaire pour passer du niveau `level` au niveau `level + 1`."""
    return 5 * level ** 2 + 50 * level + 100


def total_xp_for(level: int) -> int:
    """XP cumulée nécessaire pour atteindre `level` depuis 0."""
    return sum(xp_for_next(lvl) for lvl in range(level))


def level_from_xp(xp: int) -> tuple[int, int, int]:
    """Renvoie (niveau, xp dans le niveau, xp nécessaire pour le suivant)."""
    level = 0
    while xp >= xp_for_next(level):
        xp -= xp_for_next(level)
        level += 1
    return level, xp, xp_for_next(level)


def progress_bar(current: int, needed: int, size: int = 14) -> str:
    filled = round(size * current / needed) if needed else size
    return "▰" * filled + "▱" * (size - filled)


def period_start(period: str, today: date | None = None) -> str | None:
    """Premier jour de la période (lundi de la semaine / 1er du mois), au format AAAA-MM-JJ."""
    today = today or date.today()
    if period == "semaine":
        return (today - timedelta(days=today.weekday())).isoformat()
    if period == "mois":
        return today.replace(day=1).isoformat()
    return None


def voice_eligible(state: discord.VoiceState | None, channel_members: list[discord.Member]) -> bool:
    """Gagne de l'XP vocal : pas muet/sourd, pas seul (au moins un autre humain), pas dans le salon AFK."""
    if state is None or state.channel is None or state.afk:
        return False
    if state.self_deaf or state.deaf or state.self_mute or state.mute:
        return False
    humans = [m for m in channel_members if not m.bot]
    return len(humans) >= 2


class Levels(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @property
    def db(self):
        return self.bot.db  # type: ignore[attr-defined]

    async def cog_load(self) -> None:
        self.voice_tick.start()

    async def cog_unload(self) -> None:
        self.voice_tick.cancel()

    async def sync_level_roles(self, member: discord.Member, level: int) -> list[discord.Role]:
        """Donne tous les rôles de niveau atteints. Renvoie les rôles nouvellement ajoutés."""
        mapping = gconf(member.guild).get("roles", "level_roles", default={}) or {}
        to_add = []
        for lvl, role_id in mapping.items():
            role = member.guild.get_role(int(role_id or 0))
            if role and level >= int(lvl) and role not in member.roles:
                to_add.append(role)
        if to_add:
            try:
                await member.add_roles(*to_add, reason=f"Niveau {level} atteint")
            except discord.HTTPException:
                return []
        return to_add

    async def add_xp(self, member: discord.Member, amount: int) -> tuple[int, int]:
        """Ajoute (ou retire) de l'XP. Renvoie (ancien niveau, nouveau niveau)."""
        row = await self.db.fetchone("SELECT xp, level FROM levels WHERE guild_id=? AND user_id=?",
                                     (member.guild.id, member.id))
        old_xp = row["xp"] if row else 0
        old_level = row["level"] if row else 0
        new_xp = max(0, old_xp + amount)
        new_level = level_from_xp(new_xp)[0]
        await self.db.execute(
            "INSERT INTO levels (guild_id, user_id, xp, level, messages, last_xp) VALUES (?,?,?,?,0,0) "
            "ON CONFLICT(guild_id, user_id) DO UPDATE SET xp=excluded.xp, level=excluded.level",
            (member.guild.id, member.id, new_xp, new_level))
        if amount > 0:  # historique par jour, pour les classements hebdo / mensuels
            await self.db.execute(
                "INSERT INTO xp_daily (guild_id, user_id, day, xp) VALUES (?,?,?,?) "
                "ON CONFLICT(guild_id, user_id, day) DO UPDATE SET xp = xp + excluded.xp",
                (member.guild.id, member.id, date.today().isoformat(), amount))
        return old_level, new_level

    async def announce_level_up(self, member: discord.Member, new_level: int,
                                fallback: discord.abc.Messageable | None) -> None:
        cfg = gconf(member.guild)
        new_roles = await self.sync_level_roles(member, new_level)
        text = tr(member.guild, cfg.get("leveling", "level_up_message", default="") or "🎉 {mention} passe au niveau {level} !")
        text = (text.replace("{mention}", member.mention).replace("{level}", str(new_level))
                .replace("{name}", member.display_name))
        if new_roles:
            text += "\nNouveau rôle : " + ", ".join(r.mention for r in new_roles)
        target = member.guild.get_channel(cfg.channel_id("level_up")) or fallback
        if isinstance(target, discord.abc.Messageable):
            try:
                await target.send(embed=embeds.base(None, text, guild=member.guild),
                                  allowed_mentions=discord.AllowedMentions(users=False))
            except discord.HTTPException:
                pass

    # --- XP par message ------------------------------------------------
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if not message.guild or message.author.bot or not isinstance(message.author, discord.Member):
            return
        cfg = gconf(message.guild)
        if not cfg.get("leveling", "enabled", default=True):
            return
        if message.channel.id in (cfg.get("leveling", "ignored_channels", default=[]) or []):
            return

        cooldown = float(cfg.get("leveling", "cooldown_seconds", default=60))
        now = time.time()
        row = await self.db.fetchone("SELECT last_xp FROM levels WHERE guild_id=? AND user_id=?",
                                     (message.guild.id, message.author.id))
        # Compte le message même pendant le cooldown (stats), mais sans XP.
        if row and now - row["last_xp"] < cooldown:
            await self.db.execute("UPDATE levels SET messages = messages + 1 WHERE guild_id=? AND user_id=?",
                                  (message.guild.id, message.author.id))
            return

        xp_min = int(cfg.get("leveling", "xp_min", default=15))
        xp_max = max(xp_min, int(cfg.get("leveling", "xp_max", default=25)))
        gain = random.randint(xp_min, xp_max)
        if message.author.premium_since:
            gain = int(gain * float(cfg.get("leveling", "booster_multiplier", default=1.0)))

        old_level, new_level = await self.add_xp(message.author, gain)
        await self.db.execute(
            "UPDATE levels SET messages = messages + 1, last_xp=? WHERE guild_id=? AND user_id=?",
            (now, message.guild.id, message.author.id))
        if new_level > old_level:
            await self.announce_level_up(message.author, new_level, message.channel)

    # --- 💎 XP vocal -----------------------------------------------------
    @tasks.loop(minutes=1)
    async def voice_tick(self) -> None:
        for guild in self.bot.guilds:
            cfg = gconf(guild)
            if not (cfg.get("leveling", "enabled", default=True) and cfg.get("leveling", "voice_enabled", default=False)):
                continue
            per_minute = int(cfg.get("leveling", "voice_xp_per_minute", default=10) or 0)
            if per_minute <= 0:
                continue
            ignored = set(cfg.get("leveling", "ignored_channels", default=[]) or [])
            for channel in guild.voice_channels + guild.stage_channels:
                if channel.id in ignored or channel == guild.afk_channel:
                    continue
                for member in channel.members:
                    if member.bot or not voice_eligible(member.voice, channel.members):
                        continue
                    gain = per_minute
                    if member.premium_since:
                        gain = int(gain * float(cfg.get("leveling", "booster_multiplier", default=1.0)))
                    old_level, new_level = await self.add_xp(member, gain)
                    if new_level > old_level:
                        await self.announce_level_up(member, new_level, None)

    @voice_tick.before_loop
    async def _before_voice(self) -> None:
        await self.bot.wait_until_ready()

    # --- commandes -----------------------------------------------------
    @app_commands.command(name="rank", description="Affiche ton niveau (ou celui d'un membre)")
    @app_commands.guild_only()
    async def rank(self, interaction: discord.Interaction, membre: discord.Member | None = None) -> None:
        member = membre or interaction.user
        assert isinstance(member, discord.Member)
        row = await self.db.fetchone("SELECT xp, messages FROM levels WHERE guild_id=? AND user_id=?",
                                     (member.guild.id, member.id))
        xp = row["xp"] if row else 0
        messages = row["messages"] if row else 0
        level, current, needed = level_from_xp(xp)
        pos = await self.db.fetchone("SELECT COUNT(*) + 1 AS p FROM levels WHERE guild_id=? AND xp > ?",
                                     (member.guild.id, xp))
        cfg = gconf(member.guild)

        if cfg.get("leveling", "rank_card", default=False):  # 💎 carte en image
            await interaction.response.defer()
            try:
                avatar = await member.display_avatar.replace(size=256, format="png").read()
            except discord.HTTPException:
                avatar = None
            png = rank_card(member.display_name, avatar, level, pos["p"], current, needed, xp, messages, cfg.color)
            await interaction.followup.send(file=discord.File(io.BytesIO(png), filename="rang.png"))
            return

        embed = embeds.base(f"📈 {member.display_name}", guild=member.guild)
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.add_field(name="Niveau", value=str(level))
        embed.add_field(name="Classement", value=f"#{pos['p']}")
        embed.add_field(name="Messages", value=str(messages))
        embed.add_field(name=f"Progression ({current}/{needed} XP)", inline=False,
                        value=f"{progress_bar(current, needed)} {100 * current // needed}%")
        embed.add_field(name="XP totale", value=str(xp))
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="leaderboard", description="Classement des membres les plus actifs")
    @app_commands.describe(periode="Depuis toujours, cette semaine ou ce mois (💎 Premium pour semaine/mois)")
    @app_commands.choices(periode=[app_commands.Choice(name="Depuis toujours", value="tout"),
                                   app_commands.Choice(name="💎 Cette semaine", value="semaine"),
                                   app_commands.Choice(name="💎 Ce mois", value="mois")])
    @app_commands.guild_only()
    async def leaderboard(self, interaction: discord.Interaction,
                          periode: app_commands.Choice[str] | None = None) -> None:
        period = periode.value if periode else "tout"
        start = period_start(period)
        if start:
            if not await require(interaction, "Les classements de la semaine et du mois"):
                return
            rows = await self.db.fetchall(
                "SELECT user_id, SUM(xp) AS xp FROM xp_daily WHERE guild_id=? AND day >= ? "
                "GROUP BY user_id ORDER BY xp DESC LIMIT 100", (interaction.guild_id, start))
            title = "🏆 Classement de la semaine" if period == "semaine" else "🏆 Classement du mois"
        else:
            rows = await self.db.fetchall(
                "SELECT user_id, xp, level FROM levels WHERE guild_id=? ORDER BY xp DESC LIMIT 100",
                (interaction.guild_id,))
            title = "🏆 Classement"
        medals = {1: "🥇", 2: "🥈", 3: "🥉"}
        pages = []
        for page_index, group in enumerate(chunk(rows, 10)):
            lines = []
            for offset, r in enumerate(group, 1):
                rank = page_index * 10 + offset
                detail = f"niveau **{r['level']}** ({r['xp']} XP)" if not start else f"**{r['xp']}** XP gagnés"
                lines.append(f"{medals.get(rank, f'`#{rank}`')} <@{r['user_id']}> — {detail}")
            pages.append(embeds.base(title, "\n".join(lines) or "Personne n'a encore d'XP sur cette période.",
                                     guild=interaction.guild))
        await Paginator.send(interaction, pages)

    xp = app_commands.Group(name="xp", description="Gestion de l'XP (staff)", guild_only=True,
                            default_permissions=discord.Permissions(manage_guild=True))

    @xp.command(name="add", description="Ajoute de l'XP à un membre")
    async def xp_add(self, interaction: discord.Interaction, membre: discord.Member,
                     montant: app_commands.Range[int, 1, 1_000_000]) -> None:
        _, level = await self.add_xp(membre, montant)
        await self.sync_level_roles(membre, level)
        await interaction.response.send_message(
            embed=embeds.success(f"+{montant} XP pour {membre.mention} (niveau {level})."), ephemeral=True)

    @xp.command(name="remove", description="Retire de l'XP à un membre")
    async def xp_remove(self, interaction: discord.Interaction, membre: discord.Member,
                        montant: app_commands.Range[int, 1, 1_000_000]) -> None:
        _, level = await self.add_xp(membre, -montant)
        await interaction.response.send_message(
            embed=embeds.success(f"-{montant} XP pour {membre.mention} (niveau {level})."), ephemeral=True)

    @xp.command(name="reset", description="Remet l'XP d'un membre à zéro")
    async def xp_reset(self, interaction: discord.Interaction, membre: discord.Member) -> None:
        await self.db.execute("DELETE FROM levels WHERE guild_id=? AND user_id=?", (membre.guild.id, membre.id))
        await self.db.execute("DELETE FROM xp_daily WHERE guild_id=? AND user_id=?", (membre.guild.id, membre.id))
        await interaction.response.send_message(embed=embeds.success(f"XP de {membre.mention} remise à zéro."),
                                                ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Levels(bot))
