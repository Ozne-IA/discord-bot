"""💎 Alertes (Premium) : lives Twitch / Kick / TikTok, vidéos YouTube / TikTok, articles RSS.

- YouTube : flux RSS public, aucune clé nécessaire. Accepte un ID de chaîne (UC…), un lien ou un @pseudo.
- Twitch  : API officielle, nécessite TWITCH_CLIENT_ID et TWITCH_CLIENT_SECRET (gratuits, dev.twitch.tv).
- Kick    : API publique du site, aucune clé.
- TikTok  : pas d'API officielle → pages publiques (live : chaque vérification ; vidéos : toutes les 15 min,
            détectées par le nombre de vidéos du profil). Peut cesser de marcher si TikTok change son site.
- RSS     : n'importe quel flux RSS / Atom public (sites d'actu, blogs, Reddit, etc.).
Réglages par serveur dans le panel (onglet Alertes).
"""
from __future__ import annotations

import logging
import os
import re
import time
import xml.etree.ElementTree as ET

import aiohttp
import discord
from discord.ext import commands, tasks
from yarl import URL

from bot import embeds
from bot.config import gconf

log = logging.getLogger("cogs.alerts")

YT_ID_RE = re.compile(r"(UC[\w-]{22})")
YT_NS = {"a": "http://www.w3.org/2005/Atom", "yt": "http://www.youtube.com/xml/schemas/2015",
         "media": "http://search.yahoo.com/mrss/"}
DEFAULT_YT = "📺 Nouvelle vidéo de **{name}** : {title}\n{url}"
DEFAULT_TWITCH = "🔴 **{name}** est en live : {title}\n{url}"
TWITCH_LOGIN_RE = re.compile(r"^[A-Za-z0-9_]{3,25}$")
UA = {"User-Agent": "Mozilla/5.0 (compatible; DiscordBot-Alerts/1.0)"}
BROWSER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/130.0 Safari/537.36",
    "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8",
}


def fill(template: str, **values: str) -> str:
    return re.sub(r"\{(\w+)\}", lambda m: str(values.get(m.group(1), m.group(0))), template)


def parse_youtube_feed(xml_text: str) -> list[dict]:
    """Renvoie les vidéos du flux, de la plus récente à la plus ancienne."""
    root = ET.fromstring(xml_text)
    author = root.findtext("a:author/a:name", default="", namespaces=YT_NS) or root.findtext(
        "a:title", default="", namespaces=YT_NS)
    videos = []
    for entry in root.findall("a:entry", YT_NS):
        vid = entry.findtext("yt:videoId", default="", namespaces=YT_NS)
        link = entry.find("a:link", YT_NS)
        videos.append({
            "id": vid,
            "title": entry.findtext("a:title", default="", namespaces=YT_NS),
            "url": link.get("href") if link is not None else f"https://www.youtube.com/watch?v={vid}",
            "author": entry.findtext("a:author/a:name", default=author, namespaces=YT_NS),
        })
    return videos


def twitch_login(raw: str) -> str | None:
    login = raw.strip().rstrip("/").split("/")[-1].lstrip("@").lower()
    return login if TWITCH_LOGIN_RE.match(login) else None


KICK_RE = re.compile(r"^[a-z0-9_-]{2,25}$")
TIKTOK_RE = re.compile(r"^[a-z0-9_.]{2,24}$")


def clean_handle(raw: str, pattern: re.Pattern) -> str | None:
    """« https://kick.com/Pseudo », « @pseudo », « pseudo » → « pseudo »."""
    text = raw.strip().split("?")[0].rstrip("/")
    text = text.split("/")[-1] if "/" in text else text
    text = text.lstrip("@").lower()
    if text == "live":  # tiktok.com/@pseudo/live
        parts = raw.strip().split("?")[0].rstrip("/").split("/")
        text = parts[-2].lstrip("@").lower() if len(parts) > 1 else ""
    return text if pattern.match(text) else None


def parse_feed(xml_text: str) -> tuple[str, list[dict]]:
    """Flux RSS 2.0 ou Atom → (titre du flux, articles du plus récent au plus ancien)."""
    root = ET.fromstring(xml_text)
    atom = "{http://www.w3.org/2005/Atom}"
    items: list[dict] = []
    if root.tag == f"{atom}feed":
        title = root.findtext(f"{atom}title", default="") or ""
        for entry in root.findall(f"{atom}entry"):
            link_el = entry.find(f"{atom}link[@rel='alternate']")
            if link_el is None:  # (un élément XML sans enfant vaut « faux » : on teste None explicitement)
                link_el = entry.find(f"{atom}link")
            link = link_el.get("href", "") if link_el is not None else ""
            items.append({"id": entry.findtext(f"{atom}id", default="") or link,
                          "title": (entry.findtext(f"{atom}title", default="") or "").strip(), "url": link})
    else:
        channel = root.find("channel")
        if channel is None:
            raise ET.ParseError("pas un flux RSS")
        title = channel.findtext("title", default="") or ""
        for item in channel.findall("item"):
            link = (item.findtext("link", default="") or "").strip()
            items.append({"id": (item.findtext("guid", default="") or link).strip(),
                          "title": (item.findtext("title", default="") or "").strip(), "url": link})
    return title.strip(), [i for i in items if i["id"]]


async def is_public_url(url: str) -> bool:
    """Refuse les adresses internes (protection : un admin ne doit pas pouvoir faire lire le réseau local au bot)."""
    import asyncio
    import ipaddress
    import socket
    from urllib.parse import urlparse
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        return False
    try:
        infos = await asyncio.get_running_loop().getaddrinfo(parsed.hostname, parsed.port or 443,
                                                             type=socket.SOCK_STREAM)
    except OSError:
        return False
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast \
                or ip.is_unspecified:
            return False
    return bool(infos)


DEFAULT_KICK = "🟢 **{name}** est en live sur Kick : {title}\n{url}"
DEFAULT_TIKTOK_LIVE = "🎵 **{name}** est en live sur TikTok : {title}\n{url}"
DEFAULT_TIKTOK_VIDEO = "🎵 Nouvelle vidéo TikTok de **{name}** !\n{url}"
DEFAULT_RSS = "📰 **{title}**\n{url}"


class Alerts(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.http: aiohttp.ClientSession | None = None
        self.twitch_token: str | None = None
        self.twitch_token_expires = 0.0
        self.twitch_id = os.getenv("TWITCH_CLIENT_ID", "").strip()
        self.twitch_secret = os.getenv("TWITCH_CLIENT_SECRET", "").strip()

    @property
    def db(self):
        return self.bot.db  # type: ignore[attr-defined]

    async def cog_load(self) -> None:
        self.http = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=20), headers=UA)
        if not (self.twitch_id and self.twitch_secret):
            log.info("Alertes Twitch désactivées (TWITCH_CLIENT_ID / TWITCH_CLIENT_SECRET absents)")
        self.check.start()

    async def cog_unload(self) -> None:
        self.check.cancel()
        if self.http:
            await self.http.close()

    # --- état ----------------------------------------------------------
    async def _state(self, guild_id: int, kind: str, source: str) -> dict | None:
        row = await self.db.fetchone("SELECT * FROM alert_state WHERE guild_id=? AND kind=? AND source=?",
                                     (guild_id, kind, source))
        return dict(row) if row else None

    async def _save_state(self, guild_id: int, kind: str, source: str, last_id: str | None,
                          resolved: str | None) -> None:
        await self.db.execute(
            "INSERT INTO alert_state (guild_id, kind, source, last_id, resolved) VALUES (?,?,?,?,?) "
            "ON CONFLICT(guild_id, kind, source) DO UPDATE SET last_id=excluded.last_id, resolved=excluded.resolved",
            (guild_id, kind, source, last_id, resolved))

    async def _post(self, guild: discord.Guild, channel_id: int, content: str, embed: discord.Embed) -> None:
        channel = guild.get_channel(channel_id)
        if not isinstance(channel, (discord.TextChannel, discord.Thread)):
            return
        try:
            await channel.send(content=content, embed=embed,
                               allowed_mentions=discord.AllowedMentions(everyone=True, roles=True, users=True))
        except discord.HTTPException as exc:
            log.warning("Alerte impossible dans #%s (%s) : %s", channel, guild.id, exc)

    # --- YouTube -------------------------------------------------------
    async def resolve_youtube(self, source: str) -> str | None:
        found = YT_ID_RE.search(source)
        if found:
            return found.group(1)
        handle = source.strip()
        if "youtube.com/" in handle:
            url = handle if handle.startswith("http") else "https://" + handle
        else:
            url = "https://www.youtube.com/@" + handle.lstrip("@")
        assert self.http
        try:
            # Le cookie SOCS évite la page de consentement imposée en Europe
            async with self.http.get(url, headers=BROWSER_HEADERS, cookies={"SOCS": "CAI"}) as resp:
                if resp.status != 200 or "consent." in str(resp.url):
                    return None
                page = await resp.text()
        except (aiohttp.ClientError, TimeoutError):
            return None
        # L'adresse « canonique » est la plus fiable (les autres liens peuvent viser d'autres chaînes)
        for pattern in (r'<link rel="canonical" href="https://www\.youtube\.com/channel/(UC[\w-]{22})"',
                        r'"externalId":"(UC[\w-]{22})"', r'"channelId":"(UC[\w-]{22})"'):
            m = re.search(pattern, page)
            if m:
                return m.group(1)
        return None

    async def check_youtube(self, guild: discord.Guild, item: dict) -> None:
        source = item["source"]
        state = await self._state(guild.id, "youtube", source)
        channel_id = state["resolved"] if state and state["resolved"] else await self.resolve_youtube(source)
        if not channel_id:
            return
        assert self.http
        try:
            async with self.http.get("https://www.youtube.com/feeds/videos.xml",
                                     params={"channel_id": channel_id}) as resp:
                if resp.status != 200:
                    return
                videos = parse_youtube_feed(await resp.text())
        except (aiohttp.ClientError, TimeoutError, ET.ParseError):
            return
        if not videos:
            return
        latest = videos[0]["id"]
        if state is None or not state["last_id"]:
            # Première vérification : on mémorise sans annoncer (évite de reposter d'anciennes vidéos)
            await self._save_state(guild.id, "youtube", source, latest, channel_id)
            return
        new = []
        for v in videos:
            if v["id"] == state["last_id"]:
                break
            new.append(v)
        else:
            new = new[:1]  # dernière vidéo connue introuvable : on n'annonce que la plus récente
        for v in reversed(new[:3]):
            content = fill(item.get("message") or DEFAULT_YT, name=v["author"], title=v["title"], url=v["url"])
            embed = embeds.base(v["title"][:256], None, color=0xFF0000, guild=guild)
            embed.url = v["url"]
            embed.set_author(name=v["author"])
            embed.set_image(url=f"https://i.ytimg.com/vi/{v['id']}/hqdefault.jpg")
            await self._post(guild, int(item["channel"]), content, embed)
        await self._save_state(guild.id, "youtube", source, latest, channel_id)

    # --- Twitch --------------------------------------------------------
    async def _twitch_headers(self) -> dict | None:
        if not (self.twitch_id and self.twitch_secret):
            return None
        if not self.twitch_token or time.time() > self.twitch_token_expires - 300:
            assert self.http
            async with self.http.post("https://id.twitch.tv/oauth2/token", params={
                    "client_id": self.twitch_id, "client_secret": self.twitch_secret,
                    "grant_type": "client_credentials"}) as resp:
                if resp.status != 200:
                    log.warning("Jeton Twitch refusé (%s) : vérifie TWITCH_CLIENT_ID / SECRET", resp.status)
                    return None
                data = await resp.json()
            self.twitch_token = data["access_token"]
            self.twitch_token_expires = time.time() + int(data.get("expires_in", 3600))
        return {"Client-ID": self.twitch_id, "Authorization": f"Bearer {self.twitch_token}"}

    async def fetch_twitch_streams(self, logins: list[str]) -> dict[str, dict]:
        headers = await self._twitch_headers()
        if not headers or not logins:
            return {}
        assert self.http
        live: dict[str, dict] = {}
        for i in range(0, len(logins), 100):
            params = [("user_login", login) for login in logins[i:i + 100]]
            try:
                async with self.http.get("https://api.twitch.tv/helix/streams", params=params, headers=headers) as resp:
                    if resp.status == 401:
                        self.twitch_token = None
                        return live
                    if resp.status != 200:
                        continue
                    data = await resp.json()
            except (aiohttp.ClientError, TimeoutError):
                continue
            for stream in data.get("data", []):
                live[stream["user_login"].lower()] = stream
        return live

    async def check_twitch(self, items: list[tuple[discord.Guild, dict]]) -> None:
        logins = sorted({login for _, item in items if (login := twitch_login(item["login"]))})
        live = await self.fetch_twitch_streams(logins)
        for guild, item in items:
            login = twitch_login(item["login"])
            if not login:
                continue
            state = await self._state(guild.id, "twitch", login)
            stream = live.get(login)
            if not stream:
                continue
            if state and state["last_id"] == stream["id"]:
                continue  # déjà annoncé
            await self._save_state(guild.id, "twitch", login, stream["id"], None)
            url = f"https://twitch.tv/{login}"
            content = fill(item.get("message") or DEFAULT_TWITCH, name=stream["user_name"], title=stream["title"],
                           url=url, game=stream.get("game_name", ""))
            embed = embeds.base(stream["title"][:256] or "En live", None, color=0x9146FF, guild=guild)
            embed.url = url
            embed.set_author(name=f"{stream['user_name']} est en live")
            if stream.get("game_name"):
                embed.add_field(name="Jeu", value=stream["game_name"])
            embed.add_field(name="Spectateurs", value=str(stream.get("viewer_count", 0)))
            thumb = stream.get("thumbnail_url", "").replace("{width}", "1280").replace("{height}", "720")
            if thumb:
                embed.set_image(url=f"{thumb}?t={int(time.time())}")
            await self._post(guild, int(item["channel"]), content, embed)

    # --- Kick ------------------------------------------------------------
    async def fetch_kick(self, slug: str, cache: dict) -> dict | None:
        """Live en cours sur Kick (None si hors ligne ou indisponible). API publique du site."""
        key = ("kick", slug)
        if key not in cache:
            cache[key] = None
            assert self.http
            try:
                async with self.http.get(f"https://kick.com/api/v2/channels/{slug}", headers=BROWSER_HEADERS) as resp:
                    if resp.status == 200:
                        data = await resp.json(content_type=None)
                        live = data.get("livestream")
                        if live:
                            cache[key] = {"id": str(live.get("id")), "title": live.get("session_title") or "",
                                          "viewers": live.get("viewer_count", 0),
                                          "name": (data.get("user") or {}).get("username") or slug,
                                          "thumbnail": (live.get("thumbnail") or {}).get("url"),
                                          "game": ((live.get("categories") or [{}])[0] or {}).get("name", "")}
            except (aiohttp.ClientError, TimeoutError, ValueError):
                pass
        return cache[key]

    async def check_kick(self, guild: discord.Guild, item: dict, cache: dict) -> None:
        slug = clean_handle(item.get("login", ""), KICK_RE)
        if not slug:
            return
        stream = await self.fetch_kick(slug, cache)
        state = await self._state(guild.id, "kick", slug)
        if not stream or (state and state["last_id"] == stream["id"]):
            return
        await self._save_state(guild.id, "kick", slug, stream["id"], None)
        url = f"https://kick.com/{slug}"
        content = fill(item.get("message") or DEFAULT_KICK, name=stream["name"], title=stream["title"], url=url,
                       game=stream["game"])
        embed = embeds.base(stream["title"][:256] or "En live", None, color=0x53FC18, guild=guild)
        embed.url = url
        embed.set_author(name=f"{stream['name']} est en live sur Kick")
        if stream["game"]:
            embed.add_field(name="Catégorie", value=stream["game"])
        embed.add_field(name="Spectateurs", value=str(stream["viewers"]))
        if stream["thumbnail"]:
            embed.set_image(url=stream["thumbnail"])
        await self._post(guild, int(item["channel"]), content, embed)

    # --- TikTok (pas d'API officielle : pages publiques, peut cesser de fonctionner) ---------------
    async def fetch_tiktok_live(self, user: str, cache: dict) -> dict | None:
        key = ("tiktok_live", user)
        if key not in cache:
            cache[key] = None
            assert self.http
            try:
                async with self.http.get("https://www.tiktok.com/api-live/user/room/", headers=BROWSER_HEADERS,
                                         params={"aid": "1988", "uniqueId": user, "sourceType": "54"}) as resp:
                    if resp.status == 200:
                        data = (await resp.json(content_type=None)).get("data") or {}
                        room = data.get("liveRoom") or {}
                        if room.get("status") == 2:  # 2 = en direct
                            cache[key] = {"id": str((data.get("user") or {}).get("roomId") or room.get("startTime")),
                                          "title": room.get("title") or "",
                                          "name": (data.get("user") or {}).get("nickname") or user,
                                          "cover": room.get("coverUrl"),
                                          "viewers": (room.get("liveRoomStats") or {}).get("userCount", 0)}
            except (aiohttp.ClientError, TimeoutError, ValueError):
                pass
        return cache[key]

    async def fetch_tiktok_videos(self, user: str, cache: dict) -> tuple[int, str] | None:
        """(nombre de vidéos, nom affiché) lu sur la page publique du profil."""
        key = ("tiktok_videos", user)
        if key not in cache:
            cache[key] = None
            assert self.http
            try:
                async with self.http.get(f"https://www.tiktok.com/@{user}", headers=BROWSER_HEADERS) as resp:
                    if resp.status == 200:
                        page = await resp.text()
                        count = re.search(r'"videoCount":"?(\d+)', page)
                        nick = re.search(r'"nickname":"([^"]{1,60})"', page)
                        if count:
                            cache[key] = (int(count.group(1)), nick.group(1) if nick else user)
            except (aiohttp.ClientError, TimeoutError):
                pass
        return cache[key]

    async def check_tiktok(self, guild: discord.Guild, item: dict, cache: dict, videos: bool) -> None:
        user = clean_handle(item.get("login", ""), TIKTOK_RE)
        if not user:
            return
        url = f"https://www.tiktok.com/@{user}"
        live = await self.fetch_tiktok_live(user, cache)
        state = await self._state(guild.id, "tiktok", user)
        if live and not (state and state["last_id"] == live["id"]):
            await self._save_state(guild.id, "tiktok", user, live["id"], state["resolved"] if state else None)
            content = fill(item.get("message") or DEFAULT_TIKTOK_LIVE, name=live["name"], title=live["title"],
                           url=url + "/live")
            embed = embeds.base(live["title"][:256] or "En live", None, color=0xFE2C55, guild=guild)
            embed.url = url + "/live"
            embed.set_author(name=f"{live['name']} est en live sur TikTok")
            if live["cover"]:
                embed.set_image(url=live["cover"])
            await self._post(guild, int(item["channel"]), content, embed)
            state = await self._state(guild.id, "tiktok", user)
        if not videos:
            return
        info = await self.fetch_tiktok_videos(user, cache)
        if not info:
            return
        count, name = info
        known = int(state["resolved"]) if state and str(state["resolved"] or "").isdigit() else None
        await self._save_state(guild.id, "tiktok", user, state["last_id"] if state else None, str(count))
        if known is not None and count > known:
            content = fill(DEFAULT_TIKTOK_VIDEO, name=name, title="", url=url)
            embed = embeds.base(f"Nouvelle vidéo de {name}", f"[Voir le profil TikTok]({url})", color=0xFE2C55, guild=guild)
            embed.url = url
            await self._post(guild, int(item["channel"]), content, embed)

    # --- RSS -------------------------------------------------------------
    async def fetch_feed(self, url: str, cache: dict) -> tuple[str, list[dict]] | None:
        key = ("rss", url)
        if key not in cache:
            cache[key] = None
            assert self.http
            target = url
            try:
                for _ in range(4):  # redirections suivies à la main pour revérifier chaque adresse
                    if not await is_public_url(target):
                        return None
                    async with self.http.get(target, headers=BROWSER_HEADERS, allow_redirects=False) as resp:
                        if resp.status in (301, 302, 303, 307, 308) and resp.headers.get("Location"):
                            target = str(resp.url.join(URL(resp.headers["Location"])))
                            continue
                        if resp.status != 200:
                            return None
                        raw = await resp.content.read(2 * 1024 * 1024)  # 2 Mo max
                        cache[key] = parse_feed(raw.decode("utf-8", errors="replace"))
                        break
            except (aiohttp.ClientError, TimeoutError, ET.ParseError, ValueError):
                return None
        return cache[key]

    async def check_rss(self, guild: discord.Guild, item: dict, cache: dict) -> None:
        url = str(item.get("url") or "").strip()
        if not url.startswith(("http://", "https://")):
            return
        feed = await self.fetch_feed(url, cache)
        if not feed or not feed[1]:
            return
        name, entries = feed
        state = await self._state(guild.id, "rss", url[:300])
        latest = entries[0]["id"][:300]
        if state is None or not state["last_id"]:
            await self._save_state(guild.id, "rss", url[:300], latest, None)  # 1re lecture : rien n'est annoncé
            return
        new = []
        for e in entries:
            if e["id"][:300] == state["last_id"]:
                break
            new.append(e)
        else:
            new = new[:1]
        for e in reversed(new[:3]):
            content = fill(item.get("message") or DEFAULT_RSS, name=name, title=e["title"], url=e["url"])
            embed = embeds.base(e["title"][:256] or name or "Nouvel article", None, guild=guild)
            if e["url"].startswith("http"):
                embed.url = e["url"]
            if name:
                embed.set_author(name=name[:256])
            await self._post(guild, int(item["channel"]), content, embed)
        await self._save_state(guild.id, "rss", url[:300], latest, None)

    # --- boucle ---------------------------------------------------------
    @tasks.loop(minutes=3)
    async def check(self) -> None:
        twitch_items: list[tuple[discord.Guild, dict]] = []
        cache: dict = {}  # une seule requête par chaîne / flux, même suivi par plusieurs serveurs
        self.rounds = getattr(self, "rounds", 0) + 1
        videos = self.rounds % 5 == 1  # vidéos TikTok : toutes les 15 minutes
        for guild in self.bot.guilds:
            cfg = gconf(guild)  # vide si le serveur n'est pas Premium
            for item in cfg.get("alerts", "youtube", default=[]) or []:
                try:
                    await self.check_youtube(guild, item)
                except Exception:
                    log.exception("Alerte YouTube %s (%s)", item.get("source"), guild.id)
            for kind, checker in (("kick", self.check_kick), ("rss", self.check_rss)):
                for item in cfg.get("alerts", kind, default=[]) or []:
                    try:
                        await checker(guild, item, cache)
                    except Exception:
                        log.exception("Alerte %s (%s)", kind, guild.id)
            for item in cfg.get("alerts", "tiktok", default=[]) or []:
                try:
                    await self.check_tiktok(guild, item, cache, videos)
                except Exception:
                    log.exception("Alerte TikTok (%s)", guild.id)
            twitch_items += [(guild, item) for item in cfg.get("alerts", "twitch", default=[]) or []]
        if twitch_items:
            try:
                await self.check_twitch(twitch_items)
            except Exception:
                log.exception("Alertes Twitch")

    @check.before_loop
    async def _before(self) -> None:
        await self.bot.wait_until_ready()


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Alerts(bot))
