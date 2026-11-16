"""Tests v14 : pages du site (Premium, commandes, statut), image de partage, statut, test de message."""
import io
from types import SimpleNamespace

from aiohttp.test_utils import TestClient, TestServer
from PIL import Image

from bot.images import og_banner
from web import server


class FakeBot:
    user = None
    application_id = 123
    version = "14.1.0"
    latency = 0.042
    guilds = [SimpleNamespace(member_count=10), SimpleNamespace(member_count=5)]
    cogs = {"A": 1, "B": 2}

    def is_ready(self):
        return True


async def client_for(bot) -> TestClient:
    dash = server.Dashboard(bot)
    client = TestClient(TestServer(dash.make_app()))
    await client.start_server()
    return client


def test_og_banner_size():
    png = og_banner("MonBot", None, "Bot Discord tout-en-un", "3 serveurs · 104 commandes")
    img = Image.open(io.BytesIO(png))
    assert img.size == (1200, 630) and img.format == "PNG"


async def test_site_pages_and_status():
    client = await client_for(FakeBot())
    try:
        for path in ("/", "/premium", "/commands", "/status", "/dashboard", "/contact"):
            resp = await client.get(path)
            html = await resp.text()
            assert resp.status == 200, path
            assert "__ORIGIN__" not in html and "__BOT_NAME__" not in html, path
            assert "theme.js" in html, path
        contact_page = await (await client.get("/contact")).text()
        assert "__CONTACT_EMAIL__" not in contact_page and "mailto:cerbere.bot.discord@gmail.com" in contact_page
        status = await (await client.get("/api/status")).json()
        assert status["online"] and status["latency_ms"] == 42 and status["members"] == 15 and status["modules"] == 2
        assert (await (await client.get("/api/commands")).json()) == {"commands": []}
        og = await client.get("/og.png")
        assert og.status == 200 and og.content_type == "image/png"
        fav = await client.get("/favicon.png", allow_redirects=False)
        assert fav.status == 302 and fav.headers["Location"].endswith("favicon.svg")
        public = await (await client.get("/api/public")).json()
        assert public["commands"] == 0 and "store_url" in public
    finally:
        await client.close()


async def test_test_message_requires_login():
    client = await client_for(FakeBot())
    try:
        resp = await client.post("/api/guilds/1/test", json={"kind": "welcome"}, headers={"X-Requested-With": "dashboard"})
        assert resp.status == 401
        resp = await client.post("/api/guilds/1/test", json={"kind": "welcome"})
        assert resp.status == 403  # protection CSRF
    finally:
        await client.close()


def test_command_modules_cover_all_cogs():
    import pathlib
    import re
    names = set()
    for path in pathlib.Path("cogs").glob("*.py"):
        names |= set(re.findall(r"^class (\w+)\(commands\.Cog\)", path.read_text(encoding="utf-8"), re.M))
    missing = names - set(server.COMMAND_MODULES)
    assert not missing, missing
