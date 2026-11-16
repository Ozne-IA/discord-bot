"""v15.0 : Premium payé via Patreon (en attendant les abonnements Discord)."""
import hashlib
import hmac
import json

import pytest

from bot import patreon
from bot.db import Database
from bot.premium import premium
from cogs import patreon as patreon_cog

SECRET = "secret-webhook-patreon"


def member(pid: str, status: str = "active_patron", cents: int = 499) -> dict:
    return {"type": "member", "id": f"m-{pid}",
            "attributes": {"patron_status": status, "currently_entitled_amount_cents": cents, "pledge_cadence": 1,
                           "next_charge_date": "2026-12-16T00:00:00.000+00:00"},
            "relationships": {"user": {"data": {"id": pid, "type": "user"}}}}


@pytest.fixture
async def db(tmp_path, monkeypatch):
    monkeypatch.delenv("PATREON_MIN_CENTS", raising=False)
    database = Database(tmp_path / "p.db")
    await database.connect()
    yield database
    premium.set_patreon(set())
    await database.close()


def test_signature_and_parsing():
    raw = json.dumps({"data": member("42")}).encode()
    good = hmac.new(SECRET.encode(), raw, hashlib.md5).hexdigest()
    assert patreon.verify_signature(SECRET, raw, good) and patreon.verify_signature(SECRET, raw, good.upper())
    assert not patreon.verify_signature(SECRET, raw + b" ", good)
    assert not patreon.verify_signature("", raw, good) and not patreon.verify_signature(SECRET, raw, "")
    body = json.loads(raw)
    assert patreon.parse_webhook("members:pledge:create", body) == {
        "patreon_id": "42", "status": "active_patron", "cents": 499, "cadence": 1,
        "next_charge": "2026-12-16T00:00:00.000+00:00"}
    gone = patreon.parse_webhook("members:delete", body)
    assert gone["status"] == "former_patron" and gone["cents"] == 0
    # Résiliation : Patreon dit encore « active_patron » jusqu'à la fin de la période payée → on le suit
    assert patreon.parse_webhook("members:pledge:delete", body)["status"] == "active_patron"
    ended = json.loads(json.dumps(body))
    ended["data"]["attributes"]["patron_status"] = "former_patron"
    assert patreon.parse_webhook("members:pledge:delete", ended)["status"] == "former_patron"
    assert patreon.parse_webhook("members:update", {"data": {"type": "post"}}) is None
    identity = {"data": {"id": "42", "type": "user"},
                "included": [{"type": "member", "attributes": {"patron_status": "active_patron",
                                                                "currently_entitled_amount_cents": 4999}}]}
    assert patreon.identity_member(identity)["cents"] == 4999
    assert patreon.identity_member({"data": {"id": "42"}}) is None


def test_settings(monkeypatch):
    monkeypatch.setenv("PATREON_URL", "https://www.patreon.com/monbot")
    assert patreon.page_url() == "https://www.patreon.com/monbot"
    monkeypatch.setenv("PATREON_URL", "https://arnaque.example/patreon")
    assert patreon.page_url() is None
    monkeypatch.setenv("PATREON_MIN_CENTS", "300")
    assert patreon.is_active("active_patron", 499) and not patreon.is_active("active_patron", 200)
    assert not patreon.is_active("declined_patron", 499)
    monkeypatch.setenv("PATREON_CLIENT_ID", "abc")
    assert "client_id=abc" in patreon.authorize_url("https://bot.example/patreon/callback", "st")


async def test_link_assign_and_premium(db):
    await patreon.link(db, 1, "42", "Alex")
    await patreon.save_member(db, patreon.parse_member(member("42")))
    await patreon.assign(db, 1, 500, now=1000)
    assert await patreon.refresh_premium(db) == {500: 1}
    assert premium.is_premium(500) and premium.status(500)["source"] == "patreon"
    # Changer de serveur : pas avant 7 jours ; retirer puis remettre ailleurs ne contourne pas le délai
    with pytest.raises(ValueError):
        await patreon.assign(db, 1, 600, now=2000)
    await patreon.unassign(db, 1)
    with pytest.raises(ValueError):
        await patreon.assign(db, 1, 600, now=3000)
    await patreon.assign(db, 1, 500, now=3000)  # même serveur : possible tout de suite
    await patreon.assign(db, 1, 600, now=1000 + patreon.MOVE_COOLDOWN + 1)
    assert await patreon.refresh_premium(db) == {600: 1}
    assert not premium.is_premium(500)
    # Abonnement arrêté (absent de la liste relue) : plus de Premium
    assert await patreon.mark_missing_as_former(db, set()) == 1
    assert await patreon.refresh_premium(db) == {}
    state = await patreon.user_state(db, 1)
    assert state["linked"] and not state["active"] and state["guild_id"] == "600"


async def test_assign_needs_active_subscription_and_unique_link(db):
    with pytest.raises(ValueError):
        await patreon.assign(db, 1, 500)
    await patreon.link(db, 1, "42", "Alex")
    with pytest.raises(ValueError):
        await patreon.assign(db, 1, 500)          # relié mais pas abonné
    await patreon.save_member(db, patreon.parse_member(member("42")))
    await patreon.assign(db, 1, 500)
    await patreon.link(db, 2, "42", "Alex")       # même Patreon relié à un autre compte Discord
    assert not (await patreon.user_state(db, 1))["linked"]
    assert await patreon.refresh_premium(db) == {}  # l'ancien choix de serveur disparaît avec le lien


async def test_webhook_updates_premium(db, monkeypatch):
    monkeypatch.setenv("PATREON_WEBHOOK_SECRET", SECRET)
    cog = patreon_cog.Patreon.__new__(patreon_cog.Patreon)
    cog.bot = type("B", (), {"db": db, "get_guild": lambda self, gid: None})()
    notes = []

    async def notify(title, text, color):
        notes.append(title)
    cog.notify = notify
    await patreon.link(db, 1, "42", "Alex")
    await patreon.save_member(db, patreon.parse_member(member("42")))
    await patreon.assign(db, 1, 500)
    await patreon.refresh_premium(db)

    raw = json.dumps({"data": member("42")}).encode()
    status, _ = await cog.handle_webhook({"X-Patreon-Signature": "faux", "X-Patreon-Event": "members:update"}, raw)
    assert status == 401
    sig = hmac.new(SECRET.encode(), raw, hashlib.md5).hexdigest()
    status, _ = await cog.handle_webhook({"X-Patreon-Signature": sig, "X-Patreon-Event": "members:delete"}, raw)
    assert status == 200 and not premium.is_premium(500) and notes == ["💤 Premium Patreon arrêté"]
    status, _ = await cog.handle_webhook({"X-Patreon-Signature": sig, "X-Patreon-Event": "members:pledge:create"}, raw)
    assert status == 200 and premium.is_premium(500) and notes[-1] == "💎 Nouveau Premium Patreon"


async def test_creator_token_refresh_and_pages(db, monkeypatch):
    monkeypatch.setenv("AI_KEYS_SECRET", "une-phrase-secrete-assez-longue")
    monkeypatch.setenv("PATREON_CREATOR_TOKEN", "vieux")
    monkeypatch.setenv("PATREON_CREATOR_REFRESH_TOKEN", "refresh1")
    monkeypatch.setenv("PATREON_CAMPAIGN_ID", "777")
    api = patreon.PatreonAPI(db, http=None)
    calls = []

    async def fake_request(method, url, **kwargs):
        token = (kwargs.get("headers") or {}).get("Authorization", "")
        calls.append((method, url.split("?")[0], token))
        if method == "POST":
            return {"access_token": "neuf", "refresh_token": "refresh2"}
        if token == "Bearer vieux":
            raise patreon.PatreonError("expiré", 401)
        if "page%5Bcursor%5D" not in url:
            return {"data": [member("1"), {"type": "member"}], "meta": {"pagination": {"cursors": {"next": "c2"}}}}
        return {"data": [member("2", "declined_patron")], "meta": {"pagination": {"cursors": {"next": None}}}}
    api._request = fake_request
    got = [m async for m in api.members()]
    assert [m["patreon_id"] for m in got] == ["1", "2"]
    assert calls[1][0] == "POST" and calls[2][2] == "Bearer neuf"
    assert await api._creator_tokens() == ("neuf", "refresh2")  # gardés (chiffrés) pour la prochaine fois


async def test_web_routes(db):
    from aiohttp.test_utils import TestClient, TestServer

    from web import server

    class Bot:
        user, application_id, version, guilds, cogs = None, 1, "15.0.0", [], {}

        def __init__(self, database):
            self.db = database

        def is_ready(self):
            return True

        def get_cog(self, name):
            return None

    client = TestClient(TestServer(server.Dashboard(Bot(db)).make_app()))
    await client.start_server()
    try:
        assert (await client.get("/api/patreon")).status == 401                    # connexion au panel exigée
        assert (await client.post("/webhooks/patreon", data=b"{}")).status == 503  # module absent
        resp = await client.get("/patreon/connect/1", allow_redirects=False)
        assert resp.status == 302 and resp.headers["Location"] == "/login"
        public = await (await client.get("/api/public")).json()
        assert "patreon_url" in public
    finally:
        await client.close()


async def test_identity_falls_back_when_detailed_request_refused(db):
    api = patreon.PatreonAPI(db, http=None)
    urls = []

    async def fake_request(method, url, **kwargs):
        urls.append(url)
        if "?" in url:
            raise patreon.PatreonError("refusé", 400)
        return {"data": {"id": "42", "attributes": {"full_name": "Alex"}}}
    api._request = fake_request
    assert (await api.identity("jeton"))["data"]["id"] == "42" and len(urls) == 2
