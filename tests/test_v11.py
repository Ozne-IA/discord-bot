"""Tests : liens dangereux, expiration des warns, invitations, formulaires de ticket, modèles de config."""
import time

from bot.config import ConfigStore, deep_merge, sanitize
from bot.db import Database
from bot.phishing import find_dangerous, looks_like_scam
from bot.templates import TEMPLATES
from bot.translate import translate
from cogs.invites import find_used_invite


def test_phishing_lookalikes_and_official_sites():
    for bad in ("https://dlscord-gift.com/nitro", "free nitro https://discord-nitro.ru/claim", "https://steamcornmunity.com/trade",
                "https://disc0rd-app.com/login"):
        assert find_dangerous(bad), bad
    for ok in ("https://discord.gg/abc", "https://discord.com/channels/1/2", "https://cdn.discordapp.com/x.png",
               "https://steamcommunity.com/id/me", "https://youtube.com/watch?v=1", "https://monsite.fr", "https://top.gg/bot/1",
               "https://discord.me/serveur", "pas de lien ici"):
        assert find_dangerous(ok) is None, ok
    assert not looks_like_scam("discordservers.com")
    assert find_dangerous("https://mondiscord-fan.fr", allowed=["mondiscord-fan.fr"]) is None


async def test_warns_expire(tmp_path):
    from cogs import moderation
    db = Database(tmp_path / "t.db")
    await db.connect()
    store = ConfigStore(premium_check=lambda g: False)
    await store.save(db, 1, {"moderation": {"warn_expiry_days": 30}})
    original = moderation.gconf
    moderation.gconf = store.get
    try:
        cutoff = moderation.warn_cutoff(1)
        assert time.time() - 31 * 86400 < cutoff < time.time() - 29 * 86400
        await store.save(db, 1, {"moderation": {"warn_expiry_days": 0}})
        assert moderation.warn_cutoff(1) == 0
    finally:
        moderation.gconf = original
        await db.close()


def test_find_used_invite():
    before = {"abc": 3, "def": 10}
    after = {"abc": (3, 1), "def": (11, 2), "new": (0, 3)}
    assert find_used_invite(before, after) == ("def", 2)
    assert find_used_invite({"abc": 3}, {"abc": (3, 1)}) == (None, None)
    assert find_used_invite({}, {"fresh": (1, 9)}) == ("fresh", 9)


def test_ticket_form_questions_sanitized():
    clean = sanitize({"tickets": {"types": {"team": {"label": "Team", "questions": "Pseudo | Âge |  | " + " | ".join(["q"] * 10)},
                                            "support": {"label": "Aide", "questions": ["x" * 80]}}}})
    assert clean["tickets"]["types"]["team"]["questions"] == ["Pseudo", "Âge", "q", "q", "q"]
    assert clean["tickets"]["types"]["support"]["questions"] == ["x" * 45]


def test_templates_survive_sanitizing():
    for key, template in TEMPLATES.items():
        clean = sanitize(deep_merge({}, template["config"]))
        for section in template["config"]:
            if template["config"][section]:
                assert section in clean, f"{key}: {section} perdu à la validation"


async def test_store_knows_configured_servers(tmp_path):
    db = Database(tmp_path / "t.db")
    await db.connect()
    store = ConfigStore(premium_check=lambda g: False)
    assert not store.has(1)
    await store.save(db, 1, {"welcome": {"enabled": True}})
    assert store.has(1)
    await db.close()


def test_new_translations():
    assert translate("Lien dangereux (phishing) : evil.ru") == "Dangerous link (phishing): evil.ru"
    assert translate("📨 <@1> a rejoint (invitation inconnue).") == "📨 <@1> joined (unknown invite)."
