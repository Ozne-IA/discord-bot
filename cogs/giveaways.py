"""💎 Giveaways (Premium) : bouton Participer, condition de rôle, tirage automatique, reroll."""
from __future__ import annotations

import logging
import random
import time

import discord
from discord import app_commands
from discord.ext import commands, tasks

from bot import embeds
from bot.config import gconf
from bot.premium import require
from bot.utils import format_duration, parse_duration, reply_error

log = logging.getLogger("cogs.giveaways")
GOLD = 0xF1C40F


class GiveawayButton(discord.ui.DynamicItem[discord.ui.Button], template=r"giveaway:(?P<id>\d+)"):
    """Bouton persistant : l'ID du giveaway est dans le custom_id (marche après redémarrage)."""

    def __init__(self, giveaway_id: int, count: int = 0, disabled: bool = False) -> None:
        super().__init__(discord.ui.Button(label=f"Participer ({count})", emoji="🎉",
                                           style=discord.ButtonStyle.success, disabled=disabled,
                                           custom_id=f"giveaway:{giveaway_id}"))
        self.giveaway_id = giveaway_id

    @classmethod
    async def from_custom_id(cls, interaction: discord.Interaction, item: discord.ui.Button, match):
        return cls(int(match["id"]))

    async def callback(self, interaction: discord.Interaction) -> None:
        cog: Giveaways = interaction.client.get_cog("Giveaways")  # type: ignore[assignment]
        await cog.toggle_entry(interaction, self.giveaway_id)


def giveaway_view(giveaway_id: int, count: int, ended: bool = False) -> discord.ui.View:
    view = discord.ui.View(timeout=None)
    view.add_item(GiveawayButton(giveaway_id, count, disabled=ended))
    return view


class Giveaways(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @property
    def db(self):
        return self.bot.db  # type: ignore[attr-defined]

    async def cog_load(self) -> None:
        self.bot.add_dynamic_items(GiveawayButton)
        self.check_ended.start()

    async def cog_unload(self) -> None:
        self.check_ended.cancel()
        self.bot.remove_dynamic_items(GiveawayButton)

    # --- affichage -----------------------------------------------------
    def build_embed(self, g: dict, count: int) -> discord.Embed:
        lines = [f"**Organisé par** <@{g['host_id']}>",
                 f"**Gagnant(s)** : {g['winners']}",
                 f"**Participants** : {count}"]
        if g["required_role"]:
            lines.append(f"**Rôle requis** : <@&{g['required_role']}>")
        if g["ended"]:
            winners = [w for w in (g["winner_ids"] or "").split(",") if w]
            lines.insert(0, "🏁 **Terminé**")
            lines.append("**Gagnant(s)** : " + (", ".join(f"<@{w}>" for w in winners) or "aucun participant"))
            color = 0x95A5A6
        else:
            lines.insert(0, f"⏰ Fin <t:{int(g['ends_at'])}:R>")
            lines.append("\nClique sur **🎉 Participer** pour tenter ta chance !")
            color = GOLD
        return embeds.base(f"🎁 {g['prize']}", "\n".join(lines), color=color)

    async def _get(self, giveaway_id: int) -> dict | None:
        row = await self.db.fetchone("SELECT * FROM giveaways WHERE id=?", (giveaway_id,))
        return dict(row) if row else None

    async def _count(self, giveaway_id: int) -> int:
        row = await self.db.fetchone("SELECT COUNT(*) AS n FROM giveaway_entries WHERE giveaway_id=?", (giveaway_id,))
        return row["n"]

    async def refresh_message(self, g: dict) -> None:
        channel = self.bot.get_channel(g["channel_id"])
        if not isinstance(channel, discord.TextChannel) or not g["message_id"]:
            return
        count = await self._count(g["id"])
        try:
            msg = channel.get_partial_message(g["message_id"])
            await msg.edit(embed=self.build_embed(g, count), view=giveaway_view(g["id"], count, bool(g["ended"])))
        except discord.HTTPException:
            pass

    # --- participation -------------------------------------------------
    async def toggle_entry(self, interaction: discord.Interaction, giveaway_id: int) -> None:
        g = await self._get(giveaway_id)
        member = interaction.user
        if not g or g["ended"] or g["guild_id"] != interaction.guild_id or not isinstance(member, discord.Member):
            await interaction.response.send_message(embed=embeds.error("Ce giveaway est terminé."), ephemeral=True)
            return
        if g["required_role"] and not any(r.id == g["required_role"] for r in member.roles):
            await interaction.response.send_message(
                embed=embeds.error(f"Il faut le rôle <@&{g['required_role']}> pour participer."), ephemeral=True)
            return
        exists = await self.db.fetchone("SELECT 1 FROM giveaway_entries WHERE giveaway_id=? AND user_id=?",
                                        (giveaway_id, member.id))
        if exists:
            await self.db.execute("DELETE FROM giveaway_entries WHERE giveaway_id=? AND user_id=?",
                                  (giveaway_id, member.id))
            text = "Tu ne participes plus à ce giveaway."
        else:
            await self.db.execute("INSERT INTO giveaway_entries (giveaway_id, user_id) VALUES (?,?)",
                                  (giveaway_id, member.id))
            text = "🎉 Tu participes ! Reclique pour te retirer."
        count = await self._count(giveaway_id)
        await interaction.response.edit_message(embed=self.build_embed(g, count),
                                                view=giveaway_view(giveaway_id, count))
        await interaction.followup.send(embed=embeds.success(text), ephemeral=True)

    # --- tirage --------------------------------------------------------
    async def draw(self, g: dict, amount: int, exclude: set[int] = frozenset()) -> list[int]:  # type: ignore[assignment]
        rows = await self.db.fetchall("SELECT user_id FROM giveaway_entries WHERE giveaway_id=?", (g["id"],))
        guild = self.bot.get_guild(g["guild_id"])
        pool = [r["user_id"] for r in rows if r["user_id"] not in exclude
                and (guild is None or guild.get_member(r["user_id"]) is not None)]
        return random.sample(pool, min(amount, len(pool)))

    async def finish(self, g: dict) -> list[int]:
        winners = await self.draw(g, g["winners"])
        await self.db.execute("UPDATE giveaways SET ended=1, winner_ids=? WHERE id=?",
                              (",".join(map(str, winners)), g["id"]))
        g = await self._get(g["id"]) or g
        await self.refresh_message(g)
        channel = self.bot.get_channel(g["channel_id"])
        if isinstance(channel, discord.TextChannel):
            text = (f"🎉 Félicitations {', '.join(f'<@{w}>' for w in winners)} ! Vous gagnez **{g['prize']}** !"
                    if winners else f"Personne n'a participé au giveaway **{g['prize']}** 😢")
            try:
                ref = channel.get_partial_message(g["message_id"]) if g["message_id"] else None
                await channel.send(text, reference=ref, allowed_mentions=discord.AllowedMentions(users=True))
            except discord.HTTPException:
                pass
        return winners

    @tasks.loop(seconds=20)
    async def check_ended(self) -> None:
        rows = await self.db.fetchall("SELECT * FROM giveaways WHERE ended=0 AND ends_at <= ?", (time.time(),))
        for row in rows:
            try:
                await self.finish(dict(row))
            except Exception:
                log.exception("Fin du giveaway %s impossible", row["id"])

    @check_ended.before_loop
    async def _before(self) -> None:
        await self.bot.wait_until_ready()

    # --- commandes -----------------------------------------------------
    group = app_commands.Group(name="giveaway", description="💎 Giveaways (Premium)", guild_only=True)

    async def _can_manage(self, interaction: discord.Interaction) -> bool:
        member = interaction.user
        assert isinstance(member, discord.Member)
        manager = int(gconf(interaction.guild).get("giveaways", "manager_role", default=0) or 0)
        if member.guild_permissions.manage_guild or any(r.id == manager for r in member.roles):
            return True
        await reply_error(interaction, "Il faut la permission « Gérer le serveur » ou le rôle gestionnaire des giveaways.")
        return False

    @group.command(name="start", description="Lance un giveaway")
    @app_commands.describe(prix="Ce qu'on gagne", duree="Ex : 30m, 2h, 1d, 7d", gagnants="Nombre de gagnants",
                           salon="Salon du giveaway (par défaut : ici)", role_requis="Rôle nécessaire pour participer")
    async def start(self, interaction: discord.Interaction, prix: app_commands.Range[str, 1, 200], duree: str,
                    gagnants: app_commands.Range[int, 1, 20] = 1, salon: discord.TextChannel | None = None,
                    role_requis: discord.Role | None = None) -> None:
        if not await require(interaction, "Les giveaways") or not await self._can_manage(interaction):
            return
        delta = parse_duration(duree)
        if not delta or delta.total_seconds() < 60 or delta.days > 60:
            await reply_error(interaction, "Durée invalide (entre 1 minute et 60 jours). Exemples : `30m`, `2h`, `7d`.")
            return
        channel = salon or interaction.channel
        assert isinstance(channel, discord.TextChannel)
        ends = time.time() + delta.total_seconds()
        gid = await self.db.execute(
            "INSERT INTO giveaways (guild_id, channel_id, host_id, prize, winners, required_role, ends_at) "
            "VALUES (?,?,?,?,?,?,?)",
            (interaction.guild_id, channel.id, interaction.user.id, prix, gagnants,
             role_requis.id if role_requis else None, ends))
        g = await self._get(gid)
        assert g
        msg = await channel.send(embed=self.build_embed(g, 0), view=giveaway_view(gid, 0))
        await self.db.execute("UPDATE giveaways SET message_id=? WHERE id=?", (msg.id, gid))
        await interaction.response.send_message(embed=embeds.success(
            f"Giveaway #{gid} lancé dans {channel.mention} pour **{format_duration(delta)}**."), ephemeral=True)

    @group.command(name="end", description="Termine un giveaway maintenant")
    async def end(self, interaction: discord.Interaction, giveaway_id: int) -> None:
        if not await require(interaction, "Les giveaways") or not await self._can_manage(interaction):
            return
        g = await self._get(giveaway_id)
        if not g or g["guild_id"] != interaction.guild_id or g["ended"]:
            await reply_error(interaction, "Giveaway introuvable ou déjà terminé.")
            return
        await interaction.response.defer(ephemeral=True)
        winners = await self.finish(g)
        await interaction.followup.send(embed=embeds.success(f"Giveaway terminé : {len(winners)} gagnant(s)."),
                                        ephemeral=True)

    @group.command(name="reroll", description="Tire de nouveaux gagnants")
    async def reroll(self, interaction: discord.Interaction, giveaway_id: int,
                     gagnants: app_commands.Range[int, 1, 20] = 1) -> None:
        if not await require(interaction, "Les giveaways") or not await self._can_manage(interaction):
            return
        g = await self._get(giveaway_id)
        if not g or g["guild_id"] != interaction.guild_id or not g["ended"]:
            await reply_error(interaction, "Le giveaway doit exister et être terminé.")
            return
        previous = {int(w) for w in (g["winner_ids"] or "").split(",") if w}
        winners = await self.draw(g, gagnants, exclude=previous)
        if not winners:
            await reply_error(interaction, "Plus aucun participant disponible pour un nouveau tirage.")
            return
        await self.db.execute("UPDATE giveaways SET winner_ids=? WHERE id=?",
                              (",".join(map(str, previous | set(winners))), g["id"]))
        await interaction.response.send_message(
            f"🔁 Nouveau tirage pour **{g['prize']}** : {', '.join(f'<@{w}>' for w in winners)} 🎉",
            allowed_mentions=discord.AllowedMentions(users=True))

    @group.command(name="list", description="Giveaways en cours")
    async def list_(self, interaction: discord.Interaction) -> None:
        rows = await self.db.fetchall(
            "SELECT * FROM giveaways WHERE guild_id=? AND ended=0 ORDER BY ends_at", (interaction.guild_id,))
        text = "\n".join(f"`#{r['id']}` **{r['prize']}** — <#{r['channel_id']}> — fin <t:{int(r['ends_at'])}:R>"
                         for r in rows) or "Aucun giveaway en cours."
        await interaction.response.send_message(embed=embeds.info(text, "🎁 Giveaways en cours"), ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Giveaways(bot))
