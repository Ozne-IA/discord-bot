"""Votes top.gg : vérification des webhooks, enregistrement et récompenses.

top.gg prévient le bot à chaque vote (webhook vers PUBLIC_URL/webhooks/topgg). Deux formats existent :
  - ancien (v0) : en-tête Authorization = le secret choisi par toi, corps {"user", "type", "isWeekend"} ;
  - nouveau (v1) : en-tête x-topgg-signature "t=<horodatage>,v1=<HMAC-SHA256 hex de "t.corps">"
    signé avec le secret du webhook (whs_…), corps {"type": "vote.create", "data": {...}}.
Les deux sont acceptés avec la même variable TOPGG_WEBHOOK_SECRET.

Un vote est global (il ne dépend pas d'un serveur) : le membre le récupère ensuite avec /vote
sur le serveur de son choix, une fois par vote.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Mapping

if TYPE_CHECKING:
    from bot.db import Database

VOTE_COOLDOWN = 12 * 3600      # top.gg : un vote toutes les 12 h
CLAIM_WINDOW = 24 * 3600       # le vote peut être récupéré pendant 24 h
SIGNATURE_MAX_AGE = 300        # signature v1 refusée au-delà de 5 minutes
TOPGG_API = "https://top.gg/api"


def topgg_token() -> str:
    return os.getenv("TOPGG_TOKEN", "").strip()


def webhook_secret() -> str:
    return os.getenv("TOPGG_WEBHOOK_SECRET", "").strip()


def vote_url(application_id: int | None) -> str | None:
    return f"https://top.gg/bot/{application_id}/vote" if application_id else None


def enabled() -> bool:
    return bool(webhook_secret())


@dataclass
class Vote:
    user_id: int
    weekend: bool = False
    test: bool = False


class WebhookError(Exception):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


def _header(headers: Mapping[str, str], name: str) -> str:
    for key, value in headers.items():
        if key.lower() == name:
            return value
    return ""


def verify_signature(secret: str, header: str, raw: bytes, now: float | None = None) -> bool:
    """Vérifie l'en-tête x-topgg-signature (format v1)."""
    parts = dict(p.split("=", 1) for p in header.split(",") if "=" in p)
    stamp, sig = parts.get("t", "").strip(), parts.get("v1", "").strip()
    if not stamp.isdigit() or not sig:
        return False
    now = time.time() if now is None else now
    if abs(now - int(stamp)) > SIGNATURE_MAX_AGE:
        return False
    expected = hmac.new(secret.encode(), stamp.encode() + b"." + raw, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, sig)


def parse_webhook(headers: Mapping[str, str], raw: bytes, secret: str, now: float | None = None) -> Vote:
    """Vérifie l'authenticité de la requête et en extrait le vote. Lève WebhookError sinon."""
    if not secret:
        raise WebhookError("TOPGG_WEBHOOK_SECRET n'est pas configuré.", 503)
    signature = _header(headers, "x-topgg-signature")
    if signature:
        if not verify_signature(secret, signature, raw, now):
            raise WebhookError("Signature invalide.", 401)
    else:
        auth = _header(headers, "authorization").strip()
        if not auth or not hmac.compare_digest(auth.encode(), secret.encode()):
            raise WebhookError("Secret invalide.", 401)
    try:
        body = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise WebhookError("Corps illisible.") from None
    if not isinstance(body, dict):
        raise WebhookError("Corps illisible.")

    kind = str(body.get("type", ""))
    if kind in ("vote.create", "webhook.test"):          # format v1
        data = body.get("data") or {}
        user = (data.get("user") or {}) if isinstance(data, dict) else {}
        user_id = str(user.get("platform_id") or "")
        weekend = isinstance(data, dict) and int(data.get("weight") or 1) > 1
        test = kind == "webhook.test"
    elif kind in ("upvote", "test"):                        # format v0
        user_id = str(body.get("user") or "")
        weekend = bool(body.get("isWeekend"))
        test = kind == "test"
    else:
        raise WebhookError("Type d'événement inconnu.")
    if not user_id.isdigit():
        raise WebhookError("Utilisateur manquant.")
    return Vote(int(user_id), weekend, test)


async def record_vote(db: "Database", vote: Vote, now: float | None = None) -> None:
    await db.execute("INSERT INTO bot_votes (user_id, voted_at, weekend) VALUES (?,?,?)",
                     (vote.user_id, time.time() if now is None else now, int(vote.weekend)))


async def last_vote(db: "Database", user_id: int):
    return await db.fetchone("SELECT * FROM bot_votes WHERE user_id=? ORDER BY voted_at DESC LIMIT 1", (user_id,))


async def claim(db: "Database", user_id: int, guild_id: int, now: float | None = None):
    """Marque le vote non récupéré le plus récent comme récupéré sur ce serveur. Renvoie la ligne, ou None."""
    now = time.time() if now is None else now
    row = await db.fetchone(
        "SELECT * FROM bot_votes WHERE user_id=? AND claimed_guild IS NULL AND voted_at > ? "
        "ORDER BY voted_at DESC LIMIT 1", (user_id, now - CLAIM_WINDOW))
    if not row:
        return None
    await db.execute("UPDATE bot_votes SET claimed_guild=?, claimed_at=? WHERE id=? AND claimed_guild IS NULL",
                     (guild_id, now, row["id"]))
    # Vérifie que c'est bien cette demande qui l'a obtenu (deux /vote en même temps)
    check = await db.fetchone("SELECT claimed_guild, claimed_at FROM bot_votes WHERE id=?", (row["id"],))
    if not check or check["claimed_guild"] != guild_id or check["claimed_at"] != now:
        return None
    return row


def reward_amount(base: int, weekend: bool) -> int:
    return max(0, int(base)) * (2 if weekend else 1)
