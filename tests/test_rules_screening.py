"""Rôle donné quand un membre accepte l'écran de règles de Discord (membership screening)."""
from types import SimpleNamespace

import pytest

from cogs import verification

MEMBER, UNVERIFIED = SimpleNamespace(id=10, mention="@Membre"), SimpleNamespace(id=11, mention="@NonVerifie")


class FakeCfg:
    def __init__(self, discord_rules=True, captcha=False):
        self.values = {("verification", "discord_rules"): discord_rules, ("verification", "captcha"): captcha}

    def get(self, *keys, default=None):
        return self.values.get(keys, default)

    def role_id(self, name):
        return {"member": 10, "unverified": 11}[name]


class FakeMember:
    def __init__(self, pending, roles=()):
        self.pending = pending
        self.roles = list(roles)
        self.mention = "@nouveau"
        self.guild = SimpleNamespace(get_role=lambda rid: {10: MEMBER, 11: UNVERIFIED}.get(rid))
        self.added, self.removed = [], []

    async def add_roles(self, role, reason=None):
        self.added.append(role)
        self.roles.append(role)

    async def remove_roles(self, role, reason=None):
        self.removed.append(role)
        self.roles.remove(role)


@pytest.fixture
def logs(monkeypatch):
    sent = []

    async def fake_log(guild, embed, channel="logs"):
        sent.append(embed.title)
    monkeypatch.setattr(verification, "send_log", fake_log)
    return sent


async def _update(monkeypatch, cfg, before_pending=True, after_pending=False, roles=(UNVERIFIED,)):
    monkeypatch.setattr(verification, "gconf", lambda g: cfg)
    cog = verification.Verification(bot=None)
    before, after = FakeMember(before_pending), FakeMember(after_pending, roles)
    await cog.on_member_update(before, after)
    return after


async def test_role_given_when_rules_accepted(monkeypatch, logs):
    after = await _update(monkeypatch, FakeCfg())
    assert after.added == [MEMBER] and after.removed == [UNVERIFIED]
    assert logs == ["✅ Vérification"]


async def test_nothing_when_option_off_or_captcha_on(monkeypatch, logs):
    assert (await _update(monkeypatch, FakeCfg(discord_rules=False))).added == []
    assert (await _update(monkeypatch, FakeCfg(captcha=True))).added == []


async def test_nothing_on_other_member_updates(monkeypatch, logs):
    assert (await _update(monkeypatch, FakeCfg(), before_pending=False)).added == []   # pseudo changé, etc.
    assert (await _update(monkeypatch, FakeCfg(), roles=(MEMBER,))).added == []        # a déjà le rôle
