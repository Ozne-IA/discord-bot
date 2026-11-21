"""v14.10 : /contact et e-mail du créateur du bot."""
from types import SimpleNamespace

from bot import contact
from cogs import contact as contact_cog


def test_contact_email(monkeypatch):
    monkeypatch.delenv("CONTACT_EMAIL", raising=False)
    monkeypatch.delenv("CONTACT", raising=False)
    assert contact.contact_email() == contact.DEFAULT_EMAIL
    assert contact.public_contact() == contact.DEFAULT_EMAIL
    monkeypatch.setenv("CONTACT", "https://discord.gg/abc")
    assert contact.contact_email() == contact.DEFAULT_EMAIL     # un lien n'est pas un e-mail
    assert contact.public_contact() == "https://discord.gg/abc"
    monkeypatch.setenv("CONTACT_EMAIL", "moi@exemple.fr")
    assert contact.contact_email() == "moi@exemple.fr"


def test_cooldown_and_report():
    cd = contact.Cooldown(600)
    assert cd.remaining(1, now=1000) == 0
    cd.hit(1, now=1000)
    assert cd.remaining(1, now=1300) == 300 and cd.remaining(2, now=1300) == 0
    title, text = contact.format_report("bug", " Tickets ", "x" * 5000, "alex", 5, "Mon serveur", 9)
    assert title == "🐛 Contact · Un module ne marche pas"
    assert "`5`" in text and "**Mon serveur** (`9`)" in text and "Tickets" in text and len(text) < 3300
    assert "message privé" in contact.format_report("weird", "s", "m", "a", 1, None, None)[1]


async def test_contact_view_only_has_valid_buttons():
    """Discord refuse les boutons lien qui ne sont pas http(s) (ex. mailto:) : /contact renvoyait une erreur."""
    view = contact_cog.ContactView(contact_cog.Contact(SimpleNamespace(get_cog=lambda name: None)))
    assert len(view.children) == len(contact.KINDS)
    for item in view.children:
        url = getattr(item, "url", None)
        assert url is None or url.startswith(("https://", "http://")), url


class FakeResponse:
    def __init__(self):
        self.sent = []

    async def send_message(self, *args, **kwargs):
        self.sent.append(kwargs)


async def test_send_report_goes_to_owner():
    notes = []

    async def notify(title, text, **kw):
        notes.append((title, kw))
        return True

    bot = SimpleNamespace(get_cog=lambda name: SimpleNamespace(notify=notify) if name == "Ops" else None)
    cog = contact_cog.Contact(bot)
    inter = SimpleNamespace(user=SimpleNamespace(id=7, __str__=lambda self: "alex"), guild=None,
                            response=FakeResponse())
    await cog.send_report(inter, "idea", "Sujet", "Un long message d'idée")
    assert notes and notes[0][1]["force"] is True
    assert cog.cooldown.remaining(7) > 0
    await cog.send_report(inter, "idea", "Sujet", "encore")      # trop tôt : refusé
    assert len(notes) == 1 and len(inter.response.sent) == 2
