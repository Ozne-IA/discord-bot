"""/contact : signaler un module qui ne marche pas, proposer une idée ou écrire au propriétaire du bot."""
from __future__ import annotations

import logging

import discord
from discord import app_commands
from discord.ext import commands

from bot import contact, embeds

log = logging.getLogger("cogs.contact")
COLORS = {"bug": 0xE74C3C, "idea": 0xF1C40F, "other": 0x5865F2}


class ContactModal(discord.ui.Modal):
    def __init__(self, cog: "Contact", kind: str):
        emoji, label = contact.KINDS[kind]
        super().__init__(title=f"{emoji} {label}"[:45], timeout=900)
        self.cog, self.kind = cog, kind
        self.subject = discord.ui.TextInput(
            label="Sujet", max_length=100,
            placeholder="Ex : les tickets ne s'ouvrent pas" if kind == "bug" else "En quelques mots")
        self.message = discord.ui.TextInput(
            label="Message", style=discord.TextStyle.paragraph, min_length=10, max_length=2000,
            placeholder=("Quel module, ce que tu as fait, ce qui s'est passé…" if kind == "bug"
                         else "Explique-nous tout"))
        self.add_item(self.subject)
        self.add_item(self.message)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await self.cog.send_report(interaction, self.kind, str(self.subject), str(self.message))


class ContactView(discord.ui.View):
    def __init__(self, cog: "Contact"):
        super().__init__(timeout=300)
        for kind, (emoji, label) in contact.KINDS.items():
            button = discord.ui.Button(label=label, emoji=emoji, style=discord.ButtonStyle.secondary)
            button.callback = self._open(cog, kind)
            self.add_item(button)
        self.add_item(discord.ui.Button(label="E-mail", emoji="📧", url=f"mailto:{contact.contact_email()}"))

    @staticmethod
    def _open(cog: "Contact", kind: str):
        async def callback(interaction: discord.Interaction) -> None:
            left = cog.cooldown.remaining(interaction.user.id)
            if left > 0:
                await interaction.response.send_message(embed=embeds.error(
                    f"Tu as déjà envoyé un message il y a peu. Réessaie dans {max(1, round(left / 60))} min."),
                    ephemeral=True)
                return
            await interaction.response.send_modal(ContactModal(cog, kind))
        return callback


class Contact(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.cooldown = contact.Cooldown()

    @app_commands.command(name="contact", description="Signaler un bug, proposer une idée ou écrire au créateur du bot")
    async def contact_cmd(self, interaction: discord.Interaction) -> None:
        email = contact.contact_email()
        await interaction.response.send_message(embed=embeds.info(
            "Un module ne marche pas, une idée, une question ? Choisis ci-dessous : ton message arrive "
            f"directement au créateur du bot.\n\nTu peux aussi écrire à **{email}**.", "📬 Contacter le créateur"),
            view=ContactView(self), ephemeral=True)

    async def send_report(self, interaction: discord.Interaction, kind: str, subject: str, message: str) -> None:
        if self.cooldown.remaining(interaction.user.id) > 0:
            await interaction.response.send_message(embed=embeds.error("Tu as déjà envoyé un message il y a peu."),
                                                    ephemeral=True)
            return
        guild = interaction.guild
        title, text = contact.format_report(kind, subject, message, str(interaction.user), interaction.user.id,
                                            guild.name if guild else None, guild.id if guild else None)
        ops = self.bot.get_cog("Ops")
        sent = False
        if ops is not None:
            sent = await ops.notify(title, text, color=COLORS.get(kind, 0x5865F2), force=True)  # type: ignore[attr-defined]
        if not sent:
            log.warning("Message /contact impossible à transmettre (%s) : %s", kind, subject[:100])
            await interaction.response.send_message(embed=embeds.error(
                f"Le message n'a pas pu être transmis. Écris directement à {contact.contact_email()}."),
                ephemeral=True)
            return
        self.cooldown.hit(interaction.user.id)
        log.info("Message /contact reçu (%s)", kind)
        await interaction.response.send_message(embed=embeds.success(
            "Merci ! Ton message est bien arrivé. Le créateur du bot peut te répondre en message privé."),
            ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Contact(bot))
