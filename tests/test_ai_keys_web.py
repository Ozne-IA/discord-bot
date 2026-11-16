"""API du panel pour la clé IA : la clé n'est jamais renvoyée, seuls les admins y touchent."""
from types import SimpleNamespace

import pytest
from aiohttp.test_utils import TestClient, TestServer

from bot import ai_keys
from bot.ai_providers import ProviderError
from bot.db import Database
from web import server as web_server
from web.server import Dashboard, HTTPError

KEY = "AIzaSyTESTKEY1234567890abcd"
HEADERS = {"X-Requested-With": "dashboard"}


@pytest.fixture
async def client(tmp_path, monkeypatch):
    monkeypatch.setenv("AI_KEYS_SECRET", "secret de test assez long pour fernet")
    db = Database(tmp_path / "t.db")
    await db.connect()
    bot = SimpleNamespace(db=db, user=None, guilds=[], version="t", latency=0.0, application_id=1, cogs={})
    dash = Dashboard(bot)
    guild = SimpleNamespace(id=7, name="Serveur", member_count=3)
    access = {"full": True}

    async def fake_require(request, need=None):
        if need == "full" and not access["full"]:
            raise HTTPError(403, "réservé aux admins")
        return {"user_id": 99, "username": "admin"}, guild
    monkeypatch.setattr(dash, "_require_guild", fake_require)

    async def fake_list(provider, key, http):
        if key != KEY:
            raise ProviderError("Clé refusée par Gemini (Google)", "auth")
        return ["gemini-flash", "gemini-pro"]
    monkeypatch.setattr(web_server, "list_models", fake_list)
    c = TestClient(TestServer(dash.make_app()))
    await c.start_server()
    dash._http = c.session
    yield c, db, access
    await c.close()
    await db.close()


async def test_models_save_delete(client):
    c, db, access = client
    url = "/api/guilds/7/ai-key"
    r = await c.post(url + "/models", json={"provider": "gemini", "key": "mauvaise"}, headers=HEADERS)
    assert r.status == 400 and "refusée" in (await r.json())["error"]
    r = await c.post(url + "/models", json={"provider": "gemini", "key": KEY}, headers=HEADERS)
    assert (await r.json())["models"] == ["gemini-flash", "gemini-pro"]

    r = await c.put(url, json={"provider": "gemini", "key": KEY, "model": "inconnu"}, headers=HEADERS)
    assert r.status == 400
    r = await c.put(url, json={"provider": "gemini", "key": KEY, "model": "gemini-flash"}, headers=HEADERS)
    text = await r.text()
    assert r.status == 200 and KEY not in text and (await r.json())["ai_key"]["key_hint"] == "AIz…abcd"
    # changer seulement le modèle : la clé enregistrée est réutilisée
    r = await c.put(url, json={"provider": "gemini", "key": "", "model": "gemini-pro"}, headers=HEADERS)
    assert r.status == 200 and (await ai_keys.load(db, 7)).model == "gemini-pro"
    # autre fournisseur sans clé : refusé
    r = await c.post(url + "/models", json={"provider": "openai", "key": ""}, headers=HEADERS)
    assert r.status == 400

    access["full"] = False  # rôle avec accès partiel au panel
    assert (await c.put(url, json={"provider": "gemini", "key": KEY, "model": "gemini-flash"}, headers=HEADERS)).status == 403
    assert (await c.delete(url, headers=HEADERS)).status == 403
    access["full"] = True
    assert (await c.put(url, json={"provider": "gemini", "key": KEY, "model": "gemini-flash"})).status == 403  # anti-CSRF
    assert (await c.delete(url, headers=HEADERS)).status == 200
    assert await ai_keys.load(db, 7) is None
    audit = await db.fetchall("SELECT action, details FROM panel_audit WHERE guild_id=7")
    assert [a["action"] for a in audit] == ["ai_key", "ai_key", "ai_key_delete"]
    assert all(KEY not in (a["details"] or "") for a in audit)
