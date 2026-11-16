"""Chiffrement des secrets confiés par les serveurs (clés d'API d'IA).

La clé de chiffrement vient de la variable AI_KEYS_SECRET (à garder précieusement : si elle change ou se
perd, les clés déjà enregistrées deviennent illisibles et les admins doivent les recoller).
N'importe quelle phrase longue convient ; une clé Fernet (44 caractères) est utilisée telle quelle.
"""
from __future__ import annotations

import base64
import hashlib
import os

from cryptography.fernet import Fernet, InvalidToken

MIN_SECRET_LENGTH = 16


class SecretError(Exception):
    pass


def _fernet() -> Fernet | None:
    secret = os.getenv("AI_KEYS_SECRET", "").strip()
    if len(secret) < MIN_SECRET_LENGTH:
        return None
    try:
        return Fernet(secret.encode())
    except (ValueError, TypeError):
        # Une phrase quelconque : on en dérive une clé de 32 octets
        return Fernet(base64.urlsafe_b64encode(hashlib.sha256(secret.encode()).digest()))


def available() -> bool:
    return _fernet() is not None


def encrypt(text: str) -> str:
    f = _fernet()
    if f is None:
        raise SecretError("Le chiffrement n'est pas configuré (AI_KEYS_SECRET manquant).")
    return f.encrypt(text.encode()).decode()


def decrypt(token: str) -> str:
    f = _fernet()
    if f is None:
        raise SecretError("Le chiffrement n'est pas configuré (AI_KEYS_SECRET manquant).")
    try:
        return f.decrypt(token.encode()).decode()
    except InvalidToken:
        raise SecretError("Clé illisible : AI_KEYS_SECRET a changé depuis son enregistrement.") from None


def hint(key: str) -> str:
    """Version masquée affichable : « sk-…a4f2 »."""
    key = key.strip()
    if len(key) <= 8:
        return "…" + key[-2:]
    return f"{key[:3]}…{key[-4:]}"
