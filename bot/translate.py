"""Traduction automatique des messages envoyés par le bot (serveurs réglés en anglais).

Le code du bot écrit ses messages en français. Au moment de l'envoi (message, embed, boutons, menus,
formulaires), si le serveur est réglé en anglais dans le panel, les textes sont traduits grâce aux
modèles de `bot/locale_en.py`. Ainsi, aucune commande n'a besoin de connaître la langue.

Les messages composés de plusieurs lignes sont traduits ligne par ligne si le message entier n'est
pas connu ; les parties variables ({}) sont elles-mêmes traduites quand c'est possible.
"""
from __future__ import annotations

import contextlib
import contextvars
import logging
import re
from typing import Any

import discord

from bot.locale_en import MESSAGES_EN

log = logging.getLogger("bot.translate")

_current_lang: contextvars.ContextVar[str] = contextvars.ContextVar("bot_lang", default="fr")
_EXACT: dict[str, str] = {}
_PATTERNS: list[tuple[re.Pattern[str], str]] = []


def _build() -> None:
    from bot.i18n import TEXTS_EN  # textes des panneaux (sans {variables} nommées)
    merged = {k: v for k, v in TEXTS_EN.items() if "{" not in k} | MESSAGES_EN
    templates = []
    for fr, en in merged.items():
        # les espaces autour sont gérés à part (on garde ceux du texte d'origine)
        fr, en = fr.strip(), en.strip()
        if "{}" not in fr:
            _EXACT[fr] = en
            continue
        parts = fr.split("{}")
        regex = "^" + "(.*?)".join(re.escape(p) for p in parts) + "$"
        literal = sum(len(p) for p in parts)
        templates.append((literal, re.compile(regex, re.DOTALL), en))
    # les modèles les plus précis (le plus de texte fixe) d'abord
    templates.sort(key=lambda t: -t[0])
    _PATTERNS.extend((rx, en) for _, rx, en in templates)


_build()


def _fill(template: str, values: list[str]) -> str:
    if re.search(r"\{\d+\}", template):
        return re.sub(r"\{(\d+)\}", lambda m: values[int(m.group(1))], template)
    it = iter(values)
    return re.sub(r"\{\}", lambda m: next(it, ""), template)


def _whole(text: str, depth: int) -> str | None:
    core = text.strip()
    if not core:
        return None
    lead, trail = text[:len(text) - len(text.lstrip())], text[len(text.rstrip()):]
    if core in _EXACT:
        return lead + _EXACT[core] + trail
    if depth > 3:
        return None
    for rx, en in _PATTERNS:
        m = rx.match(core)
        if m:
            values = [translate(g, depth + 1) if g else g for g in m.groups()]
            return lead + _fill(en, values) + trail
    return None


def translate(text: Any, depth: int = 0) -> Any:
    """Traduit un texte français connu ; renvoie le texte inchangé sinon."""
    if not isinstance(text, str) or not text.strip():
        return text
    result = _whole(text, depth)
    if result is not None:
        return result
    if "\n" in text and depth == 0:
        return "\n".join(translate(line, depth) for line in text.split("\n"))
    bullet = _BULLET.match(text)
    if bullet:  # « • texte », « - texte », « > texte »
        rest = _whole(bullet.group(2), depth)
        if rest is not None:
            return bullet.group(1) + rest
    return text


_BULLET = re.compile(r"^(\s*(?:[•\-–>]|\d+\.)\s+)(.+)$", re.DOTALL)


# --------------------------------------------------------------------------- #
#  Langue courante
# --------------------------------------------------------------------------- #
def language_of(guild: discord.Guild | int | None) -> str:
    if guild is None:
        return _current_lang.get()
    from bot.i18n import language
    return language(guild)


@contextlib.contextmanager
def use_language(guild: discord.Guild | int | None):
    """Pour les envois sans serveur évident (messages privés depuis une tâche de fond)."""
    token = _current_lang.set(language_of(guild) if guild is not None else "fr")
    try:
        yield
    finally:
        _current_lang.reset(token)


# --------------------------------------------------------------------------- #
#  Traduction des objets Discord
# --------------------------------------------------------------------------- #
def translate_embed(embed: discord.Embed) -> discord.Embed:
    if embed.title:
        embed.title = translate(embed.title)
    if embed.description:
        embed.description = translate(embed.description)
    for i, field in enumerate(list(embed.fields)):
        embed.set_field_at(i, name=translate(field.name), value=translate(field.value), inline=field.inline)
    if embed.footer and embed.footer.text:
        embed.set_footer(text=translate(embed.footer.text), icon_url=embed.footer.icon_url)
    if embed.author and embed.author.name:
        embed.set_author(name=translate(embed.author.name), url=embed.author.url, icon_url=embed.author.icon_url)
    return embed


def _translate_item(item: Any) -> None:
    inner = getattr(item, "item", None)  # DynamicItem
    if inner is not None and inner is not item:
        _translate_item(inner)
    if isinstance(item, discord.ui.Button) and item.label:
        item.label = translate(item.label)
    elif isinstance(item, discord.ui.Select):
        if item.placeholder:
            item.placeholder = translate(item.placeholder)
        for option in item.options:
            option.label = translate(option.label)
            if option.description:
                option.description = translate(option.description)
    elif isinstance(item, discord.ui.TextInput):
        item.label = translate(item.label)
        if item.placeholder:
            item.placeholder = translate(item.placeholder)


def translate_view(view: Any) -> Any:
    if view is not None and hasattr(view, "children"):
        for item in view.children:
            _translate_item(item)
    return view


def _translate_kwargs(kwargs: dict) -> None:
    if isinstance(kwargs.get("content"), str):
        kwargs["content"] = translate(kwargs["content"])
    if isinstance(kwargs.get("embed"), discord.Embed):
        translate_embed(kwargs["embed"])
    if isinstance(kwargs.get("embeds"), list):
        for e in kwargs["embeds"]:
            if isinstance(e, discord.Embed):
                translate_embed(e)
    if kwargs.get("view") is not None:
        translate_view(kwargs["view"])


# --------------------------------------------------------------------------- #
#  Branchement sur discord.py (une seule fois au démarrage)
# --------------------------------------------------------------------------- #
def install() -> None:
    if getattr(discord, "_bot_translate_installed", False):
        return
    discord._bot_translate_installed = True  # type: ignore[attr-defined]

    def guild_of(obj: Any) -> Any:
        return getattr(obj, "guild", None)

    # 1) Salons, membres, messages privés : Messageable.send
    original_send = discord.abc.Messageable.send

    async def send(self, content=None, **kwargs):
        if language_of(guild_of(self)) == "en":
            kwargs["content"] = content
            _translate_kwargs(kwargs)
            content = kwargs.pop("content")
        return await original_send(self, content, **kwargs)

    discord.abc.Messageable.send = send  # type: ignore[method-assign]

    # 2) Réponses aux interactions (commandes, boutons, menus, formulaires)
    response_cls = discord.InteractionResponse

    def remember(self) -> str:
        lang = language_of(getattr(self._parent, "guild", None) or getattr(self._parent, "guild_id", None))
        _current_lang.set(lang)
        return lang

    original_send_message = response_cls.send_message

    async def send_message(self, content=None, **kwargs):
        if remember(self) == "en":
            kwargs["content"] = content
            _translate_kwargs(kwargs)
            content = kwargs.pop("content")
        return await original_send_message(self, content, **kwargs)

    original_edit_message = response_cls.edit_message

    async def edit_message(self, **kwargs):
        if remember(self) == "en":
            _translate_kwargs(kwargs)
        return await original_edit_message(self, **kwargs)

    original_send_modal = response_cls.send_modal

    async def send_modal(self, modal):
        if remember(self) == "en":
            modal.title = translate(modal.title)
            translate_view(modal)
        return await original_send_modal(self, modal)

    original_defer = response_cls.defer

    async def defer(self, **kwargs):
        remember(self)
        return await original_defer(self, **kwargs)

    response_cls.send_message = send_message  # type: ignore[method-assign]
    response_cls.edit_message = edit_message  # type: ignore[method-assign]
    response_cls.send_modal = send_modal  # type: ignore[method-assign]
    response_cls.defer = defer  # type: ignore[method-assign]

    # 3) Messages de suivi (followup) et modifications : langue mémorisée par la réponse
    original_webhook_send = discord.Webhook.send

    async def webhook_send(self, content=discord.utils.MISSING, **kwargs):
        if _current_lang.get() == "en":
            if isinstance(content, str):
                content = translate(content)
            _translate_kwargs(kwargs)
        return await original_webhook_send(self, content, **kwargs)

    discord.Webhook.send = webhook_send  # type: ignore[method-assign]

    original_edit_original = discord.Interaction.edit_original_response

    async def edit_original_response(self, **kwargs):
        if language_of(self.guild or self.guild_id) == "en":
            _translate_kwargs(kwargs)
        return await original_edit_original(self, **kwargs)

    discord.Interaction.edit_original_response = edit_original_response  # type: ignore[method-assign]

    for cls in (discord.Message, discord.PartialMessage):
        original_edit = cls.edit

        def make(original):
            async def edit(self, **kwargs):
                if language_of(guild_of(self)) == "en":
                    _translate_kwargs(kwargs)
                return await original(self, **kwargs)
            return edit

        cls.edit = make(original_edit)  # type: ignore[method-assign]
    log.info("Traduction automatique des messages activée (serveurs réglés en anglais)")
