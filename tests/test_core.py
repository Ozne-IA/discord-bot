"""Tests sans Discord : base de données, config par serveur, formules, durées, automod, panel."""
from datetime import timedelta

from bot.config import DEFAULTS, ConfigStore, deep_merge, sanitize
from bot.db import MIGRATIONS, Database
from bot.utils import format_duration, parse_duration
from cogs.automod import normalize
from cogs.levels import level_from_xp, total_xp_for, xp_for_next
from web.server import stringify_ids

BIG_ID = 1234567890123456789


async def make_db(tmp_path, name="t.db"):
    db = Database(tmp_path / name)
    await db.connect()
    return db


async def test_migrations_create_all_tables(tmp_path):
    db = await make_db(tmp_path)
    rows = await db.fetchall("SELECT name FROM sqlite_master WHERE type='table'")
    names = {r["name"] for r in rows}
    assert {"levels", "cases", "notes", "tickets", "tempbans", "security_logs", "settings",
            "guild_config", "web_sessions"} <= names
    version = await db.fetchone("SELECT MAX(version) AS v FROM schema_version")
    assert version["v"] == len(MIGRATIONS)
    await db.close()


async def test_migrations_are_idempotent(tmp_path):
    for _ in range(2):
        db = await make_db(tmp_path)
        await db.close()


async def test_settings_roundtrip(tmp_path):
    db = await make_db(tmp_path)
    await db.set_setting(1, "k", "a")
    await db.set_setting(1, "k", "b")
    assert await db.get_setting(1, "k") == "b"
    assert await db.get_setting(1, "absent", "def") == "def"
    await db.close()


async def test_backup(tmp_path):
    db = await make_db(tmp_path)
    await db.execute("INSERT INTO levels (guild_id, user_id, xp) VALUES (1, 2, 50)")
    await db.backup_to(tmp_path / "copy.db")
    copy = await make_db(tmp_path, "copy.db")
    row = await copy.fetchone("SELECT xp FROM levels WHERE user_id=2")
    assert row["xp"] == 50
    await db.close()
    await copy.close()


# --- configuration par serveur ------------------------------------------------
async def test_config_is_isolated_per_guild_and_persisted(tmp_path):
    db = await make_db(tmp_path)
    store = ConfigStore()
    await store.load_all(db)
    await store.save(db, 1, {"channels": {"logs": str(BIG_ID)}, "leveling": {"xp_min": "30"}})
    assert store.get(1).channel_id("logs") == BIG_ID
    assert store.get(1).get("leveling", "xp_min") == 30
    assert store.get(1).get("leveling", "xp_max") == DEFAULTS["leveling"]["xp_max"]  # défaut conservé
    assert store.get(2).channel_id("logs") == 0  # autre serveur intact

    reloaded = ConfigStore()
    await reloaded.load_all(db)
    assert reloaded.get(1).channel_id("logs") == BIG_ID
    await db.close()


async def test_config_update_patch(tmp_path):
    db = await make_db(tmp_path)
    store = ConfigStore()
    await store.save(db, 1, {"welcome": {"enabled": False}})
    await store.update(db, 1, {"roles": {"staff": BIG_ID}})
    cfg = store.get(1)
    assert cfg.role_id("staff") == BIG_ID
    assert cfg.get("welcome", "enabled") is False
    await db.close()


def test_sanitize_rejects_unknown_and_wrong_types():
    clean = sanitize({
        "hack": {"x": 1},
        "brand": {"color": "javascript:alert(1)", "footer": "x" * 5000},
        "welcome": {"enabled": "yes", "message": 123},
        "leveling": {"xp_min": "-5", "booster_multiplier": "abc", "ignored_channels": [str(BIG_ID), "nope", 0]},
        "channels": {"logs": "not-an-id"},
    })
    assert "hack" not in clean
    assert clean["brand"]["color"] == DEFAULTS["brand"]["color"]
    assert len(clean["brand"]["footer"]) == 2000
    assert clean["welcome"] == {"enabled": True, "message": "123"}
    assert clean["leveling"]["xp_min"] == 0
    assert clean["leveling"]["booster_multiplier"] == DEFAULTS["leveling"]["booster_multiplier"]
    assert clean["leveling"]["ignored_channels"] == [BIG_ID]
    assert clean["channels"]["logs"] == 0


def test_sanitize_free_maps():
    clean = sanitize({"roles": {"notifications": {"Annonces": str(BIG_ID), "Vide": "0"},
                                "level_roles": {"10": str(BIG_ID), "abc": str(BIG_ID)}},
                      "moderation": {"escalation": {"3": {"action": "timeout", "minutes": "30"},
                                                    "4": {"action": "rm -rf"}}},
                      "tickets": {"types": {"Support Tech!": {"label": "Tech", "emoji": "🛠️"}}}})
    assert clean["roles"]["notifications"] == {"Annonces": BIG_ID}
    assert clean["roles"]["level_roles"] == {"10": BIG_ID}
    assert clean["moderation"]["escalation"] == {"3": {"action": "timeout", "minutes": 30}}
    assert clean["tickets"]["types"] == {"supporttech": {"label": "Tech", "emoji": "🛠️", "description": ""}}


def test_free_maps_are_replaced_not_merged():
    merged = deep_merge(DEFAULTS, {"tickets": {"types": {"only": {"label": "Seul"}}}})
    assert list(merged["tickets"]["types"]) == ["only"]
    merged = deep_merge({"a": {"x": 1, "y": 2}, "b": 3}, {"a": {"x": 9}})
    assert merged == {"a": {"x": 9, "y": 2}, "b": 3}


def test_ids_are_sent_as_strings_to_javascript():
    out = stringify_ids({"channels": {"logs": BIG_ID, "x": 0}, "list": [BIG_ID], "n": 25, "b": True})
    assert out == {"channels": {"logs": str(BIG_ID), "x": 0}, "list": [str(BIG_ID)], "n": 25, "b": True}


# --- formules et helpers ----------------------------------------------------
def test_level_formula():
    assert xp_for_next(0) == 100
    assert xp_for_next(1) == 155
    assert level_from_xp(0) == (0, 0, 100)
    assert level_from_xp(99)[0] == 0
    assert level_from_xp(100) == (1, 0, 155)
    for lvl in (1, 5, 10, 30):
        assert level_from_xp(total_xp_for(lvl))[0] == lvl
        assert level_from_xp(total_xp_for(lvl) - 1)[0] == lvl - 1


def test_parse_duration():
    assert parse_duration("10m") == timedelta(minutes=10)
    assert parse_duration("1h30m") == timedelta(hours=1, minutes=30)
    assert parse_duration("7d") == parse_duration("7j") == timedelta(days=7)
    assert parse_duration("abc") is None
    assert parse_duration("10x") is None
    assert parse_duration("") is None
    assert format_duration(timedelta(hours=1, minutes=5)) == "1h 5min"


def test_normalize_catches_bypasses():
    assert "idiot" in normalize("I.D.1.0.T")
    assert "idiot" in normalize("iiiidiooot")
    assert "eleve" in normalize("Élève")
