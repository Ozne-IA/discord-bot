"""v14.8 : réponses enregistrées, relance des tickets sans prise en charge, avertissement avant fermeture."""
from types import SimpleNamespace

from bot.config import sanitize
from bot.db import Database
from cogs import tickets

H = 3600


def test_ticket_due():
    now = 1_000_000
    t = {"opened_at": now - 40 * 60, "last_activity": now - 10, "claimed_by": None, "alerted": 0, "warned": 0}
    assert tickets.ticket_due(t, 30, 72, True, now) == "alert"                 # 40 min sans prise en charge
    assert tickets.ticket_due({**t, "alerted": 1}, 30, 72, True, now) is None    # relancé une seule fois
    assert tickets.ticket_due({**t, "claimed_by": 5}, 30, 72, True, now) is None
    assert tickets.ticket_due(t, 0, 72, True, now) is None                       # relance désactivée
    # 72 h : avertissement 12 h avant (à 60 h), fermeture à 72 h
    idle59 = {**t, "alerted": 1, "last_activity": now - 59 * H}
    assert tickets.ticket_due(idle59, 30, 72, True, now) is None
    assert tickets.ticket_due({**idle59, "last_activity": now - 61 * H}, 30, 72, True, now) == "warn"
    assert tickets.ticket_due({**idle59, "last_activity": now - 61 * H, "warned": 1}, 30, 72, True, now) is None
    assert tickets.ticket_due({**idle59, "last_activity": now - 61 * H}, 30, 72, False, now) is None
    assert tickets.ticket_due({**idle59, "last_activity": now - 73 * H, "warned": 1}, 30, 72, True, now) == "close"
    # 4 h : avertissement à 3 h (un quart avant)
    assert tickets.ticket_due({**idle59, "last_activity": now - 3 * H - 60}, 30, 4, True, now) == "warn"
    assert tickets.ticket_due({**idle59, "last_activity": now - 73 * H}, 30, 0, True, now) is None  # jamais


def test_saved_replies(monkeypatch):
    replies = [{"name": f"r{i}", "content": "x"} for i in range(8)]
    monkeypatch.setattr(tickets, "gconf", lambda g: SimpleNamespace(
        get=lambda *k, default=None: replies if k == ("tickets", "saved_replies") else default))
    monkeypatch.setattr(tickets, "is_premium", lambda g: False)
    assert len(tickets.saved_replies(1)) == 5
    monkeypatch.setattr(tickets, "is_premium", lambda g: True)
    assert len(tickets.saved_replies(1)) == 8
    assert tickets.fill_reply("Salut {user}, je suis {staff} (#{number})", "<@1>", "Alex", 12) == \
        "Salut <@1>, je suis Alex (#12)"
    clean = sanitize({"tickets": {"saved_replies": [{"name": "a" * 200, "content": "b" * 3000}, {"name": "", "content": "c"}]}})
    assert clean["tickets"]["saved_replies"] == [{"name": "a" * 80, "content": "b" * 1800}]


async def test_new_columns_and_reset_on_message(tmp_path):
    db = Database(tmp_path / "t.db")
    await db.connect()
    await db.execute("INSERT INTO tickets (channel_id, guild_id, user_id, number, type, subject, opened_at, last_activity, "
                     "warned) VALUES (5, 1, 2, 1, 'support', 's', 0, 0, 1)")
    cog = tickets.Tickets.__new__(tickets.Tickets)
    cog.bot, cog.open_channels = SimpleNamespace(db=db), {5}
    msg = SimpleNamespace(channel=SimpleNamespace(id=5), author=SimpleNamespace(bot=False))
    await cog.on_message(msg)
    row = await db.fetchone("SELECT warned, alerted, last_activity FROM tickets WHERE channel_id=5")
    assert row["warned"] == 0 and row["alerted"] == 0 and row["last_activity"] > 0
    await db.close()
