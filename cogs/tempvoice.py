"""Vocaux temporaires : rejoindre le salon « ➕ Créer un salon » crée un vocal perso, supprimé quand il est vide.
Le propriétaire le gère avec /vocal (renommer, limite, verrouiller, inviter, donner)."""
from __future__ import annotations

import json
import logging

import discord
from discord import app_commands
from discord.ext import commands

from bot import embeds
from bot.config import gconf
from bot.i18n import tr
from bot.utils import reply_error

log = logging.getLogger("cogs.tempvoice")
KEY = "temp_voice_channels"


class TempVoice(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.owners: dict[int, dict[int, int]] = {}  # guild_id -> {channel_id: owner_id}

    @property
    def db(self):
        return self.bot.db  # type: ignore[attr-defined]

    async def _load(self, guild_id: int) -> dict[int, int]:
        if guild_id not in self.owners:
            raw = await self.db.get_setting(guild_id, KEY) or "{}"
            self.owners[guild_id] = {int(k): int(v) for k, v in json.loads(raw).items()}
        return self.owners[guild_id]

    async def _save(self, guild_id: int) -> None:
        await self.db.set_setting(guild_id, KEY, json.dumps({str(k): v for k, v in self.owners[guild_id].items()}))

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        # Ménage au démarrage : supprime les vocaux temporaires restés vides
        for guild in self.bot.guilds:
            owners = await self._load(guild.id)
            for cid in list(owners):
                channel = guild.get_channel(cid)
                if not isinstance(channel, discord.VoiceChannel) or not channel.members:
                    owners.pop(cid, None)
                    if isinstance(channel, discord.VoiceChannel):
                        try:
                            await channel.delete(reason="Vocal temporaire vide")
                        except discord.HTTPException:
                            pass
            await self._save(guild.id)

    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState,
                                    after: discord.VoiceState) -> None:
        if member.bot or before.channel == after.channel:
            return
        guild = member.guild
        cfg = gconf(guild)
        owners = await self._load(guild.id)

        # 1) Départ d'un vocal temporaire : suppression s'il est vide
        if before.channel and before.channel.id in owners and not before.channel.members:
            owners.pop(before.channel.id, None)
            await self._save(guild.id)
            try:
                await before.channel.delete(reason="Vocal temporaire vide")
            except discord.HTTPException:
                pass

        # 2) Arrivée dans le salon « créer » : nouveau vocal perso
        creator = int(cfg.get("temp_voice", "creator_channel", default=0) or 0)
        if not (cfg.get("temp_voice", "enabled", default=True) and after.channel and after.channel.id == creator):
            return
        category = guild.get_channel(int(cfg.get("temp_voice", "category", default=0) or 0))
        if not isinstance(category, discord.CategoryChannel):
            category = after.channel.category
        template = tr(guild, cfg.get("temp_voice", "name_template", default="") or "🔊 Salon de {name}")
        name = template.replace("{name}", member.display_name)[:100]
        overwrites = dict(category.overwrites) if category else {}
        overwrites[member] = discord.PermissionOverwrite(view_channel=True, connect=True, manage_channels=True,
                                                         move_members=True, mute_members=True)
        overwrites[guild.me] = discord.PermissionOverwrite(view_channel=True, connect=True, manage_channels=True,
                                                           move_members=True)
        try:
            channel = await guild.create_voice_channel(
                name, category=category, overwrites=overwrites,
                user_limit=int(cfg.get("temp_voice", "default_limit", default=0) or 0),
                reason=f"Vocal temporaire de {member}")
            await member.move_to(channel, reason="Vocal temporaire")
        except discord.HTTPException as exc:
            log.warning("Vocal temporaire impossible sur %s : %s", guild.id, exc)
            return
        owners[channel.id] = member.id
        await self._save(guild.id)

    # --- commandes du propriétaire --------------------------------------------
    group = app_commands.Group(name="vocal", description="Gère ton salon vocal temporaire", guild_only=True)

    async def _own_channel(self, interaction: discord.Interaction) -> discord.VoiceChannel | None:
        member = interaction.user
        assert isinstance(member, discord.Member) and interaction.guild
        owners = await self._load(interaction.guild.id)
        channel = member.voice.channel if member.voice else None
        if not isinstance(channel, discord.VoiceChannel) or channel.id not in owners:
            await reply_error(interaction, "Tu dois être dans ton salon vocal temporaire.")
            return None
        if owners[channel.id] != member.id and not member.guild_permissions.manage_channels:
            await reply_error(interaction, "Ce n'est pas ton salon vocal.")
            return None
        return channel

    @group.command(name="renommer", description="Renomme ton salon vocal")
    async def rename(self, interaction: discord.Interaction, nom: app_commands.Range[str, 1, 100]) -> None:
        channel = await self._own_channel(interaction)
        if channel:
            await channel.edit(name=nom)
            await interaction.response.send_message(embed=embeds.success(f"Salon renommé : **{nom}**"), ephemeral=True)

    @group.command(name="limite", description="Nombre maximum de personnes (0 = illimité)")
    async def limit(self, interaction: discord.Interaction, places: app_commands.Range[int, 0, 99]) -> None:
        channel = await self._own_channel(interaction)
        if channel:
            await channel.edit(user_limit=places)
            text = "Plus de limite de places." if places == 0 else f"Limite : **{places}** personne(s)."
            await interaction.response.send_message(embed=embeds.success(text), ephemeral=True)

    @group.command(name="verrouiller", description="Plus personne ne peut rejoindre (sauf invités)")
    async def lock(self, interaction: discord.Interaction) -> None:
        channel = await self._own_channel(interaction)
        if channel:
            await channel.set_permissions(interaction.guild.default_role, connect=False)  # type: ignore[union-attr]
            await interaction.response.send_message(embed=embeds.success("🔒 Salon verrouillé."), ephemeral=True)

    @group.command(name="deverrouiller", description="Tout le monde peut de nouveau rejoindre")
    async def unlock(self, interaction: discord.Interaction) -> None:
        channel = await self._own_channel(interaction)
        if channel:
            await channel.set_permissions(interaction.guild.default_role, connect=None)  # type: ignore[union-attr]
            await interaction.response.send_message(embed=embeds.success("🔓 Salon déverrouillé."), ephemeral=True)

    @group.command(name="inviter", description="Autorise un membre à rejoindre même si c'est verrouillé")
    async def invite(self, interaction: discord.Interaction, membre: discord.Member) -> None:
        channel = await self._own_channel(interaction)
        if channel:
            await channel.set_permissions(membre, connect=True, view_channel=True)
            await interaction.response.send_message(embed=embeds.success(f"{membre.mention} peut rejoindre ton salon."),
                                                    ephemeral=True)

    @group.command(name="donner", description="Donne la propriété du salon à un autre membre")
    async def transfer(self, interaction: discord.Interaction, membre: discord.Member) -> None:
        channel = await self._own_channel(interaction)
        if not channel:
            return
        if membre.bot or membre not in channel.members:
            await reply_error(interaction, "Le nouveau propriétaire doit être dans le salon.")
            return
        owners = await self._load(channel.guild.id)
        owners[channel.id] = membre.id
        await self._save(channel.guild.id)
        await channel.set_permissions(membre, connect=True, view_channel=True, manage_channels=True, move_members=True,
                                      mute_members=True)
        await interaction.response.send_message(embed=embeds.success(f"{membre.mention} est maintenant propriétaire du salon."))


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(TempVoice(bot))
