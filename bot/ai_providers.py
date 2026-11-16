"""IA branchée par chaque serveur avec sa propre clé : ChatGPT (OpenAI), Mistral, Gemini (Google), Claude (Anthropic).

Deux opérations par fournisseur :
  - list_models(...)  : vérifie la clé et renvoie les modèles utilisables (jamais écrits « en dur ») ;
  - generate(...)     : une consigne (system) + une question → le texte de la réponse.

Les messages d'erreur sont pensés pour l'admin du serveur et ne contiennent JAMAIS la clé.
"""
from __future__ import annotations

import logging
import re
from typing import Any

import aiohttp
import anthropic

log = logging.getLogger("bot.ai_providers")

TIMEOUT = aiohttp.ClientTimeout(total=90)

PROVIDERS: dict[str, dict[str, str]] = {
    "openai": {"name": "ChatGPT (OpenAI)", "key_url": "https://platform.openai.com/api-keys", "prefix": "sk-"},
    "mistral": {"name": "Mistral", "key_url": "https://console.mistral.ai/api-keys", "prefix": ""},
    "gemini": {"name": "Gemini (Google)", "key_url": "https://aistudio.google.com/apikey", "prefix": ""},
    "anthropic": {"name": "Claude (Anthropic)", "key_url": "https://platform.claude.com/settings/keys",
                  "prefix": "sk-ant-"},
}

# Modèles qui ne servent pas à discuter (images, voix, embeddings…) : retirés des listes
NOT_CHAT = ("embed", "whisper", "tts", "dall-e", "image", "audio", "realtime", "moderation", "transcribe",
            "search", "ocr", "aqa", "imagen", "veo", "computer-use", "babbage", "davinci")


class ProviderError(Exception):
    """Erreur affichable telle quelle à l'admin. kind : auth, quota, model, refused, unavailable."""

    def __init__(self, message: str, kind: str = "unavailable"):
        super().__init__(message)
        self.kind = kind


_MODEL_RE = re.compile(r"^[A-Za-z0-9][\w.:\-]{0,99}$")


def valid_model(model: str) -> bool:
    """Nom de modèle sûr (il finit dans une adresse web pour Gemini)."""
    return bool(_MODEL_RE.match(model or "")) and ".." not in model


def provider_name(provider: str) -> str:
    return PROVIDERS.get(provider, {}).get("name", provider)


def _chat_model(model_id: str) -> bool:
    low = model_id.lower()
    return not any(word in low for word in NOT_CHAT)


def _status_error(provider: str, status: int, body: str = "") -> ProviderError:
    name = provider_name(provider)
    low = body.lower()
    if status in (401, 403):
        return ProviderError(f"Clé refusée par {name} : vérifie-la (ou recrée-la) dans le panel.", "auth")
    if status == 402 or "billing" in low or "credit" in low or "insufficient_quota" in low:
        return ProviderError(f"Plus de crédit chez {name} : ajoute du crédit sur ton compte {name}.", "quota")
    if status == 429:
        return ProviderError(f"{name} limite les demandes (quota ou trop de questions d'un coup). Réessaie plus tard.",
                             "quota")
    if status in (400, 404) and "model" in low:
        return ProviderError(f"Le modèle choisi n'existe plus chez {name} : choisis-en un autre dans le panel.",
                             "model")
    if status >= 500:
        return ProviderError(f"{name} a un souci de son côté, réessaie dans quelques minutes.")
    return ProviderError(f"{name} a refusé la demande (erreur {status}).")


async def _request(http: aiohttp.ClientSession, provider: str, method: str, url: str, *,
                   headers: dict[str, str], json: Any = None) -> Any:
    try:
        async with http.request(method, url, headers=headers, json=json, timeout=TIMEOUT) as resp:
            text = await resp.text()
            if resp.status >= 400:
                # Le corps n'est jamais journalisé pour les erreurs de clé (il pourrait en citer un morceau)
                if resp.status not in (401, 403):
                    log.info("%s : erreur %d %s", provider, resp.status, text[:300])
                raise _status_error(provider, resp.status, text)
            try:
                return await resp.json(content_type=None)
            except ValueError:
                raise ProviderError(f"Réponse illisible de {provider_name(provider)}.") from None
    except (aiohttp.ClientError, TimeoutError):
        raise ProviderError(f"Impossible de joindre {provider_name(provider)} pour le moment.") from None


# --------------------------------------------------------------------------- #
#  Liste des modèles (sert aussi à vérifier la clé)
# --------------------------------------------------------------------------- #
async def list_models(provider: str, key: str, http: aiohttp.ClientSession) -> list[str]:
    if provider == "openai":
        data = await _request(http, provider, "GET", "https://api.openai.com/v1/models",
                              headers={"Authorization": f"Bearer {key}"})
        ids = [m.get("id", "") for m in data.get("data", []) if isinstance(m, dict)]
        ids = [i for i in ids if i.startswith(("gpt", "o", "chatgpt")) and _chat_model(i)]
    elif provider == "mistral":
        data = await _request(http, provider, "GET", "https://api.mistral.ai/v1/models",
                              headers={"Authorization": f"Bearer {key}"})
        items = data.get("data", []) if isinstance(data, dict) else data
        ids = [m.get("id", "") for m in items if isinstance(m, dict) and not m.get("archived")
               and (m.get("capabilities") or {}).get("completion_chat", True)]
        ids = [i for i in ids if _chat_model(i)]
    elif provider == "gemini":
        data = await _request(http, provider, "GET",
                              "https://generativelanguage.googleapis.com/v1beta/models?pageSize=1000",
                              headers={"x-goog-api-key": key})
        ids = [str(m.get("name", "")).removeprefix("models/") for m in data.get("models", [])
               if isinstance(m, dict) and "generateContent" in (m.get("supportedGenerationMethods") or [])]
        ids = [i for i in ids if i and _chat_model(i)]
    elif provider == "anthropic":
        client = anthropic.AsyncAnthropic(api_key=key, max_retries=1, timeout=30.0)
        try:
            ids = [m.id async for m in client.models.list()]
        except anthropic.AuthenticationError:
            raise _status_error(provider, 401) from None
        except anthropic.PermissionDeniedError:
            raise _status_error(provider, 403) from None
        except anthropic.RateLimitError:
            raise _status_error(provider, 429) from None
        except anthropic.APIStatusError as exc:
            raise _status_error(provider, exc.status_code, str(exc.message)) from None
        except anthropic.APIConnectionError:
            raise ProviderError(f"Impossible de joindre {provider_name(provider)} pour le moment.") from None
        finally:
            await client.close()
    else:
        raise ProviderError("Fournisseur d'IA inconnu.")
    return sorted(set(ids), key=lambda s: s.lower())


# --------------------------------------------------------------------------- #
#  Génération d'une réponse
# --------------------------------------------------------------------------- #
async def generate(provider: str, key: str, model: str, system: str, prompt: str,
                   http: aiohttp.ClientSession, max_tokens: int = 2000) -> str:
    if not valid_model(model):
        raise ProviderError("Aucun modèle choisi : choisis-en un dans le panel (onglet Assistant IA).", "model")
    if provider in ("openai", "mistral"):
        url = ("https://api.openai.com/v1/chat/completions" if provider == "openai"
               else "https://api.mistral.ai/v1/chat/completions")
        body: dict[str, Any] = {"model": model, "messages": [{"role": "system", "content": system},
                                                             {"role": "user", "content": prompt}]}
        # OpenAI : max_completion_tokens (inclut le raisonnement des modèles « o ») ; Mistral : max_tokens
        body["max_completion_tokens" if provider == "openai" else "max_tokens"] = max_tokens * (
            4 if provider == "openai" else 1)
        data = await _request(http, provider, "POST", url, headers={"Authorization": f"Bearer {key}"}, json=body)
        try:
            content = data["choices"][0]["message"].get("content") or ""
        except (KeyError, IndexError, TypeError, AttributeError):
            content = ""
        if isinstance(content, list):  # certains modèles renvoient des morceaux
            content = "".join(part.get("text", "") for part in content if isinstance(part, dict))
        text = str(content).strip()
    elif provider == "gemini":
        body = {"systemInstruction": {"parts": [{"text": system}]},
                "contents": [{"role": "user", "parts": [{"text": prompt}]}],
                # marge : sur les modèles qui « réfléchissent », la réflexion compte dans ce plafond
                "generationConfig": {"maxOutputTokens": max_tokens * 4}}
        data = await _request(http, provider, "POST",
                              f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
                              headers={"x-goog-api-key": key}, json=body)
        candidates = data.get("candidates") or []
        if not candidates:
            if (data.get("promptFeedback") or {}).get("blockReason"):
                raise ProviderError("Gemini a refusé de répondre à cette demande.", "refused")
            text = ""
        else:
            parts = ((candidates[0].get("content") or {}).get("parts")) or []
            text = "".join(p.get("text", "") for p in parts if isinstance(p, dict) and not p.get("thought")).strip()
    elif provider == "anthropic":
        client = anthropic.AsyncAnthropic(api_key=key, max_retries=1, timeout=90.0)
        try:
            response = await client.messages.create(
                model=model, max_tokens=max_tokens * 4, system=system,
                messages=[{"role": "user", "content": prompt}])
        except anthropic.AuthenticationError:
            raise _status_error(provider, 401) from None
        except anthropic.PermissionDeniedError:
            raise _status_error(provider, 403) from None
        except anthropic.RateLimitError:
            raise _status_error(provider, 429) from None
        except anthropic.NotFoundError:
            raise _status_error(provider, 404, "model") from None
        except anthropic.APIStatusError as exc:
            raise _status_error(provider, exc.status_code, str(exc.message)) from None
        except anthropic.APIConnectionError:
            raise ProviderError(f"Impossible de joindre {provider_name(provider)} pour le moment.") from None
        finally:
            await client.close()
        if response.stop_reason == "refusal":
            raise ProviderError("Claude a refusé de répondre à cette demande.", "refused")
        text = "".join(b.text for b in response.content if b.type == "text").strip()
    else:
        raise ProviderError("Fournisseur d'IA inconnu.")
    if not text:
        raise ProviderError("L'IA n'a rien répondu, reformule ta question.")
    return text
