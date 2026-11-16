"""💎 Sondages (Premium) : jusqu'à 10 choix en boutons, résultats en direct, fin automatique."""
from __future__ import annotations

import json
import logging
import time

import discord
from discord import app_commands
from discord.ext import commands, tasks

from bot import embeds
from bot.premium import require
from bot.utils import parse_duration, reply_error

log = logging.getLogger("cogs.polls")
LETTERS = ["🇦", "🇧", "🇨", "🇩", "🇪", "🇫", "🇬", "🇭", "🇮", "🇯"]


def bar(ratio: float, size: int = 12) -> str:
    filled = round(ratio * size)
    return "█" * filled + "░" * (size - filled)


class PollButton(discord.ui.DynamicItem[discord.ui.Button], template=r"poll:(?P<id>\d+):(?P<idx>\d)"):
    def __init__(self, poll_id: int, index: int, label: str = "", disabled: bool = False) -> None:
        super().__init__(discord.ui.Button(label=label[:80] or str(index + 1), emoji=LETTERS[index],
                                           style=discord.ButtonStyle.secondary, disabled=disabled,
                                           custom_id=f"poll:{poll_id}:{index}"))
        self.poll_id = poll_id
        self.index = index

    @classmethod
    async def from_custom_id(cls, interaction: discord.Interaction, item: discord.ui.Button, match):
        return cls(int(match["id"]), int(match["idx"]))

    async def callback(self, interaction: discord.Interaction) -> None:
        cog: Polls = interaction.client.get_cog("Polls")  # type: ignore[assignment]
        await cog.vote(interaction, self.poll_id, self.index)


def poll_view(poll_id: int, options: list[str], ended: bool = False) -> discord.ui.View:
    view = discord.ui.View(timeout=None)
    for i, opt in enumerate(options):
        view.add_item(PollButton(poll_id, i, opt, disabled=ended))
    return view


class Polls(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @property
    def db(self):
        return self.bot.db  # type: ignore[attr-defined]

    async def cog_load(self) -> None:
        self.bot.add_dynamic_items(PollButton)
        self.check_ended.start()

    async def cog_unload(self) -> None:
        self.check_ended.cancel()
        self.bot.remove_dynamic_items(PollButton)

    async def _get(self, poll_id: int) -> dict | None:
        row = await self.db.fetchone("SELECT * FROM polls WHERE id=?", (poll_id,))
        if not row:
            return None
        poll = dict(row)
        poll["options"] = json.loads(poll["options"])
        return poll

    async def build_embed(self, poll: dict) -> discord.Embed:
        rows = await self.db.fetchall("SELECT option, COUNT(*) AS n FROM poll_votes WHERE poll_id=? GROUP BY option",
                                      (poll["id"],))
        counts = {r["option"]: r["n"] for r in rows}
        total = sum(counts.values())
        best = max(counts.values(), default=0)
        lines = []
        for i, opt in enumerate(poll["options"]):
            n = counts.get(i, 0)
            ratio = n / total if total else 0
            crown = " 🏆" if poll["ended"] and n == best and n > 0 else ""
            lines.append(f"{LETTERS[i]} **{opt}**{crown}\n`{bar(ratio)}` {ratio:.0%} ({n})")
        footer = f"\n\n🗳️ **{total}** vote(s)"
        if poll["ended"]:
            footer += " • Sondage terminé"
        elif poll["ends_at"]:
            footer += f" • Fin <t:{int(poll['ends_at'])}:R>"
        footer += f"\nPar <@{poll['author_id']}> • un seul vote, reclique pour l'annuler"
        return embeds.base(f"📊 {poll['question']}", "\n\n".join(lines) + footer,
                           color=0x95A5A6 if poll["ended"] else 0x5865F2)

    async def vote(self, interaction: discord.Interaction, poll_id: int, index: int) -> None:
        poll = await self._get(poll_id)
        if not poll or poll["ended"] or poll["guild_id"] != interaction.guild_id or index >= len(poll["options"]):
            await interaction.response.send_message(embed=embeds.error("Ce sondage est terminé."), ephemeral=True)
            return
        uid = interaction.user.id
        current = await self.db.fetchone("SELECT option FROM poll_votes WHERE poll_id=? AND user_id=?", (poll_id, uid))
        if current and current["option"] == index:
            await self.db.execute("DELETE FROM poll_votes WHERE poll_id=? AND user_id=?", (poll_id, uid))
            text = "Vote retiré."
        else:
            await self.db.execute(
                "INSERT INTO poll_votes (poll_id, user_id, option) VALUES (?,?,?) "
                "ON CONFLICT(poll_id, user_id) DO UPDATE SET option=excluded.option", (poll_id, uid, index))
            text = f"Vote enregistré pour **{poll['options'][index]}**."
        await interaction.response.edit_message(embed=await self.build_embed(poll), view=poll_view(poll_id, poll["options"]))
        await interaction.followup.send(embed=embeds.success(text), ephemeral=True)

    async def finish(self, poll: dict) -> None:
        await self.db.execute("UPDATE polls SET ended=1 WHERE id=?", (poll["id"],))
        poll["ended"] = 1
        channel = self.bot.get_channel(poll["channel_id"])
        if isinstance(channel, discord.TextChannel) and poll["message_id"]:
            try:
                await channel.get_partial_message(poll["message_id"]).edit(
                    embed=await self.build_embed(poll), view=poll_view(poll["id"], poll["options"], ended=True))
            except discord.HTTPException:
                pass

    @tasks.loop(seconds=30)
    async def check_ended(self) -> None:
        rows = await self.db.fetchall("SELECT id FROM polls WHERE ended=0 AND ends_at IS NOT NULL AND ends_at <= ?",
                                      (time.time(),))
        for row in rows:
            poll = await self._get(row["id"])
            if poll:
                await self.finish(poll)

    @check_ended.before_loop
    async def _before(self) -> None:
        await self.bot.wait_until_ready()

    group = app_commands.Group(name="sondage", description="💎 Sondages (Premium)", guild_only=True,
                               default_permissions=discord.Permissions(manage_messages=True))

    @group.command(name="creer", description="Crée un sondage à boutons")
    @app_commands.describe(question="La question", choix="Les choix séparés par | (2 à 10). Ex : Oui | Non | Peut-être",
                           duree="Fin automatique (ex : 1h, 1d). Vide = pas de fin")
    async def create(self, interaction: discord.Interaction, question: app_commands.Range[str, 1, 200],
                     choix: str, duree: str | None = None) -> None:
        if not await require(interaction, "Les sondages"):
            return
        options = [o.strip()[:80] for o in choix.split("|") if o.strip()]
        if not 2 <= len(options) <= 10:
            await reply_error(interaction, "Il faut entre 2 et 10 choix, séparés par `|`.")
            return
        ends = None
        if duree:
            delta = parse_duration(duree)
            if not delta or delta.days > 30:
                await reply_error(interaction, "Durée invalide (max 30 jours). Exemples : `30m`, `1h`, `2d`.")
                return
            ends = time.time() + delta.total_seconds()
        assert isinstance(interaction.channel, discord.TextChannel)
        poll_id = await self.db.execute(
            "INSERT INTO polls (guild_id, channel_id, author_id, question, options, ends_at) VALUES (?,?,?,?,?,?)",
            (interaction.guild_id, interaction.channel.id, interaction.user.id, question,
             json.dumps(options, ensure_ascii=False), ends))
        poll = await self._get(poll_id)
        assert poll
        await interaction.response.send_message(embed=await self.build_embed(poll), view=poll_view(poll_id, options))
        msg = await interaction.original_response()
        await self.db.execute("UPDATE polls SET message_id=? WHERE id=?", (msg.id, poll_id))

    @group.command(name="fin", description="Termine un sondage et affiche le résultat final")
    async def end(self, interaction: discord.Interaction, sondage_id: int) -> None:
        if not await require(interaction, "Les sondages"):
            return
        poll = await self._get(sondage_id)
        if not poll or poll["guild_id"] != interaction.guild_id or poll["ended"]:
            await reply_error(interaction, "Sondage introuvable ou déjà terminé.")
            return
        await self.finish(poll)
        await interaction.response.send_message(embed=embeds.success(f"Sondage #{sondage_id} terminé."), ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Polls(bot))
