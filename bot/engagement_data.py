"""Données de l'engagement : succès (badges) et quêtes. Fonctions pures, faciles à tester."""
from __future__ import annotations

import hashlib
import random
from datetime import date, timedelta

# id -> (emoji, nom, description, statistique, seuil, récompense)
ACHIEVEMENTS: dict[str, tuple[str, str, str, str, int, int]] = {
    "msg_100": ("💬", "Bavard", "Envoyer 100 messages", "messages", 100, 100),
    "msg_1000": ("🗣️", "Pipelette", "Envoyer 1 000 messages", "messages", 1000, 500),
    "msg_10000": ("📣", "Légende du chat", "Envoyer 10 000 messages", "messages", 10000, 3000),
    "lvl_5": ("⭐", "Premiers pas", "Atteindre le niveau 5", "level", 5, 100),
    "lvl_10": ("🌟", "Habitué", "Atteindre le niveau 10", "level", 10, 300),
    "lvl_25": ("💫", "Vétéran", "Atteindre le niveau 25", "level", 25, 1000),
    "lvl_50": ("👑", "Élite", "Atteindre le niveau 50", "level", 50, 5000),
    "rich_10k": ("💰", "Économe", "Posséder 10 000 (porte-monnaie + banque)", "wealth", 10000, 0),
    "rich_100k": ("🏦", "Fortune", "Posséder 100 000 (porte-monnaie + banque)", "wealth", 100000, 0),
    "daily_7": ("📅", "Fidèle", "Série /daily de 7 jours", "daily_streak", 7, 200),
    "daily_30": ("🗓️", "Inarrêtable", "Série /daily de 30 jours", "daily_streak", 30, 1500),
    "active_7": ("🔥", "Assidu", "Parler 7 jours d'affilée", "activity_streak", 7, 200),
    "active_30": ("☄️", "Pilier du serveur", "Parler 30 jours d'affilée", "activity_streak", 30, 1500),
    "invite_5": ("📨", "Recruteur", "5 invités toujours présents", "invites", 5, 300),
    "invite_25": ("🎯", "Ambassadeur", "25 invités toujours présents", "invites", 25, 2000),
    "quests_10": ("📜", "Aventurier", "Terminer 10 quêtes", "quests", 10, 300),
    "quests_50": ("🏆", "Héros des quêtes", "Terminer 50 quêtes", "quests", 50, 2000),
    "games_10": ("🎲", "Joueur", "Gagner 10 parties de mini-jeux", "game_wins", 10, 200),
    "games_100": ("🃏", "Champion du casino", "Gagner 100 parties de mini-jeux", "game_wins", 100, 2000),
}

# Quêtes : id -> (activité suivie, objectif quotidien, objectif hebdo, texte avec {n})
QUESTS: dict[str, tuple[str, int, int, str]] = {
    "messages": ("message", 30, 300, "Envoyer {n} messages"),
    "daily": ("daily", 1, 5, "Récupérer ta récompense /daily ({n} fois)"),
    "work": ("work", 2, 15, "Travailler {n} fois avec /work"),
    "play": ("game_play", 3, 20, "Jouer {n} parties de mini-jeux"),
    "win": ("game_win", 1, 8, "Gagner {n} partie(s) de mini-jeux"),
    "chat_more": ("message", 60, 600, "Envoyer {n} messages"),
}
DAILY_COUNT = 3
ECONOMY_KINDS = {"daily", "work", "game_play", "game_win"}


def day_key(today: date) -> str:
    return today.isoformat()


def week_key(today: date) -> str:
    year, week, _ = today.isocalendar()
    return f"{year}-W{week:02d}"


def next_reset(today: date, weekly: bool) -> date:
    return today + timedelta(days=7 - today.weekday()) if weekly else today + timedelta(days=1)


def _rng(guild_id: int, period: str) -> random.Random:
    seed = hashlib.sha256(f"{guild_id}:{period}".encode()).hexdigest()
    return random.Random(int(seed[:16], 16))


def quests_for(guild_id: int, period: str, weekly: bool, economy: bool = True, games: bool = True) -> list[str]:
    """Quêtes du jour (3) ou de la semaine (1), les mêmes pour tout le serveur, tirées au sort par période."""
    pool = []
    for qid, (kind, *_rest) in QUESTS.items():
        if kind in ECONOMY_KINDS and not economy:
            continue
        if kind.startswith("game") and not games:
            continue
        pool.append(qid)
    # Jamais deux quêtes de messages le même jour
    rng = _rng(guild_id, period)
    rng.shuffle(pool)
    chosen: list[str] = []
    kinds: set[str] = set()
    for qid in pool:
        if QUESTS[qid][0] in kinds:
            continue
        chosen.append(qid)
        kinds.add(QUESTS[qid][0])
        if len(chosen) == (1 if weekly else DAILY_COUNT):
            break
    return chosen


def quest_target(qid: str, weekly: bool) -> int:
    _kind, daily, week, _text = QUESTS[qid]
    return week if weekly else daily


def quest_text(qid: str, weekly: bool) -> str:
    return QUESTS[qid][3].replace("{n}", f"{quest_target(qid, weekly):,}".replace(",", " "))


def next_activity_streak(last_day: str | None, streak: int, best: int, today: date) -> tuple[int, int, bool]:
    """(nouvelle série, meilleure série, changé ?) quand un membre parle aujourd'hui."""
    today_s = today.isoformat()
    if last_day == today_s:
        return streak, best, False
    if last_day == (today - timedelta(days=1)).isoformat():
        streak += 1
    else:
        streak = 1
    return streak, max(best, streak), True


def newly_unlocked(stats: dict[str, int], already: set[str]) -> list[str]:
    return [aid for aid, (_e, _n, _d, stat, threshold, _r) in ACHIEVEMENTS.items()
            if aid not in already and stats.get(stat, 0) >= threshold]


def progress_bar(value: int, target: int, width: int = 10) -> str:
    filled = min(width, int(width * value / target)) if target else width
    return "▰" * filled + "▱" * (width - filled)
