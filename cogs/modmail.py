"""Modmail : un membre écrit au bot en message privé → un ticket « modmail » s'ouvre pour le staff.
Les messages sont relayés dans les deux sens ; un message du staff qui commence par « ! » ou « // » reste
une note interne (non envoyée). Fermeture avec /ticket close ou le bouton 🔒 (transcript inclus)."""
from __future__ import annotations

import logging
import time

import discord
from discord.ext import commands

from bot import embeds
from bot.config import gconf
from bot.translate import use_language
from bot.utils import send_log

log = logging.getLogger("cogs.modmail")
NOTE_PREFIXES = ("!", "//")
DEFAULT_GREETING = ("📬 Ton message a été transmis au staff de **{server}**. Réponds ici pour continuer la conversation ; "
                    "le staff te répondra dans ce message privé.")


def modmail_ready(guild: discord.Guild) -> bool:
    cfg = gconf(guild)
    return bool(cfg.get("modmail", "enabled", default=False)) and isinstance(
        guild.get_channel(cfg.channel_id("ticket_category")), discord.CategoryChannel)


class GuildChoice(discord.ui.View):
    """Le membre est sur plusieurs serveurs avec modmail : il choisit lequel contacter."""

    def __init__(self, cog: "Modmail", guilds: list[discord.Guild], first: discord.Message) -> None:
        super().__init__(timeout=300)
        self.cog, self.first = cog, first
        select = discord.ui.Select(placeholder="Quel serveur veux-tu contacter ?", options=[
            discord.SelectOption(label=g.name[:100], value=str(g.id)) for g in guilds[:25]])
        select.callback = self.chosen
        self.add_item(select)

    async def chosen(self, interaction: discord.Interaction) -> None:
        guild = self.cog.bot.get_guild(int(interaction.data["values"][0]))  # type: ignore[index]
        await interaction.response.edit_message(content=None, embed=embeds.info("Ouverture de la conversation…"), view=None)
        if guild:
            await self.cog.open(guild, interaction.user, self.first)
        self.stop()


class Modmail(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.warned: dict[int, float] = {}

    @property
    def db(self):
        return self.bot.db  # type: ignore[attr-defined]

    @property
    def tickets(self):
        return self.bot.get_cog("Tickets")

    async def open_ticket_for(self, user_id: int) -> dict | None:
        row = await self.db.fetchone(
            "SELECT * FROM tickets WHERE user_id=? AND type='modmail' AND status='open' ORDER BY opened_at DESC LIMIT 1",
            (user_id,))
        return dict(row) if row else None

    def _relay_embed(self, message: discord.Message, author_name: str, author_icon: str | None, color: int) -> discord.Embed:
        embed = embeds.base(None, message.content or None, color=color)
        embed.set_author(name=author_name, icon_url=author_icon)
        files = [a for a in message.attachments]
        if files:
            image = next((a.url for a in files if (a.content_type or "").startswith("image/")), None)
            if image:
                embed.set_image(url=image)
            embed.add_field(name="Pièces jointes", value="\n".join(f"[{a.filename}]({a.url})" for a in files)[:1024])
        return embed

    # --- ouverture ---------------------------------------------------------
    async def open(self, guild: discord.Guild, user: discord.abc.User, first: discord.Message) -> None:
        cfg = gconf(guild)
        category = guild.get_channel(cfg.channel_id("ticket_category"))
        staff = guild.get_role(cfg.role_id("staff"))
        overwrites: dict = {guild.default_role: discord.PermissionOverwrite(view_channel=False),
                            guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True, manage_channels=True,
                                                                  embed_links=True, attach_files=True)}
        if staff:
            overwrites[staff] = discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True)
        last = await self.db.fetchone("SELECT MAX(number) AS n FROM tickets WHERE guild_id=?", (guild.id,))
        number = (last["n"] or 0) + 1
        try:
            channel = await guild.create_text_channel(
                f"modmail-{number:04d}", category=category if isinstance(category, discord.CategoryChannel) else None,
                overwrites=overwrites, topic=f"Modmail #{number} avec {user} ({user.id})", reason=f"Modmail de {user}")
        except discord.HTTPException as exc:
            log.warning("Modmail impossible sur %s : %s", guild.id, exc)
            await first.channel.send(embed=embeds.error("Impossible d'ouvrir la conversation avec ce serveur pour le moment."))
            return
        now = time.time()
        subject = (first.content or "Pièce jointe")[:100]
        await self.db.execute(
            "INSERT INTO tickets (channel_id, guild_id, user_id, number, type, subject, opened_at, last_activity) "
            "VALUES (?,?,?,?,?,?,?,?)", (channel.id, guild.id, user.id, number, "modmail", subject, now, now))
        if self.tickets:
            self.tickets.open_channels.add(channel.id)
            from cogs.tickets import TicketControlView
            view = TicketControlView()
        else:
            view = None
        member = guild.get_member(user.id)
        intro = embeds.base(f"📬 Modmail #{number}", f"Conversation privée avec {user.mention} (`{user.id}`).\n"
                            "Écris ici pour lui répondre. Commence par `!` ou `//` pour une note interne (non envoyée).",
                            guild=guild)
        if member and member.joined_at:
            intro.add_field(name="Sur le serveur depuis", value=discord.utils.format_dt(member.joined_at, "R"))
        intro.add_field(name="Compte créé", value=discord.utils.format_dt(user.created_at, "R"))
        await channel.send(content=staff.mention if staff else None, embed=intro, view=view,
                           allowed_mentions=discord.AllowedMentions(roles=True))
        await channel.send(embed=self._relay_embed(first, str(user), user.display_avatar.url, 0x5865F2))
        greeting = cfg.get("modmail", "greeting", default="") or DEFAULT_GREETING
        greeting = greeting.replace("{server}", guild.name).replace("{name}", getattr(user, "display_name", user.name))
        with use_language(guild):  # message privé : langue du serveur contacté
            await first.channel.send(embed=embeds.success(greeting, "📬 Message transmis"))
        await send_log(guild, embeds.info(f"{user.mention} a ouvert le modmail #{number} → {channel.mention}", "📬 Modmail"),
                       channel="ticket_logs")

    # --- relais --------------------------------------------------------------
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if message.author.bot:
            return
        if message.guild is None:
            await self.from_user(message)
        elif self.tickets and message.channel.id in self.tickets.open_channels:
            await self.from_staff(message)

    async def from_user(self, message: discord.Message) -> None:
        ticket = await self.open_ticket_for(message.author.id)
        if ticket:
            channel = self.bot.get_channel(ticket["channel_id"])
            if isinstance(channel, discord.TextChannel):
                author = message.author
                await channel.send(embed=self._relay_embed(message, str(author), author.display_avatar.url, 0x5865F2))
                await self.db.execute("UPDATE tickets SET last_activity=? WHERE channel_id=?", (time.time(), channel.id))
                try:
                    await message.add_reaction("✅")
                except discord.HTTPException:
                    pass
            return
        guilds = [g for g in self.bot.guilds if g.get_member(message.author.id) and modmail_ready(g)]
        if not guilds:
            if time.time() - self.warned.get(message.author.id, 0) > 3600:  # une fois par heure maximum
                self.warned[message.author.id] = time.time()
                await message.channel.send(embed=embeds.info(
                    "Aucun de tes serveurs n'a activé le modmail. Utilise le panneau de tickets du serveur."))
            return
        if len(guilds) == 1:
            await self.open(guilds[0], message.author, message)
        else:
            await message.channel.send(embed=embeds.info("Tu es sur plusieurs serveurs : choisis celui à contacter."),
                                       view=GuildChoice(self, guilds, message))

    async def from_staff(self, message: discord.Message) -> None:
        row = await self.db.fetchone("SELECT * FROM tickets WHERE channel_id=? AND status='open' AND type='modmail'",
                                     (message.channel.id,))
        if not row or not message.content and not message.attachments:
            return
        if message.content.startswith(NOTE_PREFIXES):
            return  # note interne
        guild = message.guild
        assert guild
        anonymous = gconf(guild).get("modmail", "anonymous_staff", default=False)
        name = f"Staff de {guild.name}" if anonymous else f"{message.author.display_name} · {guild.name}"
        icon = guild.icon.url if anonymous and guild.icon else message.author.display_avatar.url
        try:
            user = self.bot.get_user(row["user_id"]) or await self.bot.fetch_user(row["user_id"])
            with use_language(guild):
                await user.send(embed=self._relay_embed(message, name, icon, gconf(guild).color))
            await message.add_reaction("📨")
        except discord.HTTPException:
            await message.add_reaction("❌")
            await message.channel.send(embed=embeds.warning("Message non délivré : le membre a fermé ses messages privés."),
                                       delete_after=10)



async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Modmail(bot))
