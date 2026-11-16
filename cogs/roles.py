"""Rôles de notification : un menu déroulant persistant pour s'abonner / se désabonner."""
from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from bot import embeds
from bot.config import gconf
from bot.i18n import tr
from bot.panels import publish_panel


def _notification_roles(guild: discord.Guild) -> dict[str, discord.Role]:
    mapping = gconf(guild).get("roles", "notifications", default={}) or {}
    roles = {}
    for label, role_id in mapping.items():
        role = guild.get_role(int(role_id or 0))
        if role:
            roles[label] = role
    return roles


class NotificationSelect(discord.ui.Select):
    """Les options dépendent du serveur ; la vue enregistrée au démarrage sert seulement
    à recevoir les clics (discord.py retrouve l'élément grâce au custom_id)."""

    def __init__(self, guild: discord.Guild | None = None) -> None:
        labels = list(_notification_roles(guild).keys())[:25] if guild else []
        options = [discord.SelectOption(label=name, value=name) for name in labels] or [
            discord.SelectOption(label="Aucun rôle configuré", value="none")]
        super().__init__(placeholder=tr(guild, "🔔 Choisis tes notifications…"), min_values=0,
                         max_values=len(options), options=options, custom_id="roles:notifications")

    async def callback(self, interaction: discord.Interaction) -> None:
        member = interaction.user
        assert isinstance(member, discord.Member) and interaction.guild
        roles = _notification_roles(interaction.guild)
        wanted = {roles[v] for v in self.values if v in roles}
        to_add = [r for r in wanted if r not in member.roles]
        to_remove = [r for r in roles.values() if r in member.roles and r not in wanted]
        if to_add:
            await member.add_roles(*to_add, reason="Rôles de notification")
        if to_remove:
            await member.remove_roles(*to_remove, reason="Rôles de notification")
        current = ", ".join(r.mention for r in wanted) or "aucune"
        await interaction.response.send_message(embed=embeds.success(f"Tes notifications : {current}"),
                                                ephemeral=True)


class NotificationView(discord.ui.View):
    def __init__(self, guild: discord.Guild | None = None) -> None:
        super().__init__(timeout=None)
        self.add_item(NotificationSelect(guild))


def build_panel(guild: discord.Guild) -> tuple[discord.Embed, discord.ui.View]:
    roles = _notification_roles(guild)
    listing = "\n".join(f"• {r.mention}" for r in roles.values())
    embed = embeds.base(
        tr(guild, "🔔 Rôles de notification"),
        tr(guild, "Sélectionne dans le menu les sujets pour lesquels tu veux être mentionné(e).\n"
                  "Désélectionne un sujet pour ne plus recevoir ses notifications.")
        + (f"\n\n{listing}" if listing else ""), guild=guild)
    return embed, NotificationView(guild)


class Roles(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def cog_load(self) -> None:
        self.bot.add_view(NotificationView())

    @app_commands.command(name="setup_notifications", description="Envoie le panneau des rôles de notification ici")
    @app_commands.default_permissions(administrator=True)
    @app_commands.guild_only()
    async def setup_notifications(self, interaction: discord.Interaction) -> None:
        assert interaction.guild and isinstance(interaction.channel, discord.TextChannel)
        await publish_panel(self.bot, interaction.guild, "notifications", interaction.channel)
        await interaction.response.send_message(embed=embeds.success("Panneau envoyé."), ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Roles(bot))
