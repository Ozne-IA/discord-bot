"""v14.7 : ménage des données (serveurs quittés, vieilles données, /mes-donnees)."""
import json
import time
from datetime import date
from types import SimpleNamespace

from bot import privacy
from bot.db import Database
from cogs import privacy as privacy_cog

DAY = 86400
GUILD, OTHER, USER = 111, 222, 9


async def make_db(tmp_path) -> Database:
    db = Database(tmp_path / "t.db")
    await db.connect()
    for gid in (GUILD, OTHER):
        await db.execute("INSERT INTO guild_config (guild_id, data) VALUES (?, '{}')", (gid,))
        await db.execute("INSERT INTO levels (guild_id, user_id, xp) VALUES (?,?,50)", (gid, USER))
        await db.execute("INSERT INTO economy (guild_id, user_id, balance) VALUES (?,?,10)", (gid, USER))
        await db.execute("INSERT INTO cases (guild_id, user_id, mod_id, action, reason, created_at) "
                         "VALUES (?,?,1,'warn','spam',0)", (gid, USER))
        gw = await db.execute("INSERT INTO giveaways (guild_id, channel_id, message_id, host_id, prize, winners, "
                              "ends_at) VALUES (?,1,1,1,'x',1,0)", (gid,))
        await db.execute("INSERT INTO giveaway_entries (giveaway_id, user_id) VALUES (?,?)", (gw, USER))
    await db.execute("INSERT INTO premium_grants (guild_id, granted_by, expires_at, note, created_at) "
                     "VALUES (?,1,0,'essai gratuit',0)", (GUILD,))
    await db.set_setting(GUILD, "premium_trial", "123")
    await db.set_setting(GUILD, "panel_verify", "456")
    await db.set_setting(0, "commands_fingerprint", "abc")
    return db


async def count(db, table, where="1=1", params=()):
    return (await db.fetchone(f"SELECT COUNT(*) AS n FROM {table} WHERE {where}", params))["n"]


async def test_guild_purged_only_after_grace(tmp_path):
    db = await make_db(tmp_path)
    now = time.time()
    # Le bot n'est plus sur GUILD (quitté pendant qu'il était éteint) : on note la date, rien n'est effacé
    assert await privacy.due_for_purge(db, {OTHER}, now=now) == []
    assert await db.get_setting(GUILD, privacy.LEFT_KEY)
    assert await privacy.due_for_purge(db, {OTHER}, now=now + 29 * DAY) == []
    assert await privacy.due_for_purge(db, {OTHER}, now=now + 31 * DAY) == [GUILD]

    await privacy.purge_guild(db, GUILD)
    for table in ("guild_config", "levels", "economy", "cases", "giveaways"):
        assert await count(db, table, "guild_id=?", (GUILD,)) == 0
        assert await count(db, table, "guild_id=?", (OTHER,)) == 1            # l'autre serveur est intact
    assert await count(db, "giveaway_entries") == 1                           # seulement celle de OTHER
    assert await count(db, "premium_grants", "guild_id=?", (GUILD,)) == 1     # trace de l'essai gardée
    assert await db.get_setting(GUILD, "premium_trial") == "123"
    assert await db.get_setting(GUILD, "panel_verify") is None
    assert await db.get_setting(0, "commands_fingerprint") == "abc"           # réglages du bot intacts
    await db.close()


async def test_guild_back_is_kept(tmp_path):
    db = await make_db(tmp_path)
    now = time.time()
    await privacy.mark_left(db, GUILD, now - 40 * DAY)
    # Le bot est revenu sur GUILD pendant qu'il était éteint : plus rien à effacer
    assert await privacy.due_for_purge(db, {GUILD, OTHER}, now=now) == []
    assert await db.get_setting(GUILD, privacy.LEFT_KEY) is None
    await db.close()


async def test_cleanup_never_runs_without_guilds(tmp_path, monkeypatch):
    db = await make_db(tmp_path)
    await privacy.mark_left(db, GUILD, time.time() - 400 * DAY)
    monkeypatch.setattr(privacy_cog, "store", SimpleNamespace(forget=lambda gid: None))
    cog = privacy_cog.Privacy.__new__(privacy_cog.Privacy)
    cog.bot = SimpleNamespace(db=db, guilds=[], is_ready=lambda: True)       # démarrage : aucun serveur visible
    assert (await cog.run_cleanup())["guilds"] == 0
    assert await count(db, "levels", "guild_id=?", (GUILD,)) == 1
    cog.bot = SimpleNamespace(db=db, guilds=[SimpleNamespace(id=OTHER)], is_ready=lambda: True)
    assert (await cog.run_cleanup())["guilds"] == 1
    assert await count(db, "levels", "guild_id=?", (GUILD,)) == 0
    await db.close()


async def test_old_data(tmp_path):
    db = await make_db(tmp_path)
    today = date(2026, 11, 16)
    for day in ("2026-01-01", "2026-11-10"):
        await db.execute("INSERT INTO stats_daily (guild_id, day) VALUES (?,?)", (GUILD, day))
        await db.execute("INSERT INTO xp_daily (guild_id, user_id, day, xp) VALUES (?,?,?,1)", (GUILD, USER, day))
    now = time.time()
    await db.execute("INSERT INTO security_logs (guild_id, user_id, module, action, reason, created_at) "
                     "VALUES (?,?,?,?,?,?)", (GUILD, USER, "automod", "x", "y", now - 400 * DAY))
    await db.execute("INSERT INTO web_sessions (id, user_id, username, access_token, guilds, created_at, expires_at) "
                     "VALUES ('s',1,'u','t','[]',0,?)", (now - 1,))
    removed = await privacy.purge_old(db, now=now, today=today)
    assert removed == 4
    assert await count(db, "stats_daily") == 1 and await count(db, "xp_daily") == 1
    await privacy.vacuum(db)
    await db.close()


async def test_member_export_and_erase(tmp_path):
    db = await make_db(tmp_path)
    data = await privacy.export_user(db, USER)
    assert set(data["data"]) >= {"levels", "economy", "cases", "giveaway_entries"}
    assert len(data["data"]["levels"]) == 2 and "notes" not in data["data"]
    json.loads(privacy.export_json(data))
    await privacy.erase_user(db, USER)
    assert await count(db, "levels") == 0 and await count(db, "economy") == 0
    assert await count(db, "giveaway_entries") == 0
    assert await count(db, "cases") == 2                                      # sanctions gardées
    await db.close()
