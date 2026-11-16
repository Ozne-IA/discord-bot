"""Événements avec inscription + rappel, et tournois à élimination directe.

/evenement creer|liste|annuler : un message avec ✅ Participer / ❌ Me retirer, places limitées en option,
  rappel (mention des inscrits) X minutes avant le début.
/tournoi creer|lancer|resultat|voir|annuler : inscriptions par bouton, tableau tiré au sort, le staff
  saisit les gagnants, le champion reçoit la récompense. 16 joueurs max en gratuit, 💎 64 en Premium.
Gestion : « Gérer le serveur » ou le rôle gestionnaire d'événements (panel).
"""
from __future__ import annotations

import logging
import re
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import discord
from discord import app_commands
from discord.ext import commands, tasks

from bot import bracket, embeds
from bot.config import gconf, limit_for
from bot.premium import is_premium
from bot.utils import reply_error

log = logging.getLogger("cogs.events")
_DATE = re.compile(r"^(\d{1,2})[/.-](\d{1,2})(?:[/.-](\d{2,4}))?$")
_TIME = re.compile(r"^(\d{1,2})\s*(?:[:hH]\s*(\d{2})?)?$")


def parse_when(day: str, hour: str, tz: ZoneInfo, now: datetime | None = None) -> datetime | None:
    """« 25/12 » + « 20h30 » (heure du serveur) → date. Sans année : la prochaine occurrence."""
    d, t = _DATE.match(day.strip()), _TIME.match(hour.strip())
    if not d or not t:
        return None
    now = now or datetime.now(tz)
    year = int(d[3]) + (2000 if d[3] and len(d[3]) == 2 else 0) if d[3] else now.year
    try:
        when = datetime(year, int(d[2]), int(d[1]), int(t[1]), int(t[2] or 0), tzinfo=tz)
    except ValueError:
        return None
    if not d[3] and when < now - timedelta(hours=1):
        when = when.replace(year=year + 1)
    return when


def server_tz(guild: discord.Guild | None) -> ZoneInfo:
    try:
        return ZoneInfo(gconf(guild).get("birthdays", "timezone", default="Europe/Paris") or "UTC")
    except Exception:
        return ZoneInfo("UTC")


class EventButton(discord.ui.DynamicItem[discord.ui.Button], template=r"event:(?P<id>\d+):(?P<action>join|leave)"):
    def __init__(self, event_id: int, action: str) -> None:
        join = action == "join"
        super().__init__(discord.ui.Button(
            label="Participer" if join else "Me retirer", emoji="✅" if join else "❌",
            style=discord.ButtonStyle.success if join else discord.ButtonStyle.secondary,
            custom_id=f"event:{event_id}:{action}"))
        self.event_id, self.action = event_id, action

    @classmethod
    async def from_custom_id(cls, interaction, item, match):
        return cls(int(match["id"]), match["action"])

    async def callback(self, interaction: discord.Interaction) -> None:
        cog: Events = interaction.client.get_cog("Events")  # type: ignore[assignment]
        await cog.event_click(interaction, self.event_id, self.action == "join")


class TourneyButton(discord.ui.DynamicItem[discord.ui.Button], template=r"tourney:(?P<id>\d+):(?P<action>join|leave)"):
    def __init__(self, tid: int, action: str) -> None:
        join = action == "join"
        super().__init__(discord.ui.Button(
            label="S'inscrire" if join else "Me désinscrire", emoji="⚔️" if join else "❌",
            style=discord.ButtonStyle.primary if join else discord.ButtonStyle.secondary,
            custom_id=f"tourney:{tid}:{action}"))
        self.tid, self.action = tid, action

    @classmethod
    async def from_custom_id(cls, interaction, item, match):
        return cls(int(match["id"]), match["action"])

    async def callback(self, interaction: discord.Interaction) -> None:
        cog: Events = interaction.client.get_cog("Events")  # type: ignore[assignment]
        await cog.tourney_click(interaction, self.tid, self.action == "join")


def buttons(kind: str, item_id: int, closed: bool = False) -> discord.ui.View | None:
    if closed:
        return None
    view = discord.ui.View(timeout=None)
    cls = EventButton if kind == "event" else TourneyButton
    view.add_item(cls(item_id, "join"))
    view.add_item(cls(item_id, "leave"))
    return view


class Events(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @property
    def db(self):
        return self.bot.db  # type: ignore[attr-defined]

    async def cog_load(self) -> None:
        self.bot.add_dynamic_items(EventButton, TourneyButton)
        self.reminders.start()

    async def cog_unload(self) -> None:
        self.reminders.cancel()

    async def _manager(self, interaction: discord.Interaction) -> bool:
        member = interaction.user
        assert isinstance(member, discord.Member)
        cfg = gconf(interaction.guild)
        if not cfg.get("events", "enabled", default=True):
            await reply_error(interaction, "Les événements et tournois sont désactivés sur ce serveur.")
            return False
        manager = int(cfg.get("events", "manager_role", default=0) or 0)
        if member.guild_permissions.manage_guild or any(r.id == manager for r in member.roles):
            return True
        await reply_error(interaction, "Il faut la permission « Gérer le serveur » ou le rôle gestionnaire d'événements.")
        return False

    # ================================================================== événements
    async def event_embed(self, ev: dict) -> discord.Embed:
        rows = await self.db.fetchall("SELECT user_id FROM event_participants WHERE event_id=?", (ev["id"],))
        guild = self.bot.get_guild(ev["guild_id"])
        title = ("❌ " if ev["cancelled"] else "📅 ") + ev["title"]
        embed = embeds.base(title[:256], ev["description"] or None, guild=guild)
        start = int(ev["starts_at"])
        embed.add_field(name="Quand", value=f"<t:{start}:F> (<t:{start}:R>)", inline=False)
        places = f"{len(rows)}/{ev['max_places']}" if ev["max_places"] else str(len(rows))
        names = " ".join(f"<@{r['user_id']}>" for r in rows[:40]) + (" …" if len(rows) > 40 else "")
        embed.add_field(name=f"Participants ({places})", value=names or "Personne pour l'instant", inline=False)
        if ev["cancelled"]:
            embed.add_field(name="Statut", value="Événement annulé", inline=False)
        embed.set_footer(text=f"Événement #{ev['id']}")
        return embed

    async def refresh_event(self, ev: dict) -> None:
        channel = self.bot.get_channel(ev["channel_id"])
        if not isinstance(channel, discord.TextChannel) or not ev["message_id"]:
            return
        try:
            msg = channel.get_partial_message(ev["message_id"])
            closed = bool(ev["cancelled"]) or ev["starts_at"] < time.time()
            await msg.edit(embed=await self.event_embed(ev), view=buttons("event", ev["id"], closed))
        except discord.HTTPException:
            pass

    async def get_event(self, event_id: int, guild_id: int | None) -> dict | None:
        row = await self.db.fetchone("SELECT * FROM events WHERE id=? AND guild_id=?", (event_id, guild_id))
        return dict(row) if row else None

    async def event_click(self, interaction: discord.Interaction, event_id: int, join: bool) -> None:
        ev = await self.get_event(event_id, interaction.guild_id)
        if not ev or ev["cancelled"] or ev["starts_at"] < time.time():
            await reply_error(interaction, "Les inscriptions à cet événement sont fermées.")
            return
        uid = interaction.user.id
        if join:
            count = (await self.db.fetchone("SELECT COUNT(*) AS n FROM event_participants WHERE event_id=?",
                                            (event_id,)))["n"]
            if ev["max_places"] and count >= ev["max_places"]:
                await reply_error(interaction, "Désolé, l'événement est complet.")
                return
            await self.db.execute("INSERT OR IGNORE INTO event_participants (event_id, user_id) VALUES (?,?)", (event_id, uid))
            text = f"Tu participes à **{ev['title']}**. Tu seras prévenu(e) avant le début."
        else:
            await self.db.execute("DELETE FROM event_participants WHERE event_id=? AND user_id=?", (event_id, uid))
            text = f"Tu ne participes plus à **{ev['title']}**."
        await interaction.response.send_message(embed=embeds.success(text), ephemeral=True)
        await self.refresh_event(ev)

    ev_group = app_commands.Group(name="evenement", description="Événements avec inscription et rappel", guild_only=True)

    @ev_group.command(name="creer", description="Crée un événement (date et heure du serveur)")
    @app_commands.describe(titre="Nom de l'événement", date="Ex : 25/12 ou 25/12/2026", heure="Ex : 20h30 ou 20:30",
                           description="Détails (facultatif)", places="Nombre de places (0 = illimité)",
                           salon="Salon où publier (vide = ici)")
    async def ev_create(self, interaction: discord.Interaction, titre: app_commands.Range[str, 1, 100], date: str,
                        heure: str, description: app_commands.Range[str, 0, 1500] = "",
                        places: app_commands.Range[int, 0, 1000] = 0, salon: discord.TextChannel | None = None) -> None:
        if not await self._manager(interaction):
            return
        when = parse_when(date, heure, server_tz(interaction.guild))
        if not when or when.timestamp() < time.time():
            await reply_error(interaction, "Date ou heure invalide (ou déjà passée). Exemple : date `25/12`, heure `20h30`.")
            return
        channel = salon or interaction.channel
        if not isinstance(channel, discord.TextChannel):
            await reply_error(interaction, "Choisis un salon textuel.")
            return
        eid = await self.db.execute(
            "INSERT INTO events (guild_id, channel_id, title, description, starts_at, max_places, created_by) "
            "VALUES (?,?,?,?,?,?,?)", (interaction.guild_id, channel.id, titre, description, when.timestamp(), places,
                                       interaction.user.id))
        ev = await self.get_event(eid, interaction.guild_id)
        assert ev
        msg = await channel.send(embed=await self.event_embed(ev), view=buttons("event", eid))
        await self.db.execute("UPDATE events SET message_id=? WHERE id=?", (msg.id, eid))
        await interaction.response.send_message(embed=embeds.success(f"Événement #{eid} publié dans {channel.mention}."),
                                                ephemeral=True)

    @ev_group.command(name="liste", description="Les événements à venir")
    async def ev_list(self, interaction: discord.Interaction) -> None:
        rows = await self.db.fetchall(
            "SELECT e.*, (SELECT COUNT(*) FROM event_participants p WHERE p.event_id=e.id) AS n FROM events e "
            "WHERE guild_id=? AND cancelled=0 AND starts_at > ? ORDER BY starts_at LIMIT 15", (interaction.guild_id, time.time()))
        lines = [f"**#{r['id']} {r['title']}** — <t:{int(r['starts_at'])}:f> · {r['n']} inscrit(s)" for r in rows]
        await interaction.response.send_message(embed=embeds.base("📅 Événements à venir", "\n".join(lines)
                                                                  or "Aucun événement prévu.", guild=interaction.guild))

    @ev_group.command(name="annuler", description="Annule un événement (les inscrits sont prévenus)")
    async def ev_cancel(self, interaction: discord.Interaction, numero: int) -> None:
        if not await self._manager(interaction):
            return
        ev = await self.get_event(numero, interaction.guild_id)
        if not ev or ev["cancelled"]:
            await reply_error(interaction, f"Événement #{numero} introuvable.")
            return
        await self.db.execute("UPDATE events SET cancelled=1 WHERE id=?", (numero,))
        ev["cancelled"] = 1
        await self.refresh_event(ev)
        await interaction.response.send_message(embed=embeds.success(f"Événement #{numero} annulé."), ephemeral=True)

    @tasks.loop(minutes=1)
    async def reminders(self) -> None:
        now = time.time()
        rows = await self.db.fetchall("SELECT * FROM events WHERE reminded=0 AND cancelled=0 AND starts_at > ?",
                                      (now - 3600,))
        for row in rows:
            ev = dict(row)
            guild = self.bot.get_guild(ev["guild_id"])
            minutes = int(gconf(guild).get("events", "reminder_minutes", default=15) or 0) if guild else 15
            if ev["starts_at"] - now > minutes * 60:
                continue
            await self.db.execute("UPDATE events SET reminded=1 WHERE id=?", (ev["id"],))
            channel = self.bot.get_channel(ev["channel_id"])
            people = await self.db.fetchall("SELECT user_id FROM event_participants WHERE event_id=?", (ev["id"],))
            if isinstance(channel, discord.TextChannel) and people:
                mentions = " ".join(f"<@{p['user_id']}>" for p in people)
                text = f"⏰ **{ev['title']}** commence <t:{int(ev['starts_at'])}:R> !"
                try:
                    for i in range(0, len(mentions), 1800):
                        await channel.send(content=(mentions[i:i + 1800] + ("\n" + text if i == 0 else "")),
                                           allowed_mentions=discord.AllowedMentions(users=True))
                except discord.HTTPException:
                    pass
            await self.refresh_event(ev)

    @reminders.before_loop
    async def _before(self) -> None:
        await self.bot.wait_until_ready()

    # ================================================================== tournois
    async def get_tourney(self, tid: int, guild_id: int | None) -> dict | None:
        row = await self.db.fetchone("SELECT * FROM tournaments WHERE id=? AND guild_id=?", (tid, guild_id))
        return dict(row) if row else None

    async def matches(self, tid: int) -> list[dict]:
        return [dict(r) for r in await self.db.fetchall(
            "SELECT round, slot, p1, p2, winner FROM tournament_matches WHERE tournament_id=? ORDER BY round, slot", (tid,))]

    async def tourney_embed(self, t: dict) -> discord.Embed:
        guild = self.bot.get_guild(t["guild_id"])
        from cogs.economy import money
        players = await self.db.fetchall("SELECT user_id FROM tournament_players WHERE tournament_id=?", (t["id"],))
        status = {"open": "📝 Inscriptions ouvertes", "running": "⚔️ En cours", "done": "🏆 Terminé",
                  "cancelled": "❌ Annulé"}[t["status"]]
        embed = embeds.base(f"🏆 {t['name']}", status, guild=guild)
        if t["reward"]:
            embed.add_field(name="Récompense du champion", value=money(guild, t["reward"]))
        if t["status"] == "open":
            names = " ".join(f"<@{p['user_id']}>" for p in players[:64])
            embed.add_field(name=f"Inscrits ({len(players)}/{t['max_players']})", value=names or "Personne pour l'instant",
                            inline=False)
        else:
            def name(uid):
                return f"<@{uid}>" if uid else "?"
            for title, lines in bracket.render(await self.matches(t["id"]), t["rounds"], name):
                embed.add_field(name=title, value=lines[:1024], inline=False)
        if t["winner_id"]:
            embed.add_field(name="Champion", value=f"🥇 <@{t['winner_id']}>", inline=False)
        embed.set_footer(text=f"Tournoi #{t['id']}")
        return embed

    async def refresh_tourney(self, t: dict) -> None:
        channel = self.bot.get_channel(t["channel_id"])
        if isinstance(channel, discord.TextChannel) and t["message_id"]:
            try:
                await channel.get_partial_message(t["message_id"]).edit(
                    embed=await self.tourney_embed(t), view=buttons("tourney", t["id"], t["status"] != "open"))
            except discord.HTTPException:
                pass

    async def tourney_click(self, interaction: discord.Interaction, tid: int, join: bool) -> None:
        t = await self.get_tourney(tid, interaction.guild_id)
        if not t or t["status"] != "open":
            await reply_error(interaction, "Les inscriptions à ce tournoi sont fermées.")
            return
        uid = interaction.user.id
        if join:
            count = (await self.db.fetchone("SELECT COUNT(*) AS n FROM tournament_players WHERE tournament_id=?",
                                            (tid,)))["n"]
            if count >= t["max_players"]:
                await reply_error(interaction, "Le tournoi est complet.")
                return
            await self.db.execute("INSERT OR IGNORE INTO tournament_players (tournament_id, user_id) VALUES (?,?)", (tid, uid))
            text = f"Tu es inscrit(e) au tournoi **{t['name']}**. Bonne chance ⚔️"
        else:
            await self.db.execute("DELETE FROM tournament_players WHERE tournament_id=? AND user_id=?", (tid, uid))
            text = f"Tu n'es plus inscrit(e) au tournoi **{t['name']}**."
        await interaction.response.send_message(embed=embeds.success(text), ephemeral=True)
        await self.refresh_tourney(t)

    async def _tourney_autocomplete(self, interaction: discord.Interaction, current: str):
        rows = await self.db.fetchall(
            "SELECT id, name, status FROM tournaments WHERE guild_id=? AND status IN ('open','running') ORDER BY id DESC "
            "LIMIT 25", (interaction.guild_id,))
        return [app_commands.Choice(name=f"#{r['id']} {r['name']}"[:100], value=r["id"]) for r in rows
                if current.lower() in f"#{r['id']} {r['name']}".lower()]

    t_group = app_commands.Group(name="tournoi", description="Tournois à élimination directe", guild_only=True)

    @t_group.command(name="creer", description="Crée un tournoi avec inscriptions par bouton")
    @app_commands.describe(nom="Nom du tournoi", places="Joueurs maximum (16 en gratuit, 💎 64)",
                           recompense="Argent du serveur pour le champion (0 = rien)", salon="Salon (vide = ici)")
    async def t_create(self, interaction: discord.Interaction, nom: app_commands.Range[str, 1, 80],
                       places: app_commands.Range[int, 2, 64] = 16, recompense: app_commands.Range[int, 0, 10**9] = 0,
                       salon: discord.TextChannel | None = None) -> None:
        if not await self._manager(interaction):
            return
        cap = limit_for("tournament_players", is_premium(interaction.guild))
        if places > cap:
            await reply_error(interaction, f"{cap} joueurs maximum sur ce serveur (💎 Premium : 64).")
            return
        channel = salon or interaction.channel
        if not isinstance(channel, discord.TextChannel):
            await reply_error(interaction, "Choisis un salon textuel.")
            return
        tid = await self.db.execute(
            "INSERT INTO tournaments (guild_id, channel_id, name, max_players, reward, created_by, created_at) "
            "VALUES (?,?,?,?,?,?,?)", (interaction.guild_id, channel.id, nom, places, recompense, interaction.user.id,
                                       time.time()))
        t = await self.get_tourney(tid, interaction.guild_id)
        assert t
        msg = await channel.send(embed=await self.tourney_embed(t), view=buttons("tourney", tid))
        await self.db.execute("UPDATE tournaments SET message_id=? WHERE id=?", (msg.id, tid))
        await interaction.response.send_message(embed=embeds.success(
            f"Tournoi #{tid} publié dans {channel.mention}. Lance-le avec `/tournoi lancer` quand les inscriptions sont finies."),
            ephemeral=True)

    @t_group.command(name="lancer", description="Ferme les inscriptions et tire le tableau au sort")
    @app_commands.autocomplete(tournoi=_tourney_autocomplete)
    async def t_start(self, interaction: discord.Interaction, tournoi: int) -> None:
        if not await self._manager(interaction):
            return
        t = await self.get_tourney(tournoi, interaction.guild_id)
        if not t or t["status"] != "open":
            await reply_error(interaction, "Tournoi introuvable ou déjà lancé.")
            return
        players = [r["user_id"] for r in await self.db.fetchall(
            "SELECT user_id FROM tournament_players WHERE tournament_id=?", (t["id"],))]
        if len(players) < 2:
            await reply_error(interaction, "Il faut au moins 2 inscrits pour lancer le tournoi.")
            return
        rounds = bracket.total_rounds(len(players))
        matches = bracket.first_round(players)
        matches += bracket.propagate(matches, rounds)
        await self._save_matches(t["id"], matches)
        await self.db.execute("UPDATE tournaments SET status='running', rounds=? WHERE id=?", (rounds, t["id"]))
        t.update(status="running", rounds=rounds)
        await self.refresh_tourney(t)
        await interaction.response.send_message(embed=await self.tourney_embed(t))

    async def _save_matches(self, tid: int, matches: list[dict]) -> None:
        for m in matches:
            await self.db.execute(
                "INSERT OR REPLACE INTO tournament_matches (tournament_id, round, slot, p1, p2, winner) VALUES (?,?,?,?,?,?)",
                (tid, m["round"], m["slot"], m["p1"], m["p2"], m["winner"]))

    @t_group.command(name="resultat", description="Indique le gagnant d'un match en cours")
    @app_commands.autocomplete(tournoi=_tourney_autocomplete)
    async def t_result(self, interaction: discord.Interaction, tournoi: int, gagnant: discord.Member) -> None:
        if not await self._manager(interaction):
            return
        t = await self.get_tourney(tournoi, interaction.guild_id)
        if not t or t["status"] != "running":
            await reply_error(interaction, "Ce tournoi n'est pas en cours.")
            return
        matches = await self.matches(t["id"])
        match = bracket.open_match_for(matches, gagnant.id)
        if not match or match["p2"] is None:
            await reply_error(interaction, f"{gagnant.mention} n'a pas de match en cours dans ce tournoi.")
            return
        match["winner"] = gagnant.id
        new = bracket.propagate(matches, t["rounds"])
        await self._save_matches(t["id"], [match, *new])
        champ = bracket.champion(matches + new, t["rounds"])
        text = f"✅ {gagnant.mention} remporte son match ({bracket.round_name(match['round'], t['rounds'])})."
        if champ:
            await self.db.execute("UPDATE tournaments SET status='done', winner_id=? WHERE id=?", (champ, t["id"]))
            t.update(status="done", winner_id=champ)
            text = f"🏆 {gagnant.mention} remporte le tournoi **{t['name']}** !"
            economy = self.bot.get_cog("Economy")
            if t["reward"] and economy and gconf(interaction.guild).get("economy", "enabled", default=True):
                from cogs.economy import money
                await economy.add(interaction.guild_id, champ, t["reward"])
                text += f"\nRécompense : {money(interaction.guild, t['reward'])}"
            self.bot.dispatch("activity", interaction.guild, gagnant, interaction.channel, "game_win", 1)
        await self.refresh_tourney(t)
        await interaction.response.send_message(embed=embeds.success(text),
                                                allowed_mentions=discord.AllowedMentions(users=True))

    @t_group.command(name="voir", description="Affiche le tableau d'un tournoi")
    @app_commands.autocomplete(tournoi=_tourney_autocomplete)
    async def t_show(self, interaction: discord.Interaction, tournoi: int) -> None:
        t = await self.get_tourney(tournoi, interaction.guild_id)
        if not t:
            await reply_error(interaction, "Tournoi introuvable.")
            return
        await interaction.response.send_message(embed=await self.tourney_embed(t), ephemeral=True)

    @t_group.command(name="annuler", description="Annule un tournoi")
    @app_commands.autocomplete(tournoi=_tourney_autocomplete)
    async def t_cancel(self, interaction: discord.Interaction, tournoi: int) -> None:
        if not await self._manager(interaction):
            return
        t = await self.get_tourney(tournoi, interaction.guild_id)
        if not t or t["status"] in ("done", "cancelled"):
            await reply_error(interaction, "Tournoi introuvable ou déjà terminé.")
            return
        await self.db.execute("UPDATE tournaments SET status='cancelled' WHERE id=?", (t["id"],))
        t["status"] = "cancelled"
        await self.refresh_tourney(t)
        await interaction.response.send_message(embed=embeds.success(f"Tournoi #{t['id']} annulé."), ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Events(bot))
