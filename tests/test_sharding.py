"""v14.9 : préparation au sharding (au-delà de 2 500 serveurs)."""
from types import SimpleNamespace

import discord

from bot import sharding


class FakeShard:
    def __init__(self, latency, closed=False):
        self.latency, self._closed = latency, closed

    def is_closed(self):
        return self._closed


def test_shard_count_from_env(monkeypatch):
    monkeypatch.delenv("SHARD_COUNT", raising=False)
    assert sharding.shard_count_from_env() is None
    for raw, expected in (("auto", None), ("0", None), ("abc", None), ("4", 4), (" 2 ", 2), ("5000", None)):
        monkeypatch.setenv("SHARD_COUNT", raw)
        assert sharding.shard_count_from_env() == expected, raw


def test_shard_summary_and_crowded():
    guilds = [SimpleNamespace(shard_id=0)] * 3 + [SimpleNamespace(shard_id=1)] * 2100
    bot = SimpleNamespace(guilds=guilds, shards={1: FakeShard(float("nan"), closed=True), 0: FakeShard(0.042)})
    summary = sharding.shard_summary(bot)
    assert summary == [{"id": 0, "online": True, "latency_ms": 42, "guilds": 3},
                       {"id": 1, "online": False, "latency_ms": None, "guilds": 2100}]
    assert [s["id"] for s in sharding.crowded_shards(summary)] == [1]
    # pas encore connecté : pas de shards, mais les serveurs sont comptés
    assert sharding.shard_summary(SimpleNamespace(guilds=[SimpleNamespace()])) == [
        {"id": 0, "online": False, "latency_ms": None, "guilds": 1}]


def test_outage_tracker():
    t = sharding.OutageTracker(after=300)
    t.disconnected(2, now=1000)
    t.disconnected(2, now=1100)          # garde l'heure de la première coupure
    assert t.due(now=1200) == []          # coupure courte : pas d'alerte
    assert t.connected(2) is None         # revenu sans alerte : pas de message « reconnecté »
    t.disconnected(3, now=0)
    assert t.due(now=301) == [3]
    assert t.due(now=900) == []           # une seule alerte par coupure
    assert t.connected(3) is not None     # alerte partie → message de retour


def test_bot_is_autosharded(monkeypatch):
    import main
    monkeypatch.setenv("SHARD_COUNT", "2")
    assert issubclass(main.AllInOneBot, discord.AutoShardedClient)
    bot = main.AllInOneBot()
    assert bot.shard_count == 2
