"""Automod : invitations, spam, mass-mentions, mots interdits (avec anti-contournement simple)."""
from __future__ import annotations

import re
import time
import unicodedata
from collections import defaultdict, deque
from datetime import timedelta

import discord
from discord.ext import commands, tasks

from bot import embeds
from bot import phishing
from bot.config import gconf
from bot.utils import is_staff, send_log

INVITE_RE = re.compile(r"(discord\.gg|discord(?:app)?\.com/invite)/[a-z0-9-]+", re.IGNORECASE)
LEET = str.maketrans({"0": "o", "1": "i", "3": "e", "4": "a", "5": "s", "7": "t", "@": "a", "$": "s", "!": "i"})


def normalize(text: str) -> str:
    """Minuscules, sans accents, leetspeak converti, lettres répétées réduites, sans séparateurs."""
    text = unicodedata.normalize("NFKD", text.lower())
    text = "".join(c for c in text if not unicodedata.combining(c)).translate(LEET)
    text = re.sub(r"[\s.\-_*|]+", "", text)
    return re.sub(r"(.)\1{2,}", r"\1", text)


class AutoMod(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.recent: dict[tuple[int, int], deque[float]] = defaultdict(deque)

    def _exempt(self, member: discord.Member) -> bool:
        exempt_ids = set(gconf(member.guild).get("automod", "exempt_roles", default=[]) or [])
        return is_staff(member) or any(r.id in exempt_ids for r in member.roles)

    def check(self, message: discord.Message) -> str | None:
        """Renvoie la raison de l'infraction, ou None si le message est correct."""
        cfg = gconf(message.guild).get("automod", default={}) or {}
        content = message.content

        if cfg.get("block_invites", True) and INVITE_RE.search(content):
            return "Invitation Discord non autorisée"

        max_mentions = int(cfg.get("max_mentions", 5))
        if max_mentions and len(message.raw_mentions) + len(message.raw_role_mentions) > max_mentions:
            return f"Trop de mentions (max {max_mentions})"

        words = [normalize(w) for w in cfg.get("banned_words", []) or [] if w]
        if words:
            flat = normalize(content)
            if any(w and w in flat for w in words):
                return "Mot interdit"

        limit = int(cfg.get("spam_messages", 6))
        window = float(cfg.get("spam_seconds", 5))
        key = (message.guild.id, message.author.id)  # type: ignore[union-attr]
        now = time.time()
        q = self.recent[key]
        q.append(now)
        while q and now - q[0] > window:
            q.popleft()
        if limit and len(q) >= limit:
            q.clear()
            return f"Spam ({limit} messages en {window:g} s)"
        return None

    async def cog_load(self) -> None:
        self.refresh_phishing.start()

    async def cog_unload(self) -> None:
        self.refresh_phishing.cancel()

    @tasks.loop(hours=6)
    async def refresh_phishing(self) -> None:
        await phishing.refresh()

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if not message.guild or message.author.bot or not isinstance(message.author, discord.Member):
            return
        cfg = gconf(message.guild)
        reason = None
        # Liens dangereux : vérifiés pour tout le monde sauf les admins (un compte staff piraté envoie souvent ces liens)
        if cfg.get("automod", "block_phishing", default=True) and not message.author.guild_permissions.administrator:
            domain = phishing.find_dangerous(message.content, cfg.get("automod", "allowed_domains", default=[]) or [])
            if domain:
                reason = f"Lien dangereux (phishing) : {domain}"
        if not reason:
            if not cfg.get("automod", "enabled", default=True) or self._exempt(message.author):
                return
            reason = self.check(message)
        if not reason:
            return
        try:
            await message.delete()
        except discord.HTTPException:
            pass
        if reason.startswith(("Spam", "Lien dangereux")):
            minutes = 10 if reason.startswith("Lien dangereux") else 5  # souvent un compte piraté : on le bloque
            try:
                await message.author.timeout(timedelta(minutes=minutes), reason=f"Automod : {reason}")
            except discord.HTTPException:
                pass
        try:
            await message.channel.send(
                embed=embeds.warning(f"{message.author.mention}, ton message a été supprimé : **{reason}**."),
                delete_after=8)
        except discord.HTTPException:
            pass
        await self.bot.db.execute(  # type: ignore[attr-defined]
            "INSERT INTO security_logs (guild_id, user_id, module, action, reason, created_at) VALUES (?,?,?,?,?,?)",
            (message.guild.id, message.author.id, "automod", "delete", reason, time.time()))
        await send_log(message.guild, embeds.warning(
            f"{message.author.mention} dans {message.channel.mention}\n**Raison** : {reason}\n"
            f"**Message** : {discord.utils.escape_markdown(message.content[:900]) or '(vide)'}",
            "🤖 Automod"), channel="mod_logs")


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(AutoMod(bot))
