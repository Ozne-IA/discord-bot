"""Base SQLite asynchrone avec migrations versionnées."""
from __future__ import annotations

import logging
import shutil
import sqlite3
import time
from pathlib import Path
from typing import Any, Iterable

import aiosqlite

log = logging.getLogger("bot.db")

DEFAULT_PATH = Path(__file__).resolve().parent.parent / "data" / "bot.db"
PENDING_RESTORE = "restore_pending.db"  # déposé par /restore, appliqué au prochain démarrage

# Chaque entrée = une version du schéma. Ne JAMAIS modifier une migration déjà
# déployée : ajoute plutôt une nouvelle entrée à la fin de la liste.
MIGRATIONS: list[str] = [
    # v1 — niveaux
    """
    CREATE TABLE levels (
        guild_id INTEGER NOT NULL,
        user_id  INTEGER NOT NULL,
        xp       INTEGER NOT NULL DEFAULT 0,
        level    INTEGER NOT NULL DEFAULT 0,
        messages INTEGER NOT NULL DEFAULT 0,
        last_xp  REAL    NOT NULL DEFAULT 0,
        PRIMARY KEY (guild_id, user_id)
    );
    """,
    # v2 — sanctions (warns, mutes, kicks, bans...) = "cases"
    """
    CREATE TABLE cases (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        guild_id   INTEGER NOT NULL,
        user_id    INTEGER NOT NULL,
        mod_id     INTEGER NOT NULL,
        action     TEXT    NOT NULL,
        reason     TEXT,
        created_at REAL    NOT NULL,
        active     INTEGER NOT NULL DEFAULT 1
    );
    CREATE INDEX idx_cases_user ON cases (guild_id, user_id);
    """,
    # v3 — notes internes du staff
    """
    CREATE TABLE notes (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        guild_id   INTEGER NOT NULL,
        user_id    INTEGER NOT NULL,
        mod_id     INTEGER NOT NULL,
        content    TEXT    NOT NULL,
        created_at REAL    NOT NULL
    );
    """,
    # v4 — tickets
    """
    CREATE TABLE tickets (
        channel_id    INTEGER PRIMARY KEY,
        guild_id      INTEGER NOT NULL,
        user_id       INTEGER NOT NULL,
        number        INTEGER NOT NULL,
        type          TEXT    NOT NULL,
        subject       TEXT,
        priority      TEXT    NOT NULL DEFAULT 'normale',
        claimed_by    INTEGER,
        status        TEXT    NOT NULL DEFAULT 'open',
        opened_at     REAL    NOT NULL,
        closed_at     REAL,
        last_activity REAL    NOT NULL
    );
    CREATE INDEX idx_tickets_user ON tickets (guild_id, user_id, status);
    """,
    # v5 — bannissements temporaires
    """
    CREATE TABLE tempbans (
        guild_id   INTEGER NOT NULL,
        user_id    INTEGER NOT NULL,
        expires_at REAL    NOT NULL,
        PRIMARY KEY (guild_id, user_id)
    );
    """,
    # v6 — journal de sécurité (anti-raid / anti-nuke / automod)
    """
    CREATE TABLE security_logs (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        guild_id   INTEGER NOT NULL,
        user_id    INTEGER,
        module     TEXT    NOT NULL,
        action     TEXT    NOT NULL,
        reason     TEXT,
        created_at REAL    NOT NULL
    );
    """,
    # v7 — paramètres modifiables depuis Discord (clé/valeur par serveur)
    """
    CREATE TABLE settings (
        guild_id INTEGER NOT NULL,
        key      TEXT    NOT NULL,
        value    TEXT,
        PRIMARY KEY (guild_id, key)
    );
    """,
    # v8 — configuration propre à chaque serveur (modifiée depuis le panel web)
    """
    CREATE TABLE guild_config (
        guild_id INTEGER PRIMARY KEY,
        data     TEXT    NOT NULL
    );
    """,
    # v9 — sessions du panel web (connexion Discord)
    """
    CREATE TABLE web_sessions (
        id           TEXT    PRIMARY KEY,
        user_id      INTEGER NOT NULL,
        username     TEXT    NOT NULL,
        avatar       TEXT,
        access_token TEXT    NOT NULL,
        guilds       TEXT    NOT NULL,
        created_at   REAL    NOT NULL,
        expires_at   REAL    NOT NULL
    );
    """,
    # v10 — premium accordé à la main par le propriétaire du bot (en plus des abonnements Discord)
    """
    CREATE TABLE premium_grants (
        guild_id   INTEGER PRIMARY KEY,
        granted_by INTEGER NOT NULL,
        expires_at REAL,
        note       TEXT,
        created_at REAL    NOT NULL
    );
    """,
    # v11 — giveaways et sondages
    """
    CREATE TABLE giveaways (
        id            INTEGER PRIMARY KEY AUTOINCREMENT,
        guild_id      INTEGER NOT NULL,
        channel_id    INTEGER NOT NULL,
        message_id    INTEGER,
        host_id       INTEGER NOT NULL,
        prize         TEXT    NOT NULL,
        winners       INTEGER NOT NULL DEFAULT 1,
        required_role INTEGER,
        ends_at       REAL    NOT NULL,
        ended         INTEGER NOT NULL DEFAULT 0,
        winner_ids    TEXT
    );
    CREATE TABLE giveaway_entries (
        giveaway_id INTEGER NOT NULL,
        user_id     INTEGER NOT NULL,
        PRIMARY KEY (giveaway_id, user_id)
    );
    CREATE TABLE polls (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        guild_id   INTEGER NOT NULL,
        channel_id INTEGER NOT NULL,
        message_id INTEGER,
        author_id  INTEGER NOT NULL,
        question   TEXT    NOT NULL,
        options    TEXT    NOT NULL,
        ends_at    REAL,
        ended      INTEGER NOT NULL DEFAULT 0
    );
    CREATE TABLE poll_votes (
        poll_id INTEGER NOT NULL,
        user_id INTEGER NOT NULL,
        option  INTEGER NOT NULL,
        PRIMARY KEY (poll_id, user_id)
    );
    """,
    # v12 — XP par jour (classements hebdo / mensuels) et état des alertes Twitch / YouTube
    """
    CREATE TABLE xp_daily (
        guild_id INTEGER NOT NULL,
        user_id  INTEGER NOT NULL,
        day      TEXT    NOT NULL,
        xp       INTEGER NOT NULL DEFAULT 0,
        PRIMARY KEY (guild_id, user_id, day)
    );
    CREATE INDEX idx_xp_daily_day ON xp_daily (guild_id, day);
    CREATE TABLE alert_state (
        guild_id INTEGER NOT NULL,
        kind     TEXT    NOT NULL,
        source   TEXT    NOT NULL,
        last_id  TEXT,
        resolved TEXT,
        PRIMARY KEY (guild_id, kind, source)
    );
    """,
    # v13 — économie
    """
    CREATE TABLE economy (
        guild_id   INTEGER NOT NULL,
        user_id    INTEGER NOT NULL,
        balance    INTEGER NOT NULL DEFAULT 0,
        last_daily REAL    NOT NULL DEFAULT 0,
        streak     INTEGER NOT NULL DEFAULT 0,
        last_work  REAL    NOT NULL DEFAULT 0,
        PRIMARY KEY (guild_id, user_id)
    );
    CREATE TABLE inventory (
        guild_id INTEGER NOT NULL,
        user_id  INTEGER NOT NULL,
        item     TEXT    NOT NULL,
        quantity INTEGER NOT NULL DEFAULT 0,
        PRIMARY KEY (guild_id, user_id, item)
    );
    """,
    # v14 — rappels et anniversaires
    """
    CREATE TABLE reminders (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id    INTEGER NOT NULL,
        guild_id   INTEGER,
        channel_id INTEGER,
        remind_at  REAL    NOT NULL,
        text       TEXT    NOT NULL,
        created_at REAL    NOT NULL
    );
    CREATE INDEX idx_reminders_time ON reminders (remind_at);
    CREATE TABLE birthdays (
        guild_id INTEGER NOT NULL,
        user_id  INTEGER NOT NULL,
        day      INTEGER NOT NULL,
        month    INTEGER NOT NULL,
        PRIMARY KEY (guild_id, user_id)
    );
    """,
    # v15 — statistiques quotidiennes et historique des modifications du panel
    """
    CREATE TABLE stats_daily (
        guild_id      INTEGER NOT NULL,
        day           TEXT    NOT NULL,
        joins         INTEGER NOT NULL DEFAULT 0,
        leaves        INTEGER NOT NULL DEFAULT 0,
        messages      INTEGER NOT NULL DEFAULT 0,
        voice_minutes INTEGER NOT NULL DEFAULT 0,
        members       INTEGER,
        PRIMARY KEY (guild_id, day)
    );
    CREATE TABLE panel_audit (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        guild_id   INTEGER NOT NULL,
        user_id    INTEGER NOT NULL,
        username   TEXT    NOT NULL,
        action     TEXT    NOT NULL,
        details    TEXT,
        created_at REAL    NOT NULL
    );
    CREATE INDEX idx_panel_audit ON panel_audit (guild_id, created_at);
    """,
    # v16 — suggestions et starboard
    """
    CREATE TABLE suggestions (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        guild_id   INTEGER NOT NULL,
        channel_id INTEGER NOT NULL,
        message_id INTEGER,
        author_id  INTEGER NOT NULL,
        content    TEXT    NOT NULL,
        status     TEXT    NOT NULL DEFAULT 'open',
        response   TEXT,
        staff_id   INTEGER,
        created_at REAL    NOT NULL
    );
    CREATE TABLE suggestion_votes (
        suggestion_id INTEGER NOT NULL,
        user_id       INTEGER NOT NULL,
        vote          INTEGER NOT NULL,
        PRIMARY KEY (suggestion_id, user_id)
    );
    CREATE TABLE starboard (
        guild_id        INTEGER NOT NULL,
        message_id      INTEGER PRIMARY KEY,
        star_message_id INTEGER,
        stars           INTEGER NOT NULL DEFAULT 0
    );
    """,
    # v17 — suivi des invitations
    """
    CREATE TABLE invite_joins (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        guild_id   INTEGER NOT NULL,
        member_id  INTEGER NOT NULL,
        inviter_id INTEGER,
        code       TEXT,
        joined_at  REAL    NOT NULL,
        left_at    REAL
    );
    CREATE INDEX idx_invite_joins ON invite_joins (guild_id, inviter_id);
    """,
    # v18 — engagement (succès, quêtes, séries d'activité, compteurs) et banque
    """
    CREATE TABLE achievements (
        guild_id    INTEGER NOT NULL,
        user_id     INTEGER NOT NULL,
        achievement TEXT    NOT NULL,
        unlocked_at REAL    NOT NULL,
        PRIMARY KEY (guild_id, user_id, achievement)
    );
    CREATE TABLE quest_progress (
        guild_id INTEGER NOT NULL,
        user_id  INTEGER NOT NULL,
        period   TEXT    NOT NULL,
        quest    TEXT    NOT NULL,
        progress INTEGER NOT NULL DEFAULT 0,
        done     INTEGER NOT NULL DEFAULT 0,
        PRIMARY KEY (guild_id, user_id, period, quest)
    );
    CREATE TABLE activity_streaks (
        guild_id INTEGER NOT NULL,
        user_id  INTEGER NOT NULL,
        last_day TEXT    NOT NULL,
        streak   INTEGER NOT NULL DEFAULT 1,
        best     INTEGER NOT NULL DEFAULT 1,
        PRIMARY KEY (guild_id, user_id)
    );
    CREATE TABLE member_counters (
        guild_id INTEGER NOT NULL,
        user_id  INTEGER NOT NULL,
        key      TEXT    NOT NULL,
        value    INTEGER NOT NULL DEFAULT 0,
        PRIMARY KEY (guild_id, user_id, key)
    );
    ALTER TABLE economy ADD COLUMN bank INTEGER NOT NULL DEFAULT 0;
    """,
    # v19 — tournois, événements, parrainage, IA, signalements, journal des messages
    """
    CREATE TABLE tournaments (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        guild_id   INTEGER NOT NULL,
        channel_id INTEGER NOT NULL,
        message_id INTEGER,
        name       TEXT    NOT NULL,
        max_players INTEGER NOT NULL,
        reward     INTEGER NOT NULL DEFAULT 0,
        status     TEXT    NOT NULL DEFAULT 'open',
        rounds     INTEGER NOT NULL DEFAULT 0,
        winner_id  INTEGER,
        created_by INTEGER NOT NULL,
        created_at REAL    NOT NULL
    );
    CREATE TABLE tournament_players (
        tournament_id INTEGER NOT NULL,
        user_id       INTEGER NOT NULL,
        PRIMARY KEY (tournament_id, user_id)
    );
    CREATE TABLE tournament_matches (
        tournament_id INTEGER NOT NULL,
        round         INTEGER NOT NULL,
        slot          INTEGER NOT NULL,
        p1            INTEGER,
        p2            INTEGER,
        winner        INTEGER,
        PRIMARY KEY (tournament_id, round, slot)
    );
    CREATE TABLE events (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        guild_id    INTEGER NOT NULL,
        channel_id  INTEGER NOT NULL,
        message_id  INTEGER,
        title       TEXT    NOT NULL,
        description TEXT,
        starts_at   REAL    NOT NULL,
        max_places  INTEGER NOT NULL DEFAULT 0,
        created_by  INTEGER NOT NULL,
        reminded    INTEGER NOT NULL DEFAULT 0,
        cancelled   INTEGER NOT NULL DEFAULT 0
    );
    CREATE TABLE event_participants (
        event_id INTEGER NOT NULL,
        user_id  INTEGER NOT NULL,
        PRIMARY KEY (event_id, user_id)
    );
    ALTER TABLE invite_joins ADD COLUMN rewarded INTEGER NOT NULL DEFAULT 0;
    CREATE TABLE ai_usage (
        guild_id INTEGER NOT NULL,
        day      TEXT    NOT NULL,
        count    INTEGER NOT NULL DEFAULT 0,
        PRIMARY KEY (guild_id, day)
    );
    CREATE TABLE reports (
        id                INTEGER PRIMARY KEY AUTOINCREMENT,
        guild_id          INTEGER NOT NULL,
        channel_id        INTEGER NOT NULL,
        message_id        INTEGER NOT NULL,
        author_id         INTEGER NOT NULL,
        reporter_id       INTEGER NOT NULL,
        reason            TEXT,
        content           TEXT,
        status            TEXT    NOT NULL DEFAULT 'open',
        handled_by        INTEGER,
        report_message_id INTEGER,
        created_at        REAL    NOT NULL
    );
    CREATE INDEX idx_reports ON reports (guild_id, status);
    CREATE TABLE message_log (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        guild_id   INTEGER NOT NULL,
        channel_id INTEGER NOT NULL,
        author_id  INTEGER NOT NULL,
        message_id INTEGER NOT NULL,
        action     TEXT    NOT NULL,
        before     TEXT,
        after      TEXT,
        created_at REAL    NOT NULL
    );
    CREATE INDEX idx_message_log ON message_log (guild_id, created_at);
    """,
    # v20 — votes top.gg (récompense récupérée avec /vote sur le serveur choisi)
    """
    CREATE TABLE bot_votes (
        id            INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id       INTEGER NOT NULL,
        voted_at      REAL    NOT NULL,
        weekend       INTEGER NOT NULL DEFAULT 0,
        claimed_guild INTEGER,
        claimed_at    REAL
    );
    CREATE INDEX idx_bot_votes_user ON bot_votes (user_id, voted_at);
    """,
    # v21 — clé d'IA propre à chaque serveur (chiffrée, jamais dans la configuration exportable)
    """
    CREATE TABLE ai_keys (
        guild_id   INTEGER PRIMARY KEY,
        provider   TEXT    NOT NULL,
        model      TEXT    NOT NULL DEFAULT '',
        key_enc    TEXT    NOT NULL,
        key_hint   TEXT    NOT NULL,
        updated_by INTEGER NOT NULL,
        updated_at REAL    NOT NULL
    );
    """,
]


def validate_backup(path: Path) -> str | None:
    """Vérifie qu'un fichier est bien une sauvegarde de ce bot. Renvoie l'erreur, ou None si c'est bon."""
    try:
        with open(path, "rb") as f:
            if f.read(16) != b"SQLite format 3\x00":
                return "Ce fichier n'est pas une base SQLite."
        conn = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
        try:
            if conn.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                return "Le fichier est endommagé."
            try:
                version = conn.execute("SELECT MAX(version) FROM schema_version").fetchone()[0] or 0
            except sqlite3.DatabaseError:
                return "Ce n'est pas une sauvegarde de ce bot."
        finally:
            conn.close()
    except (OSError, sqlite3.DatabaseError):
        return "Fichier illisible."
    if version > len(MIGRATIONS):
        return "Cette sauvegarde vient d'une version plus récente du bot : mets d'abord le bot à jour."
    return None


def apply_pending_restore(db_path: Path) -> bool:
    """Remplace la base par la sauvegarde déposée avec /restore (l'ancienne est gardée dans backups/)."""
    pending = db_path.parent / PENDING_RESTORE
    if not pending.exists():
        return False
    error = validate_backup(pending)
    if error:
        log.error("Restauration annulée (%s) : le fichier est mis de côté", error)
        pending.replace(pending.with_suffix(".rejected"))
        return False
    if db_path.exists():
        keep = db_path.parent / "backups" / f"before_restore_{time.strftime('%Y%m%d_%H%M%S')}"
        keep.mkdir(parents=True, exist_ok=True)
        for suffix in ("", "-wal", "-shm"):
            part = Path(f"{db_path}{suffix}")
            if part.exists():
                shutil.move(str(part), keep / part.name)
    pending.replace(db_path)
    log.warning("Base de données restaurée depuis la sauvegarde envoyée avec /restore")
    return True


class Database:
    def __init__(self, path: Path | str = DEFAULT_PATH):
        self.path = Path(path)
        self.conn: aiosqlite.Connection | None = None

    async def connect(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        apply_pending_restore(self.path)
        self.conn = await aiosqlite.connect(self.path)
        self.conn.row_factory = aiosqlite.Row
        await self.conn.execute("PRAGMA journal_mode=WAL")
        await self.conn.execute("PRAGMA foreign_keys=ON")
        await self._migrate()

    async def _migrate(self) -> None:
        assert self.conn
        await self.conn.execute(
            "CREATE TABLE IF NOT EXISTS schema_version (version INTEGER PRIMARY KEY)"
        )
        row = await (await self.conn.execute("SELECT MAX(version) FROM schema_version")).fetchone()
        current = row[0] or 0
        for version, sql in enumerate(MIGRATIONS, start=1):
            if version <= current:
                continue
            await self.conn.executescript(sql)
            await self.conn.execute("INSERT INTO schema_version (version) VALUES (?)", (version,))
            log.info("Migration v%d appliquée", version)
        await self.conn.commit()

    @property
    def version(self) -> int:
        return len(MIGRATIONS)

    async def execute(self, sql: str, params: Iterable[Any] = ()) -> int:
        """Exécute une requête d'écriture et renvoie lastrowid."""
        assert self.conn, "Base non connectée"
        cur = await self.conn.execute(sql, tuple(params))
        await self.conn.commit()
        return cur.lastrowid or 0

    async def fetchone(self, sql: str, params: Iterable[Any] = ()) -> aiosqlite.Row | None:
        assert self.conn, "Base non connectée"
        cur = await self.conn.execute(sql, tuple(params))
        return await cur.fetchone()

    async def fetchall(self, sql: str, params: Iterable[Any] = ()) -> list[aiosqlite.Row]:
        assert self.conn, "Base non connectée"
        cur = await self.conn.execute(sql, tuple(params))
        return list(await cur.fetchall())

    async def backup_to(self, target: Path) -> None:
        """Copie cohérente de la base (fonctionne même pendant que le bot tourne)."""
        assert self.conn
        target.parent.mkdir(parents=True, exist_ok=True)
        async with aiosqlite.connect(target) as dest:
            await self.conn.backup(dest)

    # --- paramètres par serveur -------------------------------------------
    async def get_setting(self, guild_id: int, key: str, default: str | None = None) -> str | None:
        row = await self.fetchone(
            "SELECT value FROM settings WHERE guild_id=? AND key=?", (guild_id, key)
        )
        return row["value"] if row else default

    async def set_setting(self, guild_id: int, key: str, value: str | None) -> None:
        await self.execute(
            "INSERT INTO settings (guild_id, key, value) VALUES (?,?,?) "
            "ON CONFLICT(guild_id, key) DO UPDATE SET value=excluded.value",
            (guild_id, key, value),
        )

    async def close(self) -> None:
        if self.conn:
            await self.conn.close()
            self.conn = None
