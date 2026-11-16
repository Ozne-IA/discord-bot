"""Restauration de la base avec /restore (déménagement PC → Railway)."""
import sqlite3

from bot.db import MIGRATIONS, PENDING_RESTORE, Database, apply_pending_restore, validate_backup


async def _make_db(path, xp=0):
    db = Database(path)
    await db.connect()
    if xp:
        await db.execute("INSERT INTO levels (guild_id, user_id, xp) VALUES (1, 2, ?)", (xp,))
    await db.close()


async def test_validate_backup(tmp_path):
    good = tmp_path / "good.db"
    await _make_db(good)
    assert validate_backup(good) is None

    text = tmp_path / "text.db"
    text.write_text("pas une base")
    assert validate_backup(text) == "Ce fichier n'est pas une base SQLite."

    other = tmp_path / "other.db"
    sqlite3.connect(other).execute("CREATE TABLE x (a)").connection.commit()
    assert validate_backup(other) == "Ce n'est pas une sauvegarde de ce bot."

    newer = tmp_path / "newer.db"
    await _make_db(newer)
    conn = sqlite3.connect(newer)
    conn.execute("INSERT INTO schema_version (version) VALUES (?)", (len(MIGRATIONS) + 1,))
    conn.commit()
    conn.close()
    assert "plus récente" in validate_backup(newer)


async def test_pending_restore_replaces_db(tmp_path):
    live = tmp_path / "bot.db"
    await _make_db(live, xp=5)
    await _make_db(tmp_path / PENDING_RESTORE, xp=999)

    db = Database(live)
    await db.connect()  # applique la restauration avant d'ouvrir la base
    row = await db.fetchone("SELECT xp FROM levels WHERE guild_id=1 AND user_id=2")
    await db.close()
    assert row["xp"] == 999
    assert not (tmp_path / PENDING_RESTORE).exists()
    kept = list((tmp_path / "backups").glob("before_restore_*/bot.db"))
    assert len(kept) == 1


def test_bad_pending_file_is_set_aside(tmp_path):
    live = tmp_path / "bot.db"
    (tmp_path / PENDING_RESTORE).write_text("abîmé")
    assert apply_pending_restore(live) is False
    assert (tmp_path / "restore_pending.rejected").exists()
    assert not live.exists()
