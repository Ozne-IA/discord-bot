"""Tests de la version Premium et des nouveaux modules (sans Discord)."""
import time
from datetime import date

from bot.config import DEFAULTS, FREE_OVERRIDES, ConfigStore, sanitize
from bot.db import Database
from bot.images import CAPTCHA_ALPHABET, captcha_image, new_captcha_code, rank_card
from bot.premium import PremiumRegistry
from cogs.alerts import fill, parse_youtube_feed, twitch_login
from cogs.levels import period_start

BIG = 1234567890123456789


async def test_free_server_gets_free_values_premium_gets_its_own(tmp_path):
    db = Database(tmp_path / "t.db")
    await db.connect()
    premium_guilds = {2}
    store = ConfigStore(premium_check=lambda gid: gid in premium_guilds)
    custom = {"brand": {"color": "#FF0000"}, "welcome": {"message": "Yo {mention}"},
              "anti_nuke": {"enabled": True}, "verification": {"captcha": True},
              "alerts": {"youtube": [{"source": "@test", "channel": str(BIG), "message": ""}]}}
    await store.save(db, 1, custom)
    await store.save(db, 2, custom)

    free, paid = store.get(1), store.get(2)
    assert free.get("brand", "color") == DEFAULTS["brand"]["color"]
    assert free.get("welcome", "message") == DEFAULTS["welcome"]["message"]
    assert free.get("anti_nuke", "enabled") is False
    assert free.get("verification", "captcha") is False
    assert free.get("alerts", "youtube") == []
    assert paid.get("brand", "color") == "#FF0000"
    assert paid.get("welcome", "message") == "Yo {mention}"
    assert paid.get("verification", "captcha") is True
    assert paid.get("alerts", "youtube")[0]["channel"] == BIG

    # le panel voit toujours ce que l'admin a réglé
    assert store.raw(1).get("brand", "color") == "#FF0000"

    # passage en Premium : la config est recalculée
    premium_guilds.add(1)
    store.invalidate(1)
    assert store.get(1).get("brand", "color") == "#FF0000"
    await db.close()


def test_free_overrides_cover_existing_paths():
    for path in FREE_OVERRIDES:
        cur = DEFAULTS
        for key in path.split("."):
            assert key in cur, f"{path} absent de defaults.json"
            cur = cur[key]


async def test_premium_registry_grants_and_expiry(tmp_path):
    db = Database(tmp_path / "t.db")
    await db.connect()
    reg = PremiumRegistry()
    changed = []
    reg.on_change(changed.append)
    assert not reg.is_premium(5)
    await reg.grant(db, 5, by=1, days=30)
    assert reg.is_premium(5) and changed == [5]
    assert reg.status(5)["source"] == "grant"
    reg.grants[6] = time.time() - 10  # expiré
    assert not reg.is_premium(6)
    reloaded = PremiumRegistry()
    await reloaded.load(db)
    assert reloaded.is_premium(5)
    await reg.revoke(db, 5)
    assert not reg.is_premium(5)
    await db.close()


def test_sanitize_alert_lists():
    clean = sanitize({"alerts": {
        "twitch": [{"login": "zerator", "channel": str(BIG), "message": "Live !", "hack": 1},
                   {"login": "", "channel": str(BIG)}, {"login": "x", "channel": "0"}, "nope"],
        "youtube": [{"source": "@MrBeast", "channel": str(BIG)}]}})
    assert clean["alerts"]["twitch"] == [{"login": "zerator", "channel": BIG, "message": "Live !"}]
    assert clean["alerts"]["youtube"] == [{"source": "@MrBeast", "channel": BIG, "message": ""}]


def test_captcha_and_rank_card_render():
    code = new_captcha_code()
    assert len(code) == 5 and all(c in CAPTCHA_ALPHABET for c in code)
    assert captcha_image(code)[:8] == b"\x89PNG\r\n\x1a\n"
    png = rank_card("Un pseudo vraiment très très long pour tester", None, 12, 3, 830, 1420, 9150, 412)
    assert png[:8] == b"\x89PNG\r\n\x1a\n"


def test_period_start():
    wednesday = date(2026, 11, 18)
    assert period_start("semaine", wednesday) == "2026-11-16"
    assert period_start("mois", wednesday) == "2026-11-01"
    assert period_start("tout", wednesday) is None


FEED = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns:yt="http://www.youtube.com/xml/schemas/2015" xmlns="http://www.w3.org/2005/Atom">
 <title>Ma Chaîne</title><author><name>Ma Chaîne</name></author>
 <entry><yt:videoId>NEW123</yt:videoId><title>Vidéo récente</title>
  <link rel="alternate" href="https://www.youtube.com/watch?v=NEW123"/><author><name>Ma Chaîne</name></author></entry>
 <entry><yt:videoId>OLD456</yt:videoId><title>Ancienne</title>
  <link rel="alternate" href="https://www.youtube.com/watch?v=OLD456"/><author><name>Ma Chaîne</name></author></entry>
</feed>"""


def test_youtube_feed_and_helpers():
    videos = parse_youtube_feed(FEED)
    assert [v["id"] for v in videos] == ["NEW123", "OLD456"]
    assert videos[0]["author"] == "Ma Chaîne" and videos[0]["url"].endswith("NEW123")
    assert fill("{name} : {title} {inconnu}", name="A", title="B") == "A : B {inconnu}"
    assert twitch_login("https://www.twitch.tv/ZeratoR/") == "zerator"
    assert twitch_login("@kameto") == "kameto"
    assert twitch_login("pas valide!") is None
