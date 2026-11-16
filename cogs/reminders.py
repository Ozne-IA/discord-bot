"""Rappels et anniversaires.
Rappels : /rappel (3 actifs en gratuit, 25 en 💎 Premium), envoyés en message privé.
Anniversaires : annonce automatique le jour J (gratuit) ; 💎 rôle « anniversaire » 24 h et message personnalisé."""
from __future__ import annotations

import calendar
import logging
import time
from datetime import date, datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import discord
from discord import app_commands
from discord.ext import commands, tasks

from bot import embeds
from bot.config import gconf
from bot.i18n import tr
from bot.premium import is_premium
from bot.translate import use_language
from bot.utils import fill_template, format_duration, parse_duration, reply_error

log = logging.getLogger("cogs.reminders")
FREE_REMINDERS = 3
PREMIUM_REMINDERS = 25
MONTHS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre",
          "novembre", "décembre"]


def local_today(tz_name: str) -> date:
    try:
        return datetime.now(ZoneInfo(tz_name or "Europe/Paris")).date()
    except (ZoneInfoNotFoundError, ValueError):
        return datetime.now(ZoneInfo("Europe/Paris")).date()


def birthday_matches(day: int, month: int, today: date) -> bool:
    """Le 29 février est fêté le 28 février les années non bissextiles."""
    if (day, month) == (today.day, today.month):
        return True
    return (day, month) == (29, 2) and today == date(today.year, 2, 28) and not calendar.isleap(today.year)


def days_until(day: int, month: int, today: date) -> int:
    year = today.year
    for y in (year, year + 1):
        d = 28 if (day, month) == (29, 2) and not calendar.isleap(y) else day
        target = date(y, month, d)
        if target >= today:
            return (target - today).days
    return 365


class Reminders(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @property
    def db(self):
        return self.bot.db  # type: ignore[attr-defined]

    async def cog_load(self) -> None:
        self.deliver.start()
        self.birthday_check.start()

    async def cog_unload(self) -> None:
        self.deliver.cancel()
        self.birthday_check.cancel()

    # ------------------------------------------------------------------ rappels
    rappel = app_commands.Group(name="rappel", description="Rappels personnels")

    @rappel.command(name="ajouter", description="Programme un rappel (ex : 10m, 2h, 1d)")
    @app_commands.describe(dans="Dans combien de temps (ex : 10m, 1h30m, 2d)", texte="De quoi te rappeler",
                           ici="Si tes messages privés sont fermés, te le rappeler dans ce salon")
    async def add(self, interaction: discord.Interaction, dans: str, texte: app_commands.Range[str, 1, 500],
                  ici: bool = True) -> None:
        if interaction.guild and not gconf(interaction.guild).get("reminders", "enabled", default=True):
            await reply_error(interaction, "Les rappels sont désactivés sur ce serveur.")
            return
        delta = parse_duration(dans)
        if not delta or delta.days > 365:
            await reply_error(interaction, "Durée invalide (max 1 an). Exemples : `10m`, `1h30m`, `2d`.")
            return
        limit = PREMIUM_REMINDERS if is_premium(interaction.guild_id) else FREE_REMINDERS
        count = await self.db.fetchone("SELECT COUNT(*) AS n FROM reminders WHERE user_id=?", (interaction.user.id,))
        if count["n"] >= limit:
            msg = f"Tu as déjà {count['n']} rappel(s) actif(s) (maximum {limit})."
            if limit == FREE_REMINDERS:
                msg += f" Les serveurs 💎 Premium en permettent {PREMIUM_REMINDERS}."
            await reply_error(interaction, msg)
            return
        at = time.time() + delta.total_seconds()
        rid = await self.db.execute(
            "INSERT INTO reminders (user_id, guild_id, channel_id, remind_at, text, created_at) VALUES (?,?,?,?,?,?)",
            (interaction.user.id, interaction.guild_id, interaction.channel_id if ici else None, at, texte, time.time()))
        await interaction.response.send_message(embed=embeds.success(
            f"Je te rappellerai <t:{int(at)}:R> (<t:{int(at)}:f>) :\n> {texte}\n\nRappel n°{rid}.", "⏰ Rappel programmé"),
            ephemeral=True)

    @rappel.command(name="liste", description="Tes rappels en attente")
    async def list_(self, interaction: discord.Interaction) -> None:
        rows = await self.db.fetchall("SELECT * FROM reminders WHERE user_id=? ORDER BY remind_at",
                                      (interaction.user.id,))
        text = "\n".join(f"`#{r['id']}` <t:{int(r['remind_at'])}:R> — {r['text'][:80]}" for r in rows) \
            or "Aucun rappel en attente."
        await interaction.response.send_message(embed=embeds.info(text, "⏰ Tes rappels"), ephemeral=True)

    @rappel.command(name="supprimer", description="Supprime un de tes rappels")
    async def delete(self, interaction: discord.Interaction, numero: int) -> None:
        before = self.db.conn.total_changes
        await self.db.execute("DELETE FROM reminders WHERE id=? AND user_id=?", (numero, interaction.user.id))
        if self.db.conn.total_changes == before:
            await reply_error(interaction, "Rappel introuvable (vérifie le numéro avec `/rappel liste`).")
            return
        await interaction.response.send_message(embed=embeds.success(f"Rappel n°{numero} supprimé."), ephemeral=True)

    @tasks.loop(seconds=20)
    async def deliver(self) -> None:
        rows = await self.db.fetchall("SELECT * FROM reminders WHERE remind_at <= ? ORDER BY remind_at LIMIT 50",
                                      (time.time(),))
        for r in rows:
            await self.db.execute("DELETE FROM reminders WHERE id=?", (r["id"],))
            ago = format_duration_from(r["created_at"])
            embed = embeds.info(f"{r['text']}\n\n*Programmé il y a {ago}.*", "⏰ Rappel")
            delivered = False
            try:
                user = self.bot.get_user(r["user_id"]) or await self.bot.fetch_user(r["user_id"])
                with use_language(r["guild_id"]):  # message privé : langue du serveur où le rappel a été créé
                    await user.send(embed=embed)
                delivered = True
            except discord.HTTPException:
                pass
            if not delivered and r["channel_id"]:
                channel = self.bot.get_channel(r["channel_id"])
                if isinstance(channel, (discord.TextChannel, discord.Thread)):
                    try:
                        await channel.send(content=f"<@{r['user_id']}>", embed=embed,
                                           allowed_mentions=discord.AllowedMentions(users=True))
                    except discord.HTTPException:
                        log.info("Rappel %s non délivré", r["id"])

    @deliver.before_loop
    async def _before_deliver(self) -> None:
        await self.bot.wait_until_ready()

    # ------------------------------------------------------------------ anniversaires
    anniv = app_commands.Group(name="anniversaire", description="Anniversaires du serveur", guild_only=True)

    @anniv.command(name="definir", description="Enregistre ta date d'anniversaire")
    async def set_birthday(self, interaction: discord.Interaction, jour: app_commands.Range[int, 1, 31],
                           mois: app_commands.Range[int, 1, 12]) -> None:
        if jour > calendar.monthrange(2024, mois)[1]:  # 2024 : bissextile, donc le 29/02 est accepté
            await reply_error(interaction, "Cette date n'existe pas.")
            return
        await self.db.execute(
            "INSERT INTO birthdays (guild_id, user_id, day, month) VALUES (?,?,?,?) "
            "ON CONFLICT(guild_id, user_id) DO UPDATE SET day=excluded.day, month=excluded.month",
            (interaction.guild_id, interaction.user.id, jour, mois))
        await interaction.response.send_message(embed=embeds.success(
            f"Anniversaire enregistré : **{jour} {MONTHS[mois - 1]}** 🎂"), ephemeral=True)

    @anniv.command(name="retirer", description="Supprime ta date d'anniversaire")
    async def remove_birthday(self, interaction: discord.Interaction) -> None:
        await self.db.execute("DELETE FROM birthdays WHERE guild_id=? AND user_id=?",
                              (interaction.guild_id, interaction.user.id))
        await interaction.response.send_message(embed=embeds.success("Date d'anniversaire supprimée."), ephemeral=True)

    @anniv.command(name="prochains", description="Les prochains anniversaires du serveur")
    async def upcoming(self, interaction: discord.Interaction) -> None:
        rows = await self.db.fetchall("SELECT user_id, day, month FROM birthdays WHERE guild_id=?",
                                      (interaction.guild_id,))
        today = local_today(gconf(interaction.guild).get("birthdays", "timezone", default="Europe/Paris"))
        guild = interaction.guild
        assert guild
        upcoming = sorted((days_until(r["day"], r["month"], today), r) for r in rows if guild.get_member(r["user_id"]))
        lines = []
        for days, r in upcoming[:15]:
            when = "🎉 **aujourd'hui**" if days == 0 else ("demain" if days == 1 else f"dans {days} jours")
            lines.append(f"<@{r['user_id']}> — {r['day']} {MONTHS[r['month'] - 1]} ({when})")
        await interaction.response.send_message(embed=embeds.base(
            "🎂 Prochains anniversaires", "\n".join(lines) or "Personne n'a encore enregistré son anniversaire.\n"
            "Utilise `/anniversaire definir`.", guild=guild))

    @tasks.loop(minutes=10)
    async def birthday_check(self) -> None:
        for guild in self.bot.guilds:
            try:
                await self.run_birthdays(guild)
            except Exception:
                log.exception("Anniversaires du serveur %s", guild.id)

    @birthday_check.before_loop
    async def _before_birthdays(self) -> None:
        await self.bot.wait_until_ready()

    async def run_birthdays(self, guild: discord.Guild) -> None:
        cfg = gconf(guild)
        if not cfg.get("birthdays", "enabled", default=True):
            return
        today = local_today(cfg.get("birthdays", "timezone", default="Europe/Paris"))
        if await self.db.get_setting(guild.id, "birthday_last_run") == today.isoformat():
            return  # déjà fait aujourd'hui
        await self.db.set_setting(guild.id, "birthday_last_run", today.isoformat())

        # 💎 retire le rôle « anniversaire » donné hier
        role = guild.get_role(int(cfg.get("birthdays", "role", default=0) or 0))
        previous = await self.db.get_setting(guild.id, "birthday_role_holders") or ""
        for uid in filter(None, previous.split(",")):
            member = guild.get_member(int(uid))
            if member and role and role in member.roles:
                try:
                    await member.remove_roles(role, reason="Fin de l'anniversaire")
                except discord.HTTPException:
                    pass

        rows = await self.db.fetchall("SELECT user_id, day, month FROM birthdays WHERE guild_id=?", (guild.id,))
        members = [m for r in rows if birthday_matches(r["day"], r["month"], today)
                   and (m := guild.get_member(r["user_id"])) is not None]
        holders = []
        channel = guild.get_channel(int(cfg.get("birthdays", "channel", default=0) or 0))
        template = cfg.get("birthdays", "message", default="") or "🎂 Joyeux anniversaire {mention} !"
        for member in members:
            if role and role < guild.me.top_role:
                try:
                    await member.add_roles(role, reason="Anniversaire")
                    holders.append(str(member.id))
                except discord.HTTPException:
                    pass
            if isinstance(channel, discord.TextChannel):
                try:
                    embed = embeds.base(tr(guild, "🎂 Joyeux anniversaire !"), fill_template(tr(guild, template), member),
                                        guild=guild)
                    embed.set_thumbnail(url=member.display_avatar.url)
                    await channel.send(content=member.mention, embed=embed,
                                       allowed_mentions=discord.AllowedMentions(users=True))
                except discord.HTTPException:
                    pass
        await self.db.set_setting(guild.id, "birthday_role_holders", ",".join(holders))


def format_duration_from(timestamp: float) -> str:
    from datetime import timedelta
    return format_duration(timedelta(seconds=max(1, int(time.time() - timestamp))))


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Reminders(bot))
