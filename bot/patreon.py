"""Premium payé via Patreon (en attendant les abonnements Discord).

Comment ça marche :
1. Le membre s'abonne sur la page Patreon du bot (mensuel ou annuel, prix réglés sur Patreon).
2. Dans le panel, il relie son compte Patreon (connexion OAuth : on apprend son identifiant Patreon).
3. Il choisit le serveur qui reçoit le Premium (1 serveur par abonnement, changement possible tous les 7 jours).
4. Patreon prévient le bot à chaque changement (webhook signé) et le bot relit la liste des abonnés
   toutes les 6 heures : le Premium s'arrête tout seul si l'abonnement s'arrête.

Variables : PATREON_CLIENT_ID, PATREON_CLIENT_SECRET (connexion), PATREON_WEBHOOK_SECRET (webhook),
PATREON_CREATOR_TOKEN et PATREON_CREATOR_REFRESH_TOKEN (liste des abonnés), PATREON_URL (page publique),
PATREON_MIN_CENTS (montant minimum, 1 = n'importe quel abonnement payant), PATREON_CAMPAIGN_ID (facultatif).
"""
from __future__ import annotations

import hashlib
import hmac
import logging
import os
import time
from typing import TYPE_CHECKING, Any, AsyncIterator
from urllib.parse import urlencode

import aiohttp

from bot import secrets_box

if TYPE_CHECKING:
    from bot.db import Database

log = logging.getLogger("bot.patreon")

AUTHORIZE_URL = "https://www.patreon.com/oauth2/authorize"
TOKEN_URL = "https://www.patreon.com/api/oauth2/token"
API = "https://www.patreon.com/api/oauth2/v2"
SCOPES = ("identity",)  # sans identity.memberships, Patreon ne renvoie que l'abonnement à NOTRE page
HEADERS = {"User-Agent": "DiscordBot-Premium/1.0"}  # Patreon refuse parfois les appels sans User-Agent
MEMBER_FIELDS = "patron_status,currently_entitled_amount_cents,pledge_cadence,next_charge_date"
ACTIVE = "active_patron"
MOVE_COOLDOWN = 7 * 24 * 3600
TOKEN_SETTING = "patreon_creator_tokens"  # table settings (serveur 0) : jetons créateur à jour, chiffrés


class PatreonError(Exception):
    def __init__(self, message: str, status: int = 0):
        super().__init__(message)
        self.status = status


# --------------------------------------------------------------------------- #
#  Réglages
# --------------------------------------------------------------------------- #
def _env(name: str) -> str:
    return os.getenv(name, "").strip()


def client_id() -> str:
    return _env("PATREON_CLIENT_ID")


def client_secret() -> str:
    return _env("PATREON_CLIENT_SECRET")


def webhook_secret() -> str:
    return _env("PATREON_WEBHOOK_SECRET")


def configured() -> bool:
    """Connexion des membres possible."""
    return bool(client_id() and client_secret())


def page_url() -> str | None:
    """Page Patreon publique où s'abonner (seulement une adresse patreon.com)."""
    url = _env("PATREON_URL")
    if url.startswith(("https://www.patreon.com/", "https://patreon.com/")) and " " not in url:
        return url
    return None


def min_cents() -> int:
    raw = _env("PATREON_MIN_CENTS")
    return max(1, int(raw)) if raw.isdigit() else 1


def authorize_url(redirect_uri: str, state: str) -> str:
    return AUTHORIZE_URL + "?" + urlencode({"response_type": "code", "client_id": client_id(),
                                            "redirect_uri": redirect_uri, "scope": " ".join(SCOPES),
                                            "state": state})


# --------------------------------------------------------------------------- #
#  Lecture des données Patreon
# --------------------------------------------------------------------------- #
def verify_signature(secret: str, raw: bytes, signature: str) -> bool:
    """Signature des webhooks : HMAC-MD5 du corps avec le secret du webhook, en hexadécimal."""
    if not secret or not signature:
        return False
    expected = hmac.new(secret.encode(), raw, hashlib.md5).hexdigest()
    return hmac.compare_digest(expected, signature.strip().lower())


def is_active(status: str | None, cents: int | None, minimum: int | None = None) -> bool:
    return status == ACTIVE and int(cents or 0) >= (min_cents() if minimum is None else minimum)


def parse_member(resource: dict | None) -> dict | None:
    """Ressource « member » de Patreon → {patreon_id, status, cents, cadence, next_charge}."""
    if not isinstance(resource, dict) or resource.get("type") != "member":
        return None
    attrs = resource.get("attributes") or {}
    user = (((resource.get("relationships") or {}).get("user") or {}).get("data") or {})
    patreon_id = str(user.get("id") or "").strip()
    if not patreon_id:
        return None
    return {"patreon_id": patreon_id, "status": attrs.get("patron_status") or None,
            "cents": int(attrs.get("currently_entitled_amount_cents") or 0),
            "cadence": attrs.get("pledge_cadence"), "next_charge": attrs.get("next_charge_date")}


def parse_webhook(event: str, body: dict) -> dict | None:
    member = parse_member((body or {}).get("data"))
    if member and (event == "members:delete" or (event.endswith(":delete") and member["status"] is None)):
        member.update(status="former_patron", cents=0)  # membre retiré : plus de Premium
    # Résiliation (members:pledge:delete) : Patreon garde « active_patron » jusqu'à la fin de la période payée,
    # on suit donc l'état qu'il envoie (la relecture toutes les 6 h coupe le Premium au bon moment).
    return member


def identity_member(identity: dict) -> dict | None:
    """Abonnement du membre connecté à la page du bot (renvoyé par /identity?include=memberships)."""
    user_id = str(((identity or {}).get("data") or {}).get("id") or "")
    for item in (identity or {}).get("included") or []:
        if item.get("type") != "member":
            continue
        item = {**item, "relationships": {**(item.get("relationships") or {}),
                                          "user": {"data": {"id": user_id, "type": "user"}}}}
        return parse_member(item)
    return None


# --------------------------------------------------------------------------- #
#  Base de données
# --------------------------------------------------------------------------- #
async def link(db: "Database", user_id: int, patreon_id: str, name: str | None) -> None:
    """Relie un compte Discord à un compte Patreon (un compte Patreon = un seul compte Discord)."""
    other = await db.fetchone("SELECT user_id FROM patreon_links WHERE patreon_id=? AND user_id<>?",
                              (patreon_id, user_id))
    if other:  # le même Patreon relié à un autre compte Discord : on déplace le lien
        await db.execute("DELETE FROM patreon_slots WHERE user_id=?", (other["user_id"],))
        await db.execute("DELETE FROM patreon_links WHERE user_id=?", (other["user_id"],))
    await db.execute(
        "INSERT INTO patreon_links (user_id, patreon_id, patreon_name, linked_at) VALUES (?,?,?,?) "
        "ON CONFLICT(user_id) DO UPDATE SET patreon_id=excluded.patreon_id, patreon_name=excluded.patreon_name, "
        "linked_at=excluded.linked_at", (user_id, patreon_id, (name or "")[:100], time.time()))


async def unlink(db: "Database", user_id: int) -> None:
    await db.execute("DELETE FROM patreon_slots WHERE user_id=?", (user_id,))
    await db.execute("DELETE FROM patreon_links WHERE user_id=?", (user_id,))


async def save_member(db: "Database", member: dict) -> None:
    await db.execute(
        "INSERT INTO patreon_members (patreon_id, status, cents, cadence, next_charge, updated_at) "
        "VALUES (?,?,?,?,?,?) ON CONFLICT(patreon_id) DO UPDATE SET status=excluded.status, cents=excluded.cents, "
        "cadence=excluded.cadence, next_charge=excluded.next_charge, updated_at=excluded.updated_at",
        (member["patreon_id"], member["status"], member["cents"], member.get("cadence"),
         member.get("next_charge"), time.time()))


async def mark_missing_as_former(db: "Database", seen: set[str]) -> int:
    """Après une lecture complète de la liste : ceux qui n'y sont plus ne sont plus abonnés."""
    rows = await db.fetchall("SELECT patreon_id FROM patreon_members WHERE status=?", (ACTIVE,))
    gone = [r["patreon_id"] for r in rows if r["patreon_id"] not in seen]
    for pid in gone:
        await db.execute("UPDATE patreon_members SET status='former_patron', cents=0, updated_at=? WHERE patreon_id=?",
                         (time.time(), pid))
    return len(gone)


async def premium_guilds(db: "Database") -> dict[int, int]:
    """Serveurs Premium grâce à Patreon → membre Discord qui paie."""
    rows = await db.fetchall(
        "SELECT s.guild_id, s.user_id FROM patreon_slots s JOIN patreon_links l ON l.user_id=s.user_id "
        "JOIN patreon_members m ON m.patreon_id=l.patreon_id WHERE s.active=1 AND m.status=? AND m.cents>=?",
        (ACTIVE, min_cents()))
    return {r["guild_id"]: r["user_id"] for r in rows}


async def user_state(db: "Database", user_id: int, now: float | None = None) -> dict:
    """Ce que le panel affiche pour ce membre."""
    now = time.time() if now is None else now
    row = await db.fetchone(
        "SELECT l.patreon_id, l.patreon_name, m.status, m.cents, m.cadence, m.next_charge FROM patreon_links l "
        "LEFT JOIN patreon_members m ON m.patreon_id=l.patreon_id WHERE l.user_id=?", (user_id,))
    slot = await db.fetchone("SELECT guild_id, assigned_at, active FROM patreon_slots WHERE user_id=?", (user_id,))
    if not row:
        return {"linked": False, "active": False, "guild_id": None, "can_move_at": None}
    return {"linked": True, "name": row["patreon_name"], "active": is_active(row["status"], row["cents"]),
            "status": row["status"], "cadence": row["cadence"], "next_charge": row["next_charge"],
            "guild_id": str(slot["guild_id"]) if slot and slot["active"] else None,
            "last_guild_id": str(slot["guild_id"]) if slot else None,
            "can_move_at": (slot["assigned_at"] + MOVE_COOLDOWN) if slot and slot["assigned_at"] + MOVE_COOLDOWN > now
            else None}


async def assign(db: "Database", user_id: int, guild_id: int, now: float | None = None) -> None:
    """Donne le Premium de ce membre à un serveur. ValueError si ce n'est pas possible."""
    now = time.time() if now is None else now
    state = await user_state(db, user_id, now)
    if not state["linked"]:
        raise ValueError("Relie d'abord ton compte Patreon.")
    if not state["active"]:
        raise ValueError("Aucun abonnement Patreon actif trouvé sur ce compte.")
    if state["last_guild_id"] == str(guild_id):  # même serveur qu'avant : pas de délai
        await db.execute("UPDATE patreon_slots SET active=1 WHERE user_id=?", (user_id,))
        return
    if state["can_move_at"]:
        days = max(1, round((state["can_move_at"] - now) / 86400))
        raise ValueError(f"Tu as changé de serveur récemment. Réessaie dans {days} jour(s).")
    await db.execute(
        "INSERT INTO patreon_slots (user_id, guild_id, assigned_at, active) VALUES (?,?,?,1) ON CONFLICT(user_id) "
        "DO UPDATE SET guild_id=excluded.guild_id, assigned_at=excluded.assigned_at, active=1", (user_id, guild_id, now))


async def unassign(db: "Database", user_id: int) -> None:
    """Retire le Premium du serveur (la date du dernier choix est gardée pour le délai de 7 jours)."""
    await db.execute("UPDATE patreon_slots SET active=0 WHERE user_id=?", (user_id,))


async def refresh_premium(db: "Database") -> dict[int, int]:
    """Recalcule les serveurs Premium via Patreon et prévient le registre Premium."""
    from bot.premium import premium
    guilds = await premium_guilds(db)
    premium.set_patreon(set(guilds))
    return guilds


# --------------------------------------------------------------------------- #
#  API Patreon
# --------------------------------------------------------------------------- #
class PatreonAPI:
    def __init__(self, db: "Database", http: aiohttp.ClientSession):
        self.db, self.http = db, http
        self._campaign: str | None = _env("PATREON_CAMPAIGN_ID") or None

    async def _request(self, method: str, url: str, **kwargs) -> Any:
        headers = {**HEADERS, **kwargs.pop("headers", {})}
        try:
            async with self.http.request(method, url, headers=headers,
                                         timeout=aiohttp.ClientTimeout(total=20), **kwargs) as resp:
                data = await resp.json(content_type=None) if resp.content_length != 0 else {}
                if resp.status >= 400:
                    raise PatreonError(f"Patreon a répondu {resp.status}", resp.status)
                return data
        except aiohttp.ClientError as exc:
            raise PatreonError(f"Patreon injoignable ({exc.__class__.__name__})") from None

    # --- membres : connexion OAuth ------------------------------------------
    async def exchange_code(self, code: str, redirect_uri: str) -> dict:
        return await self._request("POST", TOKEN_URL, data={
            "code": code, "grant_type": "authorization_code", "client_id": client_id(),
            "client_secret": client_secret(), "redirect_uri": redirect_uri})

    async def identity(self, access_token: str) -> dict:
        auth = {"Authorization": f"Bearer {access_token}"}
        query = urlencode({"include": "memberships", "fields[user]": "full_name", "fields[member]": MEMBER_FIELDS})
        try:
            return await self._request("GET", f"{API}/identity?{query}", headers=auth)
        except PatreonError as exc:
            if exc.status != 400:
                raise
        # Demande détaillée refusée : identité seule (l'abonnement sera lu par la relecture de la liste)
        return await self._request("GET", f"{API}/identity", headers=auth)

    # --- créateur : liste des abonnés ---------------------------------------
    async def _creator_tokens(self) -> tuple[str, str]:
        stored = await self.db.get_setting(0, TOKEN_SETTING)
        if stored and secrets_box.available():
            try:
                access, _, refresh = secrets_box.decrypt(stored).partition("\n")
                if access:
                    return access, refresh
            except secrets_box.SecretError:
                pass
        return _env("PATREON_CREATOR_TOKEN"), _env("PATREON_CREATOR_REFRESH_TOKEN")

    async def creator_ready(self) -> bool:
        access, _ = await self._creator_tokens()
        return bool(access)

    async def _refresh_creator(self) -> str:
        _, refresh = await self._creator_tokens()
        if not refresh:
            raise PatreonError("Jeton créateur expiré et aucun jeton de rafraîchissement", 401)
        data = await self._request("POST", TOKEN_URL, data={
            "grant_type": "refresh_token", "refresh_token": refresh,
            "client_id": client_id(), "client_secret": client_secret()})
        access = data.get("access_token") or ""
        if not access:
            raise PatreonError("Patreon n'a pas renvoyé de nouveau jeton", 401)
        if secrets_box.available():  # les jetons changent à chaque rafraîchissement : on garde les nouveaux
            await self.db.set_setting(0, TOKEN_SETTING,
                                      secrets_box.encrypt(f"{access}\n{data.get('refresh_token') or refresh}"))
        log.info("Jeton créateur Patreon rafraîchi")
        return access

    async def _creator_get(self, url: str) -> dict:
        access, _ = await self._creator_tokens()
        if not access:
            raise PatreonError("PATREON_CREATOR_TOKEN manquant", 401)
        try:
            return await self._request("GET", url, headers={"Authorization": f"Bearer {access}"})
        except PatreonError as exc:
            if exc.status != 401:
                raise
        access = await self._refresh_creator()
        return await self._request("GET", url, headers={"Authorization": f"Bearer {access}"})

    async def campaign_id(self) -> str:
        if not self._campaign:
            data = await self._creator_get(f"{API}/campaigns")
            items = data.get("data") or []
            if not items:
                raise PatreonError("Aucune page Patreon trouvée sur ce compte créateur")
            self._campaign = str(items[0]["id"])
        return self._campaign

    async def members(self) -> AsyncIterator[dict]:
        """Tous les abonnés de la page (lecture page par page)."""
        campaign = await self.campaign_id()
        cursor = None
        for _ in range(500):  # garde-fou
            params = {"include": "user", "fields[member]": MEMBER_FIELDS, "page[count]": "1000"}
            if cursor:
                params["page[cursor]"] = cursor
            data = await self._creator_get(f"{API}/campaigns/{campaign}/members?{urlencode(params)}")
            for item in data.get("data") or []:
                member = parse_member(item)
                if member:
                    yield member
            cursor = (((data.get("meta") or {}).get("pagination") or {}).get("cursors") or {}).get("next")
            if not cursor:
                return
