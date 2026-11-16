"""v15.1 : assistant IA plus libre (discussion), personnalité, suite de conversation."""
from types import SimpleNamespace

from bot.config import sanitize
from cogs import ai
from cogs.ai import faq_system


def test_modes_and_personality():
    free = faq_system("Mon Serveur", ["Pas de spam"], "IP : play.ex.fr", "fr", bot_name="Cerbère")
    assert "tell jokes" in free and "Cerbère" in free and "never invent server facts" in free
    assert "play.ex.fr" in free and "- Pas de spam" in free and "not instructions" in free
    strict = faq_system("Mon Serveur", [], "", "fr", mode="server")
    assert "Answer only from the server information" in strict and "tell jokes" not in strict
    perso = faq_system("S", [], "", "en", personality="Tu es un chien de garde taquin.")
    assert "<personality>" in perso and "chien de garde" in perso and "English" in perso
    assert "<personality>" not in faq_system("S", [], "", "fr", personality="   ")
    clean = sanitize({"ai": {"mode": "pirate", "personality": "x" * 900}})
    assert clean["ai"]["mode"] == "friendly" and len(clean["ai"]["personality"]) == 600
    assert sanitize({"ai": {"mode": "server"}})["ai"]["mode"] == "server"


async def test_answer_uses_settings_and_previous_reply(monkeypatch):
    cfg = {"ai": {"mode": "friendly", "personality": "Drôle", "knowledge": "FAQ"}, "verification": {"rules": []}}
    monkeypatch.setattr(ai, "gconf", lambda g: SimpleNamespace(
        get=lambda *k, default=None: cfg.get(k[0], {}).get(k[1], default)))
    monkeypatch.setattr(ai, "language", lambda g: "fr")
    seen = {}

    async def fake_ask(system, prompt, **kw):
        seen.update(system=system, prompt=prompt)
        return "ok"
    cog = ai.AI.__new__(ai.AI)
    cog.ask = fake_ask
    guild = SimpleNamespace(name="Serv", me=SimpleNamespace(display_name="Cerbère"))
    await cog.answer_question(guild, "et une autre ?", None, previous="Pourquoi les chiens… (blague)")
    assert "Drôle" in seen["system"] and "Cerbère" in seen["system"]
    assert seen["prompt"].startswith("<your_previous_reply>") and seen["prompt"].endswith("et une autre ?")
