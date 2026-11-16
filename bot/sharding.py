"""Sharding : la connexion à Discord est découpée en « shards » (obligatoire à partir de 2 500 serveurs).

Le bot utilise discord.py en mode AutoSharded : Discord indique lui-même combien de shards ouvrir
(1 seul tant que le bot est petit), et tout tourne dans le même programme, avec la même base de données.
SHARD_COUNT (facultatif) force un nombre de shards ; vide = automatique (recommandé).
"""
from __future__ import annotations

import os
import time

GUILDS_PER_SHARD = 2500        # limite imposée par Discord
FULL_WARNING = 0.8             # alerte quand un shard dépasse 80 % (2 000 serveurs)
OUTAGE_ALERT_AFTER = 5 * 60    # un shard déconnecté plus de 5 min → alerte au propriétaire
MAX_SHARDS = 1024


def shard_count_from_env() -> int | None:
    """Nombre de shards forcé par SHARD_COUNT, ou None pour laisser Discord choisir."""
    raw = os.getenv("SHARD_COUNT", "").strip().lower()
    if raw.isdigit() and 1 <= int(raw) <= MAX_SHARDS:
        return int(raw)
    return None


def _ms(latency: float | None) -> int | None:
    if latency is None or latency != latency or latency >= 60:  # NaN ou pas encore mesurée
        return None
    return round(latency * 1000)


def shard_summary(bot) -> list[dict]:
    """État de chaque shard : en ligne, latence, nombre de serveurs."""
    counts: dict[int, int] = {}
    for guild in getattr(bot, "guilds", []) or []:
        sid = getattr(guild, "shard_id", 0) or 0
        counts[sid] = counts.get(sid, 0) + 1
    shards = getattr(bot, "shards", None) or {}
    out = []
    for sid, info in sorted(shards.items()):
        out.append({"id": sid, "online": not info.is_closed(), "latency_ms": _ms(info.latency),
                    "guilds": counts.get(sid, 0)})
    if not out:  # bot pas encore connecté
        out = [{"id": sid, "online": False, "latency_ms": None, "guilds": n} for sid, n in sorted(counts.items())]
    return out


def crowded_shards(summary: list[dict], ratio: float = FULL_WARNING) -> list[dict]:
    """Shards trop remplis : au redémarrage, Discord en recalculera le nombre."""
    return [s for s in summary if s["guilds"] >= GUILDS_PER_SHARD * ratio]


class OutageTracker:
    """Suit les shards déconnectés pour n'alerter que si la coupure dure (les reconnexions courtes sont normales)."""

    def __init__(self, after: float = OUTAGE_ALERT_AFTER):
        self.after = after
        self.down: dict[int, float] = {}
        self.alerted: set[int] = set()

    def disconnected(self, shard_id: int, now: float | None = None) -> None:
        self.down.setdefault(shard_id, time.time() if now is None else now)

    def connected(self, shard_id: int) -> float | None:
        """Le shard est revenu. Renvoie la durée de coupure si une alerte était partie (pour annoncer le retour)."""
        since = self.down.pop(shard_id, None)
        if shard_id in self.alerted:
            self.alerted.discard(shard_id)
            return time.time() - since if since else 0.0
        return None

    def due(self, now: float | None = None) -> list[int]:
        """Shards coupés depuis assez longtemps et pas encore signalés (marqués comme signalés)."""
        now = time.time() if now is None else now
        late = sorted(sid for sid, since in self.down.items()
                      if now - since >= self.after and sid not in self.alerted)
        self.alerted.update(late)
        return late
