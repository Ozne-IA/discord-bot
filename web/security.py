"""Protections du site : limite de requêtes par adresse IP et politique de sécurité du contenu (CSP)."""
from __future__ import annotations

import time
from collections import deque

from aiohttp import web

# (nom, nombre de requêtes, fenêtre en secondes)
RULES = {
    "auth": (20, 60),     # connexion Discord
    "write": (40, 60),    # modifications depuis le panel
    "api": (180, 60),     # lectures de l'API
    "page": (120, 60),    # pages du site
    "webhook": (60, 60),  # votes top.gg
}


def bucket_for(method: str, path: str) -> str | None:
    """Catégorie de limite d'une requête (None = pas de limite)."""
    if path == "/health" or path.startswith("/static/"):
        return None
    if path in ("/login", "/callback"):
        return "auth"
    if path.startswith("/webhooks/"):
        return "webhook"
    if path.startswith("/api/") or path == "/logout":
        return "api" if method in ("GET", "HEAD") else "write"
    return "page"


def client_ip(request: web.Request) -> str:
    """Adresse du visiteur derrière Cloudflare / Railway."""
    for header in ("CF-Connecting-IP", "X-Real-IP"):
        value = request.headers.get(header, "").strip()
        if value:
            return value[:64]
    forwarded = request.headers.get("X-Forwarded-For", "")
    if forwarded:
        return forwarded.split(",")[0].strip()[:64]
    return request.remote or "?"


class RateLimiter:
    """Fenêtre glissante en mémoire : au plus N requêtes par fenêtre, par IP et par catégorie."""

    def __init__(self, rules: dict[str, tuple[int, int]] | None = None):
        self.rules = rules or RULES
        self.hits: dict[tuple[str, str], deque[float]] = {}
        self._last_cleanup = 0.0

    def check(self, ip: str, bucket: str, now: float | None = None) -> int:
        """0 si la requête passe, sinon le nombre de secondes à attendre."""
        now = time.monotonic() if now is None else now
        limit, window = self.rules[bucket]
        q = self.hits.setdefault((ip, bucket), deque())
        while q and now - q[0] >= window:
            q.popleft()
        if len(q) >= limit:
            return max(1, int(window - (now - q[0])) + 1)
        q.append(now)
        if now - self._last_cleanup > 300:
            self._cleanup(now)
        return 0

    def _cleanup(self, now: float) -> None:
        self._last_cleanup = now
        longest = max(w for _, w in self.rules.values())
        for key in [k for k, q in self.hits.items() if not q or now - q[-1] >= longest]:
            del self.hits[key]


def content_security_policy(nonce: str) -> str:
    """Le navigateur n'exécute que les scripts du site (et les scripts intégrés marqués du nonce)."""
    return "; ".join([
        "default-src 'self'",
        f"script-src 'self' 'nonce-{nonce}'",
        "style-src 'self' 'unsafe-inline'",
        "img-src 'self' data: blob: https:",
        "font-src 'self' data:",
        "connect-src 'self'",
        "object-src 'none'",
        "base-uri 'self'",
        "form-action 'self'",
        "frame-ancestors 'none'",
    ])
