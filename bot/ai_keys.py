"""Clé d'IA de chaque serveur : enregistrement chiffré, lecture, suppression.

La clé en clair ne sort de ce module que pour appeler le fournisseur ; le panel ne reçoit que
le fournisseur, le modèle et la version masquée (« sk-…a4f2 »).
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import TYPE_CHECKING

from bot import secrets_box
from bot.ai_providers import PROVIDERS

if TYPE_CHECKING:
    from bot.db import Database


@dataclass
class GuildAIKey:
    provider: str
    model: str
    key: str


async def info(db: "Database", guild_id: int) -> dict | None:
    """Ce que le panel a le droit de voir (jamais la clé)."""
    row = await db.fetchone("SELECT provider, model, key_hint, updated_at FROM ai_keys WHERE guild_id=?", (guild_id,))
    return dict(row) if row else None


async def load(db: "Database", guild_id: int) -> GuildAIKey | None:
    """La clé déchiffrée, ou None. Lève secrets_box.SecretError si elle est illisible."""
    row = await db.fetchone("SELECT provider, model, key_enc FROM ai_keys WHERE guild_id=?", (guild_id,))
    if not row:
        return None
    return GuildAIKey(row["provider"], row["model"], secrets_box.decrypt(row["key_enc"]))


async def save(db: "Database", guild_id: int, provider: str, key: str, model: str, by: int) -> dict:
    if provider not in PROVIDERS:
        raise ValueError("Fournisseur d'IA inconnu.")
    key = key.strip()
    await db.execute(
        "INSERT INTO ai_keys (guild_id, provider, model, key_enc, key_hint, updated_by, updated_at) "
        "VALUES (?,?,?,?,?,?,?) ON CONFLICT(guild_id) DO UPDATE SET provider=excluded.provider, "
        "model=excluded.model, key_enc=excluded.key_enc, key_hint=excluded.key_hint, "
        "updated_by=excluded.updated_by, updated_at=excluded.updated_at",
        (guild_id, provider, model, secrets_box.encrypt(key), secrets_box.hint(key), by, time.time()))
    return await info(db, guild_id) or {}


async def set_model(db: "Database", guild_id: int, model: str, by: int) -> None:
    await db.execute("UPDATE ai_keys SET model=?, updated_by=?, updated_at=? WHERE guild_id=?",
                     (model, by, time.time(), guild_id))


async def delete(db: "Database", guild_id: int) -> None:
    await db.execute("DELETE FROM ai_keys WHERE guild_id=?", (guild_id,))
