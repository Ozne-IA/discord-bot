"""Appels à l'API Twitch (Helix) et gestion des jetons.

- Jeton d'application (client_credentials) : abonnements EventSub. Ne se rafraîchit pas : on en redemande un.
- Jetons utilisateur (compte bot, streamers) : le jeton de rafraîchissement est stocké CHIFFRÉ (secrets_box) ;
  Twitch peut en renvoyer un nouveau à chaque rafraîchissement, qu'on réenregistre.
"""
from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING, Any

import aiohttp

from bot import secrets_box, twitch

if TYPE_CHECKING:
    from bot.db import Database

log = logging.getLogger("bot.twitch_api")
TIMEOUT = aiohttp.ClientTimeout(total=20)


class TwitchError(Exception):
    def __init__(self, message: str, status: int = 0):
        super().__init__(message)
        self.status = status


class TwitchAPI:
    def __init__(self, db: "Database", http: aiohttp.ClientSession):
        self.db = db
        self.http = http
        self._app: tuple[str, float] | None = None
        self._users: dict[tuple[int, str], tuple[str, float]] = {}  # (user_id, kind) -> (jeton, expiration)

    # ------------------------------------------------------------------ #
    #  Jetons
    # ------------------------------------------------------------------ #
    async def _post_token(self, data: dict) -> dict:
        data = {"client_id": twitch.client_id(), "client_secret": twitch.client_secret(), **data}
        try:
            async with self.http.post(twitch.TOKEN_URL, data=data, timeout=TIMEOUT) as resp:
                body = await resp.json(content_type=None)
                if resp.status != 200:
                    raise TwitchError("Twitch a refusé la connexion.", resp.status)
                return body
        except (aiohttp.ClientError, TimeoutError, ValueError):
            raise TwitchError("Twitch est injoignable pour le moment.") from None

    async def app_token(self) -> str:
        if self._app and self._app[1] > time.time() + 300:
            return self._app[0]
        data = await self._post_token({"grant_type": "client_credentials"})
        self._app = (data["access_token"], time.time() + int(data.get("expires_in", 3600)))
        return self._app[0]

    async def exchange_code(self, code: str, redirect_uri: str) -> dict:
        return await self._post_token({"grant_type": "authorization_code", "code": code,
                                       "redirect_uri": redirect_uri})

    async def validate(self, access_token: str) -> dict | None:
        """Infos du jeton (user_id, login, scopes), ou None s'il n'est plus valable."""
        try:
            async with self.http.get(twitch.VALIDATE_URL, headers={"Authorization": f"OAuth {access_token}"},
                                     timeout=TIMEOUT) as resp:
                if resp.status != 200:
                    return None
                return await resp.json(content_type=None)
        except (aiohttp.ClientError, TimeoutError, ValueError):
            raise TwitchError("Twitch est injoignable pour le moment.") from None

    async def store_user(self, kind: str, info: dict, tokens: dict) -> None:
        """Enregistre un compte autorisé (bot ou streamer) avec son jeton de rafraîchissement chiffré."""
        user_id = int(info["user_id"])
        await self.db.execute(
            "INSERT INTO twitch_tokens (user_id, kind, login, refresh_enc, scopes, updated_at) VALUES (?,?,?,?,?,?) "
            "ON CONFLICT(user_id, kind) DO UPDATE SET login=excluded.login, refresh_enc=excluded.refresh_enc, "
            "scopes=excluded.scopes, updated_at=excluded.updated_at",
            (user_id, kind, info.get("login") or "", secrets_box.encrypt(tokens["refresh_token"]),
             " ".join(info.get("scopes") or tokens.get("scope") or []), time.time()))
        self._users[(user_id, kind)] = (tokens["access_token"], time.time() + int(tokens.get("expires_in", 3600)))
        if kind == "bot":
            # Un seul compte bot : on oublie les anciens
            await self.db.execute("DELETE FROM twitch_tokens WHERE kind='bot' AND user_id != ?", (user_id,))

    async def bot_account(self) -> dict | None:
        row = await self.db.fetchone("SELECT user_id, login, scopes FROM twitch_tokens WHERE kind='bot' LIMIT 1")
        return dict(row) if row else None

    async def user_token(self, user_id: int, kind: str) -> str:
        cached = self._users.get((user_id, kind))
        if cached and cached[1] > time.time() + 120:
            return cached[0]
        row = await self.db.fetchone("SELECT refresh_enc FROM twitch_tokens WHERE user_id=? AND kind=?",
                                     (user_id, kind))
        if not row:
            raise TwitchError("Compte Twitch non connecté.", 401)
        try:
            refresh = secrets_box.decrypt(row["refresh_enc"])
        except secrets_box.SecretError as exc:
            raise TwitchError(str(exc), 401) from None
        try:
            data = await self._post_token({"grant_type": "refresh_token", "refresh_token": refresh})
        except TwitchError as exc:
            if exc.status in (400, 401):
                raise TwitchError("L'autorisation Twitch a été retirée : il faut reconnecter le compte.", 401) from None
            raise
        await self.db.execute("UPDATE twitch_tokens SET refresh_enc=?, updated_at=? WHERE user_id=? AND kind=?",
                              (secrets_box.encrypt(data.get("refresh_token") or refresh), time.time(), user_id, kind))
        self._users[(user_id, kind)] = (data["access_token"], time.time() + int(data.get("expires_in", 3600)))
        return data["access_token"]

    def forget(self, user_id: int, kind: str) -> None:
        self._users.pop((user_id, kind), None)

    # ------------------------------------------------------------------ #
    #  Helix
    # ------------------------------------------------------------------ #
    async def helix(self, method: str, path: str, *, token: str, params: Any = None, json: Any = None) -> tuple[int, Any]:
        headers = {"Client-Id": twitch.client_id(), "Authorization": f"Bearer {token}"}
        try:
            async with self.http.request(method, twitch.HELIX + path, headers=headers, params=params, json=json,
                                         timeout=TIMEOUT) as resp:
                text = await resp.text()
                try:
                    data = await resp.json(content_type=None) if text else None
                except ValueError:
                    data = None
                return resp.status, data
        except (aiohttp.ClientError, TimeoutError):
            raise TwitchError("Twitch est injoignable pour le moment.") from None

    async def _as_bot(self, method: str, path: str, **kwargs) -> tuple[int, Any]:
        bot = await self.bot_account()
        if not bot:
            raise TwitchError("Le compte Twitch du bot n'est pas encore connecté.", 401)
        token = await self.user_token(bot["user_id"], "bot")
        status, data = await self.helix(method, path, token=token, **kwargs)
        if status == 401:  # jeton expiré entre-temps : un nouvel essai
            self.forget(bot["user_id"], "bot")
            token = await self.user_token(bot["user_id"], "bot")
            status, data = await self.helix(method, path, token=token, **kwargs)
        return status, data

    @staticmethod
    def _explain(status: int, data: Any) -> TwitchError:
        message = (data or {}).get("message", "") if isinstance(data, dict) else ""
        if status == 403:
            return TwitchError("Le bot n'est pas modérateur de cette chaîne : tape /mod <nom du bot> dans le chat.", 403)
        if status == 429:
            return TwitchError("Twitch limite les actions : réessaie dans une minute.", 429)
        if status == 400 and message:
            return TwitchError(f"Twitch a refusé : {message[:200]}", 400)
        return TwitchError(f"Twitch a refusé l'action (erreur {status}).", status)

    async def _moderator_id(self) -> int:
        bot = await self.bot_account()
        if not bot:
            raise TwitchError("Le compte Twitch du bot n'est pas encore connecté.", 401)
        return int(bot["user_id"])

    async def ban(self, broadcaster_id: int, user_id: int, reason: str, duration: int | None = None) -> None:
        """Ban définitif (duration=None) ou timeout de `duration` secondes (1 à 1 209 600)."""
        mod = await self._moderator_id()
        body: dict[str, Any] = {"user_id": str(user_id), "reason": reason[:500]}
        if duration:
            body["duration"] = max(1, min(int(duration), 1_209_600))
        status, data = await self._as_bot("POST", "/moderation/bans", json={"data": body},
                                          params={"broadcaster_id": str(broadcaster_id), "moderator_id": str(mod)})
        if status != 200:
            raise self._explain(status, data)

    async def unban(self, broadcaster_id: int, user_id: int) -> None:
        mod = await self._moderator_id()
        status, data = await self._as_bot("DELETE", "/moderation/bans", params={
            "broadcaster_id": str(broadcaster_id), "moderator_id": str(mod), "user_id": str(user_id)})
        if status not in (204, 200):
            raise self._explain(status, data)

    async def delete_message(self, broadcaster_id: int, message_id: str) -> None:
        mod = await self._moderator_id()
        status, data = await self._as_bot("DELETE", "/moderation/chat", params={
            "broadcaster_id": str(broadcaster_id), "moderator_id": str(mod), "message_id": message_id})
        if status not in (204, 200):
            raise self._explain(status, data)

    async def send_message(self, broadcaster_id: int, text: str) -> None:
        mod = await self._moderator_id()
        status, data = await self._as_bot("POST", "/chat/messages", json={
            "broadcaster_id": str(broadcaster_id), "sender_id": str(mod), "message": text[:500]})
        if status != 200:
            raise self._explain(status, data)

    async def is_moderator(self, broadcaster_id: int) -> bool | None:
        """Le bot est-il modérateur de la chaîne ? None si on ne peut pas le savoir."""
        bot = await self.bot_account()
        if not bot:
            return None
        if int(bot["user_id"]) == int(broadcaster_id):
            return True
        try:
            token = await self.user_token(int(broadcaster_id), "broadcaster")
        except TwitchError:
            return None
        status, data = await self.helix("GET", "/moderation/moderators", token=token, params={
            "broadcaster_id": str(broadcaster_id), "user_id": str(bot["user_id"])})
        if status != 200:
            return None
        return bool((data or {}).get("data"))

    # ------------------------------------------------------------------ #
    #  Abonnements EventSub (webhook)
    # ------------------------------------------------------------------ #
    async def list_subscriptions(self) -> list[dict]:
        token = await self.app_token()
        out: list[dict] = []
        cursor = None
        for _ in range(50):
            params = {"after": cursor} if cursor else None
            status, data = await self.helix("GET", "/eventsub/subscriptions", token=token, params=params)
            if status != 200:
                raise self._explain(status, data)
            out.extend((data or {}).get("data") or [])
            cursor = ((data or {}).get("pagination") or {}).get("cursor")
            if not cursor:
                break
        return out

    async def subscribe(self, sub_type: str, version: str, condition: dict, callback: str, secret: str) -> int:
        token = await self.app_token()
        status, data = await self.helix("POST", "/eventsub/subscriptions", token=token, json={
            "type": sub_type, "version": version, "condition": condition,
            "transport": {"method": "webhook", "callback": callback, "secret": secret}})
        if status not in (202, 409):  # 409 = existe déjà
            log.warning("Abonnement Twitch %s refusé (%s) : %s", sub_type, status,
                        (data or {}).get("message") if isinstance(data, dict) else "")
        return status

    async def unsubscribe(self, sub_id: str) -> None:
        token = await self.app_token()
        await self.helix("DELETE", "/eventsub/subscriptions", token=token, params={"id": sub_id})
