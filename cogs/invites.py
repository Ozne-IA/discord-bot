"""Suivi des invitations : qui a invité qui, invitations encore présentes ou parties, classement.

Discord ne dit pas quelle invitation a été utilisée : le bot garde en mémoire le nombre d'utilisations
de chaque invitation et compare à chaque arrivée. Nécessite la permission « Gérer le serveur »."""
from __future__ import annotations

import logging
import time

import discord
from discord import app_commands
from discord.ext import commands, tasks

from bot import embeds
from bot.config import gconf
from bot.pagination import Paginator, chunk
from bot.utils import fill_template

log = logging.getLogger("cogs.invites")


def find_used_invite(before: dict[str, int], after: dict[str, tuple[int, int | None]]) -> tuple[str | None, int | None]:
    """Compare les compteurs d'utilisation : renvoie (code, id de l'inviteur) de l'invitation utilisée."""
    for code, (uses, inviter) in after.items():
        if uses > before.get(code, 0):
            return code, inviter
    return None, None


class Invites(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.cache: dict[int, dict[str, int]] = {}

    @property
    def db(self):
        return self.bot.db  # type: ignore[attr-defined]

    async def snapshot(self, guild: discord.Guild) -> dict[str, tuple[int, int | None]]:
        if not guild.me.guild_permissions.manage_guild:
            return {}
        try:
            invites = await guild.invites()
        except discord.HTTPException:
            return {}
        data = {i.code: (i.uses or 0, i.inviter.id if i.inviter else None) for i in invites}
        if "VANITY_URL" in guild.features:
            try:
                vanity = await guild.vanity_invite()
                if vanity:
                    data[vanity.code] = (vanity.uses or 0, None)
            except discord.HTTPException:
                pass
        return data

    async def remember(self, guild: discord.Guild) -> dict[str, tuple[int, int | None]]:
        snap = await self.snapshot(guild)
        self.cache[guild.id] = {code: uses for code, (uses, _) in snap.items()}
        return snap

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        for guild in self.bot.guilds:
            await self.remember(guild)

    # --- parrainage : récompense quand l'invité est resté X jours ----------------------
    async def cog_load(self) -> None:
        self.referrals.start()

    async def cog_unload(self) -> None:
        self.referrals.cancel()

    @tasks.loop(hours=1)
    async def referrals(self) -> None:
        economy = self.bot.get_cog("Economy")
        from cogs.economy import money
        for guild in self.bot.guilds:
            cfg = gconf(guild)
            reward = int(cfg.get("invites", "referral_reward", default=0) or 0)
            if not reward or not economy or not cfg.get("invites", "enabled", default=True) \
                    or not cfg.get("economy", "enabled", default=True):
                continue
            days = max(0, int(cfg.get("invites", "referral_days", default=7) or 0))
            rows = await self.db.fetchall(
                "SELECT id, member_id, inviter_id FROM invite_joins WHERE guild_id=? AND rewarded=0 AND left_at IS NULL "
                "AND inviter_id IS NOT NULL AND inviter_id != member_id AND joined_at <= ? LIMIT 200",
                (guild.id, time.time() - days * 86400))
            channel = guild.get_channel(int(cfg.get("invites", "channel", default=0) or 0))
            for r in rows:
                await self.db.execute("UPDATE invite_joins SET rewarded=1 WHERE id=?", (r["id"],))
                if guild.get_member(r["member_id"]) is None or guild.get_member(r["inviter_id"]) is None:
                    continue  # l'un des deux est parti entre-temps
                await economy.add(guild.id, r["inviter_id"], reward)
                if isinstance(channel, discord.TextChannel):
                    try:
                        await channel.send(embed=embeds.base(None, (
                            f"🤝 <@{r['inviter_id']}> reçoit {money(guild, reward)} : <@{r['member_id']}>, "
                            f"qu'il/elle a invité(e), est resté(e) {days} jour(s) !"), guild=guild),
                            allowed_mentions=discord.AllowedMentions.none())
                    except discord.HTTPException:
                        pass

    @referrals.before_loop
    async def _before_referrals(self) -> None:
        await self.bot.wait_until_ready()

    @commands.Cog.listener()
    async def on_guild_join(self, guild: discord.Guild) -> None:
        await self.remember(guild)

    @commands.Cog.listener()
    async def on_invite_create(self, invite: discord.Invite) -> None:
        if invite.guild:
            self.cache.setdefault(invite.guild.id, {})[invite.code] = invite.uses or 0

    @commands.Cog.listener()
    async def on_invite_delete(self, invite: discord.Invite) -> None:
        if invite.guild:
            self.cache.get(invite.guild.id, {}).pop(invite.code, None)

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        guild = member.guild
        if member.bot or not gconf(guild).get("invites", "enabled", default=True):
            return
        before = self.cache.get(guild.id, {})
        after = await self.remember(guild)
        code, inviter_id = find_used_invite(before, after)
        await self.db.execute(
            "INSERT INTO invite_joins (guild_id, member_id, inviter_id, code, joined_at) VALUES (?,?,?,?,?)",
            (guild.id, member.id, inviter_id, code, time.time()))
        channel = guild.get_channel(int(gconf(guild).get("invites", "channel", default=0) or 0))
        if not isinstance(channel, discord.TextChannel):
            return
        if inviter_id:
            count = (await self.db.fetchone(
                "SELECT COUNT(*) AS n FROM invite_joins WHERE guild_id=? AND inviter_id=? AND left_at IS NULL",
                (guild.id, inviter_id)))["n"]
            inviter = guild.get_member(inviter_id)
            template = gconf(guild).get("invites", "message", default="") or "📨 {mention} a rejoint grâce à **{inviter}**."
            text = fill_template(template, member).replace("{inviter}", inviter.display_name if inviter else str(inviter_id)) \
                .replace("{count}", str(count))
        elif code:
            text = f"📨 {member.mention} a rejoint avec l'invitation personnalisée du serveur (`{code}`)."
        else:
            text = f"📨 {member.mention} a rejoint (invitation inconnue)."
        try:
            await channel.send(embed=embeds.base(None, text, guild=guild), allowed_mentions=discord.AllowedMentions.none())
        except discord.HTTPException:
            pass

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member) -> None:
        await self.db.execute(
            "UPDATE invite_joins SET left_at=? WHERE guild_id=? AND member_id=? AND left_at IS NULL",
            (time.time(), member.guild.id, member.id))

    # --- commandes -----------------------------------------------------------
    group = app_commands.Group(name="invitations", description="Suivi des invitations", guild_only=True)

    @group.command(name="voir", description="Invitations d'un membre (ou les tiennes)")
    async def show(self, interaction: discord.Interaction, membre: discord.Member | None = None) -> None:
        member = membre or interaction.user
        rows = await self.db.fetchall(
            "SELECT member_id, left_at FROM invite_joins WHERE guild_id=? AND inviter_id=? ORDER BY joined_at DESC",
            (interaction.guild_id, member.id))
        present = [r for r in rows if r["left_at"] is None]
        left = len(rows) - len(present)
        invited_by = await self.db.fetchone(
            "SELECT inviter_id FROM invite_joins WHERE guild_id=? AND member_id=? ORDER BY joined_at DESC LIMIT 1",
            (interaction.guild_id, member.id))
        embed = embeds.base(f"📨 Invitations de {member.display_name}", guild=interaction.guild)
        embed.add_field(name="Toujours là", value=str(len(present)))
        embed.add_field(name="Partis", value=str(left))
        embed.add_field(name="Total", value=str(len(rows)))
        if invited_by and invited_by["inviter_id"]:
            embed.add_field(name="Invité par", value=f"<@{invited_by['inviter_id']}>", inline=False)
        if present:
            embed.add_field(name="Derniers invités", value=" ".join(f"<@{r['member_id']}>" for r in present[:15]), inline=False)
        await interaction.response.send_message(embed=embed)

    @group.command(name="classement", description="Les membres qui ont invité le plus de monde")
    async def leaderboard(self, interaction: discord.Interaction) -> None:
        rows = await self.db.fetchall(
            "SELECT inviter_id, SUM(left_at IS NULL) AS present, COUNT(*) AS total FROM invite_joins "
            "WHERE guild_id=? AND inviter_id IS NOT NULL GROUP BY inviter_id ORDER BY present DESC, total DESC LIMIT 100",
            (interaction.guild_id,))
        medals = {1: "🥇", 2: "🥈", 3: "🥉"}
        pages = []
        for p, group in enumerate(chunk(rows, 10)):
            lines = [f"{medals.get(p * 10 + i, f'`#{p * 10 + i}`')} <@{r['inviter_id']}> — **{r['present']}** invitation(s) "
                     f"({r['total'] - r['present']} partis)" for i, r in enumerate(group, 1)]
            empty = "Aucune invitation suivie pour l'instant."
            pages.append(embeds.base("📨 Classement des invitations", "\n".join(lines) or empty,
                                     guild=interaction.guild))
        await Paginator.send(interaction, pages)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Invites(bot))
