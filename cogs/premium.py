"""Premium : statut du serveur, bouton d'abonnement, suivi des abonnements Discord, accès manuels."""
from __future__ import annotations

import logging
import time
from datetime import datetime

import discord
from discord import app_commands
from discord.ext import commands, tasks

from bot import embeds
from bot.config import store
from bot.premium import (TRIAL_KEY, how_to_subscribe, patreon_buttons, premium, sku_id, trial_days, upsell_embed,
                          upsell_view)
from bot.utils import dashboard_url

log = logging.getLogger("cogs.premium")

FEATURES = [
    "🎉 Giveaways et 📊 sondages",
    "🔐 Captcha de vérification",
    "🎙️ XP vocal, 🖼️ carte de rang en image, 📅 classements hebdo/mensuels",
    "📺 Alertes Twitch et YouTube",
    "🎨 Couleur, pied de page et tous les messages personnalisés",
    "📄 Transcripts HTML des tickets et ⭐ avis",
    "💥 Anti-nuke, 🔒 lockdown automatique et alertes au propriétaire",
]


def _fmt_expiry(ts: float | None) -> str:
    if ts is None:
        return "sans date de fin"
    return discord.utils.format_dt(datetime.fromtimestamp(ts), "D")


class TrialView(discord.ui.View):
    """Bouton « Essai gratuit » sous /premium (réservé à ceux qui gèrent le serveur)."""

    def __init__(self, cog: "Premium", with_store: bool, guild_id: int | None = None):
        super().__init__(timeout=600)
        self.cog = cog
        button = discord.ui.Button(label=f"Essai gratuit {trial_days()} jours", emoji="🎁",
                                   style=discord.ButtonStyle.success)
        button.callback = self.start
        self.add_item(button)
        if with_store and sku_id():
            self.add_item(discord.ui.Button(style=discord.ButtonStyle.premium, sku_id=sku_id()))
        elif with_store:
            for item in patreon_buttons(guild_id):
                self.add_item(item)

    async def start(self, interaction: discord.Interaction) -> None:
        assert interaction.guild
        member = interaction.user
        if not (isinstance(member, discord.Member) and member.guild_permissions.manage_guild):
            await interaction.response.send_message(
                embed=embeds.error("Seuls ceux qui ont la permission « Gérer le serveur » peuvent lancer l'essai."),
                ephemeral=True)
            return
        await self.cog.start_trial(interaction)


class Premium(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def cog_load(self) -> None:
        self.refresh.start()
        self.resync.start()

    async def cog_unload(self) -> None:
        self.refresh.cancel()
        self.resync.cancel()

    # --- abonnements Discord -------------------------------------------
    @commands.Cog.listener()
    async def on_entitlement_create(self, ent: discord.Entitlement) -> None:
        premium.apply_entitlement(ent)
        log.info("Nouvel abonnement Premium : serveur %s", ent.guild_id)
        guild = self.bot.get_guild(ent.guild_id) if ent.guild_id else None
        from cogs.ops import notify_owner
        await notify_owner(self.bot, "💎 Nouvel abonnement Premium",
                           f"**{guild.name if guild else ent.guild_id}** vient de s'abonner.", 0xF1C40F)
        if guild and guild.owner:
            try:
                await guild.owner.send(embed=embeds.success(
                    f"Merci ! **{guild.name}** est maintenant **Premium** 💎\n"
                    f"Configure les nouveautés sur le panel : {dashboard_url(guild.id) or '/dashboard'}",
                    "💎 Premium activé"))
            except discord.HTTPException:
                pass

    @commands.Cog.listener()
    async def on_entitlement_update(self, ent: discord.Entitlement) -> None:
        premium.apply_entitlement(ent)

    @commands.Cog.listener()
    async def on_entitlement_delete(self, ent: discord.Entitlement) -> None:
        premium.apply_entitlement(ent, deleted=True)

    @tasks.loop(minutes=10)
    async def refresh(self) -> None:
        # Fait expirer les accès arrivés à échéance (la config est recalculée au prochain accès).
        store.invalidate_all()
        await self.trial_reminders()

    async def trial_reminders(self) -> None:
        """Prévient le propriétaire du serveur 1 jour avant la fin de l'essai, puis à la fin."""
        if not self.bot.is_ready():
            return
        db = self.bot.db  # type: ignore[attr-defined]
        now = time.time()
        for row in await db.fetchall("SELECT guild_id, value FROM settings WHERE key=?", (TRIAL_KEY,)):
            gid, ends = row["guild_id"], float(row["value"] or 0)
            if gid in premium.subscriptions and premium._active(premium.subscriptions[gid]):
                continue  # abonné entre-temps : plus besoin de relancer
            if ends - now < 86400 and ends > now:
                step, title, text = "reminded", "⏳ Plus qu'un jour d'essai Premium", (
                    "L'essai gratuit de **{name}** se termine {when}. Pour garder les fonctions 💎, "
                    "abonne-toi avec `/premium`.")
            elif ends <= now:
                step, title, text = "ended", "💎 Essai Premium terminé", (
                    "L'essai gratuit de **{name}** est terminé : le serveur est repassé en version gratuite. "
                    "Tes réglages Premium sont gardés et reviennent dès que tu t'abonnes avec `/premium`.")
            else:
                continue
            key = f"{TRIAL_KEY}_{step}"
            guild = self.bot.get_guild(gid)
            if not guild or not guild.owner or await db.get_setting(gid, key):
                continue
            await db.set_setting(gid, key, str(now))
            when = discord.utils.format_dt(datetime.fromtimestamp(ends), "R")
            embed = embeds.base(title, text.format(name=guild.name, when=when), color=0xF1C40F)
            view = upsell_view(gid)
            try:
                await guild.owner.send(embed=embed, **({"view": view} if view else {}))
            except discord.HTTPException:
                pass

    async def start_trial(self, interaction: discord.Interaction) -> None:
        assert interaction.guild
        try:
            ends = await premium.start_trial(self.bot.db, interaction.guild.id, interaction.user.id)  # type: ignore[attr-defined]
        except ValueError as exc:
            await interaction.response.send_message(embed=embeds.error(str(exc)), ephemeral=True)
            return
        log.info("Essai Premium démarré : serveur %s par %s", interaction.guild.id, interaction.user.id)
        url = dashboard_url(interaction.guild.id)
        await interaction.response.send_message(embed=embeds.success(
            f"🎁 **{interaction.guild.name}** est Premium jusqu'au {_fmt_expiry(ends)} !\n"
            "Toutes les fonctions 💎 sont débloquées. Tu seras prévenu un jour avant la fin."
            + (f"\nConfigure-les sur le panel ➜ {url}" if url else ""), "💎 Essai gratuit activé"))
        from cogs.ops import notify_owner
        await notify_owner(self.bot, "🎁 Essai Premium démarré",
                           f"**{interaction.guild.name}** (`{interaction.guild.id}`) · "
                           f"{interaction.guild.member_count} membres", 0xF1C40F)

    @tasks.loop(hours=6)
    async def resync(self) -> None:
        """Au démarrage puis toutes les 6 h : relit les abonnements (sécurité si un événement a été manqué)."""
        await premium.sync_entitlements(self.bot)

    @resync.before_loop
    async def _before_resync(self) -> None:
        await self.bot.wait_until_ready()

    # --- commandes -----------------------------------------------------
    @app_commands.command(name="premium", description="Statut Premium de ce serveur et avantages")
    @app_commands.guild_only()
    async def premium_status(self, interaction: discord.Interaction) -> None:
        assert interaction.guild
        st = premium.status(interaction.guild.id)
        features = "\n".join(f"• {f}" for f in FEATURES)
        if st["active"]:
            source = {"subscription": "abonnement Discord", "patreon": "abonnement Patreon"}.get(st["source"],
                                                                                              "accès offert")
            embed = embeds.base("💎 Ce serveur est Premium",
                                f"Merci pour ton soutien ! ({source}, {_fmt_expiry(st['expires_at'])})\n\n{features}",
                                color=0xF1C40F)
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        embed = upsell_embed("La version complète")
        embed.description = f"Ce serveur utilise la version **gratuite**.\n\nAvec **Premium** :\n{features}"
        if not sku_id():
            embed.description += "\n\n" + how_to_subscribe()
        view = upsell_view(interaction.guild.id)
        if await premium.trial_state(self.bot.db, interaction.guild.id) == "available":  # type: ignore[attr-defined]
            embed.description += (f"\n\n🎁 **Essai gratuit de {trial_days()} jours** (tout Premium, sans "
                                  "paiement, une seule fois par serveur).")
            view = TrialView(self, with_store=True, guild_id=interaction.guild.id)
        if view:
            await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
        else:
            await interaction.response.send_message(embed=embed, ephemeral=True)

    admin = app_commands.Group(name="premium_admin", description="[Propriétaire du bot] Gérer les accès Premium",
                               default_permissions=discord.Permissions(administrator=True))

    async def _owner(self, interaction: discord.Interaction) -> bool:
        if await self.bot.is_owner(interaction.user):
            return True
        await interaction.response.send_message(embed=embeds.error("Réservé au propriétaire du bot."), ephemeral=True)
        return False

    @admin.command(name="give", description="Offre Premium à un serveur")
    @app_commands.describe(serveur_id="ID du serveur (vide = ce serveur)", jours="Durée en jours (vide = à vie)")
    async def give(self, interaction: discord.Interaction, serveur_id: str | None = None,
                   jours: app_commands.Range[int, 1, 3650] | None = None, note: str = "") -> None:
        if not await self._owner(interaction):
            return
        gid = int(serveur_id) if serveur_id and serveur_id.isdigit() else interaction.guild_id
        if not gid:
            await interaction.response.send_message(embed=embeds.error("Donne un ID de serveur."), ephemeral=True)
            return
        expires = await premium.grant(self.bot.db, gid, interaction.user.id, jours, note)  # type: ignore[attr-defined]
        guild = self.bot.get_guild(gid)
        await interaction.response.send_message(embed=embeds.success(
            f"Premium accordé à **{guild.name if guild else gid}** ({_fmt_expiry(expires)})."), ephemeral=True)

    @admin.command(name="remove", description="Retire le Premium offert à un serveur")
    async def remove(self, interaction: discord.Interaction, serveur_id: str | None = None) -> None:
        if not await self._owner(interaction):
            return
        gid = int(serveur_id) if serveur_id and serveur_id.isdigit() else interaction.guild_id
        await premium.revoke(self.bot.db, gid)  # type: ignore[arg-type, attr-defined]
        await interaction.response.send_message(embed=embeds.success(f"Accès Premium manuel retiré ({gid})."),
                                                ephemeral=True)

    @admin.command(name="list", description="Liste des serveurs Premium")
    async def list_(self, interaction: discord.Interaction) -> None:
        if not await self._owner(interaction):
            return
        lines = []
        for gid, ends in premium.subscriptions.items():
            g = self.bot.get_guild(gid)
            lines.append(f"💳 {g.name if g else gid} — abonnement, {_fmt_expiry(ends)}")
        for gid, ends in premium.grants.items():
            g = self.bot.get_guild(gid)
            state = "" if premium._active(ends) else " (expiré)"
            lines.append(f"🎁 {g.name if g else gid} — offert, {_fmt_expiry(ends)}{state}")
        await interaction.response.send_message(
            embed=embeds.info("\n".join(lines) or "Aucun serveur Premium pour l'instant.", "💎 Serveurs Premium"),
            ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Premium(bot))
