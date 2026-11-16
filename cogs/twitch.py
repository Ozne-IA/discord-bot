"""Modération Twitch : automod du chat, journal des sanctions dans Discord, boutons pour agir depuis Discord.

Une chaîne Twitch est reliée à un seul serveur Discord (panel → Twitch). Twitch envoie les événements
au site du bot (web/server.py → /webhooks/twitch → handle_webhook). Le compte Twitch du bot doit être
modérateur de la chaîne pour supprimer des messages, mettre en sourdine (timeout) ou bannir.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from collections import deque

import aiohttp
import discord
from discord.ext import commands, tasks

from bot import embeds, twitch
from bot.config import gconf, limit_for
from bot.i18n import language
from bot.premium import is_premium
from bot.twitch_api import TwitchAPI, TwitchError
from bot.utils import is_staff

log = logging.getLogger("cogs.twitch")
RECENT_WINDOW = 60          # secondes gardées pour repérer les messages répétés
ERROR_COOLDOWN = 3600       # même erreur dans le journal : une fois par heure
TWITCH_COLOR = 0x9146FF
WARN_TEXT = {
    "fr": "@{user} message retiré ({rule}).",
    "en": "@{user} message removed ({rule}).",
}
RULE_NAMES_EN = {"phishing": "scam link", "words": "banned word", "links": "link not allowed",
                 "caps": "too many caps", "repeat": "repeated message"}


def callback_url() -> str:
    return os.getenv("PUBLIC_URL", "").rstrip("/") + "/webhooks/twitch"


def _fmt_duration(seconds: int) -> str:
    minutes = max(1, round(seconds / 60))
    if minutes < 60:
        return f"{minutes} min"
    if minutes < 1440:
        return f"{minutes // 60} h"
    return f"{minutes // 1440} j"


class TwitchActionButton(discord.ui.DynamicItem[discord.ui.Button],
                         template=r"tw:(?P<act>unban|timeout|ban):(?P<b>[0-9]{1,20}):(?P<u>[0-9]{1,20})"):
    """Bouton sous une entrée du journal : agit sur Twitch (marche encore après un redémarrage)."""

    LABELS = {"unban": ("Débannir / annuler", "✅", discord.ButtonStyle.success),
              "timeout": ("Timeout", "⏳", discord.ButtonStyle.secondary),
              "ban": ("Bannir", "🔨", discord.ButtonStyle.danger)}

    def __init__(self, act: str, broadcaster_id: int, user_id: int):
        label, emoji, style = self.LABELS[act]
        super().__init__(discord.ui.Button(label=label, emoji=emoji, style=style,
                                           custom_id=f"tw:{act}:{broadcaster_id}:{user_id}"))
        self.act, self.broadcaster_id, self.user_id = act, broadcaster_id, user_id

    @classmethod
    async def from_custom_id(cls, interaction: discord.Interaction, item: discord.ui.Button, match):
        return cls(match["act"], int(match["b"]), int(match["u"]))

    async def callback(self, interaction: discord.Interaction) -> None:
        cog = interaction.client.get_cog("TwitchMod")
        if isinstance(cog, TwitchMod):
            await cog.on_button(interaction, self.act, self.broadcaster_id, self.user_id)


def action_view(broadcaster_id: int, user_id: int, acts: tuple[str, ...]) -> discord.ui.View:
    view = discord.ui.View(timeout=None)
    for act in acts:
        view.add_item(TwitchActionButton(act, broadcaster_id, user_id))
    return view


class TwitchMod(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.http: aiohttp.ClientSession | None = None
        self.api: TwitchAPI | None = None
        self.states = twitch.OAuthStates()
        self.seen = twitch.SeenIds()
        self.channels: dict[int, int] = {}     # broadcaster_id -> guild_id
        self.logins: dict[int, str] = {}       # broadcaster_id -> pseudo
        self.active: set[int] = set()          # chaînes dans la limite gratuit/Premium du serveur
        self.bot_user_id: int | None = None
        self.recent: dict[tuple[int, int], deque] = {}
        self._errors: dict[tuple[int, str], float] = {}

    @property
    def db(self):
        return self.bot.db  # type: ignore[attr-defined]

    async def cog_load(self) -> None:
        self.http = aiohttp.ClientSession()
        self.api = TwitchAPI(self.db, self.http)
        self.bot.add_dynamic_items(TwitchActionButton)
        await self.load_channels()
        if twitch.configured():
            self.maintenance.start()
        else:
            log.info("Modération Twitch inactive (TWITCH_CLIENT_ID / SECRET / TWITCH_EVENTSUB_SECRET manquants)")

    async def cog_unload(self) -> None:
        self.maintenance.cancel()
        if self.http:
            await self.http.close()

    # ------------------------------------------------------------------ #
    #  Chaînes reliées
    # ------------------------------------------------------------------ #
    async def load_channels(self) -> None:
        rows = await self.db.fetchall("SELECT broadcaster_id, guild_id, login FROM twitch_channels ORDER BY created_at")
        self.channels = {r["broadcaster_id"]: r["guild_id"] for r in rows}
        self.logins = {r["broadcaster_id"]: r["login"] for r in rows}
        per_guild: dict[int, int] = {}
        self.active = set()
        for r in rows:
            gid = r["guild_id"]
            per_guild[gid] = per_guild.get(gid, 0) + 1
            if per_guild[gid] <= limit_for("twitch_channels", is_premium(gid)):
                self.active.add(r["broadcaster_id"])
        bot = await self.api.bot_account() if self.api else None
        self.bot_user_id = int(bot["user_id"]) if bot else None

    async def guild_channels(self, guild_id: int) -> list[dict]:
        rows = await self.db.fetchall("SELECT broadcaster_id, login, created_at FROM twitch_channels WHERE guild_id=? "
                                      "ORDER BY created_at", (guild_id,))
        return [dict(r) for r in rows]

    async def connect_channel(self, guild_id: int, user_id: int, info: dict, tokens: dict) -> str | None:
        """Relie une chaîne au serveur. Renvoie un message d'erreur, ou None si c'est fait."""
        assert self.api
        bid = int(info["user_id"])
        owner = self.channels.get(bid)
        if owner and owner != guild_id:
            return "Cette chaîne Twitch est déjà reliée à un autre serveur Discord."
        if not owner and len(await self.guild_channels(guild_id)) >= limit_for("twitch_channels", is_premium(guild_id)):
            return "Limite de chaînes atteinte pour ce serveur (💎 Premium : jusqu'à 5)."
        await self.api.store_user("broadcaster", info, tokens)
        await self.db.execute(
            "INSERT INTO twitch_channels (broadcaster_id, guild_id, login, connected_by, created_at) VALUES (?,?,?,?,?) "
            "ON CONFLICT(broadcaster_id) DO UPDATE SET login=excluded.login",
            (bid, guild_id, info.get("login") or "", user_id, time.time()))
        await self.load_channels()
        asyncio.ensure_future(self.reconcile())
        return None

    async def disconnect_channel(self, broadcaster_id: int) -> None:
        await self.db.execute("DELETE FROM twitch_channels WHERE broadcaster_id=?", (broadcaster_id,))
        await self.db.execute("DELETE FROM twitch_tokens WHERE user_id=? AND kind='broadcaster'", (broadcaster_id,))
        if self.api:
            self.api.forget(broadcaster_id, "broadcaster")
        await self.load_channels()
        asyncio.ensure_future(self.reconcile())

    async def connect_bot(self, info: dict, tokens: dict) -> None:
        assert self.api
        await self.api.store_user("bot", info, tokens)
        await self.load_channels()
        asyncio.ensure_future(self.reconcile())

    @commands.Cog.listener()
    async def on_guild_remove(self, guild: discord.Guild) -> None:
        for bid in [b for b, g in self.channels.items() if g == guild.id]:
            await self.disconnect_channel(bid)

    # ------------------------------------------------------------------ #
    #  Abonnements Twitch et vérification des jetons (toutes les heures)
    # ------------------------------------------------------------------ #
    async def reconcile(self) -> None:
        """Crée les abonnements manquants, supprime ceux des chaînes retirées."""
        if not (self.api and twitch.configured() and self.bot_user_id and callback_url().startswith("https://")):
            return
        try:
            existing = await self.api.list_subscriptions()
        except TwitchError as exc:
            log.warning("Abonnements Twitch illisibles : %s", exc)
            return
        ours = [s for s in existing if (s.get("transport") or {}).get("callback") == callback_url()]
        have: set[tuple[str, int]] = set()
        for sub in ours:
            cond = sub.get("condition") or {}
            bid = int(cond.get("broadcaster_user_id") or 0)
            healthy = sub.get("status") in ("enabled", "webhook_callback_verification_pending")
            wanted = bid in self.active and (sub["type"] != "channel.chat.message"
                                             or int(cond.get("user_id") or 0) == self.bot_user_id)
            if wanted and healthy:
                have.add((sub["type"], bid))
            else:
                await self.api.unsubscribe(sub["id"])
        for bid in self.active:
            for sub_type, version, needs_bot in twitch.SUBSCRIPTIONS:
                if (sub_type, bid) in have:
                    continue
                condition = {"broadcaster_user_id": str(bid)}
                if needs_bot:
                    condition["user_id"] = str(self.bot_user_id)
                await self.api.subscribe(sub_type, version, condition, callback_url(), twitch.eventsub_secret())

    @tasks.loop(hours=1)
    async def maintenance(self) -> None:
        await self.load_channels()
        if self.api and self.bot_user_id:
            # Twitch demande de vérifier les jetons au démarrage puis toutes les heures
            try:
                token = await self.api.user_token(self.bot_user_id, "bot")
                if await self.api.validate(token) is None:
                    self.api.forget(self.bot_user_id, "bot")
                    await self.api.user_token(self.bot_user_id, "bot")
            except TwitchError as exc:
                log.error("Compte Twitch du bot inutilisable : %s", exc)
        await self.reconcile()

    @maintenance.before_loop
    async def _before_maintenance(self) -> None:
        await self.bot.wait_until_ready()

    # ------------------------------------------------------------------ #
    #  Webhook : appelé par web/server.py
    # ------------------------------------------------------------------ #
    async def handle_webhook(self, headers, raw: bytes) -> tuple[int, str, str]:
        """Renvoie (statut HTTP, corps, type de contenu)."""
        if not twitch.verify_event(headers, raw, twitch.eventsub_secret()):
            return 403, "signature invalide", "text/plain"
        try:
            body = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return 400, "corps illisible", "text/plain"
        kind = twitch._header(headers, "twitch-eventsub-message-type")
        if kind == "webhook_callback_verification":
            return 200, str(body.get("challenge", "")), "text/plain"
        if kind == "revocation":
            sub = body.get("subscription") or {}
            log.warning("Twitch a retiré l'abonnement %s (%s)", sub.get("type"), sub.get("status"))
            asyncio.ensure_future(self.reconcile())
            return 204, "", "text/plain"
        if kind == "notification" and self.seen.add(twitch._header(headers, "twitch-eventsub-message-id")):
            sub_type = (body.get("subscription") or {}).get("type", "")
            asyncio.ensure_future(self.handle_event(sub_type, body.get("event") or {}))
        return 204, "", "text/plain"

    async def handle_event(self, sub_type: str, event: dict) -> None:
        try:
            if sub_type == "channel.chat.message":
                await self.on_chat(event)
            elif sub_type == "channel.ban":
                await self.on_ban(event)
            elif sub_type == "channel.unban":
                await self.on_unban(event)
        except Exception:
            log.exception("Événement Twitch %s mal traité", sub_type)

    def _guild_for(self, broadcaster_id: int) -> discord.Guild | None:
        if broadcaster_id not in self.active:
            return None
        return self.bot.get_guild(self.channels.get(broadcaster_id, 0))

    # ------------------------------------------------------------------ #
    #  Automod du chat
    # ------------------------------------------------------------------ #
    async def on_chat(self, ev: dict) -> None:
        bid = int(ev.get("broadcaster_user_id") or 0)
        guild = self._guild_for(bid)
        chatter = int(ev.get("chatter_user_id") or 0)
        if guild is None or not chatter or chatter in (bid, self.bot_user_id):
            return
        cfg = gconf(guild).get("twitch_mod", default={}) or {}
        if twitch.exempt(ev.get("badges"), bool(cfg.get("exempt_subscribers"))):
            return
        text = str((ev.get("message") or {}).get("text") or "")
        key, now = (bid, chatter), time.time()
        recent = self.recent.setdefault(key, deque(maxlen=10))
        while recent and now - recent[0][0] > RECENT_WINDOW:
            recent.popleft()
        result = twitch.check_message(text, cfg, [m for _, m in recent])
        recent.append((now, twitch.normalize(text)))
        if len(self.recent) > 20000:  # ménage
            self.recent = {k: v for k, v in self.recent.items() if v and now - v[-1][0] < RECENT_WINDOW}
        if result:
            await self.punish(guild, cfg, bid, ev, *result)

    async def punish(self, guild: discord.Guild, cfg: dict, bid: int, ev: dict, rule: str, action: str) -> None:
        assert self.api
        chatter, login = int(ev["chatter_user_id"]), str(ev.get("chatter_user_login") or ev.get("chatter_user_name") or "?")
        rule_name = twitch.RULE_NAMES[rule]
        minutes = max(1, min(int(cfg.get("timeout_minutes") or 10), 20160))
        try:
            if action == "delete":
                await self.api.delete_message(bid, str(ev.get("message_id") or ""))
            elif action == "timeout":
                await self.api.ban(bid, chatter, f"Automod : {rule_name}", duration=minutes * 60)
            elif action == "ban":
                await self.api.ban(bid, chatter, f"Automod : {rule_name}")
            else:
                return
        except TwitchError as exc:
            await self.report_error(guild, bid, str(exc))
            return
        if cfg.get("warn_in_chat", True) and action != "ban":
            lang = "en" if language(guild) == "en" else "fr"
            name = RULE_NAMES_EN[rule] if lang == "en" else rule_name.lower()
            try:
                await self.api.send_message(bid, WARN_TEXT[lang].format(user=login, rule=name))
            except TwitchError:
                pass
        titles = {"delete": "🛡️ Message supprimé", "timeout": f"⏳ Timeout {_fmt_duration(minutes * 60)}",
                  "ban": "🔨 Banni"}
        buttons = {"delete": ("timeout", "ban"), "timeout": ("unban", "ban"), "ban": ("unban",)}[action]
        await self.log(guild, bid, f"{titles[action]} par l'automod", login, chatter, buttons,
                       rule=rule_name, message=str((ev.get("message") or {}).get("text") or ""))

    # ------------------------------------------------------------------ #
    #  Bans / débans faits sur Twitch (par les modos humains)
    # ------------------------------------------------------------------ #
    async def on_ban(self, ev: dict) -> None:
        bid = int(ev.get("broadcaster_user_id") or 0)
        guild = self._guild_for(bid)
        if guild is None or int(ev.get("moderator_user_id") or 0) == self.bot_user_id:
            return  # déjà journalisé par le bot lui-même
        user_id, login = int(ev.get("user_id") or 0), str(ev.get("user_login") or "?")
        mod = str(ev.get("moderator_user_login") or ev.get("moderator_user_name") or "?")
        if ev.get("is_permanent", True):
            title, buttons = f"🔨 Banni par {mod}", ("unban",)
        else:
            title, buttons = f"⏳ Timeout par {mod}", ("unban", "ban")
            ends = ev.get("ends_at") or ""
            if ends:
                title += f" (jusqu'à {ends[11:16]} UTC)"
        await self.log(guild, bid, title, login, user_id, buttons, reason=str(ev.get("reason") or ""))

    async def on_unban(self, ev: dict) -> None:
        bid = int(ev.get("broadcaster_user_id") or 0)
        guild = self._guild_for(bid)
        if guild is None or int(ev.get("moderator_user_id") or 0) == self.bot_user_id:
            return
        mod = str(ev.get("moderator_user_login") or ev.get("moderator_user_name") or "?")
        await self.log(guild, bid, f"✅ Débanni par {mod}", str(ev.get("user_login") or "?"),
                       int(ev.get("user_id") or 0), ())

    # ------------------------------------------------------------------ #
    #  Journal Discord
    # ------------------------------------------------------------------ #
    def _log_channel(self, guild: discord.Guild) -> discord.TextChannel | None:
        cid = int(gconf(guild).get("twitch_mod", "log_channel", default=0) or 0)
        channel = guild.get_channel(cid or gconf(guild).channel_id("mod_logs"))
        return channel if isinstance(channel, discord.TextChannel) else None

    async def log(self, guild: discord.Guild, bid: int, title: str, login: str, user_id: int,
                  buttons: tuple[str, ...], *, rule: str = "", reason: str = "", message: str = "") -> None:
        channel = self._log_channel(guild)
        if channel is None:
            return
        embed = embeds.base(f"Twitch · {title}", color=TWITCH_COLOR, guild=guild)
        embed.add_field(name="Chaîne", value=f"[{self.logins.get(bid, bid)}](https://twitch.tv/{self.logins.get(bid, '')})")
        embed.add_field(name="Spectateur", value=f"[{login}](https://twitch.tv/{login})")
        if rule:
            embed.add_field(name="Règle", value=rule)
        if reason:
            embed.add_field(name="Raison", value=reason[:1000], inline=False)
        if message:
            embed.add_field(name="Message", value=discord.utils.escape_markdown(message)[:1000], inline=False)
        embed.timestamp = discord.utils.utcnow()
        kwargs = {"embed": embed}
        if buttons and user_id:
            kwargs["view"] = action_view(bid, user_id, buttons)
        try:
            await channel.send(**kwargs)
        except discord.HTTPException as exc:
            log.warning("Journal Twitch impossible sur %s : %s", guild.id, exc)

    async def report_error(self, guild: discord.Guild, bid: int, error: str) -> None:
        key = (bid, error[:60])
        if time.time() - self._errors.get(key, 0) < ERROR_COOLDOWN:
            return
        self._errors[key] = time.time()
        channel = self._log_channel(guild)
        if channel:
            try:
                await channel.send(embed=embeds.warning(
                    f"Chaîne **{self.logins.get(bid, bid)}** : {error}", "⚠️ Modération Twitch"))
            except discord.HTTPException:
                pass

    # ------------------------------------------------------------------ #
    #  Boutons du journal
    # ------------------------------------------------------------------ #
    async def on_button(self, interaction: discord.Interaction, act: str, bid: int, user_id: int) -> None:
        guild, member = interaction.guild, interaction.user
        if guild is None or not isinstance(member, discord.Member) or self.channels.get(bid) != guild.id:
            await interaction.response.send_message(embed=embeds.error("Cette chaîne n'est plus reliée à ce serveur."),
                                                    ephemeral=True)
            return
        if not is_staff(member):
            await interaction.response.send_message(embed=embeds.error("Réservé au staff."), ephemeral=True)
            return
        assert self.api
        await interaction.response.defer(ephemeral=True, thinking=True)
        minutes = max(1, min(int(gconf(guild).get("twitch_mod", "timeout_minutes", default=10) or 10), 20160))
        reason = f"Depuis Discord par {member.display_name}"
        try:
            if act == "unban":
                await self.api.unban(bid, user_id)
            elif act == "timeout":
                await self.api.ban(bid, user_id, reason, duration=minutes * 60)
            else:
                await self.api.ban(bid, user_id, reason)
        except TwitchError as exc:
            await interaction.followup.send(embed=embeds.error(str(exc)), ephemeral=True)
            return
        done = {"unban": "✅ Débanni", "timeout": f"⏳ Timeout {_fmt_duration(minutes * 60)}", "ban": "🔨 Banni"}[act]
        await interaction.followup.send(embed=embeds.success(f"{done} sur Twitch."), ephemeral=True)
        login = "?"
        if interaction.message and interaction.message.embeds:
            for field in interaction.message.embeds[0].fields:
                if field.name in ("Spectateur", "Viewer") and field.value:
                    login = field.value.split("]")[0].lstrip("[")
        buttons = {"unban": (), "timeout": ("unban", "ban"), "ban": ("unban",)}[act]
        await self.log(guild, bid, f"{done} depuis Discord par {member.display_name}", login, user_id, buttons)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(TwitchMod(bot))
