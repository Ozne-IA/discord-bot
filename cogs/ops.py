"""Surveillance pour le propriétaire du bot : alertes en message privé et sauvegardes automatiques.

- Démarrage : message « bot en ligne », avec un avertissement si l'arrêt précédent n'était pas prévu.
- Erreurs : chaque erreur écrite dans les logs est aussi envoyée (regroupée, 1 fois par heure au plus
  pour la même erreur, 20 alertes par heure maximum).
- Serveurs : ajout et retrait du bot.
- Sauvegarde automatique chaque nuit, compressée, gardée dans data/backups/ et envoyée au propriétaire.

Destination : OWNER_ALERT_CHANNEL_ID (un salon privé) si rempli, sinon un message privé au propriétaire
de l'application. OWNER_ALERTS=off coupe les alertes, BACKUP_AUTO=off coupe les sauvegardes auto.
"""
from __future__ import annotations

import asyncio
import io
import logging
import os
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path

import discord
from discord.ext import commands, tasks

from bot import backups, embeds

log = logging.getLogger("bot.ops")

ALERT_COOLDOWN = 3600      # même erreur : une alerte par heure au plus
ALERTS_PER_HOUR = 20       # plafond global (évite d'être inondé si tout casse d'un coup)
IGNORED_LOGGERS = ("bot.ops", "discord.gateway", "discord.http")  # pas d'alerte sur soi-même ni le bruit réseau


def alerts_enabled() -> bool:
    return os.getenv("OWNER_ALERTS", "on").strip().lower() not in ("off", "0", "non", "false", "no")


class AlertThrottle:
    """Décide si une alerte peut partir (anti-répétition)."""

    def __init__(self, cooldown: float = ALERT_COOLDOWN, per_hour: int = ALERTS_PER_HOUR):
        self.cooldown = cooldown
        self.per_hour = per_hour
        self.last: dict[str, float] = {}
        self.sent: list[float] = []

    def allow(self, key: str, now: float | None = None) -> bool:
        now = time.time() if now is None else now
        self.sent = [t for t in self.sent if now - t < 3600]
        if len(self.sent) >= self.per_hour:
            return False
        if key in self.last and now - self.last[key] < self.cooldown:
            return False
        self.last[key] = now
        self.sent.append(now)
        if len(self.last) > 500:  # ménage
            self.last = {k: t for k, t in self.last.items() if now - t < self.cooldown}
        return True


class OwnerAlertHandler(logging.Handler):
    """Relaie les erreurs des logs vers le propriétaire du bot."""

    def __init__(self, cog: "Ops"):
        super().__init__(level=logging.ERROR)
        self.cog = cog

    def emit(self, record: logging.LogRecord) -> None:
        if record.name.startswith(IGNORED_LOGGERS):
            return
        try:
            message = record.getMessage()
            details = ""
            if record.exc_info and record.exc_info[1] is not None:
                details = "".join(traceback.format_exception(*record.exc_info))
            loop = self.cog.bot.loop
            loop.call_soon_threadsafe(lambda: asyncio.ensure_future(
                self.cog.report_error(record.name, message, details)))
        except Exception:  # un log ne doit jamais faire planter le bot
            pass


class Ops(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.throttle = AlertThrottle()
        self.handler = OwnerAlertHandler(self)
        self._target: discord.abc.Messageable | None = None
        self._announced = False

    @property
    def db(self):
        return self.bot.db  # type: ignore[attr-defined]

    @property
    def backup_dir(self) -> Path:
        return Path(self.db.path).parent / "backups"

    async def cog_load(self) -> None:
        if alerts_enabled():
            logging.getLogger().addHandler(self.handler)
        if backups.auto_enabled():
            self.auto_backup.start()

    async def cog_unload(self) -> None:
        logging.getLogger().removeHandler(self.handler)
        self.auto_backup.cancel()

    # ------------------------------------------------------------------ #
    #  Envoi au propriétaire
    # ------------------------------------------------------------------ #
    async def _destination(self) -> discord.abc.Messageable | None:
        if self._target is not None:
            return self._target
        raw = os.getenv("OWNER_ALERT_CHANNEL_ID", "").strip()
        if raw.isdigit():
            channel = self.bot.get_channel(int(raw))
            if channel is None:
                try:
                    channel = await self.bot.fetch_channel(int(raw))
                except discord.HTTPException:
                    channel = None
            if isinstance(channel, discord.abc.Messageable):
                self._target = channel
                return channel
            log.warning("OWNER_ALERT_CHANNEL_ID=%s : salon introuvable, envoi en message privé à la place", raw)
        try:
            app = await self.bot.application_info()
        except discord.HTTPException:
            return None
        owner = app.team.owner if app.team and app.team.owner else app.owner
        self._target = owner
        return owner

    async def notify(self, title: str, text: str, *, color: int = 0x5865F2,
                     file: discord.File | None = None, force: bool = False) -> bool:
        """Envoie un message au propriétaire. Renvoie True si c'est parti."""
        if not (alerts_enabled() or force):
            return False
        target = await self._destination()
        if target is None:
            return False
        embed = embeds.base(title, text[:4000], color=color)
        embed.timestamp = datetime.now(timezone.utc)
        try:
            if file:
                await target.send(embed=embed, file=file)
            else:
                await target.send(embed=embed)
            return True
        except discord.HTTPException as exc:
            log.warning("Alerte au propriétaire impossible (%s) : MP fermés ?", exc)
            return False

    async def report_error(self, source: str, message: str, details: str) -> None:
        key = f"{source}:{message[:120]}"
        if not self.bot.is_ready() or not self.throttle.allow(key):
            return
        text = f"**Où :** `{source}`\n**Quoi :** {message[:500]}"
        if details:
            text += f"\n```py\n{details[-1500:]}\n```"
        text += "\nLe détail complet est dans les logs (Railway → Deployments → Logs)."
        await self.notify("🚨 Erreur dans le bot", text, color=0xE74C3C)

    # ------------------------------------------------------------------ #
    #  Démarrage et serveurs
    # ------------------------------------------------------------------ #
    @commands.Cog.listener()
    async def on_ready(self) -> None:
        if self._announced:
            return
        self._announced = True
        clean = getattr(self.bot, "previous_shutdown_clean", True)
        guilds = len(self.bot.guilds)
        text = (f"Version **{getattr(self.bot, 'version', '?')}** · **{guilds}** serveur(s) · "
                f"latence **{self.bot.latency * 1000:.0f} ms**")
        if clean:
            await self.notify("✅ Bot en ligne", text, color=0x2ECC71)
        else:
            await self.notify("⚠️ Bot redémarré après un arrêt imprévu",
                              text + "\n\nL'arrêt précédent n'était pas prévu (plantage, manque de mémoire ou "
                              "coupure). Regarde les logs Railway autour de l'heure de l'arrêt.", color=0xE67E22)

    @commands.Cog.listener()
    async def on_guild_join(self, guild: discord.Guild) -> None:
        await self.notify("➕ Nouveau serveur", f"**{guild.name}** (`{guild.id}`) · {guild.member_count} membres\n"
                          f"Total : **{len(self.bot.guilds)}** serveurs", color=0x2ECC71)

    @commands.Cog.listener()
    async def on_guild_remove(self, guild: discord.Guild) -> None:
        await self.notify("➖ Serveur quitté", f"**{guild.name}** (`{guild.id}`)\n"
                          f"Total : **{len(self.bot.guilds)}** serveurs", color=0x95A5A6)

    # ------------------------------------------------------------------ #
    #  Sauvegarde automatique
    # ------------------------------------------------------------------ #
    async def make_backup(self) -> Path:
        """Crée une sauvegarde compressée et renvoie son chemin (sans l'envoyer)."""
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M")
        folder = self.backup_dir
        raw = folder / f"{backups.AUTO_PREFIX}{stamp}.db"
        await self.db.backup_to(raw)
        packed = raw.with_suffix(".db.gz")
        await asyncio.to_thread(backups.compress, raw, packed)
        raw.unlink(missing_ok=True)
        keep = backups.env_int("BACKUP_KEEP", 14, 1, 365)
        await asyncio.to_thread(backups.prune, folder, keep)
        await self.db.set_setting(0, "last_auto_backup", str(time.time()))
        return packed

    @tasks.loop(minutes=30)
    async def auto_backup(self) -> None:
        last_raw = await self.db.get_setting(0, "last_auto_backup")
        last = float(last_raw) if last_raw else None
        now = time.time()
        hour = backups.env_int("BACKUP_HOUR", 4, 0, 23)
        if not backups.is_due(last, now, hour, datetime.now(timezone.utc).hour):
            return
        try:
            path = await self.make_backup()
        except Exception:
            log.exception("Sauvegarde automatique impossible")
            await self.notify("🚨 Sauvegarde automatique ratée",
                              "La sauvegarde de cette nuit n'a pas pu être faite. Fais un `/backup` à la main et "
                              "regarde les logs.", color=0xE74C3C, force=True)
            return
        size = path.stat().st_size
        limit = backups.env_int("BACKUP_UPLOAD_MB", 8, 1, 500) * 1024 * 1024
        human = f"{size / 1024 / 1024:.2f} Mo"
        log.info("Sauvegarde automatique créée : %s (%s)", path.name, human)
        if size > limit:
            await self.notify("📦 Sauvegarde automatique faite",
                              f"`{path.name}` ({human}) est trop lourde pour Discord : elle est gardée sur le "
                              "volume Railway, dans `data/backups/`.", force=True)
            return
        data = await asyncio.to_thread(path.read_bytes)
        sent = await self.notify(
            "📦 Sauvegarde automatique",
            f"`{path.name}` · {human}\nGarde ce fichier : il permet de tout récupérer avec `/restore` "
            "(le fichier .gz est accepté tel quel).",
            file=discord.File(io.BytesIO(data), filename=path.name), force=True)
        if not sent:
            log.warning("Sauvegarde %s créée mais pas envoyée (MP fermés ou salon introuvable)", path.name)

    @auto_backup.before_loop
    async def _before_backup(self) -> None:
        await self.bot.wait_until_ready()
        await asyncio.sleep(120)  # laisse le bot finir de démarrer


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Ops(bot))


async def notify_owner(bot: commands.Bot, title: str, text: str, color: int = 0x5865F2) -> None:
    """Raccourci utilisable depuis les autres modules (ne fait rien si le module n'est pas chargé)."""
    cog = bot.get_cog("Ops")
    if isinstance(cog, Ops):
        await cog.notify(title, text, color=color)
