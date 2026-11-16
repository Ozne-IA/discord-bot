"""Modération Twitch : outils sans réseau (signature des événements, règles de l'automod, connexion OAuth).

Fonctionnement (méthode recommandée par Twitch pour un bot hébergé en ligne) :
  - un compte Twitch « bot » autorise l'application une fois (BOT_SCOPES) : c'est lui qui modère ;
  - chaque streamer relie sa chaîne depuis le panel (BROADCASTER_SCOPES) et nomme le bot modérateur ;
  - Twitch envoie les messages du chat et les bans/débans à PUBLIC_URL/webhooks/twitch (EventSub), signés
    avec TWITCH_EVENTSUB_SECRET.
"""
from __future__ import annotations

import hashlib
import hmac
import os
import re
import secrets
import time
from collections import OrderedDict
from datetime import datetime, timezone
from typing import Mapping
from urllib.parse import urlencode

from bot.phishing import find_dangerous

AUTHORIZE_URL = "https://id.twitch.tv/oauth2/authorize"
TOKEN_URL = "https://id.twitch.tv/oauth2/token"
VALIDATE_URL = "https://id.twitch.tv/oauth2/validate"
HELIX = "https://api.twitch.tv/helix"

BOT_SCOPES = ("user:read:chat", "user:write:chat", "user:bot", "moderator:manage:banned_users",
              "moderator:manage:chat_messages")
BROADCASTER_SCOPES = ("channel:bot", "channel:moderate", "moderation:read")

# Abonnements EventSub par chaîne : (type, version, condition qui a besoin de l'ID du bot ?)
SUBSCRIPTIONS = (("channel.chat.message", "1", True), ("channel.ban", "1", False), ("channel.unban", "1", False))

MAX_EVENT_AGE = 600  # secondes : au-delà, un événement est refusé (protection contre le rejeu)
RULE_NAMES = {"phishing": "Lien d'arnaque", "words": "Mot interdit", "links": "Lien non autorisé",
              "caps": "Trop de majuscules", "repeat": "Message répété"}


def client_id() -> str:
    return os.getenv("TWITCH_CLIENT_ID", "").strip()


def client_secret() -> str:
    return os.getenv("TWITCH_CLIENT_SECRET", "").strip()


def eventsub_secret() -> str:
    secret = os.getenv("TWITCH_EVENTSUB_SECRET", "").strip()
    return secret if 10 <= len(secret) <= 100 and secret.isascii() else ""


def configured() -> bool:
    return bool(client_id() and client_secret() and eventsub_secret())


# --------------------------------------------------------------------------- #
#  Connexion OAuth (state anti-CSRF gardé en mémoire 10 minutes)
# --------------------------------------------------------------------------- #
class OAuthStates:
    def __init__(self, ttl: int = 600):
        self.ttl = ttl
        self.items: dict[str, tuple[float, dict]] = {}

    def create(self, **data) -> str:
        now = time.time()
        self.items = {k: v for k, v in self.items.items() if v[0] > now}
        state = secrets.token_urlsafe(24)
        self.items[state] = (now + self.ttl, data)
        return state

    def pop(self, state: str) -> dict | None:
        item = self.items.pop(state or "", None)
        if not item or item[0] < time.time():
            return None
        return item[1]


def authorize_url(redirect_uri: str, scopes: tuple[str, ...], state: str) -> str:
    return AUTHORIZE_URL + "?" + urlencode({
        "response_type": "code", "client_id": client_id(), "redirect_uri": redirect_uri,
        "scope": " ".join(scopes), "state": state, "force_verify": "true"})


def missing_scopes(granted: list[str] | tuple[str, ...], needed: tuple[str, ...]) -> list[str]:
    return [s for s in needed if s not in set(granted or ())]


# --------------------------------------------------------------------------- #
#  Webhook EventSub : vérification de la signature
# --------------------------------------------------------------------------- #
def _header(headers: Mapping[str, str], name: str) -> str:
    for key, value in headers.items():
        if key.lower() == name:
            return value
    return ""


def verify_event(headers: Mapping[str, str], raw: bytes, secret: str, now: float | None = None) -> bool:
    """HMAC-SHA256(secret, message_id + timestamp + corps brut) == en-tête de signature, et pas trop vieux."""
    if not secret:
        return False
    msg_id = _header(headers, "twitch-eventsub-message-id")
    stamp = _header(headers, "twitch-eventsub-message-timestamp")
    signature = _header(headers, "twitch-eventsub-message-signature")
    if not (msg_id and stamp and signature):
        return False
    expected = "sha256=" + hmac.new(secret.encode(), msg_id.encode() + stamp.encode() + raw,
                                    hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, signature):
        return False
    try:
        # Horodatage RFC3339 avec nanosecondes : on garde la seconde près
        sent = datetime.strptime(stamp[:19], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc).timestamp()
    except ValueError:
        return False
    now = time.time() if now is None else now
    return abs(now - sent) <= MAX_EVENT_AGE


class SeenIds:
    """Twitch peut envoyer deux fois le même événement : on ignore les doublons (mêmes message_id)."""

    def __init__(self, size: int = 5000):
        self.size = size
        self.ids: OrderedDict[str, None] = OrderedDict()

    def add(self, msg_id: str) -> bool:
        """True si c'est la première fois qu'on le voit."""
        if msg_id in self.ids:
            return False
        self.ids[msg_id] = None
        while len(self.ids) > self.size:
            self.ids.popitem(last=False)
        return True


# --------------------------------------------------------------------------- #
#  Automod du chat Twitch
# --------------------------------------------------------------------------- #
_DOMAIN = re.compile(r"(?:https?://)?(?:www\.)?((?:[a-z0-9-]+\.)+[a-z]{2,})(?:[/:?#]\S*)?", re.IGNORECASE)
_LETTERS = re.compile(r"[^\W\d_]", re.UNICODE)


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip().lower()


def _domain_allowed(domain: str, allowed: list[str]) -> bool:
    domain = domain.lower()
    for entry in allowed:
        entry = entry.strip().lower().removeprefix("https://").removeprefix("http://").removeprefix("www.").strip("/")
        if entry and (domain == entry or domain.endswith("." + entry)):
            return True
    return False


def links_in(text: str) -> list[str]:
    return [m.group(1).lower() for m in _DOMAIN.finditer(text or "")]


def caps_ratio(text: str) -> tuple[int, float]:
    letters = _LETTERS.findall(text or "")
    if not letters:
        return 0, 0.0
    upper = sum(1 for c in letters if c.isupper())
    return len(letters), upper / len(letters) * 100


def check_message(text: str, cfg: dict, recent: list[str]) -> tuple[str, str] | None:
    """Renvoie (règle, action) de la première règle enfreinte, ou None.

    cfg = section twitch_mod de la configuration ; recent = messages récents du même spectateur (normalisés),
    sans celui-ci.
    """
    def action(rule: str) -> str:
        return str(cfg.get(f"{rule}_action") or "off")

    if action("phishing") != "off" and find_dangerous(text):
        return "phishing", action("phishing")
    if action("words") != "off":
        low = normalize(text)
        for word in cfg.get("banned_words") or []:
            word = normalize(str(word))
            if word and re.search(rf"(?<!\w){re.escape(word)}(?!\w)", low):
                return "words", action("words")
    if action("links") != "off":
        allowed = list(cfg.get("allowed_domains") or [])
        if any(not _domain_allowed(d, allowed) for d in links_in(text)):
            return "links", action("links")
    if action("caps") != "off":
        count, ratio = caps_ratio(text)
        if count >= int(cfg.get("caps_min_length") or 15) and ratio >= int(cfg.get("caps_percent") or 70):
            return "caps", action("caps")
    if action("repeat") != "off":
        needed = max(2, int(cfg.get("repeat_count") or 3))
        current = normalize(text)
        if current and sum(1 for m in recent if m == current) + 1 >= needed:
            return "repeat", action("repeat")
    return None


def exempt(badges: list[dict] | None, exempt_subscribers: bool) -> bool:
    """Le streamer, les modos et les VIP ne sont jamais sanctionnés (les abonnés si l'option est cochée)."""
    sets = {str(b.get("set_id")) for b in badges or [] if isinstance(b, dict)}
    if sets & {"broadcaster", "moderator", "vip", "staff", "admin"}:
        return True
    return exempt_subscribers and ("subscriber" in sets or "founder" in sets)
