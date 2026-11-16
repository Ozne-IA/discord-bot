"""v14.5 : modération Twitch (signature des événements, automod du chat, sanctions, journal)."""
import hashlib
import hmac
import json
import time
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from bot import twitch
from bot.config import DEFAULTS, sanitize
from bot.db import Database
from cogs import twitch as twitch_cog

SECRET = "secret-eventsub-de-test"
CFG = dict(DEFAULTS["twitch_mod"])


def signed(body: dict, msg_type: str = "notification", msg_id: str = "m1", when: float | None = None,
           secret: str = SECRET) -> tuple[dict, bytes]:
    raw = json.dumps(body).encode()
    stamp = datetime.fromtimestamp(when or time.time(), tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.123456789Z")
    sig = "sha256=" + hmac.new(secret.encode(), msg_id.encode() + stamp.encode() + raw, hashlib.sha256).hexdigest()
    return {"Twitch-Eventsub-Message-Id": msg_id, "Twitch-Eventsub-Message-Timestamp": stamp,
            "Twitch-Eventsub-Message-Signature": sig, "Twitch-Eventsub-Message-Type": msg_type}, raw


# --- signature et doublons ---------------------------------------------------
def test_verify_event():
    headers, raw = signed({"a": 1})
    assert twitch.verify_event(headers, raw, SECRET)
    assert not twitch.verify_event(headers, raw + b" ", SECRET)          # corps modifié
    assert not twitch.verify_event(headers, raw, "autre-secret-xx")
    assert not twitch.verify_event(headers, raw, "")
    old_headers, old_raw = signed({"a": 1}, when=time.time() - 3600)
    assert not twitch.verify_event(old_headers, old_raw, SECRET)          # trop vieux (rejeu)
    seen = twitch.SeenIds(size=2)
    assert seen.add("x") and not seen.add("x") and seen.add("y") and seen.add("z") and seen.add("x")


def test_oauth_helpers(monkeypatch):
    monkeypatch.setenv("TWITCH_CLIENT_ID", "cid")
    states = twitch.OAuthStates()
    st = states.create(kind="bot", user_id=1)
    assert states.pop(st) == {"kind": "bot", "user_id": 1} and states.pop(st) is None
    url = twitch.authorize_url("https://x/twitch/callback", twitch.BOT_SCOPES, "abc")
    assert "client_id=cid" in url and "user%3Abot" in url and "state=abc" in url
    assert twitch.missing_scopes(["channel:bot"], twitch.BROADCASTER_SCOPES) == ["channel:moderate", "moderation:read"]
    monkeypatch.setenv("TWITCH_EVENTSUB_SECRET", "court")
    assert twitch.eventsub_secret() == ""


# --- automod --------------------------------------------------------------------
def test_rules():
    cfg = {**CFG, "links_action": "delete", "caps_action": "timeout", "repeat_action": "timeout",
           "banned_words": ["gros mot"], "words_action": "delete"}
    assert twitch.check_message("salut tout le monde", cfg, []) is None
    assert twitch.check_message("regarde https://twitch.tv/abc et youtu.be/x", cfg, []) is None   # sites autorisés
    assert twitch.check_message("va sur monsite.fr", cfg, []) == ("links", "delete")
    assert twitch.check_message("free nitro: discord-nitro-gift.ru/claim", cfg, []) == ("phishing", "ban")
    assert twitch.check_message("t'es un GROS MOT toi", cfg, []) == ("words", "delete")
    assert twitch.check_message("grosmotier", cfg, []) is None                                     # mot entier seulement
    assert twitch.check_message("REGARDEZ CE QUI SE PASSE LA", cfg, []) == ("caps", "timeout")
    assert twitch.check_message("OK LOL", cfg, []) is None                                         # trop court
    assert twitch.check_message("spam", cfg, ["spam"]) is None
    assert twitch.check_message("Spam ", cfg, ["spam", "spam"]) == ("repeat", "timeout")
    off = {k: ("off" if k.endswith("_action") else v) for k, v in cfg.items()}
    assert twitch.check_message("discord-nitro-gift.ru GROS MOT", off, []) is None


def test_exempt_and_config():
    assert twitch.exempt([{"set_id": "moderator"}], False) and twitch.exempt([{"set_id": "vip"}], False)
    assert not twitch.exempt([{"set_id": "subscriber"}], False) and twitch.exempt([{"set_id": "subscriber"}], True)
    clean = sanitize({"twitch_mod": {"links_action": "exploser", "caps_action": "ban", "log_channel": "123"}})
    assert clean["twitch_mod"] == {"links_action": "off", "caps_action": "ban", "log_channel": 123}


# --- le module : webhook, sanctions et journal ------------------------------------------
class FakeAPI:
    def __init__(self):
        self.calls = []
        self.fail = None

    async def _do(self, *call):
        self.calls.append(call)
        if self.fail:
            raise self.fail

    async def delete_message(self, bid, msg_id):
        await self._do("delete", bid, msg_id)

    async def ban(self, bid, uid, reason, duration=None):
        await self._do("ban", bid, uid, duration)

    async def unban(self, bid, uid):
        await self._do("unban", bid, uid)

    async def send_message(self, bid, text):
        await self._do("say", bid, text)


@pytest.fixture
def cog(monkeypatch):
    monkeypatch.setenv("TWITCH_EVENTSUB_SECRET", SECRET)
    c = twitch_cog.TwitchMod.__new__(twitch_cog.TwitchMod)
    guild = SimpleNamespace(id=50)
    c.bot = SimpleNamespace(get_guild=lambda gid: guild if gid == 50 else None)
    c.api, c.seen, c.recent, c._errors = FakeAPI(), twitch.SeenIds(), {}, {}
    c.channels, c.logins, c.active, c.bot_user_id = {100: 50}, {100: "streamer"}, {100}, 999
    cfg = {"twitch_mod": {**CFG, "links_action": "timeout", "timeout_minutes": 5}}
    monkeypatch.setattr(twitch_cog, "gconf", lambda g: SimpleNamespace(
        get=lambda *k, default=None: (cfg.get(k[0], {}).get(k[1], default) if len(k) == 2 else cfg.get(k[0], default))))
    monkeypatch.setattr(twitch_cog, "language", lambda g: "fr")
    logs = []

    async def fake_log(guild, bid, title, login, user_id, buttons, **kw):
        logs.append((title, login, buttons, kw))
    c.log = fake_log
    c.logs = logs
    return c


def chat(text, chatter=7, badges=()):
    return {"broadcaster_user_id": "100", "chatter_user_id": str(chatter), "chatter_user_login": "spammeur",
            "message_id": "abc", "message": {"text": text}, "badges": [{"set_id": b} for b in badges]}


async def test_chat_message_punished_and_logged(cog):
    await cog.on_chat(chat("viens sur monsite.fr"))
    assert cog.api.calls[0] == ("ban", 100, 7, 300)                       # timeout de 5 min
    assert cog.api.calls[1][0] == "say" and "@spammeur" in cog.api.calls[1][2]
    title, login, buttons, kw = cog.logs[0]
    assert "Timeout" in title and login == "spammeur" and buttons == ("unban", "ban") and kw["rule"] == "Lien non autorisé"


async def test_chat_ignored_cases(cog):
    await cog.on_chat(chat("monsite.fr", badges=("moderator",)))          # modo
    await cog.on_chat(chat("monsite.fr", chatter=999))                      # le bot lui-même
    await cog.on_chat(chat("monsite.fr", chatter=100))                      # le streamer
    await cog.on_chat({**chat("monsite.fr"), "broadcaster_user_id": "555"})  # chaîne inconnue
    cog.active = set()
    await cog.on_chat(chat("monsite.fr"))                                   # au-delà de la limite gratuite
    assert cog.api.calls == [] and cog.logs == []


async def test_not_moderator_reported_once(cog, monkeypatch):
    cog.api.fail = twitch_cog.TwitchError("Le bot n'est pas modérateur", 403)
    reported = []

    async def fake_report(guild, bid, error):
        reported.append(error)
    cog.report_error = fake_report
    await cog.on_chat(chat("monsite.fr"))
    assert reported == ["Le bot n'est pas modérateur"] and cog.logs == []


async def test_human_bans_logged(cog):
    await cog.on_ban({"broadcaster_user_id": "100", "user_id": "7", "user_login": "x", "moderator_user_id": "5",
                      "moderator_user_login": "modo", "reason": "insultes", "is_permanent": True})
    await cog.on_ban({"broadcaster_user_id": "100", "user_id": "8", "user_login": "y", "moderator_user_id": "5",
                      "moderator_user_login": "modo", "is_permanent": False, "ends_at": "2026-11-16T12:30:00Z"})
    await cog.on_ban({"broadcaster_user_id": "100", "user_id": "9", "moderator_user_id": "999"})  # fait par le bot
    await cog.on_unban({"broadcaster_user_id": "100", "user_id": "7", "user_login": "x", "moderator_user_id": "5",
                        "moderator_user_login": "modo"})
    titles = [entry[0] for entry in cog.logs]
    assert titles == ["🔨 Banni par modo", "⏳ Timeout par modo (jusqu'à 12:30 UTC)", "✅ Débanni par modo"]
    assert cog.logs[0][2] == ("unban",) and cog.logs[0][3]["reason"] == "insultes"


async def test_webhook_flow(cog):
    headers, raw = signed({"challenge": "abc123", "subscription": {"type": "channel.chat.message"}},
                          msg_type="webhook_callback_verification")
    assert await cog.handle_webhook(headers, raw) == (200, "abc123", "text/plain")
    bad = dict(headers, **{"Twitch-Eventsub-Message-Signature": "sha256=00"})
    assert (await cog.handle_webhook(bad, raw))[0] == 403
    handled = []

    async def fake_event(sub_type, event):
        handled.append(sub_type)
    cog.handle_event = fake_event
    body = {"subscription": {"type": "channel.ban"}, "event": {}}
    headers, raw = signed(body, msg_id="n1")
    assert (await cog.handle_webhook(headers, raw))[0] == 204
    assert (await cog.handle_webhook(headers, raw))[0] == 204          # doublon : ignoré
    import asyncio
    await asyncio.sleep(0)
    assert handled == ["channel.ban"]


async def test_channels_limit(tmp_path, monkeypatch):
    db = Database(tmp_path / "t.db")
    await db.connect()
    for i, bid in enumerate((1, 2, 3)):
        await db.execute("INSERT INTO twitch_channels (broadcaster_id, guild_id, login, connected_by, created_at) "
                         "VALUES (?,?,?,?,?)", (bid, 50, f"c{bid}", 9, i))
    monkeypatch.setattr(twitch_cog, "is_premium", lambda g: False)
    c = twitch_cog.TwitchMod.__new__(twitch_cog.TwitchMod)
    c.bot, c.api = SimpleNamespace(db=db), None
    await c.load_channels()
    assert c.active == {1} and c.channels == {1: 50, 2: 50, 3: 50}       # gratuit : 1 chaîne active
    monkeypatch.setattr(twitch_cog, "is_premium", lambda g: True)
    await c.load_channels()
    assert c.active == {1, 2, 3}
    await db.close()


# --- livraison 2 : commandes du chat -----------------------------------------------
def test_find_command_and_fill():
    cmds = [{"trigger": "!discord", "response": "Rejoins-nous {user} !"}, {"trigger": "reseaux", "response": "x"},
            {"trigger": "!vide", "response": "  "}]
    assert twitch.find_command("!Discord stp", cmds, 5) == cmds[0]
    assert twitch.find_command("!reseaux", cmds, 5) == cmds[1]            # « ! » facultatif dans le panel
    assert twitch.find_command("!reseaux", cmds, 1) is None               # au-delà de la limite gratuite
    assert twitch.find_command("discord", cmds, 5) is None
    assert twitch.find_command("!vide", cmds, 5) is None and twitch.find_command("!", cmds, 5) is None
    assert twitch.fill_response("Salut {user} sur {channel}", "Bob", "stream") == "Salut Bob sur stream"
    assert len(twitch.fill_response("a" * 900, "", "")) == 500
    clean = sanitize({"twitch_mod": {"commands": [{"trigger": "!a", "response": "b" * 600}, {"trigger": "", "response": "x"}]}})
    assert clean["twitch_mod"]["commands"] == [{"trigger": "!a", "response": "b" * 450}]


async def test_chat_command_reply_and_cooldown(cog, monkeypatch):
    monkeypatch.setattr(twitch_cog, "is_premium", lambda g: False)
    cog.cooldowns = {}
    cfg = twitch_cog.gconf(None).get("twitch_mod")
    cfg["commands"] = [{"trigger": "!discord", "response": "Discord : https://discord.gg/x ({user})"}]
    cfg["command_cooldown"] = 30
    ev = {**chat("!discord"), "chatter_user_name": "Bob"}
    await cog.on_chat(ev)
    await cog.on_chat(ev)                                                   # pendant le délai : rien
    await cog.on_chat({**chat("!discord", chatter=100), "chatter_user_name": "Streamer"})  # le streamer aussi
    says = [c for c in cog.api.calls if c[0] == "say"]
    assert says == [("say", 100, "Discord : https://discord.gg/x (Bob)")]
    cog.cooldowns.clear()
    await cog.on_chat({**chat("!discord", badges=("moderator",)), "chatter_user_name": "Modo"})
    assert cog.api.calls[-1] == ("say", 100, "Discord : https://discord.gg/x (Modo)")
