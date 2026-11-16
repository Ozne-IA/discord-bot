"""Sécurité : anti-raid (âge du compte, vague d'arrivées, lockdown) et anti-nuke (audit log)."""
from __future__ import annotations

import logging
import time
from collections import defaultdict, deque

import discord
from discord import app_commands
from discord.ext import commands

from bot import embeds
from bot.config import gconf, store
from bot.utils import send_log

log = logging.getLogger("cogs.security")


class SlidingCounter:
    """Compte des événements dans une fenêtre glissante."""

    def __init__(self) -> None:
        self.events: dict[tuple, deque[float]] = defaultdict(deque)

    def hit(self, key: tuple, window: float) -> int:
        now = time.time()
        q = self.events[key]
        q.append(now)
        while q and now - q[0] > window:
            q.popleft()
        return len(q)


class Security(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.joins = SlidingCounter()
        self.nuke = SlidingCounter()
        self.lockdown_until: dict[int, float] = {}

    @property
    def db(self):
        return self.bot.db  # type: ignore[attr-defined]

    async def record(self, guild: discord.Guild, user_id: int | None, module: str, action: str, reason: str) -> None:
        await self.db.execute(
            "INSERT INTO security_logs (guild_id, user_id, module, action, reason, created_at) VALUES (?,?,?,?,?,?)",
            (guild.id, user_id, module, action, reason, time.time()))

    @staticmethod
    def _whitelisted(guild: discord.Guild, section: str, user_id: int) -> bool:
        return user_id in (gconf(guild).get(section, "whitelist", default=[]) or [])

    # ------------------------------------------------------------------ #
    #  Anti-raid — appelé par cogs/welcome.py à chaque arrivée
    # ------------------------------------------------------------------ #
    async def screen_join(self, member: discord.Member) -> bool:
        """Renvoie True si le membre a été expulsé/banni (le message de bienvenue est alors annulé)."""
        guild = member.guild
        cfg = gconf(guild).get("anti_raid", default={}) or {}
        if not cfg.get("enabled", True):
            return False
        if self._whitelisted(guild, "anti_raid", member.id):
            return False

        reason = None
        if time.time() < self.lockdown_until.get(guild.id, 0):
            reason = "Serveur en lockdown anti-raid"

        count = self.joins.hit((guild.id,), float(cfg.get("joins_window_seconds", 10)))
        max_joins = int(cfg.get("max_joins", 8))
        if count >= max_joins:
            reason = reason or f"Vague d'arrivées ({count} en {cfg.get('joins_window_seconds', 10)} s)"
            if cfg.get("auto_lockdown", True) and time.time() >= self.lockdown_until.get(guild.id, 0):
                self.lockdown_until[guild.id] = time.time() + 300
                await send_log(guild, embeds.error(
                    "🚨 **Raid détecté** : lockdown automatique de 5 minutes.\n"
                    "Toutes les nouvelles arrivées seront refusées. `/lockdown off` pour l'arrêter.",
                    "🚨 Anti-raid"), channel="mod_logs")

        min_age = int(cfg.get("min_account_age_days", 0))
        age_days = (discord.utils.utcnow() - member.created_at).days
        if not reason and min_age and age_days < min_age and not member.bot:
            reason = f"Compte trop récent ({age_days} j < {min_age} j)"

        if not reason:
            return False

        action = cfg.get("action", "kick")
        try:
            try:
                await member.send(embed=embeds.warning(
                    f"Tu as été retiré de **{guild.name}** par la protection anti-raid.\nRaison : {reason}"))
            except discord.HTTPException:
                pass
            if action == "ban":
                await member.ban(reason=f"Anti-raid : {reason}")
            else:
                await member.kick(reason=f"Anti-raid : {reason}")
        except discord.HTTPException as exc:
            log.warning("Anti-raid : action impossible sur %s : %s", member, exc)
            return False
        await self.record(guild, member.id, "anti_raid", action, reason)
        await send_log(guild, embeds.error(f"{member} (`{member.id}`) → **{action}**\nRaison : {reason}",
                                           "🛡️ Anti-raid"), channel="mod_logs")
        return True

    # ------------------------------------------------------------------ #
    #  Anti-nuke — on retrouve l'auteur via le journal d'audit
    # ------------------------------------------------------------------ #
    @commands.Cog.listener()
    async def on_audit_log_entry_create(self, entry: discord.AuditLogEntry) -> None:
        guild = entry.guild
        cfg = gconf(guild).get("anti_nuke", default={}) or {}
        if not cfg.get("enabled", True) or entry.user_id is None:
            return
        limits = {
            discord.AuditLogAction.channel_delete: ("max_channel_deletes", "suppressions de salons"),
            discord.AuditLogAction.role_delete: ("max_role_deletes", "suppressions de rôles"),
            discord.AuditLogAction.ban: ("max_bans", "bannissements"),
            discord.AuditLogAction.channel_create: ("max_channel_creates", "créations de salons"),
        }
        if entry.action not in limits:
            return
        key, label = limits[entry.action]
        uid = entry.user_id
        if (uid in (guild.owner_id, self.bot.user.id if self.bot.user else 0)
                or self._whitelisted(guild, "anti_nuke", uid)):
            return
        count = self.nuke.hit((guild.id, uid, entry.action), float(cfg.get("window_seconds", 10)))
        if count < int(cfg.get(key, 3)):
            return

        reason = f"Anti-nuke : {count} {label} en {cfg.get('window_seconds', 10)} s"
        member = guild.get_member(uid)
        punished = "aucune action (membre introuvable)"
        try:
            if member and member.top_role < guild.me.top_role:
                if cfg.get("action", "ban") == "ban":
                    await member.ban(reason=reason)
                    punished = "banni"
                else:
                    # Retire tous les rôles dangereux
                    removable = [r for r in member.roles if r.is_assignable()]
                    await member.remove_roles(*removable, reason=reason)
                    punished = "rôles retirés"
            elif member:
                punished = "impossible (rôle supérieur au bot)"
        except discord.HTTPException as exc:
            punished = f"échec : {exc}"
        await self.record(guild, uid, "anti_nuke", punished, reason)
        await send_log(guild, embeds.error(f"<@{uid}> → **{punished}**\n{reason}", "💥 Anti-nuke"), channel="mod_logs")
        owner = guild.owner
        if owner:
            try:
                await owner.send(embed=embeds.error(f"Sur **{guild.name}** : <@{uid}> → {punished}\n{reason}",
                                                    "💥 Alerte anti-nuke"))
            except discord.HTTPException:
                pass

    # ------------------------------------------------------------------ #
    #  Commandes
    # ------------------------------------------------------------------ #
    @app_commands.command(name="lockdown", description="Active/désactive le lockdown anti-raid (refuse les arrivées)")
    @app_commands.choices(etat=[app_commands.Choice(name="on", value="on"), app_commands.Choice(name="off", value="off")])
    @app_commands.default_permissions(administrator=True)
    @app_commands.guild_only()
    async def lockdown(self, interaction: discord.Interaction, etat: app_commands.Choice[str],
                       minutes: app_commands.Range[int, 1, 1440] = 30) -> None:
        assert interaction.guild
        if etat.value == "on":
            self.lockdown_until[interaction.guild.id] = time.time() + minutes * 60
            msg = f"🔒 Lockdown actif pendant **{minutes} min** : les nouvelles arrivées sont refusées."
        else:
            self.lockdown_until.pop(interaction.guild.id, None)
            msg = "🔓 Lockdown désactivé."
        await interaction.response.send_message(embed=embeds.success(msg))
        await send_log(interaction.guild, embeds.info(f"{interaction.user.mention} : {msg}", "🛡️ Lockdown"),
                       channel="mod_logs")

    @app_commands.command(name="whitelist", description="Ajoute/retire un utilisateur de la whitelist sécurité")
    @app_commands.default_permissions(administrator=True)
    @app_commands.guild_only()
    async def whitelist(self, interaction: discord.Interaction, utilisateur: discord.User) -> None:
        assert interaction.guild
        cfg = gconf(interaction.guild)
        raid = list(cfg.get("anti_raid", "whitelist", default=[]) or [])
        nuke = list(cfg.get("anti_nuke", "whitelist", default=[]) or [])
        if utilisateur.id in raid or utilisateur.id in nuke:
            raid = [i for i in raid if i != utilisateur.id]
            nuke = [i for i in nuke if i != utilisateur.id]
            msg = f"{utilisateur.mention} retiré de la whitelist."
        else:
            raid.append(utilisateur.id)
            nuke.append(utilisateur.id)
            msg = f"{utilisateur.mention} ajouté à la whitelist (ignoré par l'anti-raid et l'anti-nuke)."
        await store.update(self.db, interaction.guild.id,
                           {"anti_raid": {"whitelist": raid}, "anti_nuke": {"whitelist": nuke}})
        await interaction.response.send_message(embed=embeds.success(msg), ephemeral=True)

    @app_commands.command(name="security", description="État des protections du serveur")
    @app_commands.default_permissions(administrator=True)
    @app_commands.guild_only()
    async def security_status(self, interaction: discord.Interaction) -> None:
        assert interaction.guild
        cfg = gconf(interaction.guild)
        raid = cfg.get("anti_raid", default={}) or {}
        nuke = cfg.get("anti_nuke", default={}) or {}
        auto = cfg.get("automod", default={}) or {}
        locked = time.time() < self.lockdown_until.get(interaction.guild.id, 0)
        wl = set(raid.get("whitelist", []) or []) | set(nuke.get("whitelist", []) or [])
        recent = await self.db.fetchall(
            "SELECT module, action, reason, created_at FROM security_logs WHERE guild_id=? ORDER BY id DESC LIMIT 5",
            (interaction.guild.id,))
        on = lambda b: "🟢 actif" if b else "🔴 inactif"  # noqa: E731
        embed = embeds.base("🛡️ Sécurité du serveur")
        embed.add_field(name="Anti-raid", value=(
            f"{on(raid.get('enabled', True))}\nÂge min : {raid.get('min_account_age_days')} j\n"
            f"Seuil : {raid.get('max_joins')} / {raid.get('joins_window_seconds')} s\nAction : {raid.get('action')}"))
        embed.add_field(name="Anti-nuke", value=(
            f"{on(nuke.get('enabled', True))}\nSalons suppr. : {nuke.get('max_channel_deletes')}\n"
            f"Rôles suppr. : {nuke.get('max_role_deletes')}\nBans : {nuke.get('max_bans')}"))
        embed.add_field(name="Automod", value=(
            f"{on(auto.get('enabled', True))}\nInvitations : {'bloquées' if auto.get('block_invites') else 'ok'}\n"
            f"Mentions max : {auto.get('max_mentions')}\nMots interdits : {len(auto.get('banned_words', []))}"))
        embed.add_field(name="Lockdown", value="🔒 ACTIF" if locked else "non")
        embed.add_field(name="Whitelist", value=str(len(wl)))
        if recent:
            embed.add_field(name="Derniers événements", inline=False, value="\n".join(
                f"<t:{int(r['created_at'])}:R> **{r['module']}** {r['action']} — {r['reason']}" for r in recent))
        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Security(bot))
