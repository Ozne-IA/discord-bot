"""Tests : économie, rappels / anniversaires, statistiques, historique du panel, langues."""
from datetime import date

from bot.config import DEFAULTS, ConfigStore, sanitize
from bot.db import Database
from bot.i18n import COMMANDS_EN, DEFAULT_MESSAGES_EN, TEXTS_EN
from cogs.economy import MAX_STREAK, daily_reward, next_streak
from cogs.reminders import birthday_matches, days_until
from web.server import build_stats, config_diff

BIG = 1234567890123456789


def test_daily_streak_rules():
    assert next_streak(0, 0, 1_000_000) == 1                  # jamais réclamé
    assert next_streak(1_000_000, 4, 1_000_000 + 30 * 3600) == 5   # revenu dans les 48 h
    assert next_streak(1_000_000, 4, 1_000_000 + 50 * 3600) == 1   # série perdue
    assert daily_reward(100, 10, 1) == 100
    assert daily_reward(100, 10, 5) == 140
    assert daily_reward(100, 10, 500) == 100 + 10 * (MAX_STREAK - 1)  # bonus plafonné


def test_shop_sanitize_and_free_mask(tmp_path):
    clean = sanitize({"economy": {"shop": [
        {"name": "VIP", "price": "500", "role": str(BIG), "description": "Rôle VIP", "x": 1},
        {"name": "", "price": 10}, {"name": "Gratuit", "price": "-5"}]}})
    assert clean["economy"]["shop"] == [
        {"name": "VIP", "price": 500, "role": BIG, "description": "Rôle VIP"},
        {"name": "Gratuit", "price": 0, "role": 0, "description": ""}]


async def test_free_server_has_no_shop_but_keeps_economy(tmp_path):
    db = Database(tmp_path / "t.db")
    await db.connect()
    store = ConfigStore(premium_check=lambda gid: False)
    await store.save(db, 1, {"economy": {"daily_amount": 250, "currency_name": "gemmes",
                                         "shop": [{"name": "VIP", "price": 5}]}})
    cfg = store.get(1)
    assert cfg.get("economy", "daily_amount") == 250                    # gratuit : réglable
    assert cfg.get("economy", "currency_name") == DEFAULTS["economy"]["currency_name"]  # Premium
    assert cfg.get("economy", "shop") == []                             # Premium
    await db.close()


def test_birthdays_dates():
    assert birthday_matches(15, 11, date(2026, 11, 15))
    assert not birthday_matches(16, 11, date(2026, 11, 15))
    assert birthday_matches(29, 2, date(2027, 2, 28))       # année non bissextile
    assert not birthday_matches(29, 2, date(2028, 2, 28))   # 2028 est bissextile : fêté le 29
    assert days_until(16, 11, date(2026, 11, 15)) == 1
    assert days_until(14, 11, date(2026, 11, 15)) == 364
    assert days_until(15, 11, date(2026, 11, 15)) == 0


async def test_stats_series_fill_missing_days(tmp_path):
    db = Database(tmp_path / "t.db")
    await db.connect()
    await db.execute("INSERT INTO stats_daily (guild_id, day, joins, messages, members) VALUES (1, '2026-11-14', 3, 40, 120)")
    await db.execute("INSERT INTO stats_daily (guild_id, day, leaves, members) VALUES (1, '2026-11-16', 1, 122)")
    stats = await build_stats(db, 1, 7, today=date(2026, 11, 16))
    assert stats["labels"][0] == "2026-11-10" and stats["labels"][-1] == "2026-11-16"
    assert stats["series"]["joins"] == [0, 0, 0, 0, 3, 0, 0]
    assert stats["series"]["leaves"][-1] == 1
    assert stats["members"][4] == 120 and stats["members"][5] is None
    assert stats["totals"]["messages"] == 40
    await db.close()


def test_config_diff_lists_changed_paths():
    before = {"welcome": {"enabled": True, "message": "a"}, "roles": {"staff": 1}}
    after = {"welcome": {"enabled": False, "message": "a"}, "roles": {"staff": 2}, "new": {"x": 1}}
    assert config_diff(before, after) == ["new", "roles.staff", "welcome.enabled"]
    assert config_diff(before, before) == []


def test_language_setting_and_texts():
    assert sanitize({"general": {"language": "en"}}) == {"general": {"language": "en"}}
    assert sanitize({"general": {"language": "de"}}) == {"general": {"language": "fr"}}
    for key in ("message", "dm_message", "goodbye_message"):
        assert DEFAULTS["welcome"][key] in DEFAULT_MESSAGES_EN
    assert DEFAULTS["leveling"]["level_up_message"] in DEFAULT_MESSAGES_EN
    assert DEFAULTS["birthdays"]["message"] in DEFAULT_MESSAGES_EN
    assert "J'accepte les règles" in TEXTS_EN
    assert all(v and v != k or k.startswith("💎 Giveaways") for k, v in COMMANDS_EN.items())
