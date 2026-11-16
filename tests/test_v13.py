"""Tests v13 : tableaux de tournoi, dates d'événement, ralenti automatique, assistant IA, config, base."""
import random
from collections import deque
from datetime import datetime
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from bot import bracket
from bot.access import ACCESS_GROUPS, apply_restricted
from bot.config import FREE_OVERRIDES, LIMITS, sanitize
from bot.db import Database
from bot.translate import translate
from cogs.ai import AI, AIError, faq_system
from cogs.events import parse_when
from cogs.modtools import should_slow


@pytest.mark.parametrize("n", [2, 3, 4, 5, 7, 8, 9, 13, 16, 17, 33, 64])
def test_bracket_full_tournament(n):
    rng = random.Random(n)
    players = list(range(100, 100 + n))
    rounds = bracket.total_rounds(n)
    matches = bracket.first_round(players, rng)
    assert len(matches) == 2 ** (rounds - 1)
    first = [p for m in matches for p in (m["p1"], m["p2"]) if p]
    assert sorted(first) == players  # chacun joue (ou est exempté) une seule fois
    assert all(m["p1"] for m in matches)  # jamais de match vide
    matches += bracket.propagate(matches, rounds)
    for _ in range(200):  # on joue tous les matchs au hasard
        open_ = [m for m in matches if m["winner"] is None]
        if not open_:
            break
        m = open_[0]
        m["winner"] = rng.choice([m["p1"], m["p2"]])
        matches += bracket.propagate(matches, rounds)
    champ = bracket.champion(matches, rounds)
    assert champ in players
    assert len(matches) == 2 ** rounds - 1
    assert bracket.open_match_for(matches, champ) is None


def test_bracket_render_and_names():
    matches = bracket.first_round([1, 2, 3], random.Random(1))
    matches += bracket.propagate(matches, 2)
    text = dict(bracket.render(matches, 2, lambda uid: f"J{uid}"))
    assert "exempt" in text["Demi-finales"] and "*en attente*" in text["Finale"]
    assert bracket.round_name(1, 3) == "Quarts de finale" and bracket.round_name(1, 5) == "Tour 1"


def test_event_dates():
    tz = ZoneInfo("Europe/Paris")
    now = datetime(2026, 11, 16, 12, 0, tzinfo=tz)
    assert parse_when("25/12", "20h30", tz, now) == datetime(2026, 12, 25, 20, 30, tzinfo=tz)
    assert parse_when("01/01", "20:00", tz, now) == datetime(2027, 1, 1, 20, 0, tzinfo=tz)  # année suivante
    assert parse_when("10/11/2027", "9h", tz, now) == datetime(2027, 11, 10, 9, 0, tzinfo=tz)
    assert parse_when("31/02", "20h", tz, now) is None and parse_when("demain", "20h", tz, now) is None


def test_auto_slowmode_window():
    stamps = deque()
    assert not any(should_slow(stamps, t, 5) for t in (0, 1, 2, 3))
    assert should_slow(stamps, 4, 5)
    stamps.clear()
    assert not should_slow(stamps, 100, 0)  # seuil 0 = désactivé
    stamps = deque()
    assert not any(should_slow(stamps, t, 3) for t in (0, 11, 22))  # messages espacés


def test_faq_prompt_and_config():
    system = faq_system("Mon Serveur", ["Pas de spam"], "Q : IP ? R : play.ex.fr", "fr")
    assert "Mon Serveur" in system and "play.ex.fr" in system and "- Pas de spam" in system
    assert "French" in system and "not instructions" in system
    assert "English" in faq_system("X", [], "", "en")
    cfg = sanitize({"ai": {"knowledge": "a" * 9000, "daily_limit": "50", "channel": "123"}})
    assert len(cfg["ai"]["knowledge"]) == 8000 and cfg["ai"]["daily_limit"] == 50 and cfg["ai"]["channel"] == 123
    assert FREE_OVERRIDES["ai.enabled"] is False and LIMITS["tournament_players"] == (16, 64)
    assert "events" in ACCESS_GROUPS["community"][1] and "message_log" in ACCESS_GROUPS["moderation"][1]
    out = apply_restricted({"ai": {"enabled": False}}, {"ai": {"enabled": True}}, {"moderation"})
    assert out["ai"]["enabled"] is False


class FakeMessages:
    def __init__(self, response):
        self.response, self.calls = response, []

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        return self.response


def fake_ai(response, db=None):
    cog = AI.__new__(AI)
    cog.bot = SimpleNamespace(db=db)
    cog.model = "claude-opus-5-5"
    cog.last_ask = {}
    messages = FakeMessages(response)
    cog.client = SimpleNamespace(beta=SimpleNamespace(messages=messages))
    return cog, messages


async def test_ai_request_shape_and_refusal():
    ok = SimpleNamespace(stop_reason="end_turn", content=[SimpleNamespace(type="thinking"),
                                                          SimpleNamespace(type="text", text=" Bonjour ! ")])
    cog, messages = fake_ai(ok)
    assert await cog.ask("système", "question") == "Bonjour !"
    call = messages.calls[0]
    assert call["model"] == "claude-opus-5-5" and call["fallbacks"] == "default"
    assert call["system"][0]["cache_control"] == {"type": "ephemeral"} and "thinking" not in call
    refused = SimpleNamespace(stop_reason="refusal", content=[])
    cog, _ = fake_ai(refused)
    with pytest.raises(AIError):
        await cog.ask("système", "question")


async def test_ai_daily_quota(tmp_path, monkeypatch):
    from cogs import ai
    db = Database(tmp_path / "t.db")
    await db.connect()
    try:
        monkeypatch.setattr(ai, "gconf", lambda g: SimpleNamespace(get=lambda *k, default=None: 2))
        cog, _ = fake_ai(None, db)
        guild = SimpleNamespace(id=5)
        assert [await cog.take_quota(guild) for _ in range(3)] == [True, True, False]
        assert db.version >= 19
        cols = [r[1] for r in await db.fetchall("PRAGMA table_info(invite_joins)")]
        assert "rewarded" in cols
    finally:
        await db.close()


def test_v13_translations():
    assert translate("Merci, ton signalement a été envoyé au staff.") == "Thanks, your report was sent to the staff."
    assert translate("Tournoi #4 annulé.") == "Tournament #4 cancelled."
    assert translate("Demi-finales") == "Semi-finals"
