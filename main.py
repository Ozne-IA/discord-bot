"""Point d'entrée du bot Discord tout-en-un."""
from __future__ import annotations

import asyncio
import hashlib
import itertools
import json
import logging
import os
import signal
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

import discord
from discord import app_commands
from discord.ext import commands, tasks
from dotenv import load_dotenv

from bot import __version__, embeds
from bot.config import store
from bot.i18n import I18N_VERSION, BotTranslator
from bot.premium import premium
from bot.translate import install as install_translation
from bot.db import Database
from web.server import Dashboard

ROOT = Path(__file__).resolve().parent
COGS = [
    "ops",
    "welcome",
    "engagement",
    "events",
    "ai",
    "modtools",
    "verification",
    "roles",
    "tickets",
    "levels",
    "moderation",
    "automod",
    "security",
    "logs",
    "admin",
    "premium",
    "giveaways",
    "polls",
    "alerts",
    "economy",
    "reminders",
    "stats",
    "games",
    "tempvoice",
    "community",
    "custom",
    "modmail",
    "invites",
    "votes",
]


def setup_logging() -> None:
    (ROOT / "data").mkdir(exist_ok=True)
    fmt = logging.Formatter("%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
                            "%Y-%m-%d %H:%M:%S")
    file_handler = RotatingFileHandler(ROOT / "data" / "bot.log", maxBytes=5_000_000,
                                       backupCount=5, encoding="utf-8")
    file_handler.setFormatter(fmt)
    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(fmt)
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.handlers = [file_handler, console]
    logging.getLogger("discord.http").setLevel(logging.WARNING)


log = logging.getLogger("bot")


class AllInOneBot(commands.Bot):
    def __init__(self) -> None:
        intents = discord.Intents.default()
        intents.members = True          # arrivées / départs
        intents.message_content = True  # XP, automod, logs de messages
        super().__init__(
            command_prefix=commands.when_mentioned,
            intents=intents,
            allowed_mentions=discord.AllowedMentions(everyone=False, roles=False),
            help_command=None,
        )
        self.db = Database(os.getenv("DATABASE_PATH") or ROOT / "data" / "bot.db")
        self.version = __version__
        self.previous_shutdown_clean = True
        self.dashboard = Dashboard(self)
        self._statuses = itertools.cycle([
            lambda b: discord.CustomActivity(name=f"🌐 {len(b.guilds)} serveurs • /help"),
            lambda b: discord.CustomActivity(name=f"👥 {sum(g.member_count or 0 for g in b.guilds)} membres"),
            lambda b: discord.CustomActivity(name="⚙️ /dashboard pour me configurer"),
            lambda b: discord.CustomActivity(name="🎫 Tickets • 📈 Niveaux • 🛡️ Sécurité"),
        ])

    async def setup_hook(self) -> None:
        install_translation()  # messages traduits en anglais pour les serveurs réglés en anglais
        await self.db.connect()
        log.info("Base de données prête (schéma v%d)", self.db.version)
        # « 0 » pendant que le bot tourne, « 1 » après un arrêt propre : sinon, c'était un plantage.
        self.previous_shutdown_clean = await self.db.get_setting(0, "clean_shutdown") != "0"
        await self.db.set_setting(0, "clean_shutdown", "0")
        await store.load_all(self.db)
        await premium.load(self.db)

        for name in COGS:
            try:
                await self.load_extension(f"cogs.{name}")
                log.info("Module chargé : %s", name)
            except Exception:
                log.exception("Échec du chargement du module %s", name)

        self.tree.on_error = self.on_app_command_error
        await self.tree.set_translator(BotTranslator())  # descriptions en anglais pour les Discord en anglais
        # Le panel démarre tout de suite ; l'envoi des commandes à Discord se fait en arrière-plan
        # (Discord limite le nombre d'envois par jour : s'il fait patienter, le panel reste accessible).
        await self.dashboard.start()
        self.rotate_status.start()
        self._sync_task = asyncio.create_task(self.sync_if_changed())

    def _commands_fingerprint(self) -> str:
        payload = sorted((c.to_dict(self.tree) for c in self.tree.get_commands()), key=lambda c: c["name"])
        raw = json.dumps(payload, sort_keys=True, ensure_ascii=False) + os.getenv("DEV_GUILD_ID", "") + I18N_VERSION
        return hashlib.sha256(raw.encode()).hexdigest()

    async def sync_if_changed(self) -> None:
        """N'envoie les commandes à Discord que si elles ont changé depuis le dernier envoi."""
        try:
            fingerprint = self._commands_fingerprint()
            if await self.db.get_setting(0, "commands_fingerprint") == fingerprint:
                log.info("Commandes slash inchangées : pas de nouvel envoi à Discord")
                return
            log.info("Envoi des commandes slash à Discord…")
            await self.sync_commands()
            await self.db.set_setting(0, "commands_fingerprint", fingerprint)
        except Exception:
            log.exception("Envoi des commandes slash impossible (réessaie avec /sync)")

    async def sync_commands(self) -> int:
        dev_guild = os.getenv("DEV_GUILD_ID", "").strip()
        if dev_guild.isdigit():
            guild = discord.Object(id=int(dev_guild))
            self.tree.copy_global_to(guild=guild)
            synced = await self.tree.sync(guild=guild)
            log.info("%d commandes synchronisées sur le serveur de dev", len(synced))
        else:
            synced = await self.tree.sync()
            log.info("%d commandes synchronisées globalement (jusqu'à 1 h de délai)", len(synced))
        return len(synced)

    async def on_ready(self) -> None:
        assert self.user
        log.info("Connecté en tant que %s (%s) sur %d serveur(s)",
                 self.user, self.user.id, len(self.guilds))

    @tasks.loop(minutes=2)
    async def rotate_status(self) -> None:
        await self.change_presence(activity=next(self._statuses)(self))

    @rotate_status.before_loop
    async def _before_status(self) -> None:
        await self.wait_until_ready()

    async def on_app_command_error(self, interaction: discord.Interaction,
                                   error: app_commands.AppCommandError) -> None:
        if isinstance(error, app_commands.MissingPermissions):
            msg = "Tu n'as pas la permission : " + ", ".join(error.missing_permissions)
        elif isinstance(error, app_commands.BotMissingPermissions):
            msg = "Il me manque la permission : " + ", ".join(error.missing_permissions)
        elif isinstance(error, app_commands.CommandOnCooldown):
            msg = f"Doucement ! Réessaie dans {error.retry_after:.0f} s."
        elif isinstance(error, app_commands.CheckFailure):
            msg = "Tu ne peux pas utiliser cette commande ici."
        elif isinstance(error, app_commands.CommandInvokeError) and isinstance(
                error.original, discord.Forbidden):
            msg = "Discord m'a refusé l'action : vérifie mes permissions et la position de mon rôle."
        else:
            log.exception("Erreur dans /%s", interaction.command.name if interaction.command else "?",
                          exc_info=error)
            msg = "Une erreur inattendue est survenue. Elle a été enregistrée dans les logs."
        embed = embeds.error(msg)
        try:
            if interaction.response.is_done():
                await interaction.followup.send(embed=embed, ephemeral=True)
            else:
                await interaction.response.send_message(embed=embed, ephemeral=True)
        except discord.HTTPException:
            pass

    async def close(self) -> None:
        log.info("Arrêt propre du bot…")
        if self.rotate_status.is_running():
            self.rotate_status.cancel()
        task = getattr(self, "_sync_task", None)
        if task and not task.done():
            task.cancel()
        await self.dashboard.stop()
        await super().close()
        if self.db.conn:
            try:
                await self.db.set_setting(0, "clean_shutdown", "1")
            except Exception:
                log.exception("Impossible de noter l'arrêt propre")
        await self.db.close()


async def main() -> None:
    load_dotenv(ROOT / ".env")
    setup_logging()
    token = os.getenv("DISCORD_TOKEN", "").strip()
    if not token or token == "ton_token_ici":
        log.critical("DISCORD_TOKEN manquant : ouvre le fichier .env (dossier du bot) et colle le token du bot "
                     "après DISCORD_TOKEN= (portail Discord → Bot → Reset Token).")
        sys.exit(1)
    bot = AllInOneBot()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, lambda: asyncio.create_task(bot.close()))
        except NotImplementedError:  # Windows
            pass

    async with bot:
        await bot.start(token)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
