"""Sauvegardes automatiques de la base : compression, rotation et calendrier.

La base contient les données de TOUS les serveurs. Une copie compressée est faite chaque nuit
dans data/backups/ et envoyée au propriétaire du bot (en message privé ou dans un salon choisi),
pour qu'il existe toujours une copie en dehors de Railway.
"""
from __future__ import annotations

import gzip
import io
import os
import shutil
from pathlib import Path

GZIP_MAGIC = b"\x1f\x8b"
AUTO_PREFIX = "auto_"
MAX_RESTORE_SIZE = 500 * 1024 * 1024  # taille maximale d'une base décompressée (protection)


def env_int(name: str, default: int, low: int, high: int) -> int:
    raw = os.getenv(name, "").strip()
    try:
        value = int(raw) if raw else default
    except ValueError:
        value = default
    return max(low, min(high, value))


def auto_enabled() -> bool:
    return os.getenv("BACKUP_AUTO", "on").strip().lower() not in ("off", "0", "non", "false", "no")


def is_due(last: float | None, now: float, hour: int, utc_hour: int) -> bool:
    """Faut-il faire la sauvegarde automatique maintenant ?

    - jamais faite : oui (premier démarrage, ou après une restauration) ;
    - sinon une fois par jour, à l'heure choisie (UTC) ;
    - rattrapage si plus de 25 h se sont écoulées (bot éteint pendant l'heure prévue).
    """
    if last is None:
        return True
    elapsed = now - last
    if elapsed >= 25 * 3600:
        return True
    return elapsed >= 23 * 3600 and utc_hour == hour


def compress(src: Path, dst: Path) -> None:
    with open(src, "rb") as fin, gzip.open(dst, "wb", compresslevel=6) as fout:
        shutil.copyfileobj(fin, fout, length=1024 * 1024)


def prune(folder: Path, keep: int, prefix: str = AUTO_PREFIX) -> list[Path]:
    """Garde les `keep` sauvegardes automatiques les plus récentes, supprime les autres."""
    files = sorted((p for p in folder.glob(f"{prefix}*") if p.is_file()), key=lambda p: p.name, reverse=True)
    removed = files[keep:]
    for p in removed:
        p.unlink(missing_ok=True)
    return removed


def maybe_decompress(data: bytes) -> bytes:
    """Accepte une sauvegarde .db ou .db.gz (renvoie toujours le contenu .db).

    Lève ValueError si l'archive est abîmée ou trop grosse une fois décompressée.
    """
    if not data.startswith(GZIP_MAGIC):
        return data
    try:
        with gzip.GzipFile(fileobj=io.BytesIO(data)) as f:
            out = f.read(MAX_RESTORE_SIZE + 1)
    except (OSError, EOFError) as exc:
        raise ValueError("Archive .gz abîmée.") from exc
    if len(out) > MAX_RESTORE_SIZE:
        raise ValueError("Sauvegarde trop grosse une fois décompressée.")
    return out
