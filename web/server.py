"""Serveur web intégré au bot (même programme, même base de données).

Pages :
  /            site de présentation du bot
  /dashboard   panel de configuration (connexion avec Discord)
API (JSON) : /api/...   — chaque appel vérifie que l'utilisateur gère bien le serveur demandé.
"""
from __future__ import annotations

import json
import logging
import os
import re
import secrets
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any
from urllib.parse import urlencode, urlparse

import aiohttp
import discord
from aiohttp import web

from bot import ai_keys, diagnostic, secrets_box
from bot.ai_providers import PROVIDERS, ProviderError, list_models, valid_model
from bot.access import apply_restricted, groups_for_roles
from bot.staff import build_staff_stats
from bot.config import DEFAULTS, LIMITS, PREMIUM_PATHS, deep_merge, gconf, limit_for, store
from bot.premium import premium, store_url, trial_days
from bot.templates import template_list
from bot.panels import PANELS, publish_panel
from web.security import RateLimiter, bucket_for, client_ip, content_security_policy

if TYPE_CHECKING:
    from main import AllInOneBot

log = logging.getLogger("web")

STATIC = Path(__file__).resolve().parent / "static"
DISCORD_API = "https://discord.com/api/v10"
SESSION_DAYS = 7
MANAGE_GUILD = 0x20
ADMINISTRATOR = 0x8
JS_MAX_INT = 2**53

# Ce que « Tout créer automatiquement » fabrique
AUTO_ROLES_BASE = {"staff": ("Staff", 0xE67E22, True), "member": ("Membre", 0x2ECC71, False),
                   "unverified": ("Non vérifié", 0x95A5A6, False)}
AUTO_NOTIFICATIONS = ["Annonces", "Événements", "Sondages", "Partenariats"]
AUTO_LEVELS = {"5": 0x3498DB, "10": 0x9B59B6, "20": 0xE91E63, "30": 0xF1C40F}
# (section, clé) -> (nom, type, visibilité)
AUTO_CHANNELS = {
    ("channels", "welcome"): ("👋・bienvenue", "text", "readonly"),
    ("panels", "verify"): ("📜・règles", "text", "readonly"),
    ("panels", "notifications"): ("🔔・rôles", "text", "readonly"),
    ("panels", "tickets"): ("📩・support", "text", "readonly"),
    ("channels", "level_up"): ("📈・niveaux", "text", "readonly"),
    ("channels", "goodbye"): ("🚪・au-revoir", "text", "readonly"),
    ("channels", "logs"): ("📋・logs", "text", "staff"),
    ("channels", "mod_logs"): ("🔨・mod-logs", "text", "staff"),
    ("channels", "ticket_logs"): ("🎫・ticket-logs", "text", "staff"),
    ("birthdays", "channel"): ("🎂・anniversaires", "text", "readonly"),
    ("suggestions", "channel"): ("💡・suggestions", "text", "readonly"),
    ("starboard", "channel"): ("⭐・starboard", "text", "readonly"),
    ("temp_voice", "creator_channel"): ("➕ Créer un salon", "voice", "public"),
    ("channels", "ticket_category"): ("📩 Tickets", "category", "staff"),
}


# Module affiché sur la page des commandes (nom de la classe du cog -> catégorie)
COMMAND_MODULES = {
    "Welcome": "Accueil", "Verification": "Vérification", "Roles": "Rôles", "Tickets": "Tickets", "Levels": "Niveaux",
    "Moderation": "Modération", "AutoMod": "Modération", "Automod": "Modération", "Security": "Sécurité",
    "Logs": "Configuration", "Admin": "Configuration", "Premium": "Premium", "Giveaways": "Giveaways & sondages",
    "Polls": "Giveaways & sondages", "Alerts": "Alertes", "Economy": "Économie", "Reminders": "Rappels & anniversaires",
    "Stats": "Statistiques", "Games": "Mini-jeux", "TempVoice": "Vocaux temporaires", "Community": "Suggestions & communauté",
    "Custom": "Commandes perso", "Modmail": "Modmail & invitations", "Invites": "Modmail & invitations",
    "Engagement": "Succès & quêtes", "Events": "Événements & tournois", "AI": "Assistant IA", "ModTools": "Modération",
    "Votes": "Économie", "Ops": "Configuration",
}
TEST_KINDS = ("welcome", "dm", "goodbye", "levelup", "birthday")


def config_diff(before: Any, after: Any, prefix: str = "") -> list[str]:
    """Liste des réglages modifiés (chemins), pour l'historique du panel."""
    if isinstance(before, dict) and isinstance(after, dict):
        out: list[str] = []
        for key in sorted(set(before) | set(after)):
            out += config_diff(before.get(key), after.get(key), f"{prefix}{key}.")
        return out
    return [prefix.rstrip(".")] if before != after else []


async def build_stats(db, guild_id: int, days: int, today: date | None = None) -> dict:
    """Séries quotidiennes pour les graphiques du panel (jours manquants = 0)."""
    today = today or datetime.now(timezone.utc).date()
    start = today - timedelta(days=days - 1)
    labels = [(start + timedelta(days=i)).isoformat() for i in range(days)]
    series = {k: dict.fromkeys(labels, 0) for k in ("joins", "leaves", "messages", "voice_minutes", "tickets", "cases")}
    members: dict[str, int | None] = dict.fromkeys(labels, None)
    for r in await db.fetchall("SELECT * FROM stats_daily WHERE guild_id=? AND day >= ?", (guild_id, labels[0])):
        if r["day"] in members:
            for k in ("joins", "leaves", "messages", "voice_minutes"):
                series[k][r["day"]] = r[k]
            members[r["day"]] = r["members"]
    since = datetime(start.year, start.month, start.day, tzinfo=timezone.utc).timestamp()
    for table, column, key in (("tickets", "opened_at", "tickets"), ("cases", "created_at", "cases")):
        rows = await db.fetchall(
            f"SELECT strftime('%Y-%m-%d', {column}, 'unixepoch') AS d, COUNT(*) AS n FROM {table} "
            f"WHERE guild_id=? AND {column} >= ? GROUP BY d", (guild_id, since))
        for r in rows:
            if r["d"] in series[key]:
                series[key][r["d"]] = r["n"]
    return {"days": days, "labels": labels,
            "series": {k: list(v.values()) for k, v in series.items()},
            "members": list(members.values()),
            "totals": {k: sum(v.values()) for k, v in series.items()}}


def stringify_ids(value: Any) -> Any:
    """Les IDs Discord sont trop grands pour JavaScript : on les envoie en texte."""
    if isinstance(value, bool):
        return value
    if isinstance(value, int) and value >= JS_MAX_INT:
        return str(value)
    if isinstance(value, dict):
        return {k: stringify_ids(v) for k, v in value.items()}
    if isinstance(value, list):
        return [stringify_ids(v) for v in value]
    return value


class HTTPError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status


class Dashboard:
    def __init__(self, bot: "AllInOneBot"):
        self.bot = bot
        self.public_url = os.getenv("PUBLIC_URL", "").rstrip("/")
        self.client_secret = os.getenv("DISCORD_CLIENT_SECRET", "").strip()
        self.port = int(os.getenv("PORT", "8080"))
        self.secure = self.public_url.startswith("https://")
        self.origin = "{0.scheme}://{0.netloc}".format(urlparse(self.public_url)) if self.public_url else ""
        self.runner: web.AppRunner | None = None
        self._http: aiohttp.ClientSession | None = None
        self.started = time.time()
        self._commands_cache: list[dict] | None = None
        self._og_cache: tuple[float, bytes] | None = None
        self._last_test: dict[int, float] = {}
        self.limiter = RateLimiter()

    @property
    def oauth_ready(self) -> bool:
        return bool(self.public_url and self.client_secret)

    @property
    def redirect_uri(self) -> str:
        return f"{self.public_url}/callback"

    @property
    def db(self):
        return self.bot.db

    # ------------------------------------------------------------------ #
    #  Démarrage
    # ------------------------------------------------------------------ #
    def make_app(self) -> web.Application:
        app = web.Application(middlewares=[self.errors_middleware, self.rate_limit_middleware], client_max_size=256 * 1024)
        r = app.router
        r.add_get("/", self.page("index.html"))
        r.add_get("/dashboard", self.page("dashboard.html"))
        r.add_get("/terms", self.page("terms.html", english="terms.en.html"))
        r.add_get("/privacy", self.page("privacy.html", english="privacy.en.html"))
        r.add_get("/premium", self.page("premium.html"))
        r.add_get("/commands", self.page("commands.html"))
        r.add_get("/status", self.page("status.html"))
        r.add_get("/og.png", self.og_image)
        r.add_get("/favicon.ico", self.favicon)
        r.add_get("/favicon.png", self.favicon)
        r.add_get("/api/commands", self.api_commands)
        r.add_get("/api/status", self.api_status)
        r.add_post("/api/guilds/{guild_id}/test", self.api_test)
        r.add_static("/static", STATIC, append_version=True)
        r.add_get("/health", self.health)
        r.add_post("/webhooks/topgg", self.topgg_webhook)
        r.add_get("/login", self.login)
        r.add_get("/callback", self.callback)
        r.add_post("/logout", self.logout)
        r.add_get("/api/public", self.api_public)
        r.add_get("/api/me", self.api_me)
        r.add_post("/api/me/refresh", self.api_refresh)
        r.add_get("/api/guilds/{guild_id}", self.api_guild)
        r.add_put("/api/guilds/{guild_id}/config", self.api_save_config)
        r.add_post("/api/guilds/{guild_id}/autocreate", self.api_autocreate)
        r.add_post("/api/guilds/{guild_id}/panels", self.api_panels)
        r.add_get("/api/guilds/{guild_id}/stats", self.api_stats)
        r.add_get("/api/guilds/{guild_id}/audit", self.api_audit)
        r.add_get("/api/guilds/{guild_id}/staffstats", self.api_staffstats)
        r.add_get("/api/guilds/{guild_id}/messagelog", self.api_messagelog)
        r.add_post("/api/guilds/{guild_id}/send", self.api_send)
        r.add_post("/api/guilds/{guild_id}/rolemenus/{menu_id}/publish", self.api_publish_menu)
        r.add_get("/api/guilds/{guild_id}/export", self.api_export)
        r.add_post("/api/guilds/{guild_id}/template", self.api_template)
        r.add_post("/api/guilds/{guild_id}/import", self.api_import)
        r.add_post("/api/guilds/{guild_id}/trial", self.api_trial)
        r.add_post("/api/guilds/{guild_id}/ai-key/models", self.api_ai_models)
        r.add_put("/api/guilds/{guild_id}/ai-key", self.api_ai_key_save)
        r.add_delete("/api/guilds/{guild_id}/ai-key", self.api_ai_key_delete)
        return app

    async def start(self) -> None:
        self._http = aiohttp.ClientSession()
        # Sessions expirées supprimées (aussi à chaque connexion) : promesse des 7 jours max de /privacy
        await self.db.execute("DELETE FROM web_sessions WHERE expires_at < ?", (time.time(),))
        self.runner = web.AppRunner(self.make_app(), access_log=None)
        await self.runner.setup()
        await web.TCPSite(self.runner, host="0.0.0.0", port=self.port).start()
        if self.oauth_ready:
            log.info("Panel web en ligne : %s (port %d)", self.public_url, self.port)
        else:
            log.warning("Panel web démarré sur le port %d, mais la connexion Discord est désactivée : "
                        "renseigne PUBLIC_URL et DISCORD_CLIENT_SECRET dans .env", self.port)

    async def stop(self) -> None:
        if self.runner:
            await self.runner.cleanup()
        if self._http:
            await self._http.close()

    # ------------------------------------------------------------------ #
    #  Utilitaires
    # ------------------------------------------------------------------ #
    @web.middleware
    async def errors_middleware(self, request: web.Request, handler):
        try:
            response = await handler(request)
        except HTTPError as exc:
            response = web.json_response({"error": str(exc)}, status=exc.status)
        except web.HTTPException:
            raise
        except discord.Forbidden:
            response = web.json_response(
                {"error": "Discord a refusé l'action : vérifie mes permissions et la position de mon rôle."}, status=400)
        except Exception:
            log.exception("Erreur dans %s %s", request.method, request.path)
            response = web.json_response({"error": "Erreur interne, elle a été enregistrée dans les logs."}, status=500)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "same-origin")
        response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        if self.secure:
            response.headers.setdefault("Strict-Transport-Security", "max-age=31536000")
        return response

    @web.middleware
    async def rate_limit_middleware(self, request: web.Request, handler):
        """Trop de requêtes depuis la même adresse : on fait patienter (protège le site et le bot)."""
        bucket = bucket_for(request.method, request.path)
        if bucket:
            wait = self.limiter.check(client_ip(request), bucket)
            if wait:
                return web.json_response({"error": f"Trop de requêtes : réessaie dans {wait} s."}, status=429,
                                         headers={"Retry-After": str(wait)})
        return await handler(request)

    def page(self, name: str, english: str | None = None):
        async def handler(request: web.Request) -> web.StreamResponse:
            # Version anglaise (pages légales) avec ?lang=en
            filename = english if english and request.query.get("lang") == "en" else name
            # Ajoute ?v=<date du fichier> aux CSS/JS : après une mise à jour, les navigateurs
            # rechargent les nouveaux fichiers au lieu de garder l'ancienne version en cache.
            html = (STATIC / filename).read_text(encoding="utf-8")

            def versioned(match: re.Match) -> str:
                path = STATIC / match.group(1)
                stamp = int(path.stat().st_mtime) if path.exists() else 0
                return f'/static/{match.group(1)}?v={stamp}"'

            html = re.sub(r'/static/([\w.-]+\.(?:css|js))"', versioned, html)
            # Balises de partage (aperçu Discord / réseaux sociaux) : remplies côté serveur
            user = self.bot.user
            html = html.replace("__ORIGIN__", self.public_url or "").replace(
                "__BOT_NAME__", (user.name if user else "Bot").replace("<", "").replace('"', ""))
            # Seuls les scripts du site et ceux écrits dans la page (marqués d'un nonce) peuvent s'exécuter
            nonce = secrets.token_urlsafe(16)
            html = html.replace("<script>", f'<script nonce="{nonce}">')
            return web.Response(text=html, content_type="text/html", headers={
                "Cache-Control": "no-cache", "Content-Security-Policy": content_security_policy(nonce)})
        return handler

    # ------------------------------------------------------------------ #
    #  Site : liste des commandes, statut, image de partage, icône
    # ------------------------------------------------------------------ #
    def command_list(self) -> list[dict]:
        if self._commands_cache is not None:
            return self._commands_cache
        tree = getattr(self.bot, "tree", None)
        out: list[dict] = []
        if tree is not None:
            from bot.i18n import COMMANDS_EN
            for cmd in tree.walk_commands():
                if not isinstance(cmd, discord.app_commands.Command):
                    continue
                cog = type(cmd.binding).__name__ if cmd.binding is not None else ""
                root = cmd.root_parent or cmd
                perms = root.default_permissions
                desc = cmd.description or ""
                owner = "premium_admin" in cmd.qualified_name or desc.startswith("[Propriétaire du bot]")
                out.append({"name": "/" + cmd.qualified_name, "description": desc, "en": COMMANDS_EN.get(desc, desc),
                            "module": COMMAND_MODULES.get(cog, cog or "Autres"), "premium": desc.startswith("💎"),
                            "staff": bool(perms and perms.value), "owner": owner,
                            "options": [p.name for p in cmd.parameters]})
            for cmd in tree.get_commands(type=discord.AppCommandType.message):
                out.append({"name": cmd.name, "description": "Clic droit sur un message → Applications",
                            "en": "Right-click a message → Apps", "module": "Modération", "premium": False,
                            "staff": False, "owner": False, "options": []})
        out = [c for c in out if not c["owner"]]
        out.sort(key=lambda c: (c["module"], c["name"]))
        self._commands_cache = out
        return out

    async def api_commands(self, _: web.Request) -> web.Response:
        return web.json_response({"commands": self.command_list()}, headers={"Cache-Control": "max-age=300"})

    async def api_status(self, _: web.Request) -> web.Response:
        latency = getattr(self.bot, "latency", float("nan"))
        return web.json_response({
            "online": self.bot.is_ready(), "latency_ms": round(latency * 1000) if latency == latency and latency < 60 else None,
            "guilds": len(self.bot.guilds), "members": sum(g.member_count or 0 for g in self.bot.guilds),
            "uptime": int(time.time() - self.started), "version": self.bot.version,
            "modules": len(getattr(self.bot, "cogs", {}) or {}), "commands": len(self.command_list()),
            "dashboard": True, "checked_at": int(time.time())})

    async def og_image(self, _: web.Request) -> web.Response:
        if self._og_cache and time.time() - self._og_cache[0] < 3600:
            return web.Response(body=self._og_cache[1], content_type="image/png")
        user = self.bot.user
        avatar = None
        if user:
            try:
                avatar = await user.display_avatar.replace(size=256, format="png").read()
            except (discord.HTTPException, AttributeError):
                avatar = None
        import asyncio

        from bot.images import og_banner
        guilds = len(self.bot.guilds)
        png = await asyncio.to_thread(
            og_banner, user.name if user else "Bot", avatar, "Bot Discord tout-en-un · panel web",
            f"{guilds} serveur(s) · {len(self.command_list())} commandes · gratuit + Premium")
        self._og_cache = (time.time(), png)
        return web.Response(body=png, content_type="image/png", headers={"Cache-Control": "max-age=3600"})

    async def favicon(self, _: web.Request) -> web.Response:
        user = self.bot.user
        if user:
            raise web.HTTPFound(user.display_avatar.replace(size=64, format="png").url)
        raise web.HTTPFound("/static/favicon.svg")

    async def health(self, request: web.Request) -> web.Response:
        ready = self.bot.is_ready() and not self.bot.is_closed()
        body = {"ok": True, "discord_ready": ready, "guilds": len(self.bot.guilds)}
        # /health?strict=1 répond 503 si le bot n'est pas connecté à Discord (pour UptimeRobot & co).
        # Sans ?strict, toujours 200 : Railway s'en sert pendant le démarrage.
        if request.query.get("strict") and not ready:
            return web.json_response({**body, "ok": False}, status=503)
        return web.json_response(body)

    async def topgg_webhook(self, request: web.Request) -> web.Response:
        """Vote sur top.gg : enregistré pour que le membre récupère sa récompense avec /vote."""
        from bot import votes
        raw = await request.read()
        try:
            vote = votes.parse_webhook(request.headers, raw, votes.webhook_secret())
        except votes.WebhookError as exc:
            log.warning("Webhook top.gg refusé : %s", exc)
            return web.json_response({"error": str(exc)}, status=exc.status)
        if vote.test:
            log.info("Webhook top.gg de test reçu (utilisateur %s)", vote.user_id)
            return web.json_response({"ok": True, "test": True})
        await votes.record_vote(self.db, vote)
        cog = self.bot.get_cog("Votes")
        if cog is not None:
            import asyncio
            asyncio.ensure_future(cog.thank(vote))  # type: ignore[attr-defined]
        return web.json_response({"ok": True})

    def _check_csrf(self, request: web.Request) -> None:
        if request.headers.get("X-Requested-With") != "dashboard":
            raise HTTPError(403, "Requête refusée.")
        origin = request.headers.get("Origin")
        if origin and self.origin and origin != self.origin:
            raise HTTPError(403, "Origine refusée.")

    async def _discord_get(self, path: str, access_token: str) -> Any:
        assert self._http
        async with self._http.get(DISCORD_API + path, headers={"Authorization": f"Bearer {access_token}"}) as resp:
            if resp.status == 401:
                raise HTTPError(401, "Session Discord expirée, reconnecte-toi.")
            if resp.status == 429:
                raise HTTPError(429, "Discord limite les requêtes, réessaie dans quelques secondes.")
            resp.raise_for_status()
            return await resp.json()

    # ------------------------------------------------------------------ #
    #  Sessions
    # ------------------------------------------------------------------ #
    async def _session(self, request: web.Request) -> dict | None:
        sid = request.cookies.get("sid")
        if not sid:
            return None
        row = await self.db.fetchone("SELECT * FROM web_sessions WHERE id=? AND expires_at > ?", (sid, time.time()))
        return dict(row) if row else None

    async def _require_session(self, request: web.Request) -> dict:
        session = await self._session(request)
        if not session:
            raise HTTPError(401, "Tu n'es pas connecté.")
        return session

    @staticmethod
    def limited_groups(guild: discord.Guild, member: discord.Member) -> set[str]:
        """💎 Groupes de réglages ouverts à ce membre par les règles d'accès du serveur (vide = aucun)."""
        if not premium.is_premium(guild.id):
            return set()
        rules = store.raw(guild.id).get("panel_access", default=[]) or []
        return groups_for_roles({r.id for r in member.roles}, rules)

    async def _require_guild(self, request: web.Request, need: str | tuple[str, ...] | None = None
                             ) -> tuple[dict, discord.Guild]:
        """Vérifie l'accès. need : None (lecture), "full" (admins seulement) ou un/des groupe(s) d'accès."""
        session = await self._require_session(request)
        try:
            guild_id = int(request.match_info["guild_id"])
        except ValueError:
            raise HTTPError(404, "Serveur inconnu.") from None
        guild = self.bot.get_guild(guild_id)
        if guild is None:
            raise HTTPError(404, "Le bot n'est pas sur ce serveur.")
        groups: set[str] | None = None  # None = accès complet
        if guild.owner_id != session["user_id"]:
            member = guild.get_member(session["user_id"])
            if member is None:
                try:
                    member = await guild.fetch_member(session["user_id"])
                except discord.HTTPException:
                    member = None
            if member is None:
                raise HTTPError(403, "Tu dois avoir la permission « Gérer le serveur » pour le configurer.")
            if not member.guild_permissions.manage_guild:
                groups = self.limited_groups(guild, member)
                if not groups:
                    raise HTTPError(403, "Tu dois avoir la permission « Gérer le serveur » pour le configurer.")
        if groups is not None and need:
            wanted = {need} if isinstance(need, str) else set(need)
            if "full" in wanted or not wanted & groups:
                raise HTTPError(403, "Ton rôle n'a pas accès à cette partie du panel (réservé aux admins).")
        request["access"] = groups
        return session, guild

    @staticmethod
    def access_payload(request: web.Request) -> dict:
        groups = request.get("access")
        return {"full": groups is None, "groups": sorted(groups or [])}

    # ------------------------------------------------------------------ #
    #  Connexion Discord (OAuth2)
    # ------------------------------------------------------------------ #
    async def login(self, request: web.Request) -> web.Response:
        if not self.oauth_ready:
            raise web.HTTPFound("/dashboard#/setup-error")
        state = secrets.token_urlsafe(24)
        params = {"client_id": self.bot.application_id, "redirect_uri": self.redirect_uri, "response_type": "code",
                  "scope": "identify guilds", "state": state, "prompt": "none"}
        resp = web.HTTPFound("https://discord.com/oauth2/authorize?" + urlencode(params))
        resp.set_cookie("oauth_state", state, max_age=600, httponly=True, secure=self.secure, samesite="Lax")
        raise resp

    async def callback(self, request: web.Request) -> web.Response:
        state = request.query.get("state")
        if not state or state != request.cookies.get("oauth_state"):
            raise web.HTTPFound("/dashboard#/login-error")
        code = request.query.get("code")
        if not code:
            raise web.HTTPFound("/")  # l'utilisateur a annulé
        assert self._http
        data = {"client_id": str(self.bot.application_id), "client_secret": self.client_secret,
                "grant_type": "authorization_code", "code": code, "redirect_uri": self.redirect_uri}
        async with self._http.post(DISCORD_API + "/oauth2/token", data=data) as resp:
            if resp.status != 200:
                log.warning("Échange OAuth refusé (%s) : %s", resp.status, await resp.text())
                raise web.HTTPFound("/dashboard#/login-error")
            token = await resp.json()
        access = token["access_token"]
        user = await self._discord_get("/users/@me", access)
        guilds = await self._discord_get("/users/@me/guilds", access)

        sid = secrets.token_urlsafe(32)
        now = time.time()
        await self.db.execute("DELETE FROM web_sessions WHERE expires_at < ?", (now,))
        await self.db.execute(
            "INSERT INTO web_sessions (id, user_id, username, avatar, access_token, guilds, created_at, expires_at) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (sid, int(user["id"]), user.get("global_name") or user["username"], user.get("avatar"), access,
             json.dumps(guilds), now, now + SESSION_DAYS * 86400))
        resp = web.HTTPFound("/dashboard")
        resp.set_cookie("sid", sid, max_age=SESSION_DAYS * 86400, httponly=True, secure=self.secure, samesite="Lax")
        resp.del_cookie("oauth_state")
        log.info("Connexion au panel : %s (%s)", user["username"], user["id"])
        raise resp

    async def logout(self, request: web.Request) -> web.Response:
        self._check_csrf(request)
        sid = request.cookies.get("sid")
        if sid:
            await self.db.execute("DELETE FROM web_sessions WHERE id=?", (sid,))
        resp = web.json_response({"ok": True})
        resp.del_cookie("sid")
        return resp

    # ------------------------------------------------------------------ #
    #  API
    # ------------------------------------------------------------------ #
    def invite_url(self, guild_id: int | None = None) -> str:
        params = {"client_id": self.bot.application_id, "permissions": 8, "scope": "bot applications.commands"}
        if guild_id:
            params |= {"guild_id": guild_id, "disable_guild_select": "true"}
        return "https://discord.com/oauth2/authorize?" + urlencode(params)

    async def api_public(self, request: web.Request) -> web.Response:
        user = self.bot.user
        return web.json_response({
            "name": user.name if user else "Bot",
            "avatar": user.display_avatar.url if user else None,
            "guilds": len(self.bot.guilds),
            "members": sum(g.member_count or 0 for g in self.bot.guilds),
            "invite": self.invite_url() if self.bot.application_id else None,
            "oauth_ready": self.oauth_ready,
            "logged_in": await self._session(request) is not None,
            "version": self.bot.version,
            "contact": os.getenv("CONTACT", "").strip(),
            "commands": len(self.command_list()),
            "store_url": store_url(self.bot.application_id),
        })

    def _guild_list(self, session: dict) -> list[dict]:
        result = []
        for g in json.loads(session["guilds"]):
            perms = int(g.get("permissions", 0))
            gid = int(g["id"])
            limited = False
            if not (g.get("owner") or perms & (MANAGE_GUILD | ADMINISTRATOR)):
                # 💎 Accès limité donné à un de ses rôles ?
                guild = self.bot.get_guild(gid)
                member = guild.get_member(session["user_id"]) if guild else None
                if not (guild and member and self.limited_groups(guild, member)):
                    continue
                limited = True
            bot_in = self.bot.get_guild(gid) is not None
            result.append({
                "id": g["id"], "name": g["name"], "bot_in": bot_in, "premium": premium.is_premium(gid), "limited": limited,
                "icon": f"https://cdn.discordapp.com/icons/{g['id']}/{g['icon']}.png?size=128" if g.get("icon") else None,
                "invite": None if bot_in else self.invite_url(gid),
            })
        result.sort(key=lambda g: (not g["bot_in"], g["name"].lower()))
        return result

    async def api_me(self, request: web.Request) -> web.Response:
        session = await self._require_session(request)
        uid = session["user_id"]
        avatar = (f"https://cdn.discordapp.com/avatars/{uid}/{session['avatar']}.png?size=64"
                  if session["avatar"] else "https://cdn.discordapp.com/embed/avatars/0.png")
        return web.json_response({"user": {"id": str(uid), "name": session["username"], "avatar": avatar},
                                  "guilds": self._guild_list(session)})

    async def api_refresh(self, request: web.Request) -> web.Response:
        self._check_csrf(request)
        session = await self._require_session(request)
        guilds = await self._discord_get("/users/@me/guilds", session["access_token"])
        await self.db.execute("UPDATE web_sessions SET guilds=? WHERE id=?", (json.dumps(guilds), session["id"]))
        session["guilds"] = json.dumps(guilds)
        return web.json_response({"guilds": self._guild_list(session)})

    async def _guild_payload(self, guild: discord.Guild) -> dict:
        me = guild.me
        # Le panel montre les réglages tels que l'admin les a faits (même ceux verrouillés en version gratuite)
        cfg = store.raw(guild.id)
        open_tickets = await self.db.fetchone(
            "SELECT COUNT(*) AS n FROM tickets WHERE guild_id=? AND status='open'", (guild.id,))
        cases = await self.db.fetchone("SELECT COUNT(*) AS n FROM cases WHERE guild_id=?", (guild.id,))
        ranked = await self.db.fetchone("SELECT COUNT(*) AS n FROM levels WHERE guild_id=?", (guild.id,))
        panels = {}
        for name in PANELS:
            raw = await self.db.get_setting(guild.id, f"panel_message:{name}")
            panels[name] = raw.split(":")[0] if raw else None
        return {
            "guild": {"id": str(guild.id), "name": guild.name, "member_count": guild.member_count,
                      "icon": guild.icon.url if guild.icon else None},
            "config": stringify_ids(cfg.data),
            "defaults": stringify_ids(DEFAULTS),
            "channels": [{"id": str(c.id), "name": c.name, "category": c.category.name if c.category else ""}
                         for c in sorted(guild.text_channels, key=lambda c: (c.category.position if c.category else -1,
                                                                              c.position))],
            "categories": [{"id": str(c.id), "name": c.name} for c in guild.categories],
            "voice_channels": [{"id": str(c.id), "name": c.name, "category": c.category.name if c.category else ""}
                               for c in guild.voice_channels + guild.stage_channels],
            "limits": {k: limit_for(k, premium.is_premium(guild.id)) for k in LIMITS},
            "configured": store.has(guild.id),
            "templates": template_list(),
            "roles": [{"id": str(r.id), "name": r.name, "color": f"#{r.color.value:06x}" if r.color.value else None,
                       "manageable": r < me.top_role}
                      for r in reversed(guild.roles) if not r.is_default() and not r.managed],
            "stats": {"members": guild.member_count, "open_tickets": open_tickets["n"], "cases": cases["n"],
                      "ranked": ranked["n"]},
            "panels": panels,
            "diagnostic": diagnostic.run(guild),
            "bot": {"can_manage": me.guild_permissions.manage_roles and me.guild_permissions.manage_channels,
                    "top_role": me.top_role.name},
            "premium": {**premium.status(guild.id),
                        "paths": PREMIUM_PATHS,
                        "store_url": store_url(self.bot.application_id),
                        "trial": await premium.trial_state(self.db, guild.id), "trial_days": trial_days(),
                        "twitch_enabled": bool(os.getenv("TWITCH_CLIENT_ID") and os.getenv("TWITCH_CLIENT_SECRET")),
                        "ai_ready": bool(os.getenv("ANTHROPIC_API_KEY", "").strip())},
            # IA du serveur : jamais la clé, seulement le fournisseur, le modèle et la version masquée
            "ai_key": await ai_keys.info(self.db, guild.id),
            "ai_keys_ready": secrets_box.available(),
            "ai_providers": [{"id": pid, "name": p["name"], "key_url": p["key_url"]} for pid, p in PROVIDERS.items()],
        }

    async def api_guild(self, request: web.Request) -> web.Response:
        _, guild = await self._require_guild(request)
        payload = await self._guild_payload(guild)
        payload["access"] = self.access_payload(request)
        return web.json_response(payload)

    async def api_save_config(self, request: web.Request) -> web.Response:
        self._check_csrf(request)
        session, guild = await self._require_guild(request)
        body = await request.json()
        if not isinstance(body, dict):
            raise HTTPError(400, "Données invalides.")
        before = store.raw(guild.id).data
        groups = request.get("access")
        if groups is not None:  # accès limité : seuls les réglages autorisés sont pris en compte
            body = apply_restricted(before, body, groups)
        await store.save(self.db, guild.id, body)
        changed = config_diff(before, store.raw(guild.id).data)
        if changed:
            await self._audit(guild.id, session, "config", changed)
        log.info("Config de %s (%s) modifiée par %s", guild.name, guild.id, session["user_id"])
        payload = await self._guild_payload(guild)
        payload["access"] = self.access_payload(request)
        return web.json_response(payload)

    async def api_messagelog(self, request: web.Request) -> web.Response:
        """Messages modifiés / supprimés (si le journal est activé), filtrables par membre, salon ou texte."""
        _, guild = await self._require_guild(request, "moderation")
        sql = "SELECT * FROM message_log WHERE guild_id=?"
        params: list[Any] = [guild.id]
        for key, column in (("user", "author_id"), ("channel", "channel_id")):
            value = request.query.get(key, "")
            if value.isdigit():
                sql += f" AND {column}=?"
                params.append(int(value))
        action = request.query.get("action", "")
        if action in ("edit", "delete"):
            sql += " AND action=?"
            params.append(action)
        text = request.query.get("q", "").strip()[:100]
        if text:
            sql += " AND (before LIKE ? OR after LIKE ?)"
            params += [f"%{text}%", f"%{text}%"]
        rows = await self.db.fetchall(sql + " ORDER BY id DESC LIMIT 200", params)
        out = []
        for r in rows:
            member = guild.get_member(r["author_id"])
            channel = guild.get_channel(r["channel_id"])
            out.append({"id": r["id"], "action": r["action"], "before": r["before"], "after": r["after"], "at": r["created_at"],
                        "author_id": str(r["author_id"]), "author": member.display_name if member else str(r["author_id"]),
                        "channel": channel.name if channel else str(r["channel_id"]),
                        "link": f"https://discord.com/channels/{guild.id}/{r['channel_id']}/{r['message_id']}"})
        return web.json_response({"enabled": bool(store.raw(guild.id).get("message_log", "enabled", default=False)),
                                  "entries": out})

    async def api_test(self, request: web.Request) -> web.Response:
        """Envoie dans Discord un message de test (bienvenue, MP, au revoir, niveau, anniversaire) avec la config enregistrée."""
        self._check_csrf(request)
        session, guild = await self._require_guild(request, "community")
        body = await request.json()
        kind = str(body.get("kind") or "")
        if kind not in TEST_KINDS:
            raise HTTPError(400, "Type de test inconnu.")
        if time.time() - self._last_test.get(session["user_id"], 0) < 5:
            raise HTTPError(429, "Attends quelques secondes entre deux tests.")
        self._last_test[session["user_id"]] = time.time()
        member = guild.get_member(session["user_id"])
        if member is None:
            try:
                member = await guild.fetch_member(session["user_id"])
            except discord.HTTPException:
                raise HTTPError(400, "Tu dois être membre du serveur pour recevoir le test.") from None
        from bot import embeds
        from bot.i18n import tr
        from bot.utils import fill_template
        cfg = gconf(guild)  # config effective (version gratuite appliquée si besoin)
        footer = "🧪 Message de test envoyé depuis le panel"
        if kind == "dm":
            text = fill_template(tr(guild, cfg.get("welcome", "dm_message", default="") or ""), member)
            if not text:
                raise HTTPError(400, "Le message privé est vide.")
            embed = embeds.base(f"Bienvenue sur {guild.name} !", text, guild=guild)
            embed.set_footer(text=footer)
            try:
                await member.send(embed=embed)
            except discord.HTTPException:
                raise HTTPError(400, "Je ne peux pas t'écrire en privé : ouvre tes messages privés pour ce serveur.") from None
            await self._audit(guild.id, session, "test", [kind])
            return web.json_response({"ok": True, "where": "MP"})
        channel_key = {"welcome": ("channels", "welcome"), "goodbye": ("channels", "goodbye"),
                       "levelup": ("channels", "level_up"), "birthday": ("birthdays", "channel")}[kind]
        channel = guild.get_channel(int(cfg.get(*channel_key, default=0) or 0))
        if not isinstance(channel, discord.TextChannel):
            raise HTTPError(400, "Choisis d'abord le salon (et enregistre), puis relance le test.")
        if not channel.permissions_for(guild.me).send_messages:
            raise HTTPError(400, f"Je ne peux pas écrire dans #{channel.name}.")
        kwargs: dict[str, Any] = {}
        if kind == "welcome":
            cog = self.bot.get_cog("Welcome")
            kwargs = await cog.welcome_payload(member) if cog else {}  # type: ignore[attr-defined]
        else:
            template = {"goodbye": cfg.get("welcome", "goodbye_message", default=""),
                        "levelup": cfg.get("leveling", "level_up_message", default="")
                        or "🎉 {mention} passe au niveau {level} !",
                        "birthday": cfg.get("birthdays", "message", default="")}[kind]
            text = fill_template(tr(guild, template or ""), member).replace("{level}", "5")
            if not text:
                raise HTTPError(400, "Le message est vide.")
            kwargs["embed"] = embeds.base(None, text, guild=guild)
        if "embed" in kwargs:
            kwargs["embed"].set_footer(text=footer)
        await channel.send(**kwargs, allowed_mentions=discord.AllowedMentions.none())
        await self._audit(guild.id, session, "test", [kind, f"#{channel.name}"])
        return web.json_response({"ok": True, "where": f"#{channel.name}"})

    async def api_staffstats(self, request: web.Request) -> web.Response:
        _, guild = await self._require_guild(request, ("stats", "moderation"))
        try:
            days = int(request.query.get("days", "30"))
        except ValueError:
            days = 30
        days = days if days in (7, 30, 90, 0) else 30
        rows = await build_staff_stats(self.db, guild.id, time.time() - days * 86400 if days else 0)
        for r in rows:
            member = guild.get_member(r["user_id"])
            r["name"] = member.display_name if member else f"Ancien membre ({r['user_id']})"
            r["avatar"] = member.display_avatar.url if member else None
            r["user_id"] = str(r["user_id"])
        return web.json_response({"days": days, "staff": rows[:50]})

    async def _audit(self, guild_id: int, session: dict, action: str, details: list[str]) -> None:
        await self.db.execute(
            "INSERT INTO panel_audit (guild_id, user_id, username, action, details, created_at) VALUES (?,?,?,?,?,?)",
            (guild_id, session["user_id"], session["username"], action,
             json.dumps(details[:40], ensure_ascii=False), time.time()))

    async def api_audit(self, request: web.Request) -> web.Response:
        _, guild = await self._require_guild(request, "stats")
        rows = await self.db.fetchall(
            "SELECT user_id, username, action, details, created_at FROM panel_audit WHERE guild_id=? "
            "ORDER BY id DESC LIMIT 100", (guild.id,))
        return web.json_response({"entries": [
            {"user_id": str(r["user_id"]), "username": r["username"], "action": r["action"],
             "details": json.loads(r["details"] or "[]"), "at": r["created_at"]} for r in rows]})

    # ------------------------------------------------------------------ #
    #  IA du serveur (clé propre)
    # ------------------------------------------------------------------ #
    @staticmethod
    def _ai_body_key(body: dict) -> str:
        key = str(body.get("key") or "").strip()
        if len(key) > 400 or any(c.isspace() for c in key):
            raise HTTPError(400, "Cette clé n'a pas le bon format : recopie-la sans espace.")
        return key

    async def _ai_key_for(self, guild: discord.Guild, provider: str, key: str) -> str:
        """La clé à utiliser : celle envoyée, sinon celle déjà enregistrée (même fournisseur)."""
        if key:
            return key
        try:
            stored = await ai_keys.load(self.db, guild.id)
        except secrets_box.SecretError as exc:
            raise HTTPError(400, f"{exc} Recolle ta clé.") from None
        if not stored or stored.provider != provider:
            raise HTTPError(400, "Colle ta clé d'API.")
        return stored.key

    async def api_ai_models(self, request: web.Request) -> web.Response:
        """Vérifie une clé et renvoie les modèles disponibles chez le fournisseur."""
        self._check_csrf(request)
        _, guild = await self._require_guild(request, "full")
        body = await request.json()
        provider = str(body.get("provider") or "")
        if provider not in PROVIDERS:
            raise HTTPError(400, "Choisis un fournisseur.")
        key = await self._ai_key_for(guild, provider, self._ai_body_key(body))
        assert self._http
        try:
            models = await list_models(provider, key, self._http)
        except ProviderError as exc:
            raise HTTPError(400, str(exc)) from None
        if not models:
            raise HTTPError(400, "La clé marche, mais aucun modèle de discussion n'est disponible sur ce compte.")
        return web.json_response({"ok": True, "models": models})

    async def api_ai_key_save(self, request: web.Request) -> web.Response:
        self._check_csrf(request)
        session, guild = await self._require_guild(request, "full")
        if not secrets_box.available():
            raise HTTPError(503, "Le propriétaire du bot doit d'abord configurer AI_KEYS_SECRET.")
        body = await request.json()
        provider = str(body.get("provider") or "")
        model = str(body.get("model") or "").strip()
        if provider not in PROVIDERS:
            raise HTTPError(400, "Choisis un fournisseur.")
        if not valid_model(model):
            raise HTTPError(400, "Choisis un modèle (bouton « Tester la clé »).")
        new_key = self._ai_body_key(body)
        key = await self._ai_key_for(guild, provider, new_key)
        assert self._http
        try:
            models = await list_models(provider, key, self._http)
        except ProviderError as exc:
            raise HTTPError(400, str(exc)) from None
        if models and model not in models:
            raise HTTPError(400, "Ce modèle n'est pas disponible avec cette clé.")
        info = await ai_keys.save(self.db, guild.id, provider, key, model, session["user_id"])
        await self._audit(guild.id, session, "ai_key", [PROVIDERS[provider]["name"], model])
        return web.json_response({"ok": True, "ai_key": info})

    async def api_ai_key_delete(self, request: web.Request) -> web.Response:
        self._check_csrf(request)
        session, guild = await self._require_guild(request, "full")
        await ai_keys.delete(self.db, guild.id)
        await self._audit(guild.id, session, "ai_key_delete", [])
        return web.json_response({"ok": True})

    async def api_trial(self, request: web.Request) -> web.Response:
        """Démarre l'essai Premium gratuit (une fois par serveur, admins seulement)."""
        self._check_csrf(request)
        session, guild = await self._require_guild(request, "full")
        try:
            ends = await premium.start_trial(self.db, guild.id, session["user_id"])
        except ValueError as exc:
            raise HTTPError(400, str(exc)) from None
        await self._audit(guild.id, session, "trial", [f"{trial_days()} jours"])
        log.info("Essai Premium démarré depuis le panel : serveur %s", guild.id)
        from cogs.ops import notify_owner
        await notify_owner(self.bot, "🎁 Essai Premium démarré",
                           f"**{guild.name}** (`{guild.id}`) · {guild.member_count} membres (depuis le panel)", 0xF1C40F)
        return web.json_response({"ok": True, "expires_at": ends})

    async def api_send(self, request: web.Request) -> web.Response:
        """Envoie tout de suite un message (embed) dans un salon, depuis le panel."""
        self._check_csrf(request)
        session, guild = await self._require_guild(request, "messages")
        body = await request.json()
        channel = guild.get_channel(int(str(body.get("channel") or 0)) if str(body.get("channel") or "").isdigit() else 0)
        title = str(body.get("title") or "").strip()[:256]
        message = str(body.get("message") or "").strip()[:4000]
        mention = {"everyone": "@everyone", "here": "@here"}.get(str(body.get("mention")))
        if not isinstance(channel, discord.TextChannel):
            raise HTTPError(400, "Choisis un salon.")
        if not (title or message):
            raise HTTPError(400, "Écris un titre ou un message.")
        if not channel.permissions_for(guild.me).send_messages:
            raise HTTPError(400, f"Je ne peux pas écrire dans #{channel.name}.")
        from cogs.custom import custom_embed
        await channel.send(content=mention, embed=custom_embed(guild, title, message),
                           allowed_mentions=discord.AllowedMentions(everyone=bool(mention)))
        await self._audit(guild.id, session, "send", [f"#{channel.name}", title or message[:60]])
        return web.json_response({"ok": True, "channel": channel.name})

    async def api_publish_menu(self, request: web.Request) -> web.Response:
        self._check_csrf(request)
        session, guild = await self._require_guild(request, "community")
        from cogs.custom import find_menu, publish_role_menu
        menu, allowed = find_menu(guild, request.match_info["menu_id"])
        if not menu:
            raise HTTPError(404, "Menu introuvable : enregistre d'abord tes modifications.")
        if not allowed:
            raise HTTPError(402, "Limite de menus de la version gratuite atteinte (💎 Premium : 15 menus).")
        if not menu["roles"]:
            raise HTTPError(400, "Ajoute au moins un rôle au menu.")
        try:
            message = await publish_role_menu(self.bot, guild, menu)
        except ValueError as exc:
            raise HTTPError(400, str(exc)) from None
        await self._audit(guild.id, session, "rolemenu", [menu.get("title") or menu["id"], f"#{message.channel}"])
        return web.json_response({"ok": True, "channel": str(message.channel)})

    async def api_export(self, request: web.Request) -> web.Response:
        _, guild = await self._require_guild(request, "full")
        data = {"bot": "config-export", "version": self.bot.version, "guild": guild.name,
                "exported_at": int(time.time()), "config": stringify_ids(store.raw(guild.id).data)}
        safe_name = re.sub(r"[^\w-]+", "-", guild.name)[:40] or "serveur"
        return web.json_response(data, dumps=lambda d: json.dumps(d, ensure_ascii=False, indent=2), headers={
            "Content-Disposition": f'attachment; filename="config-{safe_name}.json"'})

    async def api_template(self, request: web.Request) -> web.Response:
        self._check_csrf(request)
        session, guild = await self._require_guild(request, "full")
        from bot.templates import TEMPLATES
        body = await request.json()
        template = TEMPLATES.get(str(body.get("template")))
        if not template:
            raise HTTPError(404, "Modèle inconnu.")
        before = store.raw(guild.id).data
        await store.update(self.db, guild.id, template["config"])
        await self._audit(guild.id, session, "template", [template["name"]] + config_diff(before, store.raw(guild.id).data)[:30])
        return web.json_response(await self._guild_payload(guild))

    async def api_import(self, request: web.Request) -> web.Response:
        self._check_csrf(request)
        session, guild = await self._require_guild(request, "full")
        body = await request.json()
        config = body.get("config") if isinstance(body, dict) and "config" in body else body
        if not isinstance(config, dict):
            raise HTTPError(400, "Fichier invalide : ce n'est pas une sauvegarde de configuration.")
        before = store.raw(guild.id).data
        await store.save(self.db, guild.id, config)
        changed = config_diff(before, store.raw(guild.id).data)
        await self._audit(guild.id, session, "import", changed or ["aucun changement"])
        payload = await self._guild_payload(guild)
        payload["changed"] = len(changed)
        return web.json_response(payload)

    async def api_stats(self, request: web.Request) -> web.Response:
        _, guild = await self._require_guild(request, "stats")
        try:
            days = int(request.query.get("days", "7"))
        except ValueError:
            days = 7
        days = days if days in (7, 30, 90) else 7
        if days > 7 and not premium.is_premium(guild.id):
            raise HTTPError(402, "Les statistiques sur 30 et 90 jours sont réservées aux serveurs 💎 Premium.")
        return web.json_response(await build_stats(self.db, guild.id, days))

    async def api_autocreate(self, request: web.Request) -> web.Response:
        self._check_csrf(request)
        session, guild = await self._require_guild(request, "full")
        options = await request.json() if request.can_read_body else {}
        me = guild.me
        if not (me.guild_permissions.manage_roles and me.guild_permissions.manage_channels):
            raise HTTPError(400, "Il me faut les permissions « Gérer les rôles » et « Gérer les salons ».")
        cfg = gconf(guild)
        patch: dict[str, Any] = {"roles": {}, "channels": {}, "panels": {}}
        created: list[str] = []
        reason = "Configuration automatique depuis le panel web"

        async def make_role(name: str, color: int, hoist: bool = False) -> discord.Role:
            role = await guild.create_role(name=name, colour=discord.Colour(color), hoist=hoist, reason=reason)
            created.append(f"Rôle @{name}")
            return role

        for key, (name, color, hoist) in AUTO_ROLES_BASE.items():
            if guild.get_role(cfg.role_id(key)) is None:
                patch["roles"][key] = (await make_role(name, color, hoist)).id

        if options.get("notifications", True) and not cfg.get("roles", "notifications"):
            patch["roles"]["notifications"] = {n: (await make_role(n, 0)).id for n in AUTO_NOTIFICATIONS}
        if options.get("levels", True) and not cfg.get("roles", "level_roles"):
            patch["roles"]["level_roles"] = {lvl: (await make_role(f"Niveau {lvl}", c)).id
                                             for lvl, c in AUTO_LEVELS.items()}

        staff = guild.get_role(patch["roles"].get("staff") or cfg.role_id("staff"))
        everyone = guild.default_role
        bot_ow = discord.PermissionOverwrite(view_channel=True, send_messages=True, embed_links=True,
                                             attach_files=True, manage_channels=True, read_message_history=True)

        def overwrites(visibility: str) -> dict:
            if visibility == "staff":
                ow = {everyone: discord.PermissionOverwrite(view_channel=False), me: bot_ow}
                if staff:
                    ow[staff] = discord.PermissionOverwrite(view_channel=True, send_messages=True,
                                                            read_message_history=True)
                return ow
            return {everyone: discord.PermissionOverwrite(send_messages=False), me: bot_ow}

        for (section, key), (name, kind, visibility) in AUTO_CHANNELS.items():
            if guild.get_channel(int(cfg.get(section, key, default=0) or 0)) is not None:
                continue
            if kind == "category":
                channel = await guild.create_category(name, overwrites=overwrites(visibility), reason=reason)
                created.append(f"Catégorie {name}")
            elif kind == "voice":
                channel = await guild.create_voice_channel(name, reason=reason)
                created.append(f"Vocal {name}")
            else:
                channel = await guild.create_text_channel(name, overwrites=overwrites(visibility), reason=reason)
                created.append(f"Salon #{name}")
            patch.setdefault(section, {})[key] = channel.id

        await store.update(self.db, guild.id, patch)
        if created:
            await self._audit(guild.id, session, "autocreate", created)
        payload = await self._guild_payload(guild)
        payload["created"] = created
        return web.json_response(payload)

    async def api_panels(self, request: web.Request) -> web.Response:
        self._check_csrf(request)
        session, guild = await self._require_guild(request, "full")
        cfg = gconf(guild)
        results = {}
        for name in PANELS:
            channel = guild.get_channel(cfg.panel_id(name))
            if not isinstance(channel, discord.TextChannel):
                results[name] = "Salon non défini"
                continue
            try:
                await publish_panel(self.bot, guild, name, channel)
                results[name] = f"Publié dans #{channel.name}"
            except discord.HTTPException as exc:
                results[name] = f"Échec : {exc.text or exc}"
        await self._audit(guild.id, session, "panels", [f"{k} : {v}" for k, v in results.items()])
        payload = await self._guild_payload(guild)
        payload["published"] = results
        return web.json_response(payload)


__all__ = ["Dashboard", "stringify_ids", "deep_merge"]
