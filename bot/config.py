"""Configuration PAR SERVEUR, stockée en base et modifiable depuis le panel web.

Chaque serveur a sa propre config : valeurs par défaut (bot/defaults.json) + ce que
les admins du serveur ont modifié (table guild_config). Lecture synchrone depuis un
cache mémoire, écriture via `await store.save(...)`.
"""
from __future__ import annotations

import copy
import json
import logging
import re
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import discord

    from bot.db import Database

log = logging.getLogger("bot.config")

DEFAULTS_PATH = Path(__file__).resolve().parent / "defaults.json"
DEFAULTS: dict[str, Any] = json.loads(DEFAULTS_PATH.read_text(encoding="utf-8"))
DEFAULT_COLOR = 0x5865F2

# Dictionnaires dont les clés sont libres (choisies par l'admin)
FREE_MAPS = {"roles.notifications", "roles.level_roles", "moderation.escalation", "tickets.types"}
# Listes qui contiennent des IDs Discord
ID_LISTS = {"leveling.ignored_channels", "automod.exempt_roles", "anti_raid.whitelist", "anti_nuke.whitelist"}
# (automod.allowed_domains est une liste de textes : traitée par le cas général)
# Réglages simples qui sont des IDs Discord en dehors de channels / panels / roles
ID_SCALARS = {"giveaways.manager_role", "birthdays.channel", "birthdays.role", "temp_voice.creator_channel",
              "temp_voice.category", "suggestions.channel", "starboard.channel", "invites.channel",
              "engagement.channel", "events.manager_role", "ai.channel", "reports.channel",
              "twitch_mod.log_channel"}
# Réglages à choix fermé
TWITCH_ACTIONS = ("off", "delete", "timeout", "ban")
CHOICES = {"general.language": ("fr", "en"),
           **{f"twitch_mod.{rule}_action": TWITCH_ACTIONS for rule in ("phishing", "links", "words", "caps", "repeat")}}
# Listes d'objets : chemin -> (champs autorisés, champs obligatoires)
OBJECT_LISTS = {
    "alerts.twitch": (("login", "channel", "message"), ("login", "channel")),
    "alerts.youtube": (("source", "channel", "message"), ("source", "channel")),
    "alerts.kick": (("login", "channel", "message"), ("login", "channel")),
    "alerts.tiktok": (("login", "channel", "message"), ("login", "channel")),
    "alerts.rss": (("url", "channel", "message"), ("url", "channel")),
    "economy.shop": (("name", "price", "role", "description"), ("name",)),
}
OBJECT_ID_FIELDS = {"channel", "role"}
OBJECT_INT_FIELDS = {"price"}
MAX_TEXT = 2000
LONG_TEXT = {"ai.knowledge": 8000}  # textes autorisés à être plus longs
_HEX = re.compile(r"^#?[0-9a-fA-F]{6}$")

# --------------------------------------------------------------------------- #
#  Premium : valeurs imposées aux serveurs gratuits
# --------------------------------------------------------------------------- #
# Les admins peuvent préparer ces réglages dans le panel, mais ils ne s'appliquent
# qu'avec Premium. Sans Premium, c'est la valeur ci-dessous qui est utilisée.
FREE_OVERRIDES: dict[str, Any] = {
    "brand.color": DEFAULTS["brand"]["color"],
    "brand.footer": "",
    "welcome.message": DEFAULTS["welcome"]["message"],
    "welcome.dm_message": DEFAULTS["welcome"]["dm_message"],
    "welcome.goodbye_message": DEFAULTS["welcome"]["goodbye_message"],
    "leveling.level_up_message": DEFAULTS["leveling"]["level_up_message"],
    "tickets.transcripts": False,
    "tickets.feedback": False,
    "verification.captcha": False,
    "leveling.voice_enabled": False,
    "leveling.rank_card": False,
    "anti_raid.auto_lockdown": False,
    "anti_nuke.enabled": False,
    "alerts.twitch": [],
    "alerts.youtube": [],
    "alerts.kick": [],
    "alerts.tiktok": [],
    "alerts.rss": [],
    "engagement.weekly_quests": False,
    "economy.bank_interest": DEFAULTS["economy"]["bank_interest"],
    "panel_access": [],
    "message_log.days": DEFAULTS["message_log"]["days"],
    "economy.currency_name": DEFAULTS["economy"]["currency_name"],
    "economy.currency_emoji": DEFAULTS["economy"]["currency_emoji"],
    "economy.shop": [],
    "birthdays.role": 0,
    "birthdays.message": DEFAULTS["birthdays"]["message"],
    "welcome.image": False,
    "scheduled": [],
}

# Limites selon la version (appliquées par les modules au moment de l'utilisation)
LIMITS = {"tournament_players": (16, 64), "counters": (2, 5), "custom_commands": (5, 50), "role_menus": (2, 15),
          "twitch_channels": (1, 5)}


def limit_for(kind: str, premium: bool) -> int:
    free, paid = LIMITS[kind]
    return paid if premium else free
PREMIUM_PATHS = sorted(FREE_OVERRIDES)


def _apply_free_overrides(data: dict) -> dict:
    data = copy.deepcopy(data)
    for path, value in FREE_OVERRIDES.items():
        keys = path.split(".")
        cur = data
        for k in keys[:-1]:
            cur = cur.setdefault(k, {})
        cur[keys[-1]] = copy.deepcopy(value)
    return data


def deep_merge(base: dict, override: dict) -> dict:
    """Fusionne override dans base (récursif) sans modifier les originaux.
    Les dictionnaires « libres » sont remplacés entièrement (pour pouvoir supprimer des entrées)."""
    return _merge(base, override, "")


def _merge(base: dict, override: dict, prefix: str) -> dict:
    result = copy.deepcopy(base)
    for key, value in override.items():
        path = f"{prefix}{key}"
        if isinstance(value, dict) and isinstance(result.get(key), dict) and path not in FREE_MAPS:
            result[key] = _merge(result[key], value, path + ".")
        else:
            result[key] = copy.deepcopy(value)
    return result


# --------------------------------------------------------------------------- #
#  Validation des données venant du panel web (jamais confiance au navigateur)
# --------------------------------------------------------------------------- #
def _to_id(value: Any) -> int:
    try:
        n = int(str(value).strip() or 0)
    except ValueError:
        return 0
    return n if 0 <= n < 2**64 else 0


def _clean_scalar(default: Any, value: Any, path: str) -> Any:
    if isinstance(default, bool):
        return bool(value)
    if isinstance(default, int):
        # Les IDs Discord arrivent en texte (trop grands pour JavaScript)
        if path.startswith(("channels.", "panels.", "roles.")) or path in ID_SCALARS:
            return _to_id(value)
        try:
            return max(0, min(int(float(value)), 10**9))
        except (TypeError, ValueError):
            return default
    if isinstance(default, float):
        try:
            return max(0.0, min(float(value), 100.0))
        except (TypeError, ValueError):
            return default
    if isinstance(default, str):
        text = str(value or "")[:LONG_TEXT.get(path, MAX_TEXT)]
        if path in CHOICES and text not in CHOICES[path]:
            return default
        if path == "brand.color" and not _HEX.match(text):
            return default
        return text
    return default


def sanitize(incoming: dict, defaults: dict = DEFAULTS, prefix: str = "") -> dict:
    """Ne garde que les clés connues, avec le bon type."""
    clean: dict[str, Any] = {}
    if not isinstance(incoming, dict):
        return clean
    for key, default in defaults.items():
        if key not in incoming:
            continue
        path = f"{prefix}{key}"
        value = incoming[key]
        if path in CUSTOM_LISTS:
            clean[key] = CUSTOM_LISTS[path](value if isinstance(value, list) else [])
        elif path in FREE_MAPS:
            clean[key] = _sanitize_free_map(path, value)
        elif path in OBJECT_LISTS:
            clean[key] = _sanitize_object_list(path, value)
        elif isinstance(default, dict):
            clean[key] = sanitize(value, default, path + ".")
        elif isinstance(default, list):
            items = value if isinstance(value, list) else []
            if path in ID_LISTS:
                clean[key] = [i for i in (_to_id(v) for v in items[:100]) if i]
            else:
                clean[key] = [str(v)[:300] for v in items[:100] if str(v).strip()]
        else:
            clean[key] = _clean_scalar(default, value, path)
    return clean


COUNTER_TYPES = ("members", "humans", "bots", "online", "boosts", "channels", "roles")
_SLUG = re.compile(r"[^a-z0-9]")
_DATETIME = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$")


def _text(value: Any, limit: int) -> str:
    return str(value or "").strip()[:limit]


def _choice(value: Any, choices: tuple, default: str) -> str:
    return value if value in choices else default


def _slug(value: Any) -> str:
    return _SLUG.sub("", str(value or "").lower())[:12]


def _sanitize_counters(items: list) -> list[dict]:
    out = []
    for it in items[:5]:
        if isinstance(it, dict) and _to_id(it.get("channel")):
            out.append({"type": _choice(it.get("type"), COUNTER_TYPES, "members"), "channel": _to_id(it.get("channel")),
                        "template": _text(it.get("template"), 100) or "👥 Membres : {}"})
    return out


def _sanitize_custom_commands(items: list) -> list[dict]:
    out, seen = [], set()
    for it in items[:50]:
        if not isinstance(it, dict):
            continue
        trigger = _text(it.get("trigger"), 50).lower()
        response = _text(it.get("response"), 2000)
        if trigger and response and trigger not in seen:
            seen.add(trigger)
            out.append({"trigger": trigger, "response": response,
                        "mode": _choice(it.get("mode"), ("exact", "contains"), "exact"), "embed": bool(it.get("embed"))})
    return out


def _sanitize_role_menus(items: list) -> list[dict]:
    out, seen = [], set()
    for it in items[:15]:
        if not isinstance(it, dict):
            continue
        menu_id = _slug(it.get("id"))
        if not menu_id or menu_id in seen:
            continue
        seen.add(menu_id)
        roles = []
        for r in (it.get("roles") if isinstance(it.get("roles"), list) else [])[:25]:
            if isinstance(r, dict) and _to_id(r.get("role")):
                roles.append({"role": _to_id(r.get("role")), "label": _text(r.get("label"), 80),
                              "emoji": _text(r.get("emoji"), 20)})
        out.append({"id": menu_id, "channel": _to_id(it.get("channel")), "title": _text(it.get("title"), 100),
                    "description": _text(it.get("description"), 1000),
                    "style": _choice(it.get("style"), ("buttons", "select"), "buttons"),
                    "multiple": bool(it.get("multiple", True)), "roles": roles})
    return out


def _sanitize_scheduled(items: list) -> list[dict]:
    out, seen = [], set()
    for it in items[:25]:
        if not isinstance(it, dict):
            continue
        sid = _slug(it.get("id"))
        at = _text(it.get("at"), 16)
        if not sid or sid in seen or not _to_id(it.get("channel")) or not _DATETIME.match(at):
            continue
        if not (_text(it.get("title"), 256) or _text(it.get("message"), 4000)):
            continue
        seen.add(sid)
        out.append({"id": sid, "channel": _to_id(it.get("channel")), "title": _text(it.get("title"), 256),
                    "message": _text(it.get("message"), 4000), "at": at,
                    "repeat": _choice(it.get("repeat"), ("none", "daily", "weekly"), "none"),
                    "mention": _choice(it.get("mention"), ("none", "everyone", "here"), "none")})
    return out


def _sanitize_panel_access(items: list) -> list[dict]:
    from bot.access import GROUP_IDS
    out, seen = [], set()
    for it in items[:10]:
        role = _to_id(it.get("role")) if isinstance(it, dict) else 0
        if not role or role in seen:
            continue
        seen.add(role)
        out.append({"role": role, **{g: bool(it.get(g)) for g in GROUP_IDS}})
    return out


CUSTOM_LISTS = {"counters": _sanitize_counters, "custom_commands": _sanitize_custom_commands,
                "role_menus": _sanitize_role_menus, "scheduled": _sanitize_scheduled,
                "panel_access": _sanitize_panel_access}


def _sanitize_object_list(path: str, value: Any) -> list[dict]:
    if not isinstance(value, list):
        return []
    fields, required = OBJECT_LISTS[path]
    out = []
    for item in value[:25]:
        if not isinstance(item, dict):
            continue
        clean: dict[str, Any] = {}
        for field in fields:
            raw = item.get(field, "")
            if field in OBJECT_ID_FIELDS:
                clean[field] = _to_id(raw)
            elif field in OBJECT_INT_FIELDS:
                clean[field] = _clean_scalar(0, raw, "")
            else:
                clean[field] = str(raw or "").strip()[:300]
        if all(clean[f] for f in required):
            out.append(clean)
    return out


def _sanitize_free_map(path: str, value: Any) -> dict:
    if not isinstance(value, dict):
        return {}
    out: dict[str, Any] = {}
    for raw_key, item in list(value.items())[:25]:
        key = str(raw_key).strip()[:50]
        if not key:
            continue
        if path in ("roles.notifications", "roles.level_roles"):
            if path == "roles.level_roles" and not key.isdigit():
                continue
            role_id = _to_id(item)
            if role_id:
                out[key] = role_id
        elif path == "moderation.escalation":
            if not key.isdigit() or not isinstance(item, dict):
                continue
            action = item.get("action")
            if action in ("timeout", "kick", "ban"):
                out[key] = {"action": action, "minutes": _clean_scalar(0, item.get("minutes", 0), "")}
        elif path == "tickets.types":
            if not isinstance(item, dict):
                continue
            slug = re.sub(r"[^a-z0-9-]", "", key.lower())[:20] or "ticket"
            out[slug] = {
                "label": str(item.get("label") or slug)[:80],
                "emoji": str(item.get("emoji") or "🎫")[:20],
                "description": str(item.get("description") or "")[:100],
            }
            raw_q = item.get("questions") or []
            if isinstance(raw_q, str):
                raw_q = raw_q.split("|")
            questions = [str(q).strip()[:45] for q in raw_q if str(q).strip()][:5] if isinstance(raw_q, list) else []
            if questions:
                out[slug]["questions"] = questions
    return out


# --------------------------------------------------------------------------- #
#  Accès
# --------------------------------------------------------------------------- #
class GuildConfig:
    def __init__(self, data: dict[str, Any]):
        self.data = data

    def get(self, *keys: str, default: Any = None) -> Any:
        cur: Any = self.data
        for k in keys:
            if isinstance(cur, dict) and k in cur:
                cur = cur[k]
            else:
                return default
        return cur

    def channel_id(self, name: str) -> int:
        return int(self.get("channels", name, default=0) or 0)

    def panel_id(self, name: str) -> int:
        return int(self.get("panels", name, default=0) or 0)

    def role_id(self, name: str) -> int:
        return int(self.get("roles", name, default=0) or 0)

    @property
    def color(self) -> int:
        raw = str(self.get("brand", "color", default="") or "")
        return int(raw.lstrip("#"), 16) if _HEX.match(raw) else DEFAULT_COLOR


class ConfigStore:
    def __init__(self, premium_check=None) -> None:
        self._overrides: dict[int, dict] = {}
        self._merged: dict[int, GuildConfig] = {}
        # Fonction guild_id -> bool. Par défaut : registre premium global.
        self._premium_check = premium_check

    def _is_premium(self, guild_id: int) -> bool:
        if self._premium_check is not None:
            return self._premium_check(guild_id)
        from bot.premium import premium
        return premium.is_premium(guild_id)

    def invalidate(self, guild_id: int) -> None:
        """À appeler quand le statut premium d'un serveur change."""
        self._merged.pop(guild_id, None)

    def invalidate_all(self) -> None:
        self._merged.clear()

    def has(self, guild_id: int) -> bool:
        """Le serveur a-t-il déjà été configuré (au moins un enregistrement) ?"""
        return guild_id in self._overrides

    def raw(self, guild_id: int) -> GuildConfig:
        """Config telle que l'admin l'a réglée (sans les restrictions de la version gratuite) : pour le panel."""
        return GuildConfig(deep_merge(DEFAULTS, self._overrides.get(guild_id, {})))

    async def load_all(self, db: "Database") -> None:
        rows = await db.fetchall("SELECT guild_id, data FROM guild_config")
        for row in rows:
            try:
                self._overrides[row["guild_id"]] = json.loads(row["data"])
            except json.JSONDecodeError:
                log.error("Config illisible pour le serveur %s : ignorée", row["guild_id"])
        self._merged.clear()
        log.info("Configuration chargée pour %d serveur(s)", len(self._overrides))

    def get(self, guild_id: int) -> GuildConfig:
        """Config effective : celle qu'utilise le bot (restrictions gratuites appliquées si pas Premium)."""
        if guild_id not in self._merged:
            data = deep_merge(DEFAULTS, self._overrides.get(guild_id, {}))
            if not self._is_premium(guild_id):
                data = _apply_free_overrides(data)
            self._merged[guild_id] = GuildConfig(data)
        return self._merged[guild_id]

    async def save(self, db: "Database", guild_id: int, incoming: dict) -> GuildConfig:
        """Valide puis enregistre la config complète d'un serveur."""
        clean = sanitize(incoming)
        await db.execute(
            "INSERT INTO guild_config (guild_id, data) VALUES (?, ?) "
            "ON CONFLICT(guild_id) DO UPDATE SET data=excluded.data",
            (guild_id, json.dumps(clean, ensure_ascii=False)))
        self._overrides[guild_id] = clean
        self._merged.pop(guild_id, None)
        return self.get(guild_id)

    async def update(self, db: "Database", guild_id: int, patch: dict) -> GuildConfig:
        """Modifie seulement quelques valeurs (ex. IDs créés automatiquement)."""
        return await self.save(db, guild_id, deep_merge(self.raw(guild_id).data, patch))


store = ConfigStore()


def _connect_premium() -> None:
    from bot.premium import premium
    premium.on_change(store.invalidate)


_connect_premium()


def gconf(guild: "discord.Guild | int | None") -> GuildConfig:
    """Config du serveur (ou valeurs par défaut si pas de serveur, ex. en DM)."""
    if guild is None:
        return GuildConfig(copy.deepcopy(DEFAULTS))
    return store.get(guild if isinstance(guild, int) else guild.id)
