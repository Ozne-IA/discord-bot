"""Contact du propriétaire du bot : e-mail public et formulaire /contact (bug, idée, autre)."""
from __future__ import annotations

import os
import time

DEFAULT_EMAIL = "cerbere.bot.discord@gmail.com"
COOLDOWN = 10 * 60          # un message toutes les 10 min par personne
KINDS = {
    "bug": ("🐛", "Un module ne marche pas"),
    "idea": ("💡", "Une idée"),
    "other": ("✉️", "Autre chose"),
}


def contact_email() -> str:
    """E-mail public : CONTACT_EMAIL, sinon CONTACT s'il contient un e-mail, sinon l'adresse par défaut."""
    for name in ("CONTACT_EMAIL", "CONTACT"):
        value = os.getenv(name, "").strip()
        if "@" in value and " " not in value and not value.startswith("http"):
            return value
    return DEFAULT_EMAIL


def public_contact() -> str:
    """Ce qu'affichent les pages du site : CONTACT (e-mail ou lien), sinon l'e-mail."""
    return os.getenv("CONTACT", "").strip() or contact_email()


class Cooldown:
    def __init__(self, seconds: float = COOLDOWN):
        self.seconds = seconds
        self.last: dict[int, float] = {}

    def remaining(self, user_id: int, now: float | None = None) -> float:
        now = time.time() if now is None else now
        return max(0.0, self.seconds - (now - self.last.get(user_id, -1e18)))

    def hit(self, user_id: int, now: float | None = None) -> None:
        now = time.time() if now is None else now
        self.last[user_id] = now
        if len(self.last) > 5000:
            self.last = {u: t for u, t in self.last.items() if now - t < self.seconds}


def format_report(kind: str, subject: str, message: str, user: str, user_id: int,
                  guild: str | None, guild_id: int | None) -> tuple[str, str]:
    """Titre et texte du message envoyé au propriétaire."""
    emoji, label = KINDS.get(kind, KINDS["other"])
    where = f"**{guild}** (`{guild_id}`)" if guild else "message privé"
    text = (f"**De :** {user} (`{user_id}`) · <@{user_id}>\n**Serveur :** {where}\n"
            f"**Sujet :** {subject.strip()[:100]}\n\n{message.strip()[:3000]}")
    return f"{emoji} Contact · {label}", text
