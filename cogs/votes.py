"""Votes top.gg : nombre de serveurs envoyé à top.gg, /vote et récompense des votants.

TOPGG_TOKEN          → envoie le nombre de serveurs à top.gg toutes les 30 minutes.
TOPGG_WEBHOOK_SECRET → active la réception des votes (PUBLIC_URL/webhooks/topgg) et les récompenses.
"""
from __future__ import annotations

import logging
import time
from datetime import datetime, timezone

import aiohttp
import discord
from discord import app_commands
from discord.ext import commands, tasks

from bot import embeds, votes
from bot.config import gconf
from cogs.economy import money

log = logging.getLogger("cogs.votes")


class Votes(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._paused_until = 0.0
        self._last_count: int | None = None

    @property
    def db(self):
        return self.bot.db  # type: ignore[attr-defined]

    async def cog_load(self) -> None:
        if votes.topgg_token():
            self.post_stats.start()

    async def cog_unload(self) -> None:
        self.post_stats.cancel()

    # --- nombre de serveurs sur top.gg -------------------------------------
    @tasks.loop(minutes=30)
    async def post_stats(self) -> None:
        if time.time() < self._paused_until or not self.bot.user:
            return
        count = len(self.bot.guilds)
        if count == self._last_count:
            return
        url = f"{votes.TOPGG_API}/bots/{self.bot.user.id}/stats"
        headers = {"Authorization": votes.topgg_token(), "Content-Type": "application/json"}
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15)) as http:
                async with http.post(url, json={"server_count": count}, headers=headers) as resp:
                    if resp.status == 429:
                        try:
                            wait = int((await resp.json(content_type=None)).get("retry-after", 3600))
                        except Exception:
                            wait = 3600
                        self._paused_until = time.time() + wait
                        log.warning("top.gg limite les envois : pause de %d s", wait)
                    elif resp.status in (401, 403):
                        self._paused_until = time.time() + 6 * 3600
                        log.warning("top.gg refuse TOPGG_TOKEN (%d) : vérifie le token", resp.status)
                    elif resp.status >= 400:
                        log.warning("top.gg : envoi du nombre de serveurs refusé (%d)", resp.status)
                    else:
                        self._last_count = count
                        log.info("top.gg : %d serveurs envoyés", count)
        except (aiohttp.ClientError, TimeoutError) as exc:
            log.warning("top.gg injoignable : %s", exc)

    @post_stats.before_loop
    async def _before_stats(self) -> None:
        await self.bot.wait_until_ready()

    # --- remerciement après un vote ----------------------------------------
    async def thank(self, vote: votes.Vote) -> None:
        try:
            user = self.bot.get_user(vote.user_id) or await self.bot.fetch_user(vote.user_id)
            await user.send(embed=embeds.success(
                "Merci pour ton vote ! 💙\nTape **/vote** sur ton serveur dans les 24 h pour récupérer ta récompense"
                + (" (doublée le week-end !)." if vote.weekend else "."), "🗳️ Vote reçu"))
        except discord.HTTPException:
            pass  # MP fermés ou aucun serveur en commun : pas grave

    # --- /vote ---------------------------------------------------------------
    @app_commands.command(name="vote", description="Voter pour le bot sur top.gg et récupérer ta récompense")
    @app_commands.guild_only()
    async def vote(self, interaction: discord.Interaction) -> None:
        assert interaction.guild
        url = votes.vote_url(self.bot.application_id)
        view = discord.ui.View()
        if url:
            view.add_item(discord.ui.Button(label="Voter sur top.gg", url=url, emoji="🗳️"))
        if not votes.enabled():
            await interaction.response.send_message(
                embed=embeds.info("Les votes ne sont pas encore activés sur ce bot.", "🗳️ Vote"), ephemeral=True)
            return

        cfg = gconf(interaction.guild)
        base = int(cfg.get("economy", "vote_reward", default=200) or 0)
        economy = self.bot.get_cog("Economy")
        rewards_on = bool(cfg.get("economy", "enabled", default=True)) and base > 0 and economy is not None

        row = await votes.claim(self.db, interaction.user.id, interaction.guild.id) if rewards_on else None
        if row:
            amount = votes.reward_amount(base, bool(row["weekend"]))
            await economy.add(interaction.guild.id, interaction.user.id, amount)  # type: ignore[union-attr]
            text = f"Merci pour ton vote ! Tu reçois {money(interaction.guild, amount)}."
            if row["weekend"]:
                text += " (×2 le week-end 🎉)"
            await interaction.response.send_message(embed=embeds.success(text, "🗳️ Récompense de vote"), view=view)
            return

        last = await votes.last_vote(self.db, interaction.user.id)
        now = time.time()
        if last and now - last["voted_at"] < votes.VOTE_COOLDOWN:
            next_at = discord.utils.format_dt(
                datetime.fromtimestamp(last["voted_at"] + votes.VOTE_COOLDOWN, tz=timezone.utc), "R")
            text = f"Tu as déjà voté. Prochain vote possible {next_at}."
            if last["claimed_guild"] and rewards_on:
                text += "\nTa récompense a déjà été récupérée."
        else:
            text = "Vote pour le bot sur top.gg (une fois toutes les 12 h), puis reviens taper **/vote** ici."
            if rewards_on:
                text += f"\nTu gagneras {money(interaction.guild, base)} (×2 le week-end)."
        await interaction.response.send_message(embed=embeds.info(text, "🗳️ Vote"), view=view, ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Votes(bot))
