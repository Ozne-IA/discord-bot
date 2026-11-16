"""Admin & utilitaires : /help, /dashboard, /ping, infos, diagnostic, et commandes réservées au propriétaire du bot."""
from __future__ import annotations

import asyncio
import io
import logging
import platform
import time
from datetime import datetime
from pathlib import Path

import discord
from discord import app_commands
from discord.ext import commands

from bot import backups, diagnostic, embeds
from bot.db import PENDING_RESTORE, validate_backup
from bot.utils import dashboard_url

ROOT = Path(__file__).resolve().parent.parent
log = logging.getLogger("bot.admin")
ICONS = {"ok": "✅", "warn": "⚠️", "error": "❌"}

HELP_SECTIONS = {
    "🌐 Configuration": ["/dashboard", "/check_config"],
    "🚪 Accueil & vérification": ["/setup_verify", "/setup_notifications", "/welcome_test"],
    "🎫 Tickets": ["/setup_ticket", "/ticket add", "/ticket remove", "/ticket priority", "/ticket close",
                  "/ticket stats"],
    "📈 Niveaux": ["/rank", "/leaderboard", "/xp add", "/xp remove", "/xp reset"],
    "🔨 Modération": ["/warn", "/unwarn", "/history", "/note", "/mute", "/unmute", "/kick", "/ban",
                      "/softban", "/unban", "/purge", "/slowmode", "/lock", "/unlock", "/modstats"],
    "🛡️ Sécurité": ["/security", "/lockdown", "/whitelist"],
    "💎 Premium": ["/premium", "/giveaway start", "/giveaway end", "/giveaway reroll", "/giveaway list",
                  "/sondage creer", "/sondage fin", "/leaderboard periode:semaine|mois"],
    "ℹ️ Infos": ["/help", "/invite", "/vote", "/mes-donnees voir", "/mes-donnees effacer", "/ping", "/botinfo",
                "/serverinfo", "/userinfo"],
}


def invite_url(bot: commands.Bot) -> str:
    return discord.utils.oauth_url(bot.application_id or 0, permissions=discord.Permissions(administrator=True),
                                   scopes=("bot", "applications.commands"))


class Admin(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.started = time.time()

    async def _owner_only(self, interaction: discord.Interaction) -> bool:
        if await self.bot.is_owner(interaction.user):
            return True
        await interaction.response.send_message(embed=embeds.error("Commande réservée au propriétaire du bot."),
                                                ephemeral=True)
        return False

    @app_commands.command(name="help", description="Liste de toutes les commandes")
    async def help(self, interaction: discord.Interaction) -> None:
        url = dashboard_url(interaction.guild_id)
        embed = embeds.base("📖 Aide", (f"⚙️ **Tout se configure sur le panel web :** {url}\n\n" if url else "")
                            + "Les commandes de staff ne sont visibles que si tu as la permission.")
        for section, cmds in HELP_SECTIONS.items():
            embed.add_field(name=section, value=" ".join(f"`{c}`" for c in cmds), inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="dashboard", description="Lien du panel web pour configurer le bot")
    async def dashboard(self, interaction: discord.Interaction) -> None:
        url = dashboard_url(interaction.guild_id)
        if not url:
            await interaction.response.send_message(
                embed=embeds.error("Le panel web n'est pas activé sur ce bot (PUBLIC_URL manquant)."), ephemeral=True)
            return
        view = discord.ui.View()
        view.add_item(discord.ui.Button(label="Ouvrir le panel", url=url, emoji="⚙️"))
        await interaction.response.send_message(
            embed=embeds.info("Connecte-toi avec Discord pour configurer ce serveur.", "⚙️ Panel web"),
            view=view, ephemeral=True)

    @app_commands.command(name="invite", description="Lien pour ajouter le bot sur un autre serveur")
    async def invite(self, interaction: discord.Interaction) -> None:
        view = discord.ui.View()
        view.add_item(discord.ui.Button(label="Ajouter le bot", url=invite_url(self.bot), emoji="➕"))
        await interaction.response.send_message(embed=embeds.info("Merci de partager le bot ! 💙"), view=view,
                                                ephemeral=True)

    @app_commands.command(name="ping", description="Latence du bot")
    async def ping(self, interaction: discord.Interaction) -> None:
        start = time.perf_counter()
        await interaction.response.send_message(embed=embeds.info("🏓 Pong…"), ephemeral=True)
        api = (time.perf_counter() - start) * 1000
        await interaction.edit_original_response(embed=embeds.info(
            f"🏓 Gateway : **{self.bot.latency * 1000:.0f} ms**\n📡 API : **{api:.0f} ms**"))

    @app_commands.command(name="botinfo", description="Informations sur le bot")
    async def botinfo(self, interaction: discord.Interaction) -> None:
        uptime = int(time.time() - self.started)
        h, rem = divmod(uptime, 3600)
        embed = embeds.base(f"🤖 {self.bot.user.name if self.bot.user else 'Bot'}")
        embed.add_field(name="Version", value=getattr(self.bot, "version", "?"))
        embed.add_field(name="Uptime", value=f"{h} h {rem // 60} min")
        embed.add_field(name="Serveurs", value=str(len(self.bot.guilds)))
        embed.add_field(name="Membres", value=str(sum(g.member_count or 0 for g in self.bot.guilds)))
        embed.add_field(name="Python", value=platform.python_version())
        embed.add_field(name="discord.py", value=discord.__version__)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="serverinfo", description="Informations sur le serveur")
    @app_commands.guild_only()
    async def serverinfo(self, interaction: discord.Interaction) -> None:
        g = interaction.guild
        assert g
        embed = embeds.base(f"🏠 {g.name}", guild=g)
        if g.icon:
            embed.set_thumbnail(url=g.icon.url)
        embed.add_field(name="Propriétaire", value=f"<@{g.owner_id}>")
        embed.add_field(name="Créé", value=discord.utils.format_dt(g.created_at, "R"))
        embed.add_field(name="Membres", value=str(g.member_count))
        embed.add_field(name="Salons", value=str(len(g.channels)))
        embed.add_field(name="Rôles", value=str(len(g.roles)))
        embed.add_field(name="Boosts", value=f"{g.premium_subscription_count} (niveau {g.premium_tier})")
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="userinfo", description="Informations sur un membre")
    @app_commands.guild_only()
    async def userinfo(self, interaction: discord.Interaction, membre: discord.Member | None = None) -> None:
        m = membre or interaction.user
        assert isinstance(m, discord.Member)
        embed = embeds.base(f"👤 {m}", guild=m.guild)
        embed.set_thumbnail(url=m.display_avatar.url)
        embed.add_field(name="ID", value=str(m.id))
        embed.add_field(name="Compte créé", value=discord.utils.format_dt(m.created_at, "R"))
        if m.joined_at:
            embed.add_field(name="Arrivé", value=discord.utils.format_dt(m.joined_at, "R"))
        roles = [r.mention for r in reversed(m.roles) if r != m.guild.default_role]
        embed.add_field(name=f"Rôles ({len(roles)})", value=" ".join(roles[:20]) or "aucun", inline=False)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="check_config", description="Vérifie que les salons, rôles et permissions sont OK")
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.guild_only()
    async def check_config(self, interaction: discord.Interaction) -> None:
        assert interaction.guild
        results = diagnostic.run(interaction.guild)
        text = "\n".join(f"{ICONS[r['status']]} {r['text']}" for r in results)
        url = dashboard_url(interaction.guild_id)
        if url:
            text += f"\n\n➡️ Corrige tout ça sur le panel : {url}"
        await interaction.response.send_message(embed=embeds.base("🩺 Diagnostic", text[:4000]), ephemeral=True)

    # --- propriétaire du bot uniquement --------------------------------
    @app_commands.command(name="backup", description="[Propriétaire du bot] Sauvegarde de la base de données")
    @app_commands.default_permissions(administrator=True)
    async def backup(self, interaction: discord.Interaction) -> None:
        # La base contient les données de TOUS les serveurs : réservé au propriétaire du bot.
        if not await self._owner_only(interaction):
            return
        await interaction.response.defer(ephemeral=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        folder = Path(self.bot.db.path).parent / "backups"  # type: ignore[attr-defined]
        raw = folder / f"bot_{stamp}.db"
        await self.bot.db.backup_to(raw)  # type: ignore[attr-defined]
        target = raw.with_suffix(".db.gz")  # compressée : environ 5 fois plus petite
        await asyncio.to_thread(backups.compress, raw, target)
        raw.unlink(missing_ok=True)
        data = target.read_bytes()
        if len(data) > backups.env_int("BACKUP_UPLOAD_MB", 8, 1, 500) * 1024 * 1024:
            await interaction.followup.send(embed=embeds.success(f"Sauvegarde créée : `{target.name}` "
                                                                 "(trop lourde pour Discord)."), ephemeral=True)
            return
        await interaction.followup.send(embed=embeds.success("📦 Sauvegarde de la base de données"),
                                        file=discord.File(io.BytesIO(data), filename=target.name), ephemeral=True)

    @app_commands.command(name="restore", description="[Propriétaire du bot] Remplace la base par une sauvegarde")
    @app_commands.describe(fichier="Fichier .db ou .db.gz obtenu avec /backup ou la sauvegarde automatique")
    @app_commands.default_permissions(administrator=True)
    async def restore(self, interaction: discord.Interaction, fichier: discord.Attachment) -> None:
        # Sert surtout à déménager le bot (PC → Railway) : la base de TOUS les serveurs est remplacée.
        if not await self._owner_only(interaction):
            return
        if fichier.size > 100 * 1024 * 1024:
            await interaction.response.send_message(embed=embeds.error("Fichier trop lourd (100 Mo maximum)."),
                                                    ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        db_path = Path(self.bot.db.path)  # type: ignore[attr-defined]
        tmp = db_path.parent / (PENDING_RESTORE + ".tmp")
        try:
            content = backups.maybe_decompress(await fichier.read())
        except ValueError as exc:
            await interaction.followup.send(embed=embeds.error(str(exc)), ephemeral=True)
            return
        tmp.write_bytes(content)
        error = await asyncio.to_thread(validate_backup, tmp)
        if error:
            tmp.unlink(missing_ok=True)
            await interaction.followup.send(embed=embeds.error(error), ephemeral=True)
            return
        tmp.replace(db_path.parent / PENDING_RESTORE)
        await interaction.followup.send(embed=embeds.success(
            "Sauvegarde vérifiée. Le bot redémarre pour l'appliquer (environ 30 secondes). "
            "L'ancienne base est gardée dans `data/backups/`."), ephemeral=True)
        log.warning("Restauration demandée par %s : redémarrage", interaction.user)
        await asyncio.sleep(2)
        await self.bot.close()

    @app_commands.command(name="sync", description="[Propriétaire du bot] Resynchronise les commandes slash")
    @app_commands.default_permissions(administrator=True)
    async def sync(self, interaction: discord.Interaction) -> None:
        if not await self._owner_only(interaction):
            return
        await interaction.response.defer(ephemeral=True)
        count = await self.bot.sync_commands()  # type: ignore[attr-defined]
        await interaction.followup.send(embed=embeds.success(f"{count} commandes synchronisées."), ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Admin(bot))
