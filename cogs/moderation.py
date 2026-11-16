"""Modération : warn + escalade, mute, kick, ban, tempban, purge, lock, slowmode, notes, casier."""
from __future__ import annotations

import logging
import time
from datetime import timedelta

import discord
from discord import app_commands
from discord.ext import commands, tasks

from bot import embeds
from bot.config import gconf
from bot.pagination import Paginator, chunk
from bot.utils import can_act_on, format_duration, parse_duration, reply_error, send_log

log = logging.getLogger("cogs.moderation")

ACTION_ICONS = {"warn": "⚠️", "timeout": "🔇", "untimeout": "🔊", "kick": "👢", "ban": "🔨",
                "tempban": "⏳", "unban": "🕊️", "softban": "🧹"}
MAX_TIMEOUT = timedelta(days=28)


def warn_cutoff(guild: discord.Guild | int | None) -> float:
    """Date avant laquelle un avertissement est expiré (0 = jamais d'expiration)."""
    days = int(gconf(guild).get("moderation", "warn_expiry_days", default=0) or 0)
    return time.time() - days * 86400 if days > 0 else 0


class Moderation(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @property
    def db(self):
        return self.bot.db  # type: ignore[attr-defined]

    async def cog_load(self) -> None:
        self.check_tempbans.start()

    async def cog_unload(self) -> None:
        self.check_tempbans.cancel()

    # --- helpers --------------------------------------------------------
    async def add_case(self, guild: discord.Guild, user: discord.abc.User, mod: discord.abc.User,
                       action: str, reason: str) -> int:
        case_id = await self.db.execute(
            "INSERT INTO cases (guild_id, user_id, mod_id, action, reason, created_at) VALUES (?,?,?,?,?,?)",
            (guild.id, user.id, mod.id, action, reason, time.time()))
        embed = embeds.warning(
            f"**Membre** : {user.mention} (`{user.id}`)\n**Modérateur** : {mod.mention}\n**Raison** : {reason}",
            f"{ACTION_ICONS.get(action, '📝')} Cas #{case_id} — {action}")
        await send_log(guild, embed, channel="mod_logs")
        return case_id

    async def notify(self, user: discord.abc.User, guild: discord.Guild, action: str, reason: str,
                     extra: str = "") -> None:
        try:
            await user.send(embed=embeds.warning(
                f"Tu as reçu une sanction sur **{guild.name}**.\n**Type** : {action}\n**Raison** : {reason}{extra}",
                f"{ACTION_ICONS.get(action, '📝')} Sanction"))
        except discord.HTTPException:
            pass

    async def _check_target(self, interaction: discord.Interaction, target: discord.Member) -> bool:
        assert isinstance(interaction.user, discord.Member)
        problem = can_act_on(interaction.user, target)
        if problem:
            await reply_error(interaction, problem)
            return False
        return True

    async def escalate(self, member: discord.Member, warn_count: int) -> str | None:
        """Applique la sanction automatique prévue pour ce nombre d'avertissements."""
        rules = gconf(member.guild).get("moderation", "escalation", default={}) or {}
        rule = rules.get(str(warn_count))
        if not rule:
            return None
        reason = f"Escalade automatique : {warn_count} avertissements"
        me = member.guild.me
        action = rule.get("action")
        try:
            if action == "timeout":
                minutes = int(rule.get("minutes", 60))
                await member.timeout(timedelta(minutes=minutes), reason=reason)
                await self.add_case(member.guild, member, me, "timeout", f"{reason} ({minutes} min)")
                return f"🔇 Mute automatique de {minutes} min"
            if action == "kick":
                await self.notify(member, member.guild, "kick", reason)
                await member.kick(reason=reason)
                await self.add_case(member.guild, member, me, "kick", reason)
                return "👢 Expulsion automatique"
            if action == "ban":
                await self.notify(member, member.guild, "ban", reason)
                await member.ban(reason=reason, delete_message_seconds=0)
                await self.add_case(member.guild, member, me, "ban", reason)
                return "🔨 Bannissement automatique"
        except discord.HTTPException as exc:
            log.warning("Escalade impossible pour %s : %s", member, exc)
        return None

    # --- avertissements -------------------------------------------------
    @app_commands.command(name="warn", description="Avertit un membre")
    @app_commands.default_permissions(moderate_members=True)
    @app_commands.guild_only()
    async def warn(self, interaction: discord.Interaction, membre: discord.Member, raison: str) -> None:
        if not await self._check_target(interaction, membre):
            return
        assert interaction.guild
        case_id = await self.add_case(interaction.guild, membre, interaction.user, "warn", raison)
        # Seuls les avertissements actifs ET non expirés comptent pour l'escalade
        count = (await self.db.fetchone(
            "SELECT COUNT(*) AS n FROM cases WHERE guild_id=? AND user_id=? AND action='warn' AND active=1 AND created_at >= ?",
            (interaction.guild.id, membre.id, warn_cutoff(interaction.guild))))["n"]
        await self.notify(membre, interaction.guild, "warn", raison, f"\nTotal : {count} avertissement(s)")
        text = f"{membre.mention} a été averti (cas #{case_id}).\nRaison : {raison}\nTotal : **{count}**"
        escalation = await self.escalate(membre, count)
        if escalation:
            text += f"\n\n{escalation}"
        await interaction.response.send_message(embed=embeds.success(text, "⚠️ Avertissement"))

    @app_commands.command(name="unwarn", description="Annule un avertissement (par numéro de cas)")
    @app_commands.default_permissions(moderate_members=True)
    @app_commands.guild_only()
    async def unwarn(self, interaction: discord.Interaction, cas: int) -> None:
        row = await self.db.fetchone("SELECT * FROM cases WHERE id=? AND guild_id=? AND action='warn'",
                                     (cas, interaction.guild_id))
        if not row:
            await reply_error(interaction, f"Aucun avertissement #{cas}.")
            return
        await self.db.execute("UPDATE cases SET active=0 WHERE id=?", (cas,))
        await interaction.response.send_message(embed=embeds.success(f"Avertissement #{cas} annulé."))

    @app_commands.command(name="history", description="Casier d'un membre (sanctions + notes)")
    @app_commands.default_permissions(moderate_members=True)
    @app_commands.guild_only()
    async def history(self, interaction: discord.Interaction, membre: discord.User) -> None:
        cases = await self.db.fetchall(
            "SELECT * FROM cases WHERE guild_id=? AND user_id=? ORDER BY id DESC", (interaction.guild_id, membre.id))
        notes = await self.db.fetchall(
            "SELECT * FROM notes WHERE guild_id=? AND user_id=? ORDER BY id DESC", (interaction.guild_id, membre.id))
        lines = []
        cutoff = warn_cutoff(interaction.guild)
        for c in cases:
            expired = c["action"] == "warn" and c["created_at"] < cutoff
            struck = "~~" if not c["active"] or expired else ""
            suffix = " ⏳ expiré" if expired and c["active"] else ""
            lines.append(f"{struck}{ACTION_ICONS.get(c['action'], '📝')} **#{c['id']} {c['action']}** — "
                         f"<t:{int(c['created_at'])}:d> par <@{c['mod_id']}>\n{c['reason'] or '-'}{struck}{suffix}")
        for n in notes:
            lines.append(f"🗒️ **Note #{n['id']}** — <t:{int(n['created_at'])}:d> par <@{n['mod_id']}>\n{n['content']}")
        warns = sum(1 for c in cases if c["action"] == "warn" and c["active"] and c["created_at"] >= cutoff)
        pages = []
        for group in chunk(lines, 6):
            embed = embeds.base(f"📁 Casier de {membre}", "\n\n".join(group) or "Casier vierge ✨")
            embed.set_thumbnail(url=membre.display_avatar.url)
            embed.add_field(name="Avertissements actifs", value=str(warns))
            embed.add_field(name="Sanctions totales", value=str(len(cases)))
            pages.append(embed)
        await Paginator.send(interaction, pages, ephemeral=True)

    @app_commands.command(name="note", description="Ajoute une note interne (invisible pour le membre)")
    @app_commands.default_permissions(moderate_members=True)
    @app_commands.guild_only()
    async def note(self, interaction: discord.Interaction, membre: discord.User, contenu: str) -> None:
        note_id = await self.db.execute(
            "INSERT INTO notes (guild_id, user_id, mod_id, content, created_at) VALUES (?,?,?,?,?)",
            (interaction.guild_id, membre.id, interaction.user.id, contenu, time.time()))
        await interaction.response.send_message(embed=embeds.success(f"Note #{note_id} ajoutée pour {membre.mention}."),
                                                ephemeral=True)

    # --- sanctions ------------------------------------------------------
    @app_commands.command(name="mute", description="Rend un membre muet temporairement (timeout)")
    @app_commands.describe(duree="Ex : 10m, 1h, 2h30m, 7d (max 28d)")
    @app_commands.default_permissions(moderate_members=True)
    @app_commands.guild_only()
    async def mute(self, interaction: discord.Interaction, membre: discord.Member, duree: str,
                   raison: str = "Aucune raison") -> None:
        if not await self._check_target(interaction, membre):
            return
        delta = parse_duration(duree)
        if not delta or delta > MAX_TIMEOUT:
            await reply_error(interaction, "Durée invalide. Exemples : `10m`, `1h`, `2h30m`, `7d` (max 28 jours).")
            return
        await membre.timeout(delta, reason=raison)
        assert interaction.guild
        case_id = await self.add_case(interaction.guild, membre, interaction.user, "timeout",
                                      f"{raison} ({format_duration(delta)})")
        await self.notify(membre, interaction.guild, "timeout", raison, f"\nDurée : {format_duration(delta)}")
        await interaction.response.send_message(embed=embeds.success(
            f"{membre.mention} est muet pendant **{format_duration(delta)}** (cas #{case_id})."))

    @app_commands.command(name="unmute", description="Retire le mute d'un membre")
    @app_commands.default_permissions(moderate_members=True)
    @app_commands.guild_only()
    async def unmute(self, interaction: discord.Interaction, membre: discord.Member) -> None:
        await membre.timeout(None, reason=f"Unmute par {interaction.user}")
        assert interaction.guild
        await self.add_case(interaction.guild, membre, interaction.user, "untimeout", "Fin du mute")
        await interaction.response.send_message(embed=embeds.success(f"{membre.mention} peut de nouveau parler."))

    @app_commands.command(name="kick", description="Expulse un membre")
    @app_commands.default_permissions(kick_members=True)
    @app_commands.guild_only()
    async def kick(self, interaction: discord.Interaction, membre: discord.Member,
                   raison: str = "Aucune raison") -> None:
        if not await self._check_target(interaction, membre):
            return
        assert interaction.guild
        await self.notify(membre, interaction.guild, "kick", raison)
        await membre.kick(reason=raison)
        case_id = await self.add_case(interaction.guild, membre, interaction.user, "kick", raison)
        await interaction.response.send_message(embed=embeds.success(f"{membre} a été expulsé (cas #{case_id})."))

    @app_commands.command(name="ban", description="Bannit un membre (définitivement ou temporairement)")
    @app_commands.describe(duree="Laisse vide pour un ban définitif. Ex : 1d, 7d, 30d",
                           supprimer_messages="Supprimer ses messages des X derniers jours (0-7)")
    @app_commands.default_permissions(ban_members=True)
    @app_commands.guild_only()
    async def ban(self, interaction: discord.Interaction, membre: discord.User, raison: str = "Aucune raison",
                  duree: str | None = None, supprimer_messages: app_commands.Range[int, 0, 7] = 0) -> None:
        assert interaction.guild
        target = interaction.guild.get_member(membre.id)
        if target and not await self._check_target(interaction, target):
            return
        delta = parse_duration(duree) if duree else None
        if duree and not delta:
            await reply_error(interaction, "Durée invalide. Exemples : `1d`, `7d`, `12h`.")
            return
        action = "tempban" if delta else "ban"
        await self.notify(membre, interaction.guild, action, raison,
                          f"\nDurée : {format_duration(delta)}" if delta else "")
        await interaction.guild.ban(membre, reason=raison, delete_message_seconds=supprimer_messages * 86400)
        if delta:
            await self.db.execute(
                "INSERT OR REPLACE INTO tempbans (guild_id, user_id, expires_at) VALUES (?,?,?)",
                (interaction.guild.id, membre.id, time.time() + delta.total_seconds()))
        case_id = await self.add_case(interaction.guild, membre, interaction.user, action,
                                      raison + (f" ({format_duration(delta)})" if delta else ""))
        suffix = f" pour **{format_duration(delta)}**" if delta else " définitivement"
        await interaction.response.send_message(embed=embeds.success(f"{membre} a été banni{suffix} (cas #{case_id})."))

    @app_commands.command(name="softban", description="Ban + déban immédiat pour effacer les messages récents")
    @app_commands.default_permissions(ban_members=True)
    @app_commands.guild_only()
    async def softban(self, interaction: discord.Interaction, membre: discord.Member,
                      raison: str = "Nettoyage des messages") -> None:
        if not await self._check_target(interaction, membre):
            return
        assert interaction.guild
        await membre.ban(reason=f"Softban : {raison}", delete_message_seconds=7 * 86400)
        await interaction.guild.unban(membre, reason="Fin du softban")
        case_id = await self.add_case(interaction.guild, membre, interaction.user, "softban", raison)
        await interaction.response.send_message(embed=embeds.success(f"{membre} a été softban (cas #{case_id})."))

    @app_commands.command(name="unban", description="Débannit un utilisateur par son ID")
    @app_commands.default_permissions(ban_members=True)
    @app_commands.guild_only()
    async def unban(self, interaction: discord.Interaction, user_id: str, raison: str = "Aucune raison") -> None:
        assert interaction.guild
        if not user_id.isdigit():
            await reply_error(interaction, "Donne un ID numérique.")
            return
        user = discord.Object(id=int(user_id))
        try:
            await interaction.guild.unban(user, reason=raison)
        except discord.NotFound:
            await reply_error(interaction, "Cet utilisateur n'est pas banni.")
            return
        await self.db.execute("DELETE FROM tempbans WHERE guild_id=? AND user_id=?", (interaction.guild.id, int(user_id)))
        fake = await self.bot.fetch_user(int(user_id))
        await self.add_case(interaction.guild, fake, interaction.user, "unban", raison)
        await interaction.response.send_message(embed=embeds.success(f"{fake} a été débanni."))

    @tasks.loop(minutes=1)
    async def check_tempbans(self) -> None:
        rows = await self.db.fetchall("SELECT * FROM tempbans WHERE expires_at <= ?", (time.time(),))
        for row in rows:
            guild = self.bot.get_guild(row["guild_id"])
            if guild:
                try:
                    await guild.unban(discord.Object(id=row["user_id"]), reason="Fin du ban temporaire")
                    await send_log(guild, embeds.info(f"<@{row['user_id']}> débanni automatiquement (fin du tempban)."),
                                   channel="mod_logs")
                except discord.HTTPException:
                    pass
            await self.db.execute("DELETE FROM tempbans WHERE guild_id=? AND user_id=?",
                                  (row["guild_id"], row["user_id"]))

    @check_tempbans.before_loop
    async def _before_tempbans(self) -> None:
        await self.bot.wait_until_ready()

    # --- salons ---------------------------------------------------------
    @app_commands.command(name="purge", description="Supprime des messages (avec filtres optionnels)")
    @app_commands.describe(nombre="Nombre de messages à analyser (1-100)", membre="Uniquement ce membre",
                           bots="Uniquement les bots", contient="Uniquement les messages contenant ce texte")
    @app_commands.default_permissions(manage_messages=True)
    @app_commands.guild_only()
    async def purge(self, interaction: discord.Interaction, nombre: app_commands.Range[int, 1, 100],
                    membre: discord.Member | None = None, bots: bool = False, contient: str | None = None) -> None:
        def check(m: discord.Message) -> bool:
            if membre and m.author.id != membre.id:
                return False
            if bots and not m.author.bot:
                return False
            if contient and contient.lower() not in m.content.lower():
                return False
            return True

        await interaction.response.defer(ephemeral=True)
        assert isinstance(interaction.channel, discord.TextChannel)
        deleted = await interaction.channel.purge(limit=nombre, check=check)
        await interaction.followup.send(embed=embeds.success(f"🧹 {len(deleted)} message(s) supprimé(s)."), ephemeral=True)
        assert interaction.guild
        await send_log(interaction.guild, embeds.info(
            f"{interaction.user.mention} a supprimé {len(deleted)} messages dans {interaction.channel.mention}",
            "🧹 Purge"), channel="mod_logs")

    @app_commands.command(name="slowmode", description="Définit le mode lent du salon (0 pour désactiver)")
    @app_commands.default_permissions(manage_channels=True)
    @app_commands.guild_only()
    async def slowmode(self, interaction: discord.Interaction, secondes: app_commands.Range[int, 0, 21600]) -> None:
        assert isinstance(interaction.channel, discord.TextChannel)
        await interaction.channel.edit(slowmode_delay=secondes)
        msg = "Mode lent désactivé." if secondes == 0 else f"Mode lent : **{secondes} s**."
        await interaction.response.send_message(embed=embeds.success(msg))

    @app_commands.command(name="lock", description="Verrouille le salon (plus personne ne peut écrire)")
    @app_commands.default_permissions(manage_channels=True)
    @app_commands.guild_only()
    async def lock(self, interaction: discord.Interaction, raison: str = "Aucune raison") -> None:
        assert isinstance(interaction.channel, discord.TextChannel) and interaction.guild
        await interaction.channel.set_permissions(interaction.guild.default_role, send_messages=False, reason=raison)
        await interaction.response.send_message(embed=embeds.warning(f"🔒 Salon verrouillé.\nRaison : {raison}"))

    @app_commands.command(name="unlock", description="Déverrouille le salon")
    @app_commands.default_permissions(manage_channels=True)
    @app_commands.guild_only()
    async def unlock(self, interaction: discord.Interaction) -> None:
        assert isinstance(interaction.channel, discord.TextChannel) and interaction.guild
        await interaction.channel.set_permissions(interaction.guild.default_role, send_messages=None)
        await interaction.response.send_message(embed=embeds.success("🔓 Salon déverrouillé."))

    @app_commands.command(name="modstats", description="Activité du staff : sanctions, tickets pris en charge, notes")
    @app_commands.describe(periode="Période analysée")
    @app_commands.choices(periode=[app_commands.Choice(name="7 derniers jours", value="7"),
                                   app_commands.Choice(name="30 derniers jours", value="30"),
                                   app_commands.Choice(name="90 derniers jours", value="90"),
                                   app_commands.Choice(name="Depuis le début", value="all")])
    @app_commands.default_permissions(moderate_members=True)
    @app_commands.guild_only()
    async def modstats(self, interaction: discord.Interaction,
                       periode: app_commands.Choice[str] | None = None) -> None:
        from bot.staff import PERIODS, build_staff_stats
        days = PERIODS.get(periode.value if periode else "30", 30)
        since = time.time() - days * 86400 if days else 0
        rows = await build_staff_stats(self.db, interaction.guild_id or 0, since)
        lines = []
        for r in rows[:15]:
            detail = " · ".join(f"{ACTION_ICONS.get(a, '📝')} {n}" for a, n in sorted(r["actions"].items(), key=lambda x: -x[1]))
            extra = []
            if r["tickets"]:
                extra.append(f"🎫 {r['tickets']} ticket(s)")
            if r["notes"]:
                extra.append(f"🗒️ {r['notes']} note(s)")
            lines.append(f"<@{r['user_id']}> — **{r['total']}**\n" + " · ".join(x for x in [detail, *extra] if x))
        label = periode.name if periode else "30 derniers jours"
        embed = embeds.base(f"📊 Activité du staff ({label})", "\n\n".join(lines) or "Aucune activité sur cette période.")
        embed.set_footer(text="Le détail est aussi dans le panel, onglet Statistiques.")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="unnote", description="Supprime une note interne (par son numéro)")
    @app_commands.default_permissions(moderate_members=True)
    @app_commands.guild_only()
    async def unnote(self, interaction: discord.Interaction, numero: int) -> None:
        row = await self.db.fetchone("SELECT * FROM notes WHERE id=? AND guild_id=?", (numero, interaction.guild_id))
        if not row:
            await interaction.response.send_message(embed=embeds.error(f"Note #{numero} introuvable sur ce serveur."),
                                                    ephemeral=True)
            return
        await self.db.execute("DELETE FROM notes WHERE id=?", (numero,))
        await interaction.response.send_message(embed=embeds.success(f"Note #{numero} supprimée."), ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Moderation(bot))
