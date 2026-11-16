"""Premium via Patreon : réception des webhooks, relecture des abonnés toutes les 6 h, alertes au propriétaire."""
from __future__ import annotations

import asyncio
import json
import logging
import time

import aiohttp
from discord.ext import commands, tasks

from bot import patreon

log = logging.getLogger("cogs.patreon")
SYNC_THROTTLE = 60  # une relecture complète par minute au plus


class Patreon(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.http: aiohttp.ClientSession | None = None
        self.api: patreon.PatreonAPI | None = None
        self._last_sync = 0.0
        self._sync_lock = asyncio.Lock()
        self._sync_error_alerted = 0.0

    @property
    def db(self):
        return self.bot.db  # type: ignore[attr-defined]

    async def cog_load(self) -> None:
        self.http = aiohttp.ClientSession()
        self.api = patreon.PatreonAPI(self.db, self.http)
        await patreon.refresh_premium(self.db)
        self.sync_loop.start()

    async def cog_unload(self) -> None:
        self.sync_loop.cancel()
        if self.http:
            await self.http.close()

    # ------------------------------------------------------------------ #
    #  Relecture de la liste des abonnés
    # ------------------------------------------------------------------ #
    async def run_sync(self) -> int:
        """Relit tous les abonnés de la page Patreon. Renvoie le nombre d'abonnés actifs."""
        assert self.api
        async with self._sync_lock:
            self._last_sync = time.time()
            before = await patreon.premium_guilds(self.db)
            seen: set[str] = set()
            active = 0
            async for member in self.api.members():
                seen.add(member["patreon_id"])
                active += patreon.is_active(member["status"], member["cents"])
                await patreon.save_member(self.db, member)
            await patreon.mark_missing_as_former(self.db, seen)
            after = await patreon.refresh_premium(self.db)
            await self.announce(before, after)
            log.info("Patreon : %d abonné(s) actif(s), %d serveur(s) Premium", active, len(after))
            return active

    async def request_sync(self) -> None:
        """Relecture demandée (après une connexion ou un clic « Actualiser »), limitée à une par minute."""
        if time.time() - self._last_sync < SYNC_THROTTLE or not self.api or not await self.api.creator_ready():
            return
        try:
            await self.run_sync()
        except patreon.PatreonError as exc:
            log.warning("Relecture Patreon impossible : %s", exc)

    @tasks.loop(hours=6)
    async def sync_loop(self) -> None:
        if not (self.api and patreon.configured() and await self.api.creator_ready()):
            return
        try:
            await self.run_sync()
        except patreon.PatreonError as exc:
            log.warning("Relecture Patreon impossible : %s", exc)
            if exc.status == 401 and time.time() - self._sync_error_alerted > 24 * 3600:
                self._sync_error_alerted = time.time()
                await self.notify("⚠️ Patreon : jeton créateur refusé",
                                  "Le bot ne peut plus lire la liste des abonnés. Sur "
                                  "https://www.patreon.com/portal/registration/register-clients, copie le nouveau "
                                  "« Creator's Access Token » et « Creator's Refresh Token » dans les variables "
                                  "Railway PATREON_CREATOR_TOKEN et PATREON_CREATOR_REFRESH_TOKEN, puis redéploie.",
                                  0xE67E22)

    @sync_loop.before_loop
    async def _before_sync(self) -> None:
        await self.bot.wait_until_ready()

    # ------------------------------------------------------------------ #
    #  Webhook (appelé par web/server.py)
    # ------------------------------------------------------------------ #
    async def handle_webhook(self, headers, raw: bytes) -> tuple[int, dict]:
        secret = patreon.webhook_secret()
        if not secret:
            return 503, {"error": "PATREON_WEBHOOK_SECRET manquant"}
        if not patreon.verify_signature(secret, raw, headers.get("X-Patreon-Signature", "")):
            log.warning("Webhook Patreon refusé : signature invalide")
            return 401, {"error": "signature invalide"}
        event = headers.get("X-Patreon-Event", "")
        try:
            body = json.loads(raw)
        except ValueError:
            return 400, {"error": "JSON invalide"}
        member = patreon.parse_webhook(event, body)
        if member is None:
            return 200, {"ok": True, "ignored": True}
        before = await patreon.premium_guilds(self.db)
        await patreon.save_member(self.db, member)
        after = await patreon.refresh_premium(self.db)
        await self.announce(before, after)
        log.info("Webhook Patreon %s : abonné %s → %s", event, member["patreon_id"], member["status"])
        return 200, {"ok": True}

    # ------------------------------------------------------------------ #
    #  Alertes au propriétaire du bot
    # ------------------------------------------------------------------ #
    async def notify(self, title: str, text: str, color: int) -> None:
        from cogs.ops import notify_owner
        await notify_owner(self.bot, title, text, color)

    def _guild_label(self, guild_id: int) -> str:
        guild = self.bot.get_guild(guild_id)
        return f"**{guild.name}** (`{guild_id}`)" if guild else f"`{guild_id}`"

    async def announce(self, before: dict[int, int], after: dict[int, int]) -> None:
        for gid in set(after) - set(before):
            await self.notify("💎 Nouveau Premium Patreon", f"{self._guild_label(gid)} · payé par <@{after[gid]}>",
                              0xF1C40F)
        for gid in set(before) - set(after):
            await self.notify("💤 Premium Patreon arrêté", f"{self._guild_label(gid)} (abonnement arrêté ou "
                              "serveur changé)", 0x95A5A6)

    # ------------------------------------------------------------------ #
    #  Connexion d'un membre (appelé par web/server.py après Patreon)
    # ------------------------------------------------------------------ #
    async def complete_link(self, user_id: int, code: str, redirect_uri: str) -> dict:
        """Relie le compte Patreon. Renvoie l'état du membre ; lève PatreonError si Patreon refuse."""
        assert self.api
        tokens = await self.api.exchange_code(code, redirect_uri)
        token = tokens.get("access_token")
        if not token:
            raise patreon.PatreonError("Patreon n'a pas donné d'autorisation")
        identity = await self.api.identity(token)
        data = identity.get("data") or {}
        patreon_id = str(data.get("id") or "")
        if not patreon_id:
            raise patreon.PatreonError("Patreon n'a pas confirmé le compte")
        name = (data.get("attributes") or {}).get("full_name")
        await patreon.link(self.db, user_id, patreon_id, name)
        member = patreon.identity_member(identity)
        if member:
            await patreon.save_member(self.db, member)
        else:
            await self.request_sync()
        await patreon.refresh_premium(self.db)
        log.info("Compte Patreon relié (abonné actif : %s)", bool(member and patreon.is_active(
            member["status"], member["cents"])))
        return await patreon.user_state(self.db, user_id)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Patreon(bot))

