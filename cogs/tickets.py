"""Tickets : panneau à types, formulaire, claim, priorité, transcript HTML, auto-fermeture, avis,
réponses enregistrées (/ticket reponse) et relance des tickets que personne n'a pris en charge."""
from __future__ import annotations

import asyncio
import html
import io
import logging
import time

import discord
from discord import app_commands
from discord.ext import commands, tasks

from bot import embeds
from bot.config import gconf, limit_for
from bot.i18n import tr
from bot.panels import publish_panel
from bot.premium import is_premium
from bot.utils import is_staff, send_log

log = logging.getLogger("cogs.tickets")

PRIORITIES = {"basse": "🟢", "normale": "🟡", "haute": "🟠", "urgente": "🔴"}
MAX_WARNING_BEFORE = 12 * 3600  # l'avertissement arrive au plus 12 h avant la fermeture automatique


def ticket_due(ticket: dict, alert_minutes: float, close_hours: float, warn: bool, now: float) -> str | None:
    """Ce que le bot doit faire maintenant pour ce ticket : « close », « warn », « alert » ou None."""
    if close_hours > 0:
        idle = now - float(ticket.get("last_activity") or now)
        limit = close_hours * 3600
        if idle >= limit:
            return "close"
        if warn and not ticket.get("warned") and idle >= limit - min(MAX_WARNING_BEFORE, limit / 4):
            return "warn"
    if (alert_minutes > 0 and not ticket.get("claimed_by") and not ticket.get("alerted")
            and now - float(ticket.get("opened_at") or now) >= alert_minutes * 60):
        return "alert"
    return None


def saved_replies(guild: discord.Guild | int | None) -> list[dict]:
    """Réponses enregistrées utilisables (dans la limite gratuit / Premium)."""
    replies = list(gconf(guild).get("tickets", "saved_replies", default=[]) or [])
    gid = guild if isinstance(guild, int) else (guild.id if guild else 0)
    return replies[:limit_for("ticket_replies", is_premium(gid))]


def fill_reply(text: str, user_mention: str, staff_name: str, number: int) -> str:
    return (text.replace("{user}", user_mention).replace("{staff}", staff_name)
            .replace("{number}", str(number)))[:4000]


def ticket_types(guild: discord.Guild | int | None) -> dict[str, dict]:
    return gconf(guild).get("tickets", "types", default={}) or {
        "support": {"label": "Support", "emoji": "🛠️", "description": "Besoin d'aide"}}


# --------------------------------------------------------------------------- #
#  Transcript HTML
# --------------------------------------------------------------------------- #
async def build_transcript(channel: discord.TextChannel, ticket: dict) -> discord.File:
    rows = []
    async for msg in channel.history(limit=None, oldest_first=True):
        content = html.escape(msg.content or "")
        for e in msg.embeds:
            content += f"<div class='embed'><b>{html.escape(e.title or '')}</b><br>{html.escape(e.description or '')}</div>"
        for a in msg.attachments:
            content += f"<div><a href='{html.escape(a.url)}'>📎 {html.escape(a.filename)}</a></div>"
        rows.append(
            f"<div class='msg'><img src='{msg.author.display_avatar.url}'>"
            f"<div><span class='author'>{html.escape(msg.author.display_name)}</span>"
            f"<span class='time'>{msg.created_at:%d/%m/%Y %H:%M}</span>"
            f"<div class='content'>{content}</div></div></div>")
    page = f"""<!doctype html><html lang="fr"><head><meta charset="utf-8">
<title>Transcript {html.escape(channel.name)}</title>
<style>
body{{background:#313338;color:#dbdee1;font-family:system-ui,sans-serif;margin:0;padding:24px}}
h1{{font-size:20px;margin:0 0 4px}} .meta{{color:#949ba4;margin-bottom:24px}}
.msg{{display:flex;gap:12px;padding:8px 0;border-bottom:1px solid #3f4147}}
.msg img{{width:40px;height:40px;border-radius:50%}}
.author{{font-weight:600;color:#f2f3f5;margin-right:8px}} .time{{color:#949ba4;font-size:12px}}
.content{{white-space:pre-wrap;margin-top:2px}}
.embed{{border-left:4px solid #5865f2;background:#2b2d31;padding:8px;margin-top:4px;border-radius:4px}}
a{{color:#00a8fc}}
</style></head><body>
<h1>🎫 {html.escape(channel.name)}</h1>
<div class="meta">Ticket #{ticket['number']} • type : {html.escape(ticket['type'])} •
sujet : {html.escape(ticket.get('subject') or '-')} • {len(rows)} messages</div>
{''.join(rows)}
</body></html>"""
    return discord.File(io.BytesIO(page.encode("utf-8")), filename=f"transcript-{channel.name}.html")


# --------------------------------------------------------------------------- #
#  Vues
# --------------------------------------------------------------------------- #
class TicketTypeSelect(discord.ui.Select):
    """Options propres à chaque serveur ; la vue enregistrée au démarrage reçoit les clics de tous."""

    def __init__(self, guild: discord.Guild | None = None) -> None:
        options = []
        for key, t in list(ticket_types(guild).items())[:25]:
            emoji = t.get("emoji") or None
            options.append(discord.SelectOption(label=t.get("label", key)[:100], value=key,
                                                emoji=emoji, description=(t.get("description") or None)))
        super().__init__(placeholder=tr(guild, "📩 Choisis le type de ticket…"), options=options,
                         custom_id="tickets:open")

    async def callback(self, interaction: discord.Interaction) -> None:
        ticket_type = self.values[0]
        await interaction.response.send_modal(TicketModal(interaction.guild_id, ticket_type))


class TicketPanelView(discord.ui.View):
    def __init__(self, guild: discord.Guild | None = None) -> None:
        super().__init__(timeout=None)
        self.add_item(TicketTypeSelect(guild))


def build_panel(guild: discord.Guild) -> tuple[discord.Embed, discord.ui.View]:
    lines = [f"{t.get('emoji', '🎫')} **{t.get('label')}** — {t.get('description', '')}"
             for t in ticket_types(guild).values()]
    embed = embeds.base(tr(guild, "📩 Besoin d'aide ?"),
                        tr(guild, "Choisis le type de demande dans le menu ci-dessous. "
                                  "Un salon privé sera créé avec le staff.") + "\n\n" + "\n".join(lines), guild=guild)
    return embed, TicketPanelView(guild)


class TicketModal(discord.ui.Modal):
    subject = discord.ui.TextInput(label="Sujet", max_length=100,
                                   placeholder="Résume ta demande en quelques mots")
    details = discord.ui.TextInput(label="Détails", style=discord.TextStyle.paragraph,
                                   required=False, max_length=1000,
                                   placeholder="Explique ta demande (facultatif)")

    def __init__(self, guild_id: int | None, ticket_type: str) -> None:
        info = ticket_types(guild_id).get(ticket_type, {})
        super().__init__(title=f"Ticket — {info.get('label', 'Ticket')}"[:45])
        self.ticket_type = ticket_type
        # 💎 Formulaire personnalisé : jusqu'à 5 questions propres à ce type de ticket
        self.questions: list[str] = list(info.get("questions") or [])[:5] if is_premium(guild_id) else []
        if self.questions:
            self.clear_items()
            for i, question in enumerate(self.questions):
                self.add_item(discord.ui.TextInput(
                    label=question[:45], required=i == 0, max_length=100 if i == 0 else 1000,
                    style=discord.TextStyle.short if i == 0 else discord.TextStyle.paragraph))

    async def on_submit(self, interaction: discord.Interaction) -> None:
        cog: Tickets = interaction.client.get_cog("Tickets")  # type: ignore[assignment]
        if self.questions:
            answers = [str(item) for item in self.children]  # type: ignore[arg-type]
            subject = answers[0][:100] or self.questions[0]
            details = "\n".join(f"**{q}**\n{a or '—'}" for q, a in zip(self.questions, answers, strict=False))
            await cog.open_ticket(interaction, self.ticket_type, subject, details)
            return
        await cog.open_ticket(interaction, self.ticket_type, str(self.subject), str(self.details))


class TicketControlView(discord.ui.View):
    def __init__(self) -> None:
        super().__init__(timeout=None)

    @discord.ui.button(label="Prendre en charge", emoji="🙋", style=discord.ButtonStyle.primary,
                       custom_id="tickets:claim")
    async def claim(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        cog: Tickets = interaction.client.get_cog("Tickets")  # type: ignore[assignment]
        await cog.claim(interaction)

    @discord.ui.button(label="Fermer", emoji="🔒", style=discord.ButtonStyle.danger,
                       custom_id="tickets:close")
    async def close(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await interaction.response.send_message(
            embed=embeds.warning("Fermer ce ticket ? Un transcript sera sauvegardé."),
            view=ConfirmCloseView(), ephemeral=True)


class ConfirmCloseView(discord.ui.View):
    def __init__(self) -> None:
        super().__init__(timeout=60)

    @discord.ui.button(label="Oui, fermer", style=discord.ButtonStyle.danger)
    async def yes(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        cog: Tickets = interaction.client.get_cog("Tickets")  # type: ignore[assignment]
        await interaction.response.edit_message(embed=embeds.info("Fermeture en cours…"), view=None)
        assert isinstance(interaction.channel, discord.TextChannel)
        await cog.close_ticket(interaction.channel, interaction.user, "Fermé manuellement")

    @discord.ui.button(label="Annuler", style=discord.ButtonStyle.secondary)
    async def no(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await interaction.response.edit_message(embed=embeds.info("Fermeture annulée."), view=None)


class FeedbackView(discord.ui.View):
    """Envoyée en DM après fermeture : l'utilisateur note le support de 1 à 5."""

    def __init__(self, guild: discord.Guild, ticket_number: int) -> None:
        super().__init__(timeout=86400)
        self.guild = guild
        self.ticket_number = ticket_number
        for note in range(1, 6):
            button = discord.ui.Button(label="⭐" * note, style=discord.ButtonStyle.secondary)
            button.callback = self._make_callback(note)
            self.add_item(button)

    def _make_callback(self, note: int):
        async def callback(interaction: discord.Interaction) -> None:
            await interaction.response.edit_message(
                embed=embeds.success(f"Merci pour ton avis : {'⭐' * note}"), view=None)
            await send_log(self.guild, embeds.info(
                f"Ticket #{self.ticket_number} noté **{note}/5** par {interaction.user.mention}",
                "⭐ Avis ticket"), channel="ticket_logs")
            self.stop()
        return callback


# --------------------------------------------------------------------------- #
#  Cog
# --------------------------------------------------------------------------- #
class Tickets(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.open_channels: set[int] = set()  # évite une requête en base à chaque message

    @property
    def db(self):
        return self.bot.db  # type: ignore[attr-defined]

    async def cog_load(self) -> None:
        rows = await self.db.fetchall("SELECT channel_id FROM tickets WHERE status='open'")
        self.open_channels = {r["channel_id"] for r in rows}
        self.bot.add_view(TicketPanelView())
        self.bot.add_view(TicketControlView())
        self.auto_close.start()

    async def cog_unload(self) -> None:
        self.auto_close.cancel()

    async def get_ticket(self, channel_id: int) -> dict | None:
        row = await self.db.fetchone(
            "SELECT * FROM tickets WHERE channel_id=? AND status='open'", (channel_id,))
        return dict(row) if row else None

    # --- ouverture -------------------------------------------------------
    async def open_ticket(self, interaction: discord.Interaction, ticket_type: str,
                          subject: str, details: str = "") -> None:
        guild = interaction.guild
        member = interaction.user
        assert guild and isinstance(member, discord.Member)

        cfg = gconf(guild)
        if ticket_type not in ticket_types(guild):
            await interaction.response.send_message(
                embed=embeds.error("Ce type de ticket n'existe plus. Le panneau doit être republié."), ephemeral=True)
            return
        max_open = int(cfg.get("tickets", "max_open_per_user", default=1) or 1)
        row = await self.db.fetchone(
            "SELECT COUNT(*) AS n FROM tickets WHERE guild_id=? AND user_id=? AND status='open'",
            (guild.id, member.id))
        if row["n"] >= max_open:
            await interaction.response.send_message(
                embed=embeds.error(f"Tu as déjà {row['n']} ticket(s) ouvert(s). Ferme-le avant d'en ouvrir un autre."),
                ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True, thinking=True)
        category = guild.get_channel(cfg.channel_id("ticket_category"))
        staff = guild.get_role(cfg.role_id("staff"))
        overwrites: dict = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            member: discord.PermissionOverwrite(view_channel=True, send_messages=True,
                                                attach_files=True, read_message_history=True),
            guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True,
                                                  manage_channels=True, read_message_history=True),
        }
        if staff:
            overwrites[staff] = discord.PermissionOverwrite(view_channel=True, send_messages=True,
                                                            read_message_history=True)

        last = await self.db.fetchone("SELECT MAX(number) AS n FROM tickets WHERE guild_id=?", (guild.id,))
        number = (last["n"] or 0) + 1
        info = ticket_types(guild).get(ticket_type, {"label": ticket_type, "emoji": "🎫"})
        channel = await guild.create_text_channel(
            name=f"{ticket_type}-{number:04d}",
            category=category if isinstance(category, discord.CategoryChannel) else None,
            overwrites=overwrites,
            topic=f"Ticket #{number} de {member} ({member.id}) — {subject}",
            reason=f"Ticket ouvert par {member}")

        now = time.time()
        await self.db.execute(
            "INSERT INTO tickets (channel_id, guild_id, user_id, number, type, subject, opened_at, last_activity) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (channel.id, guild.id, member.id, number, ticket_type, subject, now, now))
        self.open_channels.add(channel.id)

        embed = embeds.base(f"{info.get('emoji', '🎫')} Ticket #{number} — {info['label']}",
                            f"Bonjour {member.mention}, un membre du staff va te répondre rapidement.", guild=guild)
        embed.add_field(name="Sujet", value=subject, inline=False)
        if details:
            embed.add_field(name="Détails", value=details[:1024], inline=False)
        embed.add_field(name="Priorité", value=f"{PRIORITIES['normale']} normale")
        mention = f"{member.mention} {staff.mention if staff else ''}"
        await channel.send(content=mention, embed=embed, view=TicketControlView(),
                           allowed_mentions=discord.AllowedMentions(users=True, roles=True))

        await interaction.followup.send(embed=embeds.success(f"Ton ticket est ouvert : {channel.mention}"),
                                        ephemeral=True)
        await send_log(guild, embeds.success(
            f"#{number} **{info['label']}** par {member.mention} → {channel.mention}\nSujet : {subject}",
            "🎫 Ticket ouvert"), channel="ticket_logs")

    # --- claim -----------------------------------------------------------
    async def claim(self, interaction: discord.Interaction) -> None:
        assert isinstance(interaction.user, discord.Member)
        ticket = await self.get_ticket(interaction.channel_id or 0)
        if not ticket:
            await interaction.response.send_message(embed=embeds.error("Ce salon n'est pas un ticket ouvert."), ephemeral=True)
            return
        if not is_staff(interaction.user):
            await interaction.response.send_message(embed=embeds.error("Réservé au staff."), ephemeral=True)
            return
        if ticket["claimed_by"]:
            await interaction.response.send_message(
                embed=embeds.info(f"Déjà pris en charge par <@{ticket['claimed_by']}>."), ephemeral=True)
            return
        await self.db.execute("UPDATE tickets SET claimed_by=? WHERE channel_id=?",
                              (interaction.user.id, ticket["channel_id"]))
        await interaction.response.send_message(
            embed=embeds.success(f"{interaction.user.mention} prend en charge ce ticket.", "🙋 Pris en charge"))

    # --- fermeture -------------------------------------------------------
    async def close_ticket(self, channel: discord.TextChannel, closer: discord.abc.User, reason: str) -> None:
        ticket = await self.get_ticket(channel.id)
        if not ticket:
            return
        await self.db.execute("UPDATE tickets SET status='closed', closed_at=? WHERE channel_id=?",
                              (time.time(), channel.id))
        self.open_channels.discard(channel.id)
        await channel.send(embed=embeds.warning(f"Ticket fermé par {closer.mention}. Suppression dans 5 secondes…"))

        cfg = gconf(channel.guild)
        # Transcript HTML et avis ⭐ : Premium (config forcée à False en version gratuite)
        with_transcript = bool(cfg.get("tickets", "transcripts", default=False))
        with_feedback = bool(cfg.get("tickets", "feedback", default=False))
        data = filename = None
        if with_transcript:
            transcript = await build_transcript(channel, ticket)
            data, filename = transcript.fp.read(), transcript.filename

        def attachment() -> dict:
            return {"file": discord.File(io.BytesIO(data), filename=filename)} if data else {}

        log_embed = embeds.warning(
            f"#{ticket['number']} de <@{ticket['user_id']}> fermé par {closer.mention}\n"
            f"Raison : {reason}\nPris en charge par : "
            f"{'<@' + str(ticket['claimed_by']) + '>' if ticket['claimed_by'] else 'personne'}",
            "🔒 Ticket fermé")
        log_channel = channel.guild.get_channel(cfg.channel_id("ticket_logs") or cfg.channel_id("logs"))
        if isinstance(log_channel, discord.TextChannel):
            await log_channel.send(embed=log_embed, **attachment())

        owner = channel.guild.get_member(ticket["user_id"])
        if owner and (data or with_feedback):
            text = f"Ton ticket #{ticket['number']} sur **{channel.guild.name}** est fermé."
            if data:
                text += "\nVoici le transcript de la conversation."
            if with_feedback:
                text += "\nComment s'est passé le support ?"
            kwargs = attachment()
            if with_feedback:
                kwargs["view"] = FeedbackView(channel.guild, ticket["number"])
            try:
                await owner.send(embed=embeds.info(text), **kwargs)
            except discord.HTTPException:
                pass

        await asyncio.sleep(5)
        try:
            await channel.delete(reason=f"Ticket fermé : {reason}")
        except discord.HTTPException as exc:
            log.warning("Suppression du ticket impossible : %s", exc)

    # --- activité / auto-fermeture --------------------------------------
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if message.channel.id in self.open_channels and not message.author.bot:
            await self.db.execute(
                "UPDATE tickets SET last_activity=?, warned=0 WHERE channel_id=? AND status='open'",
                (time.time(), message.channel.id))

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel: discord.abc.GuildChannel) -> None:
        if channel.id not in self.open_channels:
            return
        self.open_channels.discard(channel.id)
        await self.db.execute(
            "UPDATE tickets SET status='closed', closed_at=? WHERE channel_id=? AND status='open'",
            (time.time(), channel.id))

    @tasks.loop(minutes=10)
    async def auto_close(self) -> None:
        """Relance les tickets sans prise en charge, prévient avant la fermeture auto, puis ferme."""
        rows = await self.db.fetchall("SELECT * FROM tickets WHERE status='open'")
        now = time.time()
        for row in rows:
            ticket = dict(row)
            cfg = gconf(ticket["guild_id"])
            hours = float(cfg.get("tickets", "inactive_close_hours", default=0) or 0)
            action = ticket_due(ticket, float(cfg.get("tickets", "unclaimed_alert_minutes", default=0) or 0), hours,
                                bool(cfg.get("tickets", "inactive_warning", default=True)), now)
            channel = self.bot.get_channel(ticket["channel_id"])
            if action is None or not isinstance(channel, discord.TextChannel):
                continue
            try:
                await self.run_due(channel, ticket, action, hours, now)
            except discord.HTTPException as exc:
                log.warning("Ticket %s : action « %s » impossible (%s)", ticket["channel_id"], action, exc)

    async def run_due(self, channel: discord.TextChannel, ticket: dict, action: str, hours: float, now: float) -> None:
        if action == "close":
            assert self.bot.user
            await self.close_ticket(channel, self.bot.user, f"Inactif depuis {hours:g} h")
        elif action == "warn":
            left = max(1, round((hours * 3600 - (now - float(ticket["last_activity"]))) / 3600))
            await self.db.execute("UPDATE tickets SET warned=1 WHERE channel_id=?", (channel.id,))
            await channel.send(content=f"<@{ticket['user_id']}>", embed=embeds.warning(
                f"Ce ticket sera fermé automatiquement dans environ {left} h s'il n'y a pas de nouveau message. "
                "Écris ici si ta demande n'est pas réglée.", "⏳ Ticket inactif"),
                allowed_mentions=discord.AllowedMentions(users=True))
        elif action == "alert":
            await self.db.execute("UPDATE tickets SET alerted=1 WHERE channel_id=?", (channel.id,))
            staff = channel.guild.get_role(gconf(channel.guild).role_id("staff"))
            minutes = round((now - float(ticket["opened_at"])) / 60)
            await channel.send(content=staff.mention if staff else None, embed=embeds.warning(
                f"Ce ticket attend une prise en charge depuis {minutes} min. Clique sur **🙋 Prendre en charge**.",
                "⏰ Ticket en attente"), allowed_mentions=discord.AllowedMentions(roles=True))
            await send_log(channel.guild, embeds.warning(
                f"Ticket #{ticket['number']} ({channel.mention}) sans prise en charge depuis {minutes} min.",
                "⏰ Ticket en attente"), channel="ticket_logs")

    @auto_close.before_loop
    async def _before_auto_close(self) -> None:
        await self.bot.wait_until_ready()

    # --- commandes -------------------------------------------------------
    @app_commands.command(name="setup_ticket", description="Envoie le panneau de tickets ici")
    @app_commands.default_permissions(administrator=True)
    @app_commands.guild_only()
    async def setup_ticket(self, interaction: discord.Interaction) -> None:
        assert interaction.guild and isinstance(interaction.channel, discord.TextChannel)
        await publish_panel(self.bot, interaction.guild, "tickets", interaction.channel)
        await interaction.response.send_message(embed=embeds.success("Panneau envoyé."), ephemeral=True)

    ticket = app_commands.Group(name="ticket", description="Gestion des tickets", guild_only=True)

    async def _staff_ticket(self, interaction: discord.Interaction) -> dict | None:
        assert isinstance(interaction.user, discord.Member)
        ticket = await self.get_ticket(interaction.channel_id or 0)
        if not ticket:
            await interaction.response.send_message(
                embed=embeds.error("Utilise cette commande dans un ticket ouvert."), ephemeral=True)
            return None
        if not is_staff(interaction.user):
            await interaction.response.send_message(embed=embeds.error("Réservé au staff."), ephemeral=True)
            return None
        return ticket

    @ticket.command(name="add", description="Ajoute un membre au ticket")
    async def ticket_add(self, interaction: discord.Interaction, membre: discord.Member) -> None:
        if not await self._staff_ticket(interaction):
            return
        assert isinstance(interaction.channel, discord.TextChannel)
        await interaction.channel.set_permissions(membre, view_channel=True, send_messages=True,
                                                  read_message_history=True)
        await interaction.response.send_message(embed=embeds.success(f"{membre.mention} a été ajouté au ticket."))

    @ticket.command(name="remove", description="Retire un membre du ticket")
    async def ticket_remove(self, interaction: discord.Interaction, membre: discord.Member) -> None:
        if not await self._staff_ticket(interaction):
            return
        assert isinstance(interaction.channel, discord.TextChannel)
        await interaction.channel.set_permissions(membre, overwrite=None)
        await interaction.response.send_message(embed=embeds.success(f"{membre.mention} a été retiré du ticket."))

    @ticket.command(name="priority", description="Change la priorité du ticket")
    @app_commands.choices(niveau=[app_commands.Choice(name=f"{e} {p}", value=p) for p, e in PRIORITIES.items()])
    async def ticket_priority(self, interaction: discord.Interaction, niveau: app_commands.Choice[str]) -> None:
        ticket = await self._staff_ticket(interaction)
        if not ticket:
            return
        await self.db.execute("UPDATE tickets SET priority=? WHERE channel_id=?", (niveau.value, ticket["channel_id"]))
        assert isinstance(interaction.channel, discord.TextChannel)
        emoji = PRIORITIES[niveau.value]
        base_name = interaction.channel.name.lstrip("🟢🟡🟠🔴-")
        try:
            await interaction.channel.edit(name=f"{emoji}-{base_name}" if niveau.value != "normale" else base_name)
        except discord.HTTPException:
            pass  # renommage limité à 2 fois / 10 min par Discord
        await interaction.response.send_message(embed=embeds.success(f"Priorité : {emoji} **{niveau.value}**"))

    @ticket.command(name="close", description="Ferme le ticket actuel")
    async def ticket_close(self, interaction: discord.Interaction, raison: str = "Aucune raison") -> None:
        ticket = await self.get_ticket(interaction.channel_id or 0)
        assert isinstance(interaction.user, discord.Member)
        if not ticket or not (is_staff(interaction.user) or ticket["user_id"] == interaction.user.id):
            await interaction.response.send_message(embed=embeds.error("Impossible ici."), ephemeral=True)
            return
        await interaction.response.send_message(embed=embeds.info("Fermeture en cours…"), ephemeral=True)
        assert isinstance(interaction.channel, discord.TextChannel)
        await self.close_ticket(interaction.channel, interaction.user, raison)

    @ticket.command(name="reponse", description="Envoie une réponse enregistrée dans le ticket")
    @app_commands.describe(nom="Nom de la réponse (réglées dans le panel → Tickets)")
    async def ticket_reply(self, interaction: discord.Interaction, nom: str) -> None:
        ticket = await self._staff_ticket(interaction)
        if not ticket:
            return
        assert interaction.guild and isinstance(interaction.channel, discord.TextChannel)
        reply = next((r for r in saved_replies(interaction.guild)
                      if str(r.get("name", "")).strip().lower() == nom.strip().lower()), None)
        if reply is None:
            await interaction.response.send_message(embed=embeds.error(
                "Réponse introuvable. Elles se règlent dans le panel → Tickets (5 en gratuit, 50 en 💎 Premium)."),
                ephemeral=True)
            return
        text = fill_reply(str(reply.get("content", "")), f"<@{ticket['user_id']}>",
                          interaction.user.display_name, int(ticket["number"]))
        embed = embeds.base(None, text, guild=interaction.guild)
        embed.set_author(name=interaction.user.display_name, icon_url=interaction.user.display_avatar.url)
        await interaction.response.send_message(embed=embed, allowed_mentions=discord.AllowedMentions(users=True))
        if not ticket["claimed_by"]:  # répondre, c'est prendre en charge
            await self.db.execute("UPDATE tickets SET claimed_by=? WHERE channel_id=?",
                                  (interaction.user.id, ticket["channel_id"]))

    @ticket_reply.autocomplete("nom")
    async def _reply_autocomplete(self, interaction: discord.Interaction, current: str):
        current = current.lower()
        names = [str(r.get("name", "")) for r in saved_replies(interaction.guild)]
        return [app_commands.Choice(name=n[:100], value=n[:100]) for n in names if current in n.lower()][:25]

    @ticket.command(name="stats", description="Statistiques des tickets")
    async def ticket_stats(self, interaction: discord.Interaction) -> None:
        assert isinstance(interaction.user, discord.Member)
        if not is_staff(interaction.user):
            await interaction.response.send_message(embed=embeds.error("Réservé au staff."), ephemeral=True)
            return
        gid = interaction.guild_id
        total = await self.db.fetchone("SELECT COUNT(*) AS n FROM tickets WHERE guild_id=?", (gid,))
        open_ = await self.db.fetchone("SELECT COUNT(*) AS n FROM tickets WHERE guild_id=? AND status='open'", (gid,))
        avg = await self.db.fetchone(
            "SELECT AVG(closed_at - opened_at) AS s FROM tickets WHERE guild_id=? AND closed_at IS NOT NULL", (gid,))
        top = await self.db.fetchall(
            "SELECT claimed_by, COUNT(*) AS n FROM tickets WHERE guild_id=? AND claimed_by IS NOT NULL "
            "GROUP BY claimed_by ORDER BY n DESC LIMIT 5", (gid,))
        embed = embeds.base("📊 Statistiques tickets")
        embed.add_field(name="Total", value=str(total["n"]))
        embed.add_field(name="Ouverts", value=str(open_["n"]))
        avg_h = (avg["s"] or 0) / 3600
        embed.add_field(name="Durée moyenne", value=f"{avg_h:.1f} h")
        if top:
            embed.add_field(name="Top staff", inline=False,
                            value="\n".join(f"<@{r['claimed_by']}> — {r['n']}" for r in top))
        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Tickets(bot))
