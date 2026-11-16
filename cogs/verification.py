"""Vérification : panneau de règles + bouton « J'accepte » qui donne le rôle Membre.
💎 Premium : captcha (code en image à recopier) avant d'obtenir le rôle."""
from __future__ import annotations

import io
import time

import discord
from discord import app_commands
from discord.ext import commands

from bot import embeds
from bot.config import gconf
from bot.i18n import tr
from bot.images import captcha_image, new_captcha_code
from bot.panels import publish_panel
from bot.utils import send_log

CAPTCHA_TTL = 300        # secondes pour répondre
CAPTCHA_ATTEMPTS = 3     # essais par code
# (guild_id, user_id) -> {"code", "expires", "attempts"}
pending_captchas: dict[tuple[int, int], dict] = {}


async def grant_member(interaction: discord.Interaction) -> None:
    """Donne le rôle Membre, retire Non vérifié, confirme et journalise."""
    member = interaction.user
    assert isinstance(member, discord.Member) and interaction.guild
    cfg = gconf(interaction.guild)
    member_role = interaction.guild.get_role(cfg.role_id("member"))
    unverified = interaction.guild.get_role(cfg.role_id("unverified"))
    assert member_role
    await member.add_roles(member_role, reason="Vérification acceptée")
    if unverified and unverified in member.roles:
        await member.remove_roles(unverified, reason="Vérification acceptée")
    g = interaction.guild
    embed = embeds.success(tr(g, "Tu as maintenant accès à tout le serveur. Amuse-toi bien !"), tr(g, "✅ Vérifié(e)"))
    if interaction.response.is_done():
        await interaction.followup.send(embed=embed, ephemeral=True)
    else:
        await interaction.response.send_message(embed=embed, ephemeral=True)
    await send_log(interaction.guild, embeds.success(f"{member.mention} s'est vérifié(e).", "✅ Vérification"))


class CaptchaModal(discord.ui.Modal, title="Vérification"):
    code = discord.ui.TextInput(label="Recopie le code de l'image", min_length=4, max_length=8,
                                placeholder="Ex : A7K3P")

    async def on_submit(self, interaction: discord.Interaction) -> None:
        key = (interaction.guild_id or 0, interaction.user.id)
        entry = pending_captchas.get(key)
        if not entry or entry["expires"] < time.time():
            pending_captchas.pop(key, None)
            await interaction.response.send_message(
                embed=embeds.error("Code expiré. Reclique sur « J'accepte les règles » pour en avoir un nouveau."),
                ephemeral=True)
            return
        if str(self.code).strip().upper().replace(" ", "") == entry["code"]:
            pending_captchas.pop(key, None)
            await grant_member(interaction)
            return
        entry["attempts"] -= 1
        if entry["attempts"] <= 0:
            pending_captchas.pop(key, None)
            msg = "Code incorrect. Plus d'essais : reclique sur « J'accepte les règles » pour un nouveau code."
        else:
            msg = f"Code incorrect. Il te reste {entry['attempts']} essai(s)."
        await interaction.response.send_message(embed=embeds.error(msg), ephemeral=True)


class CaptchaView(discord.ui.View):
    def __init__(self) -> None:
        super().__init__(timeout=CAPTCHA_TTL)

    @discord.ui.button(label="Entrer le code", emoji="⌨️", style=discord.ButtonStyle.primary)
    async def enter(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await interaction.response.send_modal(CaptchaModal())


class VerifyView(discord.ui.View):
    """Vue persistante : les boutons continuent de marcher après un redémarrage."""

    def __init__(self) -> None:
        super().__init__(timeout=None)

    @discord.ui.button(label="J'accepte les règles", emoji="✅",
                       style=discord.ButtonStyle.success, custom_id="verify:accept")
    async def accept(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        member = interaction.user
        assert isinstance(member, discord.Member) and interaction.guild
        cfg = gconf(interaction.guild)
        member_role = interaction.guild.get_role(cfg.role_id("member"))

        if member_role is None:
            await interaction.response.send_message(
                embed=embeds.error("Le rôle Membre n'est pas configuré. Préviens le staff."), ephemeral=True)
            return
        if member_role in member.roles:
            await interaction.response.send_message(embed=embeds.info(tr(interaction.guild, "Tu es déjà vérifié(e) 👍")),
                                                    ephemeral=True)
            return

        if not cfg.get("verification", "captcha", default=False):
            await grant_member(interaction)
            return

        # Captcha (Premium) : un code en image, à recopier dans un formulaire.
        code = new_captcha_code()
        pending_captchas[(interaction.guild.id, member.id)] = {
            "code": code, "expires": time.time() + CAPTCHA_TTL, "attempts": CAPTCHA_ATTEMPTS}
        # petit ménage des codes expirés
        now = time.time()
        for key in [k for k, v in pending_captchas.items() if v["expires"] < now]:
            pending_captchas.pop(key, None)
        embed = embeds.info("Recopie le code affiché sur l'image en cliquant sur **Entrer le code**.\n"
                            f"Tu as {CAPTCHA_TTL // 60} minutes et {CAPTCHA_ATTEMPTS} essais.",
                            tr(interaction.guild, "🔐 Vérification anti-robot"))
        embed.set_image(url="attachment://captcha.png")
        await interaction.response.send_message(
            embed=embed, file=discord.File(io.BytesIO(captcha_image(code)), filename="captcha.png"),
            view=CaptchaView(), ephemeral=True)


def build_panel(guild: discord.Guild) -> tuple[discord.Embed, discord.ui.View]:
    rules = gconf(guild).get("verification", "rules", default=[]) or []
    text = "\n".join(f"**{i}.** {rule}" for i, rule in enumerate(rules, 1))
    embed = embeds.base(tr(guild, "📜 Règles de {server}", server=guild.name),
                        (text or tr(guild, "Respecte tout le monde."))
                        + "\n\n" + tr(guild, "Clique sur le bouton ci-dessous pour accepter les règles et accéder au serveur."),
                        guild=guild)
    view = VerifyView()
    view.accept.label = tr(guild, "J'accepte les règles")  # type: ignore[attr-defined]
    return embed, view


class Verification(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def cog_load(self) -> None:
        self.bot.add_view(VerifyView())

    @app_commands.command(name="setup_verify", description="Envoie le panneau règles + vérification ici")
    @app_commands.default_permissions(administrator=True)
    @app_commands.guild_only()
    async def setup_verify(self, interaction: discord.Interaction) -> None:
        assert interaction.guild and isinstance(interaction.channel, discord.TextChannel)
        await publish_panel(self.bot, interaction.guild, "verify", interaction.channel)
        await interaction.response.send_message(embed=embeds.success("Panneau envoyé."), ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Verification(bot))
