"""Communauté : suggestions avec votes, starboard, compteurs de membres (salons vocaux renommés)."""
from __future__ import annotations

import logging
import time

import discord
from discord import app_commands
from discord.ext import commands, tasks

from bot import embeds
from bot.config import gconf, limit_for
from bot.premium import is_premium
from bot.utils import is_staff, reply_error

log = logging.getLogger("cogs.community")
STATUS = {"open": ("🗳️ En attente", 0x5865F2), "accepted": ("✅ Acceptée", 0x57F287), "refused": ("❌ Refusée", 0xED4245)}


# --------------------------------------------------------------------------- #
#  Suggestions
# --------------------------------------------------------------------------- #
class SuggestionButton(discord.ui.DynamicItem[discord.ui.Button], template=r"suggest:(?P<id>\d+):(?P<action>up|down|yes|no)"):
    LOOK = {"up": ("👍", discord.ButtonStyle.secondary), "down": ("👎", discord.ButtonStyle.secondary),
            "yes": ("✅", discord.ButtonStyle.success), "no": ("❌", discord.ButtonStyle.danger)}

    def __init__(self, sid: int, action: str, label: str | None = None, disabled: bool = False) -> None:
        emoji, style = self.LOOK[action]
        super().__init__(discord.ui.Button(emoji=emoji, label=label, style=style, disabled=disabled,
                                           custom_id=f"suggest:{sid}:{action}"))
        self.sid, self.action = sid, action

    @classmethod
    async def from_custom_id(cls, interaction, item, match):
        return cls(int(match["id"]), match["action"])

    async def callback(self, interaction: discord.Interaction) -> None:
        cog: Community = interaction.client.get_cog("Community")  # type: ignore[assignment]
        if self.action in ("up", "down"):
            await cog.vote(interaction, self.sid, 1 if self.action == "up" else -1)
        else:
            await cog.ask_response(interaction, self.sid, self.action == "yes")


class ResponseModal(discord.ui.Modal, title="Réponse du staff"):
    reason = discord.ui.TextInput(label="Réponse (facultatif)", style=discord.TextStyle.paragraph, required=False,
                                  max_length=500)

    def __init__(self, cog: "Community", sid: int, accepted: bool) -> None:
        super().__init__()
        self.cog, self.sid, self.accepted = cog, sid, accepted

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await self.cog.respond(interaction, self.sid, self.accepted, str(self.reason))


class Community(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @property
    def db(self):
        return self.bot.db  # type: ignore[attr-defined]

    async def cog_load(self) -> None:
        self.bot.add_dynamic_items(SuggestionButton)
        self.update_counters.start()

    async def cog_unload(self) -> None:
        self.update_counters.cancel()
        self.bot.remove_dynamic_items(SuggestionButton)

    async def _suggestion(self, sid: int) -> dict | None:
        row = await self.db.fetchone("SELECT * FROM suggestions WHERE id=?", (sid,))
        return dict(row) if row else None

    async def render(self, s: dict) -> tuple[discord.Embed, discord.ui.View]:
        rows = await self.db.fetchall("SELECT vote, COUNT(*) AS n FROM suggestion_votes WHERE suggestion_id=? GROUP BY vote",
                                      (s["id"],))
        counts = {r["vote"]: r["n"] for r in rows}
        up, down = counts.get(1, 0), counts.get(-1, 0)
        label, color = STATUS[s["status"]]
        embed = embeds.base(f"💡 Suggestion #{s['id']}", s["content"], color=color)
        author = self.bot.get_user(s["author_id"])
        if author:
            embed.set_author(name=author.display_name, icon_url=author.display_avatar.url)
        embed.add_field(name="Statut", value=label)
        embed.add_field(name="Votes", value=f"👍 {up} · 👎 {down}")
        if s["response"] or s["staff_id"]:
            embed.add_field(name="Réponse du staff",
                            value=(s["response"] or "—") + (f"\n— <@{s['staff_id']}>" if s["staff_id"] else ""), inline=False)
        closed = s["status"] != "open"
        view = discord.ui.View(timeout=None)
        view.add_item(SuggestionButton(s["id"], "up", str(up), disabled=closed))
        view.add_item(SuggestionButton(s["id"], "down", str(down), disabled=closed))
        if not closed:
            view.add_item(SuggestionButton(s["id"], "yes"))
            view.add_item(SuggestionButton(s["id"], "no"))
        return embed, view

    @app_commands.command(name="suggestion", description="Propose une idée pour le serveur")
    @app_commands.guild_only()
    async def suggest(self, interaction: discord.Interaction, idee: app_commands.Range[str, 5, 1500]) -> None:
        cfg = gconf(interaction.guild)
        channel = interaction.guild.get_channel(int(cfg.get("suggestions", "channel", default=0) or 0))  # type: ignore[union-attr]
        if not cfg.get("suggestions", "enabled", default=True) or not isinstance(channel, discord.TextChannel):
            await reply_error(interaction, "Les suggestions ne sont pas configurées sur ce serveur (panel → Suggestions).")
            return
        sid = await self.db.execute(
            "INSERT INTO suggestions (guild_id, channel_id, author_id, content, created_at) VALUES (?,?,?,?,?)",
            (interaction.guild_id, channel.id, interaction.user.id, idee, time.time()))
        s = await self._suggestion(sid)
        embed, view = await self.render(s)  # type: ignore[arg-type]
        msg = await channel.send(embed=embed, view=view)
        await self.db.execute("UPDATE suggestions SET message_id=? WHERE id=?", (msg.id, sid))
        await interaction.response.send_message(
            embed=embeds.success(f"Merci ! Ta suggestion est publiée dans {channel.mention}."), ephemeral=True)

    async def vote(self, interaction: discord.Interaction, sid: int, value: int) -> None:
        s = await self._suggestion(sid)
        if not s or s["status"] != "open":
            await interaction.response.send_message(embed=embeds.error("Cette suggestion est fermée."), ephemeral=True)
            return
        current = await self.db.fetchone("SELECT vote FROM suggestion_votes WHERE suggestion_id=? AND user_id=?",
                                         (sid, interaction.user.id))
        if current and current["vote"] == value:
            await self.db.execute("DELETE FROM suggestion_votes WHERE suggestion_id=? AND user_id=?", (sid, interaction.user.id))
        else:
            await self.db.execute(
                "INSERT INTO suggestion_votes (suggestion_id, user_id, vote) VALUES (?,?,?) "
                "ON CONFLICT(suggestion_id, user_id) DO UPDATE SET vote=excluded.vote", (sid, interaction.user.id, value))
        embed, view = await self.render(s)
        await interaction.response.edit_message(embed=embed, view=view)

    async def ask_response(self, interaction: discord.Interaction, sid: int, accepted: bool) -> None:
        assert isinstance(interaction.user, discord.Member)
        if not is_staff(interaction.user):
            await interaction.response.send_message(embed=embeds.error("Réservé au staff."), ephemeral=True)
            return
        await interaction.response.send_modal(ResponseModal(self, sid, accepted))

    async def respond(self, interaction: discord.Interaction, sid: int, accepted: bool, reason: str) -> None:
        s = await self._suggestion(sid)
        if not s:
            return
        status = "accepted" if accepted else "refused"
        await self.db.execute("UPDATE suggestions SET status=?, response=?, staff_id=? WHERE id=?",
                              (status, reason or None, interaction.user.id, sid))
        s = await self._suggestion(sid)
        embed, view = await self.render(s)  # type: ignore[arg-type]
        channel = self.bot.get_channel(s["channel_id"])  # type: ignore[index]
        if isinstance(channel, discord.TextChannel) and s["message_id"]:  # type: ignore[index]
            try:
                await channel.get_partial_message(s["message_id"]).edit(embed=embed, view=view)  # type: ignore[index]
            except discord.HTTPException:
                pass
        await interaction.response.send_message(embed=embeds.success(
            f"Suggestion #{sid} {'acceptée' if accepted else 'refusée'}."), ephemeral=True)
        author = interaction.guild.get_member(s["author_id"]) if interaction.guild else None  # type: ignore[index]
        if author:
            verdict = "acceptée ✅" if accepted else "refusée ❌"
            server = interaction.guild.name if interaction.guild else "?"
            try:
                await author.send(embed=embeds.info(
                    f"Ta suggestion #{sid} sur **{server}** a été **{verdict}**." + (f"\n\n> {reason}" if reason else "")))
            except discord.HTTPException:
                pass

    # --------------------------------------------------------------------------- #
    #  Starboard
    # --------------------------------------------------------------------------- #
    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent) -> None:
        await self._starboard(payload)

    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, payload: discord.RawReactionActionEvent) -> None:
        await self._starboard(payload)

    async def _starboard(self, payload: discord.RawReactionActionEvent) -> None:
        if not payload.guild_id:
            return
        guild = self.bot.get_guild(payload.guild_id)
        cfg = gconf(payload.guild_id)
        star_channel = guild.get_channel(int(cfg.get("starboard", "channel", default=0) or 0)) if guild else None
        emoji = cfg.get("starboard", "emoji", default="⭐") or "⭐"
        if (not guild or not cfg.get("starboard", "enabled", default=True) or not isinstance(star_channel, discord.TextChannel)
                or str(payload.emoji) != emoji or payload.channel_id == star_channel.id):
            return
        channel = guild.get_channel(payload.channel_id)
        if not isinstance(channel, (discord.TextChannel, discord.Thread)):
            return
        try:
            message = await channel.fetch_message(payload.message_id)
        except discord.HTTPException:
            return
        if message.author.bot:
            return
        stars = next((r.count for r in message.reactions if str(r.emoji) == emoji), 0)
        threshold = max(1, int(cfg.get("starboard", "threshold", default=3) or 3))
        row = await self.db.fetchone("SELECT * FROM starboard WHERE message_id=?", (message.id,))
        content = f"{emoji} **{stars}** · {channel.mention}"
        if row and row["star_message_id"]:
            await self.db.execute("UPDATE starboard SET stars=? WHERE message_id=?", (stars, message.id))
            try:
                await star_channel.get_partial_message(row["star_message_id"]).edit(content=content)
            except discord.HTTPException:
                pass
            return
        if stars < threshold:
            return
        embed = embeds.base(None, message.content or None, color=0xF1C40F)
        embed.set_author(name=message.author.display_name, icon_url=message.author.display_avatar.url)
        embed.add_field(name="Message", value=f"[Aller au message]({message.jump_url})")
        image = next((a.url for a in message.attachments if (a.content_type or "").startswith("image/")), None)
        if image:
            embed.set_image(url=image)
        embed.timestamp = message.created_at
        posted = await star_channel.send(content=content, embed=embed)
        await self.db.execute(
            "INSERT INTO starboard (guild_id, message_id, star_message_id, stars) VALUES (?,?,?,?) "
            "ON CONFLICT(message_id) DO UPDATE SET star_message_id=excluded.star_message_id, stars=excluded.stars",
            (guild.id, message.id, posted.id, stars))

    # --------------------------------------------------------------------------- #
    #  Compteurs (salons renommés toutes les 10 minutes : limite de Discord)
    # --------------------------------------------------------------------------- #
    @staticmethod
    def counter_value(kind: str, guild: discord.Guild, online: int | None) -> int:
        members = guild.members
        return {
            "members": guild.member_count or len(members),
            "humans": sum(1 for m in members if not m.bot),
            "bots": sum(1 for m in members if m.bot),
            "online": online or 0,
            "boosts": guild.premium_subscription_count or 0,
            "channels": len(guild.channels),
            "roles": len(guild.roles) - 1,
        }.get(kind, 0)

    @tasks.loop(minutes=10)
    async def update_counters(self) -> None:
        for guild in self.bot.guilds:
            counters = (gconf(guild).get("counters", default=[]) or [])[:limit_for("counters", is_premium(guild))]
            if not counters:
                continue
            online = None
            if any(c["type"] == "online" for c in counters):
                try:
                    online = (await self.bot.fetch_guild(guild.id, with_counts=True)).approximate_presence_count
                except discord.HTTPException:
                    online = None
            for c in counters:
                channel = guild.get_channel(int(c["channel"]))
                if channel is None:
                    continue
                template = c.get("template") or "{}"
                value = f"{self.counter_value(c['type'], guild, online):,}".replace(",", " ")
                name = (template.replace("{}", value) if "{}" in template else f"{template} {value}")[:100]
                if channel.name != name:
                    try:
                        await channel.edit(name=name, reason="Compteur")
                    except discord.HTTPException as exc:
                        log.info("Compteur %s non mis à jour : %s", channel.id, exc)

    @update_counters.before_loop
    async def _before_counters(self) -> None:
        await self.bot.wait_until_ready()


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Community(bot))
