"""Arrivées et départs : filtre anti-raid, rôle « Non vérifié », messages, DM, logs.
Gère aussi l'ajout du bot sur un nouveau serveur (message d'accueil avec le lien du panel)."""
from __future__ import annotations

import asyncio
import io
import logging

import discord
from discord import app_commands
from discord.ext import commands

from bot import embeds
from bot.config import gconf
from bot.i18n import language, tr
from bot.images import welcome_card
from bot.utils import dashboard_url, fill_template, send_log

log = logging.getLogger("cogs.welcome")


class Welcome(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    def _welcome_embed(self, member: discord.Member) -> discord.Embed:
        cfg = gconf(member.guild)
        g = member.guild
        text = fill_template(tr(g, cfg.get("welcome", "message", default="Bienvenue {mention} !")), member)
        embed = embeds.base(tr(g, "👋 Nouveau membre !"), text, guild=g)
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.add_field(name=tr(g, "Compte créé"), value=discord.utils.format_dt(member.created_at, "R"))
        embed.add_field(name=tr(g, "Membre n°"), value=str(g.member_count))
        return embed

    async def welcome_payload(self, member: discord.Member) -> dict:
        """Embed de bienvenue + 💎 carte en image si activée."""
        embed = self._welcome_embed(member)
        cfg = gconf(member.guild)
        if not cfg.get("welcome", "image", default=False):
            return {"embed": embed}
        try:
            avatar = await member.display_avatar.replace(size=256, format="png").read()
        except discord.HTTPException:
            avatar = None
        english = language(member.guild) == "en"
        png = await asyncio.to_thread(
            welcome_card, member.display_name, avatar, member.guild.name, member.guild.member_count or 0, cfg.color,
            "WELCOME" if english else "BIENVENUE", "Member #{}" if english else "Membre n°{}")
        embed.set_thumbnail(url=None)
        embed.set_image(url="attachment://bienvenue.png")
        return {"embed": embed, "file": discord.File(io.BytesIO(png), filename="bienvenue.png")}

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        # 1) Anti-raid : si le module sécurité expulse le membre, on s'arrête là.
        security = self.bot.get_cog("Security")
        if security is not None and await security.screen_join(member):  # type: ignore[attr-defined]
            return
        if member.bot:
            return
        cfg = gconf(member.guild)

        # 2) Rôle « Non vérifié »
        role = member.guild.get_role(cfg.role_id("unverified"))
        if role:
            try:
                await member.add_roles(role, reason="Nouvel arrivant (non vérifié)")
            except discord.HTTPException as exc:
                log.warning("Impossible d'ajouter le rôle non vérifié : %s", exc)

        if not cfg.get("welcome", "enabled", default=True):
            return

        # 3) Message dans le salon de bienvenue
        channel = member.guild.get_channel(cfg.channel_id("welcome"))
        if isinstance(channel, discord.TextChannel):
            try:
                await channel.send(content=member.mention, **await self.welcome_payload(member),
                                   allowed_mentions=discord.AllowedMentions(users=True))
            except discord.HTTPException as exc:
                log.warning("Message de bienvenue impossible : %s", exc)

        # 4) Message privé
        if cfg.get("welcome", "send_dm", default=True):
            dm_text = fill_template(tr(member.guild, cfg.get("welcome", "dm_message", default="")), member)
            if dm_text:
                try:
                    await member.send(embed=embeds.base(f"Bienvenue sur {member.guild.name} !", dm_text,
                                                        guild=member.guild))
                except discord.HTTPException:
                    pass  # DM fermés : pas grave

        # 5) Log staff
        age_days = (discord.utils.utcnow() - member.created_at).days
        log_embed = embeds.success(
            f"{member.mention} (`{member.id}`)\nCompte créé il y a **{age_days} jours**", "📥 Arrivée")
        log_embed.set_thumbnail(url=member.display_avatar.url)
        await send_log(member.guild, log_embed)

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member) -> None:
        cfg = gconf(member.guild)
        channel = member.guild.get_channel(cfg.channel_id("goodbye"))
        template = cfg.get("welcome", "goodbye_message")
        if isinstance(channel, discord.TextChannel) and template and not member.bot:
            try:
                await channel.send(embed=embeds.base(None, fill_template(tr(member.guild, template), member),
                                                     guild=member.guild))
            except discord.HTTPException:
                pass
        roles = [r.mention for r in member.roles if r != member.guild.default_role]
        joined = discord.utils.format_dt(member.joined_at, "R") if member.joined_at else "?"
        await send_log(member.guild, embeds.warning(
            f"{member} (`{member.id}`)\nArrivé {joined}\nRôles : {', '.join(roles) or 'aucun'}", "📤 Départ"))

    @commands.Cog.listener()
    async def on_guild_join(self, guild: discord.Guild) -> None:
        """Le bot vient d'être ajouté : on explique comment le configurer."""
        log.info("Ajouté sur %s (%s) — %s membres", guild.name, guild.id, guild.member_count)
        url = dashboard_url(guild.id)
        text = ("Merci de m'avoir ajouté ! 🎉\n\n"
                + (f"**Configure-moi en 2 minutes sur le panel web :**\n{url}\n\n" if url else "")
                + "Commandes utiles : `/help`, `/check_config`.\n"
                "📬 Un souci ou une idée ? Tape `/contact` : ton message arrive directement au créateur du bot.\n"
                "⚠️ Place mon rôle **au-dessus** des rôles que je dois gérer (Paramètres du serveur → Rôles).")
        target = guild.system_channel
        if target is None or not target.permissions_for(guild.me).send_messages:
            target = next((c for c in guild.text_channels if c.permissions_for(guild.me).send_messages), None)
        if target:
            try:
                await target.send(embed=embeds.base("👋 Bonjour !", text))
            except discord.HTTPException:
                pass

    @app_commands.command(name="welcome_test", description="Prévisualise le message de bienvenue")
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.guild_only()
    async def welcome_test(self, interaction: discord.Interaction) -> None:
        assert isinstance(interaction.user, discord.Member)
        await interaction.response.defer(ephemeral=True)
        await interaction.followup.send(**await self.welcome_payload(interaction.user), ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Welcome(bot))
