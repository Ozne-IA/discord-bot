"""Tests : compteurs, commandes perso, menus de rôles, messages programmés, carte de bienvenue, traductions."""
from datetime import datetime, timedelta, timezone

from bot.config import DEFAULTS, ConfigStore, limit_for, sanitize
from bot.db import Database
from bot.images import welcome_card
from bot.translate import translate
from cogs.custom import command_matches, due_occurrence

BIG = 1234567890123456789


def test_sanitize_new_lists():
    clean = sanitize({
        "counters": [{"type": "online", "channel": str(BIG), "template": "🟢 {}"}, {"type": "hack", "channel": "1"},
                     {"type": "members", "channel": "0"}],
        "custom_commands": [{"trigger": " !IP ", "response": "play.exemple.fr", "mode": "contains", "embed": 1},
                            {"trigger": "!ip", "response": "doublon"}, {"trigger": "", "response": "x"}],
        "role_menus": [{"id": "Jeux 1!", "channel": str(BIG), "title": "🎮", "style": "evil",
                        "roles": [{"role": str(BIG), "label": "Valo", "emoji": "🎯"}, {"role": "0"}]}],
        "scheduled": [{"id": "abc", "channel": str(BIG), "at": "2026-12-01T18:30", "repeat": "weekly", "title": "Hey"},
                      {"id": "bad", "channel": str(BIG), "at": "demain", "title": "x"}],
    })
    assert clean["counters"] == [{"type": "online", "channel": BIG, "template": "🟢 {}"},
                                 {"type": "members", "channel": 1, "template": "👥 Membres : {}"}]
    assert clean["custom_commands"] == [{"trigger": "!ip", "response": "play.exemple.fr", "mode": "contains", "embed": True}]
    menu = clean["role_menus"][0]
    assert menu["id"] == "jeux1" and menu["style"] == "buttons"
    assert menu["roles"] == [{"role": BIG, "label": "Valo", "emoji": "🎯"}]
    assert [s["id"] for s in clean["scheduled"]] == ["abc"]


async def test_scheduled_messages_are_premium(tmp_path):
    db = Database(tmp_path / "t.db")
    await db.connect()
    item = {"id": "a", "channel": str(BIG), "at": "2026-12-01T18:30", "title": "x"}
    free, paid = ConfigStore(premium_check=lambda g: False), ConfigStore(premium_check=lambda g: True)
    await free.save(db, 1, {"scheduled": [item], "welcome": {"image": True}})
    await paid.save(db, 1, {"scheduled": [item], "welcome": {"image": True}})
    assert free.get(1).get("scheduled") == [] and free.get(1).get("welcome", "image") is False
    assert len(paid.get(1).get("scheduled")) == 1 and paid.get(1).get("welcome", "image") is True
    await db.close()


def test_limits():
    assert limit_for("counters", False) == 2 and limit_for("counters", True) == 5
    assert limit_for("custom_commands", False) == 5 and limit_for("role_menus", True) == 15
    assert DEFAULTS["temp_voice"]["enabled"] is True


def test_due_occurrence():
    tz = timezone.utc
    at = datetime(2026, 11, 16, 18, 0, tzinfo=tz)
    assert due_occurrence(at, "none", at - timedelta(minutes=1)) is None
    assert due_occurrence(at, "none", at + timedelta(minutes=5)) == at
    assert due_occurrence(at, "daily", at + timedelta(days=3, hours=2)) == at + timedelta(days=3)
    assert due_occurrence(at, "weekly", at + timedelta(days=15)) == at + timedelta(days=14)


def test_command_matching():
    exact = {"trigger": "!ip", "mode": "exact"}
    contains = {"trigger": "bonjour", "mode": "contains"}
    assert command_matches(exact, "  !IP ") and not command_matches(exact, "!ip stp")
    assert command_matches(contains, "Bonjour tout le monde") and not command_matches(contains, "salut")


def test_welcome_card_and_new_translations():
    assert welcome_card("Nouveau", None, "Serveur", 42)[:8] == b"\x89PNG\r\n\x1a\n"
    assert translate("Merci ! Ta suggestion est publiée dans <#1>.") == "Thanks! Your suggestion was posted in <#1>."
    assert translate("Limite : **4** personne(s).") == "Limit: **4** user(s)."
