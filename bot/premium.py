"""Version premium : qui y a droit, et comment le proposer.

Deux sources de premium pour un serveur :
  1. un abonnement Discord (App Subscriptions, SKU défini par PREMIUM_SKU_ID) ;
  2. un accès accordé à la main par le propriétaire du bot (/premium_admin give),
     pratique tant que le bot n'est pas vérifié, pour des partenaires ou des tests.

Le statut est gardé en mémoire (lecture instantanée et synchrone, utilisée par la config).
"""
from __future__ import annotations

import logging
import os
import time
from typing import TYPE_CHECKING

import discord

if TYPE_CHECKING:
    from bot.db import Database

log = logging.getLogger("bot.premium")


def sku_id() -> int:
    raw = os.getenv("PREMIUM_SKU_ID", "").strip()
    return int(raw) if raw.isdigit() else 0


class PremiumRegistry:
    def __init__(self) -> None:
        self.subscriptions: dict[int, float | None] = {}  # guild_id -> fin (None = sans fin connue)
        self.grants: dict[int, float | None] = {}          # guild_id -> fin (None = à vie)
        self._listeners: list = []

    def on_change(self, callback) -> None:
        """callback(guild_id) appelé quand le statut d'un serveur change (ex. vider un cache)."""
        self._listeners.append(callback)

    def _changed(self, guild_id: int) -> None:
        for cb in self._listeners:
            cb(guild_id)

    # --- lecture ----------------------------------------------------------
    @staticmethod
    def _active(ends: float | None) -> bool:
        return ends is None or ends > time.time()

    def is_premium(self, guild_id: int | None) -> bool:
        if not guild_id:
            return False
        if guild_id in self.subscriptions and self._active(self.subscriptions[guild_id]):
            return True
        return guild_id in self.grants and self._active(self.grants[guild_id])

    def status(self, guild_id: int) -> dict:
        if guild_id in self.subscriptions and self._active(self.subscriptions[guild_id]):
            return {"active": True, "source": "subscription", "expires_at": self.subscriptions[guild_id]}
        if guild_id in self.grants and self._active(self.grants[guild_id]):
            return {"active": True, "source": "grant", "expires_at": self.grants[guild_id]}
        return {"active": False, "source": None, "expires_at": None}

    # --- chargement -------------------------------------------------------
    async def load(self, db: "Database") -> None:
        rows = await db.fetchall("SELECT guild_id, expires_at FROM premium_grants")
        self.grants = {r["guild_id"]: r["expires_at"] for r in rows}
        log.info("%d accès premium manuels chargés", len(self.grants))

    async def sync_entitlements(self, bot: discord.Client) -> None:
        """Récupère auprès de Discord tous les abonnements actifs."""
        sku = sku_id()
        if not sku:
            log.info("PREMIUM_SKU_ID non défini : abonnements Discord désactivés (accès manuels seulement)")
            return
        subs: dict[int, float | None] = {}
        try:
            async for ent in bot.entitlements(skus=[discord.Object(id=sku)], exclude_ended=True, limit=None):
                if ent.guild_id and not ent.is_expired():
                    subs[ent.guild_id] = ent.ends_at.timestamp() if ent.ends_at else None
        except discord.HTTPException as exc:
            log.warning("Impossible de lire les abonnements Discord : %s", exc)
            return
        changed = set(subs) ^ set(self.subscriptions)
        self.subscriptions = subs
        for gid in changed:
            self._changed(gid)
        log.info("%d serveur(s) abonné(s) via Discord", len(subs))

    def apply_entitlement(self, ent: discord.Entitlement, deleted: bool = False) -> None:
        if not ent.guild_id or ent.sku_id != sku_id():
            return
        if deleted or ent.is_expired() or ent.deleted:
            self.subscriptions.pop(ent.guild_id, None)
        else:
            self.subscriptions[ent.guild_id] = ent.ends_at.timestamp() if ent.ends_at else None
        self._changed(ent.guild_id)

    # --- accès manuels ----------------------------------------------------
    async def grant(self, db: "Database", guild_id: int, by: int, days: int | None, note: str = "") -> float | None:
        expires = time.time() + days * 86400 if days else None
        await db.execute(
            "INSERT INTO premium_grants (guild_id, granted_by, expires_at, note, created_at) VALUES (?,?,?,?,?) "
            "ON CONFLICT(guild_id) DO UPDATE SET granted_by=excluded.granted_by, expires_at=excluded.expires_at, "
            "note=excluded.note", (guild_id, by, expires, note, time.time()))
        self.grants[guild_id] = expires
        self._changed(guild_id)
        return expires

    async def revoke(self, db: "Database", guild_id: int) -> None:
        await db.execute("DELETE FROM premium_grants WHERE guild_id=?", (guild_id,))
        self.grants.pop(guild_id, None)
        self._changed(guild_id)


premium = PremiumRegistry()


def is_premium(guild: "discord.Guild | int | None") -> bool:
    if guild is None:
        return False
    return premium.is_premium(guild if isinstance(guild, int) else guild.id)


# --------------------------------------------------------------------------- #
#  Proposer l'abonnement
# --------------------------------------------------------------------------- #
def store_url(application_id: int | None) -> str | None:
    sku = sku_id()
    if not (sku and application_id):
        return None
    return f"https://discord.com/application-directory/{application_id}/store/{sku}"


def upsell_view() -> discord.ui.View | None:
    """Bouton « S'abonner » natif de Discord (ouvre directement le paiement)."""
    sku = sku_id()
    if not sku:
        return None
    view = discord.ui.View()
    view.add_item(discord.ui.Button(style=discord.ButtonStyle.premium, sku_id=sku))
    return view


def upsell_embed(feature: str) -> discord.Embed:
    from bot import embeds  # import tardif (embeds dépend de la config)
    text = (f"**{feature}** fait partie de la version **Premium**.\n\n"
            "Premium débloque : giveaways et sondages, captcha de vérification, XP vocal, carte de rang, "
            "classements hebdo/mensuels, alertes Twitch/YouTube, personnalisation complète des messages, "
            "transcripts HTML et avis, anti-nuke et lockdown automatique.")
    if not sku_id():
        text += "\n\nContacte le propriétaire du bot pour l'activer sur ce serveur."
    return embeds.base("💎 Fonction Premium", text, color=0xF1C40F)


async def require(interaction: discord.Interaction, feature: str) -> bool:
    """À appeler au début d'une commande premium. Répond et renvoie False si le serveur n'est pas premium."""
    if is_premium(interaction.guild_id):
        return True
    view = upsell_view()
    kwargs = {"embed": upsell_embed(feature), "ephemeral": True}
    if view:
        kwargs["view"] = view
    if interaction.response.is_done():
        await interaction.followup.send(**kwargs)
    else:
        await interaction.response.send_message(**kwargs)
    return False
