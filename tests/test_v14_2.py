"""v14.2 : sauvegardes automatiques, alertes, protections du site, votes top.gg, essai Premium."""
import gzip
import hashlib
import hmac
import json
import time

import pytest

from bot import backups, votes
from bot.db import Database, validate_backup
from bot.premium import TRIAL_KEY, PremiumRegistry
from cogs.ops import AlertThrottle
from web.security import RateLimiter, bucket_for, content_security_policy

SECRET = "whs_test_secret"


# --- sauvegardes -----------------------------------------------------------
def test_backup_schedule():
    day = 86400
    assert backups.is_due(None, 1000, 4, 12)                      # jamais faite
    assert not backups.is_due(0, 10 * 3600, 4, 4)                 # trop tôt
    assert backups.is_due(0, 23 * 3600, 4, 4)                     # à l'heure prévue
    assert not backups.is_due(0, 23 * 3600, 4, 5)                 # pas la bonne heure
    assert backups.is_due(0, day + 2 * 3600, 4, 9)                # rattrapage après 25 h


async def test_compress_prune_and_restore_gz(tmp_path):
    db = Database(tmp_path / "bot.db")
    await db.connect()
    await db.execute("INSERT INTO levels (guild_id, user_id, xp) VALUES (1, 2, 3)")
    folder = tmp_path / "backups"
    for i in range(5):
        raw = folder / f"auto_2026010{i}_0400.db"
        await db.backup_to(raw)
        backups.compress(raw, raw.with_suffix(".db.gz"))
        raw.unlink()
    await db.close()
    removed = backups.prune(folder, keep=3)
    assert [p.name for p in removed] == ["auto_20260101_0400.db.gz", "auto_20260100_0400.db.gz"]
    assert len(list(folder.iterdir())) == 3

    packed = (folder / "auto_20260104_0400.db.gz").read_bytes()
    restored = tmp_path / "restored.db"
    restored.write_bytes(backups.maybe_decompress(packed))
    assert validate_backup(restored) is None
    assert backups.maybe_decompress(b"SQLite format 3\x00abc") == b"SQLite format 3\x00abc"
    with pytest.raises(ValueError):
        backups.maybe_decompress(b"\x1f\x8b" + b"pas du gzip")


def test_env_int(monkeypatch):
    monkeypatch.setenv("BACKUP_KEEP", "abc")
    assert backups.env_int("BACKUP_KEEP", 14, 1, 365) == 14
    monkeypatch.setenv("BACKUP_KEEP", "9999")
    assert backups.env_int("BACKUP_KEEP", 14, 1, 365) == 365
    monkeypatch.setenv("BACKUP_AUTO", "off")
    assert not backups.auto_enabled()


# --- alertes ---------------------------------------------------------------
def test_alert_throttle():
    t = AlertThrottle(cooldown=3600, per_hour=3)
    assert t.allow("a", now=0)
    assert not t.allow("a", now=10)          # même erreur : pas de doublon
    assert t.allow("b", now=20) and t.allow("c", now=30)
    assert not t.allow("d", now=40)          # plafond par heure
    assert t.allow("a", now=3700)            # une heure plus tard


# --- site --------------------------------------------------------------------
def test_rate_limiter():
    rl = RateLimiter({"write": (3, 60)})
    assert [rl.check("1.2.3.4", "write", now=t) for t in (0, 1, 2)] == [0, 0, 0]
    assert rl.check("1.2.3.4", "write", now=3) > 0
    assert rl.check("5.6.7.8", "write", now=3) == 0       # autre visiteur : pas bloqué
    assert rl.check("1.2.3.4", "write", now=61) == 0      # fenêtre écoulée


def test_buckets_and_csp():
    assert bucket_for("GET", "/health") is None
    assert bucket_for("GET", "/static/style.css") is None
    assert bucket_for("GET", "/login") == "auth"
    assert bucket_for("PUT", "/api/guilds/1/config") == "write"
    assert bucket_for("GET", "/api/me") == "api"
    assert bucket_for("POST", "/webhooks/topgg") == "webhook"
    csp = content_security_policy("abc")
    assert "script-src 'self' 'nonce-abc'" in csp and "frame-ancestors 'none'" in csp
    assert "unsafe-eval" not in csp


# --- votes top.gg ------------------------------------------------------------
def _signed(body: dict, stamp: int, secret: str = SECRET) -> tuple[dict, bytes]:
    raw = json.dumps(body).encode()
    sig = hmac.new(secret.encode(), f"{stamp}.".encode() + raw, hashlib.sha256).hexdigest()
    return {"x-topgg-signature": f"t={stamp},v1={sig}"}, raw


def test_webhook_v0_and_v1():
    raw = json.dumps({"bot": "1", "user": "42", "type": "upvote", "isWeekend": True}).encode()
    vote = votes.parse_webhook({"Authorization": SECRET}, raw, SECRET)
    assert (vote.user_id, vote.weekend, vote.test) == (42, True, False)
    with pytest.raises(votes.WebhookError):
        votes.parse_webhook({"Authorization": "faux"}, raw, SECRET)
    with pytest.raises(votes.WebhookError):
        votes.parse_webhook({"Authorization": SECRET}, raw, "")

    now = int(time.time())
    body = {"type": "vote.create", "data": {"weight": 1, "user": {"platform_id": "77"}}}
    headers, raw = _signed(body, now)
    vote = votes.parse_webhook(headers, raw, SECRET, now=now)
    assert (vote.user_id, vote.weekend, vote.test) == (77, False, False)
    with pytest.raises(votes.WebhookError):                       # signature trop ancienne
        votes.parse_webhook(headers, raw, SECRET, now=now + 1000)
    bad_headers, _ = _signed(body, now, secret="autre")
    with pytest.raises(votes.WebhookError):
        votes.parse_webhook(bad_headers, raw, SECRET, now=now)
    test_headers, test_raw = _signed({"type": "webhook.test", "data": {"user": {"platform_id": "5"}}}, now)
    assert votes.parse_webhook(test_headers, test_raw, SECRET, now=now).test


async def test_vote_claim_once(tmp_path):
    db = Database(tmp_path / "t.db")
    await db.connect()
    await votes.record_vote(db, votes.Vote(42, weekend=True), now=1000)
    row = await votes.claim(db, 42, guild_id=9, now=2000)
    assert row and row["weekend"] == 1
    assert votes.reward_amount(200, bool(row["weekend"])) == 400
    assert await votes.claim(db, 42, guild_id=10, now=2001) is None        # déjà récupéré
    await votes.record_vote(db, votes.Vote(43), now=0)
    assert await votes.claim(db, 43, guild_id=9, now=votes.CLAIM_WINDOW + 10) is None  # trop tard
    await db.close()


# --- essai Premium -----------------------------------------------------------
async def test_trial_once_per_server(tmp_path, monkeypatch):
    monkeypatch.setenv("PREMIUM_TRIAL_DAYS", "7")
    db = Database(tmp_path / "t.db")
    await db.connect()
    reg = PremiumRegistry()
    assert await reg.trial_state(db, 1) == "available"
    ends = await reg.start_trial(db, 1, by=5)
    assert reg.is_premium(1) and abs(ends - time.time() - 7 * 86400) < 5
    assert await reg.trial_state(db, 1) == "active"
    with pytest.raises(ValueError):
        await reg.start_trial(db, 1, by=5)
    # fin de l'essai : le serveur redevient gratuit et ne peut pas recommencer
    reg.grants[1] = time.time() - 1
    await db.set_setting(1, TRIAL_KEY, str(time.time() - 1))
    assert not reg.is_premium(1)
    assert await reg.trial_state(db, 1) == "used"
    # un serveur déjà Premium n'a pas d'essai, et l'essai peut être désactivé
    reg.subscriptions[2] = None
    assert await reg.trial_state(db, 2) == "premium"
    monkeypatch.setenv("PREMIUM_TRIAL_DAYS", "0")
    assert await reg.trial_state(db, 3) == "off"
    await db.close()


def test_gzip_roundtrip_is_smaller(tmp_path):
    src = tmp_path / "a.db"
    src.write_bytes(b"x" * 100_000)
    backups.compress(src, tmp_path / "a.db.gz")
    assert (tmp_path / "a.db.gz").stat().st_size < 10_000
    assert gzip.decompress((tmp_path / "a.db.gz").read_bytes()) == b"x" * 100_000
