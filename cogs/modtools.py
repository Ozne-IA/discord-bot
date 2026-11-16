"""Modération avancée : signalements, ralenti automatique, journal des messages.

- Clic droit sur un message → Applications → « Signaler le message » : le staff reçoit le signalement dans le
  salon prévu, avec des boutons (supprimer le message, muter l'auteur 10 min, marquer comme traité).
  /signalements liste ceux en attente.
- Ralenti automatique : si un salon reçoit trop de messages en 10 secondes, le mode lent s'active quelques minutes.
- Journal des messages (option du panel) : messages modifiés / supprimés gardés 7 jours (💎 jusqu'à 30) et
  consultables dans le panel. Désactivé par défaut.
"""
from __future__ import annotations

import asyncio
import logging
import time
from collections import defaultdict, deque
from datetime import timedelta

import discord
from discord import app_commands
from discord.ext import commands, tasks

from bot import embeds
from bot.config import gconf
from bot.utils import is_staff, reply_error, send_log

log = logging.getLogger("cogs.modtools")
WINDOW = 10  # secondes (ralenti automatique)
REPORTS_PER_10_MIN = 5
MAX_LOG_DAYS = 30


def should_slow(stamps: deque, now: float, threshold: int) -> bool:
    """Garde les messages des 10 dernières secondes ; vrai si le seuil est atteint."""
    stamps.append(now)
    while stamps and now - stamps[0] > WINDOW:
        stamps.popleft()
    return threshold > 0 and len(stamps) >= threshold


class ReportModal(discord.ui.Modal, title="Signaler un message"):
    reason = discord.ui.TextInput(label="Pourquoi ? (facultatif)", style=discord.TextStyle.paragraph, max_length=500,
                                  required=False, placeholder="Insulte, spam, arnaque, contenu choquant…")

    def __init__(self, cog: "ModTools", message: discord.Message) -> None:
        super().__init__()
        self.cog, self.message = cog, message

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await self.cog.create_report(interaction, self.message, str(self.reason).strip())


class ReportButton(discord.ui.DynamicItem[discord.ui.Button], template=r"report:(?P<id>\d+):(?P<action>delete|mute|done)"):
    LOOK = {"delete": ("Supprimer le message", "🗑️", discord.ButtonStyle.danger),
            "mute": ("Muter 10 min", "🔇", discord.ButtonStyle.secondary),
            "done": ("Traité", "✅", discord.ButtonStyle.success)}

    def __init__(self, report_id: int, action: str) -> None:
        label, emoji, style = self.LOOK[action]
        super().__init__(discord.ui.Button(label=label, emoji=emoji, style=style, custom_id=f"report:{report_id}:{action}"))
        self.report_id, self.action = report_id, action

    @classmethod
    async def from_custom_id(cls, interaction, item, match):
        return cls(int(match["id"]), match["action"])

    async def callback(self, interaction: discord.Interaction) -> None:
        cog: ModTools = interaction.client.get_cog("ModTools")  # type: ignore[assignment]
        await cog.handle_report(interaction, self.report_id, self.action)


def report_view(report_id: int) -> discord.ui.View:
    view = discord.ui.View(timeout=None)
    for action in ("delete", "mute", "done"):
        view.add_item(ReportButton(report_id, action))
    return view


class ModTools(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.rates: dict[int, deque] = defaultdict(deque)
        self.slowed: set[int] = set()
        self.recent_reports: dict[tuple[int, int], deque] = defaultdict(deque)
        self.menu = app_commands.ContextMenu(name="Signaler le message", callback=self.report_menu)
        self.menu.guild_only = True

    @property
    def db(self):
        return self.bot.db  # type: ignore[attr-defined]

    async def cog_load(self) -> None:
        self.bot.tree.add_command(self.menu)
        self.bot.add_dynamic_items(ReportButton)
        self.purge_log.start()

    async def cog_unload(self) -> None:
        self.bot.tree.remove_command(self.menu.name, type=self.menu.type)
        self.purge_log.cancel()

    # ================================================================== signalements
    async def report_menu(self, interaction: discord.Interaction, message: discord.Message) -> None:
        if not gconf(interaction.guild).get("reports", "enabled", default=True):
            await reply_error(interaction, "Les signalements sont désactivés sur ce serveur.")
            return
        if message.author.bot or message.author.id == interaction.user.id:
            await reply_error(interaction, "Tu ne peux pas signaler ce message.")
            return
        await interaction.response.send_modal(ReportModal(self, message))

    def report_channel(self, guild: discord.Guild) -> discord.TextChannel | None:
        cfg = gconf(guild)
        for cid in (int(cfg.get("reports", "channel", default=0) or 0), cfg.channel_id("mod_logs"), cfg.channel_id("logs")):
            channel = guild.get_channel(cid)
            if isinstance(channel, discord.TextChannel):
                return channel
        return None

    async def create_report(self, interaction: discord.Interaction, message: discord.Message, reason: str) -> None:
        guild = interaction.guild
        assert guild
        key = (guild.id, interaction.user.id)
        stamps = self.recent_reports[key]
        now = time.time()
        while stamps and now - stamps[0] > 600:
            stamps.popleft()
        if len(stamps) >= REPORTS_PER_10_MIN:
            await reply_error(interaction, "Tu as envoyé beaucoup de signalements. Réessaie dans quelques minutes.")
            return
        already = await self.db.fetchone("SELECT id FROM reports WHERE message_id=? AND reporter_id=?",
                                         (message.id, interaction.user.id))
        if already:
            await reply_error(interaction, "Tu as déjà signalé ce message.")
            return
        channel = self.report_channel(guild)
        if channel is None:
            await reply_error(interaction, "Le staff n'a pas encore choisi de salon pour les signalements.")
            return
        stamps.append(now)
        content = message.content or ("[pièce jointe] " + " ".join(a.filename for a in message.attachments))
        rid = await self.db.execute(
            "INSERT INTO reports (guild_id, channel_id, message_id, author_id, reporter_id, reason, content, created_at) "
            "VALUES (?,?,?,?,?,?,?,?)", (guild.id, message.channel.id, message.id, message.author.id, interaction.user.id,
                                         reason, content[:1500], now))
        embed = embeds.base(f"🚩 Signalement #{rid}", content[:2000] or "—", color=0xED4245, guild=guild)
        embed.set_author(name=f"{message.author} ({message.author.id})", icon_url=message.author.display_avatar.url)
        embed.add_field(name="Salon", value=f"{message.channel.mention} · [Voir le message]({message.jump_url})")
        embed.add_field(name="Signalé par", value=interaction.user.mention)
        if reason:
            embed.add_field(name="Raison", value=reason[:1024], inline=False)
        count = (await self.db.fetchone("SELECT COUNT(*) AS n FROM reports WHERE guild_id=? AND author_id=?",
                                        (guild.id, message.author.id)))["n"]
        if count > 1:
            embed.add_field(name="Signalements contre ce membre", value=str(count))
        try:
            sent = await channel.send(embed=embed, view=report_view(rid))
            await self.db.execute("UPDATE reports SET report_message_id=? WHERE id=?", (sent.id, rid))
        except discord.HTTPException:
            pass
        await interaction.response.send_message(embed=embeds.success("Merci, ton signalement a été envoyé au staff."),
                                                ephemeral=True)

    async def handle_report(self, interaction: discord.Interaction, report_id: int, action: str) -> None:
        member = interaction.user
        if not isinstance(member, discord.Member) or not (is_staff(member) or member.guild_permissions.moderate_members):
            await reply_error(interaction, "Réservé au staff.")
            return
        row = await self.db.fetchone("SELECT * FROM reports WHERE id=? AND guild_id=?", (report_id, interaction.guild_id))
        if not row:
            await reply_error(interaction, "Signalement introuvable.")
            return
        guild = interaction.guild
        assert guild
        result = ""
        if action == "delete":
            channel = guild.get_channel(row["channel_id"])
            try:
                if isinstance(channel, (discord.TextChannel, discord.Thread)):
                    await channel.get_partial_message(row["message_id"]).delete()
                result = "🗑️ Message supprimé"
            except discord.NotFound:
                result = "🗑️ Message déjà supprimé"
            except discord.HTTPException:
                await reply_error(interaction, "Je n'ai pas pu supprimer le message (permissions ?).")
                return
        elif action == "mute":
            target = guild.get_member(row["author_id"])
            if target is None:
                await reply_error(interaction, "Ce membre n'est plus sur le serveur.")
                return
            from bot.utils import can_act_on
            if problem := can_act_on(member, target):
                await reply_error(interaction, problem)
                return
            try:
                await target.timeout(timedelta(minutes=10), reason=f"Signalement #{report_id} (par {member})")
            except discord.HTTPException:
                await reply_error(interaction, "Je n'ai pas pu muter ce membre (permissions ou rôle trop haut).")
                return
            await self.db.execute(
                "INSERT INTO cases (guild_id, user_id, mod_id, action, reason, created_at) VALUES (?,?,?,?,?,?)",
                (guild.id, target.id, member.id, "mute", f"Signalement #{report_id} : 10 min", time.time()))
            result = "🔇 Auteur muté 10 min"
        else:
            result = "✅ Traité"
        await self.db.execute("UPDATE reports SET status='done', handled_by=? WHERE id=?", (member.id, report_id))
        embed = interaction.message.embeds[0] if interaction.message and interaction.message.embeds else None
        if embed:
            embed.color = discord.Color.green()
            embed.add_field(name="Décision", value=f"{result} — {member.mention}", inline=False)
        await interaction.response.edit_message(embed=embed, view=None)

    @app_commands.command(name="signalements", description="Signalements en attente de traitement")
    @app_commands.default_permissions(moderate_members=True)
    @app_commands.guild_only()
    async def reports_list(self, interaction: discord.Interaction) -> None:
        rows = await self.db.fetchall(
            "SELECT * FROM reports WHERE guild_id=? AND status='open' ORDER BY id DESC LIMIT 20", (interaction.guild_id,))
        lines = []
        for r in rows:
            link = f"https://discord.com/channels/{r['guild_id']}/{r['channel_id']}/{r['message_id']}"
            lines.append(f"**#{r['id']}** <@{r['author_id']}> — <t:{int(r['created_at'])}:R> · [message]({link})\n"
                         f"{(r['reason'] or r['content'] or '')[:120]}")
        await interaction.response.send_message(embed=embeds.base("🚩 Signalements en attente", "\n\n".join(lines)
                                                                  or "Aucun signalement en attente 🎉"), ephemeral=True)

    # ================================================================== ralenti automatique
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        guild = message.guild
        channel = message.channel
        if guild is None or message.author.bot or not isinstance(channel, discord.TextChannel):
            return
        cfg = gconf(guild)
        if not (cfg.get("automod", "enabled", default=True) and cfg.get("automod", "auto_slowmode", default=True)):
            return
        if channel.id in self.slowed or channel.slowmode_delay:
            return
        threshold = int(cfg.get("automod", "slowmode_messages", default=15) or 0)
        if not should_slow(self.rates[channel.id], time.time(), threshold):
            return
        if not channel.permissions_for(guild.me).manage_channels:
            return
        seconds = max(1, min(21600, int(cfg.get("automod", "slowmode_seconds", default=5) or 5)))
        minutes = max(1, min(120, int(cfg.get("automod", "slowmode_minutes", default=5) or 5)))
        self.slowed.add(channel.id)
        self.rates[channel.id].clear()
        try:
            await channel.edit(slowmode_delay=seconds, reason="Ralenti automatique : trop de messages")
            await channel.send(embed=embeds.warning(
                f"🐢 Beaucoup de messages d'un coup : mode lent ({seconds} s) activé pour {minutes} minute(s)."), delete_after=60)
            await send_log(guild, embeds.warning(f"Mode lent automatique dans {channel.mention} ({seconds} s, {minutes} min).",
                                                 "🐢 Ralenti automatique"), channel="mod_logs")
        except discord.HTTPException:
            self.slowed.discard(channel.id)
            return
        self.bot.loop.create_task(self._restore(channel, seconds, minutes))

    async def _restore(self, channel: discord.TextChannel, seconds: int, minutes: int) -> None:
        await asyncio.sleep(minutes * 60)
        try:
            fresh = channel.guild.get_channel(channel.id)
            if isinstance(fresh, discord.TextChannel) and fresh.slowmode_delay == seconds:  # pas modifié à la main
                await fresh.edit(slowmode_delay=0, reason="Fin du ralenti automatique")
        except discord.HTTPException:
            pass
        finally:
            self.slowed.discard(channel.id)

    # ================================================================== journal des messages
    def log_enabled(self, guild: discord.Guild | None) -> bool:
        return bool(guild and gconf(guild).get("message_log", "enabled", default=False))

    async def store(self, message: discord.Message, action: str, before: str | None, after: str | None) -> None:
        await self.db.execute(
            "INSERT INTO message_log (guild_id, channel_id, author_id, message_id, action, before, after, created_at) "
            "VALUES (?,?,?,?,?,?,?,?)", (message.guild.id, message.channel.id, message.author.id, message.id, action,
                                         (before or "")[:1500], (after or "")[:1500], time.time()))

    @commands.Cog.listener()
    async def on_message_edit(self, before: discord.Message, after: discord.Message) -> None:
        if after.author.bot or before.content == after.content or not self.log_enabled(after.guild):
            return
        await self.store(after, "edit", before.content, after.content)

    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message) -> None:
        if message.author.bot or not self.log_enabled(message.guild):
            return
        content = message.content or " ".join(f"[{a.filename}]" for a in message.attachments)
        await self.store(message, "delete", content, None)

    @tasks.loop(hours=6)
    async def purge_log(self) -> None:
        """Les messages ne sont gardés que le temps choisi (7 jours par défaut, 30 maximum)."""
        for guild in self.bot.guilds:
            days = max(1, min(MAX_LOG_DAYS, int(gconf(guild).get("message_log", "days", default=7) or 7)))
            if not gconf(guild).get("message_log", "enabled", default=False):
                days = 0  # désactivé : on efface tout
            await self.db.execute("DELETE FROM message_log WHERE guild_id=? AND created_at < ?",
                                  (guild.id, time.time() - days * 86400))
        known = {g.id for g in self.bot.guilds}
        if known:  # serveurs quittés
            marks = ",".join("?" * len(known))
            await self.db.execute(f"DELETE FROM message_log WHERE guild_id NOT IN ({marks})", tuple(known))

    @purge_log.before_loop
    async def _before_purge(self) -> None:
        await self.bot.wait_until_ready()


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(ModTools(bot))
