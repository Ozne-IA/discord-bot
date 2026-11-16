"""Tableau de tournoi à élimination directe (fonctions pures, testables).

Un match = {"round": r, "slot": s, "p1": id|None, "p2": id|None, "winner": id|None}.
Tour 1 : les joueurs sont mélangés puis placés ; s'il manque des joueurs pour une puissance de 2,
certains passent directement au tour suivant (« exempt »). Le gagnant des matchs (r, 2k) et (r, 2k+1)
se retrouvent au match (r+1, k).
"""
from __future__ import annotations

import math
import random


def total_rounds(players: int) -> int:
    return max(1, math.ceil(math.log2(max(2, players))))


def first_round(players: list[int], rng: random.Random | None = None) -> list[dict]:
    pool = list(players)
    (rng or random).shuffle(pool)
    size = 2 ** total_rounds(len(pool))
    byes = size - len(pool)
    # Les exemptés sont répartis un par match : jamais de match entre deux cases vides
    slots: list[tuple[int | None, int | None]] = []
    it = iter(pool)
    for i in range(size // 2):
        p1 = next(it)
        p2 = None if i < byes else next(it)
        slots.append((p1, p2))
    matches = []
    for slot, (p1, p2) in enumerate(slots):
        matches.append({"round": 1, "slot": slot, "p1": p1, "p2": p2, "winner": p1 if p2 is None else None})
    return matches


def propagate(matches: list[dict], rounds: int) -> list[dict]:
    """Crée les matchs des tours suivants dont les deux adversaires sont connus (exempts compris)."""
    by_key = {(m["round"], m["slot"]): m for m in matches}
    created: list[dict] = []
    for r in range(1, rounds):
        slots = 2 ** (rounds - r)
        for k in range(slots // 2):
            if (r + 1, k) in by_key:
                continue
            a, b = by_key.get((r, 2 * k)), by_key.get((r, 2 * k + 1))
            if a and b and a["winner"] and b["winner"]:
                m = {"round": r + 1, "slot": k, "p1": a["winner"], "p2": b["winner"], "winner": None}
                by_key[(r + 1, k)] = m
                created.append(m)
    return created


def open_match_for(matches: list[dict], player: int) -> dict | None:
    return next((m for m in matches if m["winner"] is None and player in (m["p1"], m["p2"])), None)


def champion(matches: list[dict], rounds: int) -> int | None:
    final = next((m for m in matches if m["round"] == rounds and m["slot"] == 0), None)
    return final["winner"] if final else None


def round_name(r: int, rounds: int) -> str:
    left = rounds - r
    return {0: "Finale", 1: "Demi-finales", 2: "Quarts de finale"}.get(left, f"Tour {r}")


def render(matches: list[dict], rounds: int, name) -> list[tuple[str, str]]:
    """[(titre du tour, lignes)] pour un embed. name(id) -> texte affiché."""
    out = []
    for r in range(1, rounds + 1):
        lines = []
        for m in sorted((m for m in matches if m["round"] == r), key=lambda m: m["slot"]):
            if m["p2"] is None and r == 1:
                lines.append(f"✅ {name(m['p1'])} — *exempt*")
                continue
            a, b = name(m["p1"]), name(m["p2"])
            if m["winner"]:
                a = f"**{a}** 🏆" if m["winner"] == m["p1"] else f"~~{a}~~"
                b = f"**{b}** 🏆" if m["winner"] == m["p2"] else f"~~{b}~~"
                lines.append(f"{a} vs {b}")
            else:
                lines.append(f"⚔️ {a} vs {b}")
        out.append((round_name(r, rounds), "\n".join(lines) or "*en attente*"))
    return out
