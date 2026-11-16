"""v14.4 : chaque serveur branche sa propre IA (clé chiffrée)."""
from types import SimpleNamespace

import pytest
from cryptography.fernet import Fernet

from bot import ai_keys, ai_providers, secrets_box
from bot.ai_providers import ProviderError
from bot.db import Database
from cogs import ai as ai_cog

SECRET_KEY = "sk-proj-ABCDEFGHIJKLMNOP1234"


@pytest.fixture
def secret(monkeypatch):
    monkeypatch.setenv("AI_KEYS_SECRET", "une phrase secrète assez longue pour les tests")


# --- chiffrement -------------------------------------------------------------
def test_encrypt_roundtrip_and_hint(secret, monkeypatch):
    token = secrets_box.encrypt(SECRET_KEY)
    assert SECRET_KEY not in token and secrets_box.decrypt(token) == SECRET_KEY
    assert secrets_box.hint(SECRET_KEY) == "sk-…1234"
    # une vraie clé Fernet est aussi acceptée
    monkeypatch.setenv("AI_KEYS_SECRET", Fernet.generate_key().decode())
    assert secrets_box.decrypt(secrets_box.encrypt("x")) == "x"
    # secret changé : la clé devient illisible (message clair, sans planter)
    monkeypatch.setenv("AI_KEYS_SECRET", "un tout autre secret de plus de 16 caractères")
    with pytest.raises(secrets_box.SecretError):
        secrets_box.decrypt(token)
    monkeypatch.setenv("AI_KEYS_SECRET", "court")
    assert not secrets_box.available()


async def test_key_store_never_exposes_key(secret, tmp_path):
    db = Database(tmp_path / "t.db")
    await db.connect()
    info = await ai_keys.save(db, 1, "mistral", f"  {SECRET_KEY} ", "mistral-small-latest", by=9)
    assert info["provider"] == "mistral" and info["key_hint"] == "sk-…1234" and "key" not in info
    row = await db.fetchone("SELECT key_enc FROM ai_keys WHERE guild_id=1")
    assert SECRET_KEY not in row["key_enc"]
    loaded = await ai_keys.load(db, 1)
    assert (loaded.provider, loaded.model, loaded.key) == ("mistral", "mistral-small-latest", SECRET_KEY)
    await ai_keys.set_model(db, 1, "mistral-large-latest", by=9)
    assert (await ai_keys.load(db, 1)).model == "mistral-large-latest"
    with pytest.raises(ValueError):
        await ai_keys.save(db, 1, "inconnu", "k", "m", by=9)
    await ai_keys.delete(db, 1)
    assert await ai_keys.load(db, 1) is None
    await db.close()


# --- fournisseurs (réponses simulées) --------------------------------------------
@pytest.fixture
def fake_http(monkeypatch):
    calls = []
    replies = {}

    async def fake_request(http, provider, method, url, *, headers, json=None):
        calls.append({"provider": provider, "method": method, "url": url, "headers": headers, "json": json})
        reply = replies[(provider, method)]
        if isinstance(reply, Exception):
            raise reply
        return reply
    monkeypatch.setattr(ai_providers, "_request", fake_request)
    return calls, replies


async def test_openai_and_mistral(fake_http):
    calls, replies = fake_http
    replies[("openai", "GET")] = {"data": [{"id": "gpt-5-mini"}, {"id": "text-embedding-3-small"},
                                           {"id": "whisper-1"}, {"id": "o4-mini"}, {"id": "dall-e-3"}]}
    assert await ai_providers.list_models("openai", "k", None) == ["gpt-5-mini", "o4-mini"]
    replies[("openai", "POST")] = {"choices": [{"message": {"content": " Bonjour "}}]}
    assert await ai_providers.generate("openai", "k", "gpt-5-mini", "sys", "q", None) == "Bonjour"
    body = calls[-1]["json"]
    assert body["messages"][0] == {"role": "system", "content": "sys"} and "max_completion_tokens" in body
    assert calls[-1]["headers"]["Authorization"] == "Bearer k"

    replies[("mistral", "GET")] = [{"id": "mistral-small-latest", "capabilities": {"completion_chat": True}},
                                   {"id": "mistral-embed", "capabilities": {"completion_chat": False}},
                                   {"id": "old", "archived": True}]
    assert await ai_providers.list_models("mistral", "k", None) == ["mistral-small-latest"]
    replies[("mistral", "GET")] = {"data": [{"id": "open-mistral-nemo"}]}  # autre forme de réponse
    assert await ai_providers.list_models("mistral", "k", None) == ["open-mistral-nemo"]
    replies[("mistral", "POST")] = {"choices": [{"message": {"content": "Salut"}}]}
    assert await ai_providers.generate("mistral", "k", "mistral-small-latest", "s", "q", None) == "Salut"
    assert "max_tokens" in calls[-1]["json"]


async def test_gemini(fake_http):
    calls, replies = fake_http
    replies[("gemini", "GET")] = {"models": [
        {"name": "models/gemini-flash", "supportedGenerationMethods": ["generateContent", "countTokens"]},
        {"name": "models/text-embedding", "supportedGenerationMethods": ["embedContent"]}]}
    assert await ai_providers.list_models("gemini", "k", None) == ["gemini-flash"]
    replies[("gemini", "POST")] = {"candidates": [{"content": {"parts": [
        {"text": "réflexion", "thought": True}, {"text": "Réponse"}]}}]}
    assert await ai_providers.generate("gemini", "k", "gemini-flash", "s", "q", None) == "Réponse"
    call = calls[-1]
    assert call["url"].endswith("/models/gemini-flash:generateContent") and call["headers"] == {"x-goog-api-key": "k"}
    assert call["json"]["systemInstruction"]["parts"][0]["text"] == "s"
    replies[("gemini", "POST")] = {"promptFeedback": {"blockReason": "SAFETY"}}
    with pytest.raises(ProviderError):
        await ai_providers.generate("gemini", "k", "gemini-flash", "s", "q", None)


async def test_bad_model_and_errors(fake_http):
    _, replies = fake_http
    for bad in ("", "../secret", "a/b", "x" * 200):
        with pytest.raises(ProviderError):
            await ai_providers.generate("gemini", "k", bad, "s", "q", None)
    err = ai_providers._status_error("openai", 401, "Incorrect API key provided: sk-abc")
    assert err.kind == "auth" and "sk-abc" not in str(err)
    assert ai_providers._status_error("openai", 429, "insufficient_quota").kind == "quota"
    assert ai_providers._status_error("mistral", 404, "model not found").kind == "model"
    replies[("openai", "POST")] = {"choices": [{"message": {"content": ""}}]}
    with pytest.raises(ProviderError):
        await ai_providers.generate("openai", "k", "gpt-5-mini", "s", "q", None)


# --- quelle IA répond ? -------------------------------------------------------------
async def test_backend_choice(secret, tmp_path, monkeypatch):
    db = Database(tmp_path / "t.db")
    await db.connect()
    enabled = {"on": True}
    monkeypatch.setattr(ai_cog, "gconf", lambda g: SimpleNamespace(
        get=lambda *k, default=None: enabled["on"] if k == ("ai", "enabled") else default))
    premium = {"on": False}
    monkeypatch.setattr(ai_cog, "is_premium", lambda g: premium["on"])
    cog = ai_cog.AI.__new__(ai_cog.AI)
    cog.bot, cog.client, cog.http = SimpleNamespace(db=db), None, None
    guild = SimpleNamespace(id=5)

    backend, problem = await cog.backend(guild)
    assert backend is None and problem == ai_cog.NEED_KEY            # gratuit, sans clé
    premium["on"] = True
    assert (await cog.backend(guild))[0] is None                     # Premium mais IA incluse absente
    cog.client = object()
    assert (await cog.backend(guild))[0].own is None                 # Premium : IA incluse
    await ai_keys.save(db, 5, "gemini", SECRET_KEY, "gemini-flash", by=1)
    premium["on"] = False
    backend, _ = await cog.backend(guild)
    assert backend.own.provider == "gemini" and backend.own.key == SECRET_KEY  # sa clé, même en gratuit
    monkeypatch.setenv("AI_KEYS_SECRET", "secret changé entre-temps, assez long")
    backend, problem = await cog.backend(guild)
    assert backend is None and "recoller" in problem
    enabled["on"] = False
    assert "désactivé" in (await cog.backend(guild))[1]
    await db.close()


async def test_ask_uses_server_key(monkeypatch):
    seen = {}

    async def fake_generate(provider, key, model, system, prompt, http, max_tokens=2000):
        seen.update(provider=provider, key=key, model=model)
        if prompt == "boom":
            raise ProviderError("Clé refusée par Mistral", "auth")
        return "ok"
    monkeypatch.setattr(ai_cog, "generate", fake_generate)
    cog = ai_cog.AI.__new__(ai_cog.AI)
    cog.client, cog.http = None, object()
    backend = ai_cog.Backend(ai_keys.GuildAIKey("mistral", "mistral-small-latest", "cle"))
    assert await cog.ask("s", "q", backend=backend) == "ok"
    assert seen == {"provider": "mistral", "key": "cle", "model": "mistral-small-latest"}
    with pytest.raises(ai_cog.AIError):
        await cog.ask("s", "boom", backend=backend)
