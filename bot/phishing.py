"""Détection des liens dangereux (phishing, faux Nitro, faux Steam).

Deux méthodes combinées :
1. une liste publique de domaines d'arnaque connus, téléchargée et rafraîchie toutes les 6 h ;
2. une détection des imitations (« dlscord-gift.com », « steamcornmunity.ru »…) : domaine qui ressemble
   à un site officiel sans en être un.
"""
from __future__ import annotations

import logging
import re
import time

import aiohttp

log = logging.getLogger("bot.phishing")

REMOTE_LIST = "https://raw.githubusercontent.com/nikolaischunk/discord-phishing-links/main/domain-list.json"
REFRESH_SECONDS = 6 * 3600
URL_RE = re.compile(r"(?:https?://)?(?:www\.)?((?:[a-z0-9-]+\.)+[a-z]{2,})(?:[/:?#]\S*)?", re.IGNORECASE)

OFFICIAL = {
    "discord.com", "discord.gg", "discordapp.com", "discord.gift", "discord.media", "discordapp.net", "discord.new",
    "discord.dev", "discordstatus.com", "steamcommunity.com", "steampowered.com", "steamstatic.com", "store.steampowered.com",
    "twitch.tv", "youtube.com", "youtu.be", "google.com", "github.com", "epicgames.com", "roblox.com", "spotify.com",
    # sites communautaires légitimes qui contiennent « discord » dans leur nom
    "discord.me", "discordbotlist.com", "discordbots.org", "discords.com", "discordservers.com", "discordlist.gg",
    "discord.bio", "discordjs.guide", "discord.js.org", "discordpy.readthedocs.io", "discordtemplates.me", "disboard.org",
    "top.gg", "steamdb.info", "steamgifts.com", "steamcharts.com", "steamladder.com", "steamrep.com",
}
BRANDS = {"discord": ("discord.com", "discord.gg", "discord.gift", "discordapp.com"),
          "steam": ("steamcommunity.com", "steampowered.com"),
          "nitro": ("discord.gift",)}
LOOKALIKE = str.maketrans({"0": "o", "1": "l", "3": "e", "4": "a", "5": "s", "7": "t", "@": "a", "$": "s"})

_known: set[str] = set()
_loaded_at = 0.0


def domains_in(text: str) -> list[str]:
    return [m.group(1).lower().rstrip(".") for m in URL_RE.finditer(text or "")]


def _registrable(domain: str) -> str:
    parts = domain.split(".")
    return ".".join(parts[-2:]) if len(parts) >= 2 else domain


def _distance(a: str, b: str) -> int:
    """Distance de Levenshtein (petits mots uniquement)."""
    if abs(len(a) - len(b)) > 3:
        return 99
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def is_official(domain: str) -> bool:
    return domain in OFFICIAL or any(domain.endswith("." + o) for o in OFFICIAL)


def looks_like_scam(domain: str) -> bool:
    """Imitation d'un site officiel : contient la marque ou en est très proche, sans être le vrai site."""
    if is_official(domain):
        return False
    base = _registrable(domain)
    name = base.rsplit(".", 1)[0]
    flat = name.translate(LOOKALIKE).replace("-", "").replace("rn", "m").replace("l", "i")
    for brand, real_sites in BRANDS.items():
        if brand.replace("l", "i") in flat:
            return True
        for real in real_sites:
            real_name = real.rsplit(".", 1)[0].replace("l", "i")
            if _distance(flat, real_name) <= 2:
                return True
    return False


def find_dangerous(text: str, allowed: list[str] | tuple = ()) -> str | None:
    """Renvoie le premier domaine dangereux trouvé dans le texte, ou None. `allowed` : domaines autorisés par le serveur."""
    allowed_set = {a.lower().strip().removeprefix("www.") for a in allowed if a}
    for domain in domains_in(text):
        if domain in allowed_set or any(domain.endswith("." + a) for a in allowed_set):
            continue
        if domain in _known or _registrable(domain) in _known or looks_like_scam(domain):
            return domain
    return None


async def refresh(session: aiohttp.ClientSession | None = None) -> None:
    """Télécharge la liste publique (silencieux en cas d'échec : la détection des imitations reste active)."""
    global _loaded_at
    if time.time() - _loaded_at < REFRESH_SECONDS:
        return
    _loaded_at = time.time()
    own = session is None
    session = session or aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=20))
    try:
        async with session.get(REMOTE_LIST) as resp:
            if resp.status == 200:
                data = await resp.json(content_type=None)
                domains = data.get("domains", []) if isinstance(data, dict) else data
                _known.clear()
                _known.update(d.lower().strip() for d in domains if isinstance(d, str) and d.strip())
                log.info("Liste anti-phishing chargée : %d domaines", len(_known))
    except Exception as exc:  # réseau, format…
        log.info("Liste anti-phishing indisponible (%s) : détection des imitations seulement", exc)
    finally:
        if own:
            await session.close()
