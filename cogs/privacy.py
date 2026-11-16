"""Ménage des données : serveurs quittés (après 30 jours), vieilles données, et /mes-donnees pour chaque membre."""
from __future__ import annotations

import io
import logging
import time

import discord
from discord import app_commands
from discord.ext import commands, tasks

from bot import embeds, privacy
from bot.config import store

log = logging.getLogger("cogs.privacy")
CLEANUP_EVERY = 24 * 3600
VACUUM_EVERY = 7 * 24 * 3600
EXPORT_COOLDOWN = 3600


class EraseView(discord.ui.View):
    def __init__(self, cog: "Privacy", user_id: int):
        super().__init__(timeout=120)
        self.cog, self.user_id = cog, user_id

    @discord.ui.button(label="Oui, tout effacer", emoji="🗑️", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message(embed=embeds.error("Ce bouton n'est pas pour toi."), ephemeral=True)
            return
        count = await privacy.erase_user(self.cog.db, self.user_id)
        log.info("Données effacées à la demande d'un membre (%d lignes)", count)
        await interaction.response.edit_message(embed=embeds.success(
            f"C'est fait : {count} élément(s) effacé(s) sur tous les serveurs."), view=None)
        self.stop()

    @discord.ui.button(label="Annuler", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await interaction.response.edit_message(embed=embeds.info("Rien n'a été effacé."), view=None)
        self.stop()


class Privacy(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.last_export: dict[int, float] = {}

    @property
    def db(self):
        return self.bot.db  # type: ignore[attr-defined]

    async def cog_load(self) -> None:
        self.cleanup.start()

    async def cog_unload(self) -> None:
        self.cleanup.cancel()

    # --- serveurs quittés / revenus ---------------------------------------------
    @commands.Cog.listener()
    async def on_guild_remove(self, guild: discord.Guild) -> None:
        await privacy.mark_left(self.db, guild.id)

    @commands.Cog.listener()
    async def on_guild_join(self, guild: discord.Guild) -> None:
        await privacy.mark_back(self.db, guild.id)

    # --- ménage quotidien --------------------------------------------------------
    async def run_cleanup(self) -> dict:
        present = {g.id for g in self.bot.guilds}
        report = {"guilds": 0, "rows": 0}
        # Sécurité : jamais d'effacement si le bot ne voit encore aucun serveur (démarrage, panne Discord)
        if present and self.bot.is_ready():
            for gid in await privacy.due_for_purge(self.db, present):
                report["rows"] += await privacy.purge_guild(self.db, gid)
                report["guilds"] += 1
                store.forget(gid)
                log.info("Données du serveur %s effacées (bot retiré depuis plus de %d jours)", gid,
                         privacy.GRACE_DAYS)
        report["rows"] += await privacy.purge_old(self.db)
        return report

    @tasks.loop(hours=6)
    async def cleanup(self) -> None:
        last = float(await self.db.get_setting(0, "last_cleanup") or 0)
        now = time.time()
        if now - last < CLEANUP_EVERY:
            return
        await self.db.set_setting(0, "last_cleanup", str(now))
        try:
            report = await self.run_cleanup()
            if now - float(await self.db.get_setting(0, "last_vacuum") or 0) >= VACUUM_EVERY:
                await self.db.set_setting(0, "last_vacuum", str(now))
                await privacy.vacuum(self.db)
        except Exception:
            log.exception("Ménage des données impossible")
            return
        log.info("Ménage des données : %d serveur(s) effacé(s), %d ligne(s) supprimée(s)",
                 report["guilds"], report["rows"])

    @cleanup.before_loop
    async def _before_cleanup(self) -> None:
        await self.bot.wait_until_ready()

    # --- /mes-donnees --------------------------------------------------------------
    group = app_commands.Group(name="mes-donnees", description="Voir ou effacer les données que le bot garde sur toi")

    @group.command(name="voir", description="Reçois un fichier avec toutes les données que le bot garde sur toi")
    async def show(self, interaction: discord.Interaction) -> None:
        now = time.time()
        if now - self.last_export.get(interaction.user.id, 0) < EXPORT_COOLDOWN:
            await interaction.response.send_message(
                embed=embeds.error("Tu as déjà demandé tes données il y a moins d'une heure."), ephemeral=True)
            return
        self.last_export[interaction.user.id] = now
        await interaction.response.defer(ephemeral=True, thinking=True)
        data = await privacy.export_user(self.db, interaction.user.id)
        count = sum(len(rows) for rows in data["data"].values())
        await interaction.followup.send(
            embed=embeds.info(f"Voici tes données ({count} élément(s), tous serveurs confondus). "
                              "Les notes internes du staff ne sont pas incluses.", "📦 Mes données"),
            file=discord.File(io.BytesIO(privacy.export_json(data)), filename="mes-donnees.json"), ephemeral=True)

    @group.command(name="effacer", description="Efface tes niveaux, ton argent, tes succès, rappels et anniversaire")
    async def erase(self, interaction: discord.Interaction) -> None:
        text = ("Cela efface **sur tous les serveurs** tes niveaux et ton XP, ton argent et tes objets, tes succès et "
                "quêtes, tes séries, ton anniversaire, tes rappels, tes participations (giveaways, sondages, événements) "
                "et tes votes.\n\n"
                "Les sanctions, tickets et signalements sont gardés (ils servent à la modération des serveurs). "
                "**C'est définitif.**")
        await interaction.response.send_message(embed=embeds.warning(text, "🗑️ Effacer mes données"),
                                                view=EraseView(self, interaction.user.id), ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Privacy(bot))
