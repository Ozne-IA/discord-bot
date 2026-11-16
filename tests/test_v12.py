"""Tests v12 : succès, quêtes, séries, banque, accès au panel par rôle, stats du staff, alertes Kick / TikTok / RSS."""
import time
from datetime import date

from bot.access import ACCESS_GROUPS, apply_restricted, groups_for_roles
from bot.config import FREE_OVERRIDES, ConfigStore, sanitize
from bot.db import Database
from bot.engagement_data import (ACHIEVEMENTS, QUESTS, newly_unlocked, next_activity_streak, progress_bar, quest_text,
                                 quests_for, week_key)
from bot.staff import build_staff_stats
from bot.translate import translate
from cogs.alerts import KICK_RE, TIKTOK_RE, clean_handle, is_public_url, parse_feed
from cogs.economy import bank_rate, parse_amount


def test_daily_quests_are_stable_and_varied():
    a = quests_for(42, "2026-11-16", weekly=False)
    assert a == quests_for(42, "2026-11-16", weekly=False)  # mêmes quêtes pour tout le serveur toute la journée
    assert len(a) == 3 and len({QUESTS[q][0] for q in a}) == 3  # jamais deux fois la même activité
    assert len(quests_for(42, "2026-W47", weekly=True)) == 1
    no_eco = quests_for(42, "2026-11-16", weekly=False, economy=False, games=False)
    assert no_eco and all(QUESTS[q][0] == "message" for q in no_eco)
    assert quest_text("messages", False) == "Envoyer 30 messages"
    assert quest_text("messages", True) == "Envoyer 300 messages"
    assert week_key(date(2026, 11, 16)) == "2026-W47"


def test_activity_streak():
    d = date(2026, 11, 16)
    assert next_activity_streak(None, 0, 0, d) == (1, 1, True)
    assert next_activity_streak("2026-11-15", 4, 6, d) == (5, 6, True)
    assert next_activity_streak("2026-11-16", 5, 6, d) == (5, 6, False)
    assert next_activity_streak("2026-11-10", 9, 9, d) == (1, 9, True)


def test_achievements_unlock():
    got = newly_unlocked({"messages": 150, "level": 10, "game_wins": 3}, {"msg_100"})
    assert "lvl_5" in got and "lvl_10" in got and "msg_100" not in got and "games_10" not in got
    assert len(ACHIEVEMENTS) == 19
    assert progress_bar(5, 10) == "▰▰▰▰▰▱▱▱▱▱" and progress_bar(50, 10).count("▰") == 10


def test_bank_helpers():
    assert parse_amount("tout", 250) == 250 and parse_amount("all", 0) is None
    assert parse_amount("1 000", 0) == 1000 and parse_amount("-5", 10) is None and parse_amount("abc", 10) is None
    assert bank_rate(1.5) == 1.5 and bank_rate(50) == 10 and bank_rate("x") == 0


def test_panel_access_rules():
    rules = sanitize({"panel_access": [{"role": "123", "moderation": True, "stats": 1},
                                       {"role": "123", "community": True}, {"role": "0", "alerts": True}]})["panel_access"]
    assert rules == [{"role": 123, "community": False, "moderation": True, "tickets": False, "alerts": False,
                      "messages": False, "stats": True}]
    assert groups_for_roles({123, 9}, rules) == {"moderation", "stats"}
    assert groups_for_roles({9}, rules) == set()
    assert FREE_OVERRIDES["panel_access"] == []  # 💎 Premium uniquement


def test_restricted_save_only_touches_allowed_groups():
    current = {"automod": {"enabled": True}, "welcome": {"enabled": True}, "channels": {"logs": 5, "welcome": 1},
               "panel_access": [{"role": 1, "moderation": True}]}
    incoming = {"automod": {"enabled": False}, "welcome": {"enabled": False}, "channels": {"logs": 999, "welcome": 2},
                "panel_access": [{"role": 1, "moderation": True, "community": True}]}
    out = apply_restricted(current, incoming, {"moderation"})
    assert out["automod"]["enabled"] is False  # autorisé
    assert out["welcome"]["enabled"] is True and out["channels"] == {"logs": 5, "welcome": 1}  # refusé
    assert out["panel_access"] == current["panel_access"]  # jamais modifiable par un accès limité
    out = apply_restricted(current, incoming, {"community"})
    assert out["welcome"]["enabled"] is False and out["channels"] == {"logs": 5, "welcome": 2}
    assert all(paths or g == "stats" for g, (_n, paths) in ACCESS_GROUPS.items())


def test_feeds_and_handles():
    rss = """<?xml version="1.0"?><rss version="2.0"><channel><title>Mon blog</title>
      <item><title>Article 2</title><link>https://ex.com/2</link><guid>2</guid></item>
      <item><title>Article 1</title><link>https://ex.com/1</link></item></channel></rss>"""
    name, items = parse_feed(rss)
    assert name == "Mon blog" and [i["id"] for i in items] == ["2", "https://ex.com/1"]
    atom = """<feed xmlns="http://www.w3.org/2005/Atom"><title>Patch notes</title>
      <entry><id>tag:1</id><title>v1.2</title><link rel="alternate" href="https://ex.com/v12"/></entry></feed>"""
    name, items = parse_feed(atom)
    assert name == "Patch notes" and items[0] == {"id": "tag:1", "title": "v1.2", "url": "https://ex.com/v12"}
    assert clean_handle("https://kick.com/XQC", KICK_RE) == "xqc"
    assert clean_handle("https://www.tiktok.com/@khaby.lame/live", TIKTOK_RE) == "khaby.lame"
    assert clean_handle("@Squeezie", TIKTOK_RE) == "squeezie"
    assert clean_handle("pas valide !", KICK_RE) is None
    cfg = sanitize({"alerts": {"rss": [{"url": "https://ex.com/rss", "channel": "55"}, {"url": "", "channel": "1"}],
                               "kick": [{"login": "xqc", "channel": "7"}]}})
    assert cfg["alerts"]["rss"] == [{"url": "https://ex.com/rss", "channel": 55, "message": ""}]
    assert cfg["alerts"]["kick"][0]["login"] == "xqc"


async def test_rss_refuses_internal_addresses():
    for url in ("http://127.0.0.1:8080/health", "http://localhost/", "ftp://ex.com/feed", "http://10.0.0.5/rss",
                "http://[::1]/"):
        assert not await is_public_url(url), url


async def test_staff_stats_and_bank_migration(tmp_path):
    db = Database(tmp_path / "t.db")
    await db.connect()
    try:
        now = time.time()
        for mod, action in ((1, "warn"), (1, "warn"), (1, "ban"), (2, "mute")):
            await db.execute("INSERT INTO cases (guild_id, user_id, mod_id, action, created_at) VALUES (9,5,?,?,?)",
                             (mod, action, now))
        await db.execute("INSERT INTO cases (guild_id, user_id, mod_id, action, created_at) VALUES (9,5,2,'kick',?)",
                         (now - 60 * 86400,))
        await db.execute("INSERT INTO tickets (channel_id, guild_id, user_id, number, type, claimed_by, opened_at, "
                         "last_activity) VALUES (1,9,5,1,'support',2,?,?)", (now, now))
        await db.execute("INSERT INTO notes (guild_id, user_id, mod_id, content, created_at) VALUES (9,5,3,'x',?)", (now,))
        rows = await build_staff_stats(db, 9, now - 30 * 86400)
        assert [r["user_id"] for r in rows] == [1, 2, 3]
        assert rows[0]["actions"] == {"warn": 2, "ban": 1} and rows[0]["total"] == 3
        assert rows[1]["actions"] == {"mute": 1} and rows[1]["tickets"] == 1  # le kick d'il y a 60 jours est exclu
        assert len(await build_staff_stats(db, 9, 0)) == 3 and (await build_staff_stats(db, 9, 0))[1]["cases"] == 2
        await db.execute("INSERT INTO economy (guild_id, user_id, balance) VALUES (9,5,100)")
        row = await db.fetchone("SELECT bank FROM economy WHERE guild_id=9 AND user_id=5")
        assert row["bank"] == 0 and db.version >= 18
    finally:
        await db.close()


async def test_quest_completion_and_counters(tmp_path, monkeypatch):
    from cogs import engagement
    db = Database(tmp_path / "t.db")
    await db.connect()
    store = ConfigStore(premium_check=lambda g: False)
    monkeypatch.setattr(engagement, "gconf", store.get)

    class Guild:
        id = 77

    class Member:
        id, bot, mention = 5, False, "@m"

    class Bot:
        def __init__(self):
            self.db = db

        def get_cog(self, _):
            return None

    cog = engagement.Engagement(Bot())
    try:
        today = engagement.server_today(Guild())
        active = cog.active_quests(Guild(), today)
        assert len(active) == 3 and not any(w for _p, _q, w in active)  # pas de quête hebdo sans Premium
        period, qid, _ = next(a for a in active)
        kind = QUESTS[qid][0]
        for _ in range(QUESTS[qid][1] + 5):
            await cog.on_activity(Guild(), Member(), None, kind, 1)
        row = await db.fetchone("SELECT progress, done FROM quest_progress WHERE quest=?", (qid,))
        assert row["done"] == 1 and row["progress"] == QUESTS[qid][1]  # plafonné à l'objectif
        assert (await cog.counters(77, 5))["quests"] == 1  # comptée une seule fois
    finally:
        await db.close()


def test_v12_translations():
    assert translate("Tu as déposé 500 🪙 pièces à la banque.") == "You deposited 500 🪙 pièces in the bank."
    assert translate("📜 Quête terminée") == "📜 Quest completed"
    assert translate("Envoyer 30 messages") == "Send 30 messages"
