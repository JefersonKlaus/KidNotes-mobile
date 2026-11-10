"""Groq API client (OpenAI-compatible chat completions) for report drafts.

Every call is logged (logger "reports.ai") so a failure can be diagnosed from
the terminal: the URL, the model, the HTTP status, Groq's own error message
and the request id. The prompt and the answer are NOT logged (they are about
the children), only their sizes; the API key is masked.
"""

import logging
import os
import time
from dataclasses import dataclass, field
from typing import Any

import httpx

logger = logging.getLogger(__name__)

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODELS_URL = "https://api.groq.com/openai/v1/models"
# First choice. Groq retires models from time to time, and a key's project may
# not have access to every model: when Groq answers "model_not_found" /
# "model_decommissioned", the client asks Groq which models the key can use and
# switches to the first one of PREFERRED_MODELS (see `complete`).
# Development: GROQ_MODEL in .env overrides it. Catalog: https://console.groq.com/docs/models
GROQ_MODEL = "llama-3.3-70b-versatile"
# Good at long texts in Portuguese, best first. Reasoning models come last:
# they spend tokens "thinking" before answering.
PREFERRED_MODELS = (
    "llama-3.3-70b-versatile",
    "moonshotai/kimi-k2-instruct-0905",
    "moonshotai/kimi-k2-instruct",
    "meta-llama/llama-4-maverick-17b-128e-instruct",
    "openai/gpt-oss-120b",
    "meta-llama/llama-4-scout-17b-16e-instruct",
    "openai/gpt-oss-20b",
)  # Small models (e.g. llama-3.1-8b-instant) are left out: they invent more.
# Groq error codes meaning "this model can't be used" (the request itself is fine).
MODEL_UNAVAILABLE_CODES = ("model_not_found", "model_decommissioned")
TIMEOUT_SECONDS = 60
LOGGED_BODY_MAX = 2000  # characters of an error response kept in the log
# Response headers that help to understand a failure (rate limits, support tickets).
LOGGED_HEADERS = (
    "x-request-id",
    "retry-after",
    "x-ratelimit-limit-requests",
    "x-ratelimit-remaining-requests",
    "x-ratelimit-reset-requests",
    "x-ratelimit-limit-tokens",
    "x-ratelimit-remaining-tokens",
    "x-ratelimit-reset-tokens",
)


class ReportAIError(Exception):
    """`code`: missing_key, invalid_key, rate_limited, timeout, network, service, empty,
    model (no usable model for this key), ungrounded (the answer wasn't based on the records).

    `detail`: technical explanation for the log (HTTP status, Groq's message...).
    """

    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(f"{code}: {detail}" if detail else code)
        self.code = code
        self.detail = detail


def mask_key(key: str) -> str:
    """Enough of the key to tell which one is used, never the whole key."""
    if not key:
        return "<empty>"
    if len(key) <= 12:
        return f"<{len(key)} chars>"
    return f"{key[:4]}...{key[-4:]} ({len(key)} chars)"


def _redact(text: str, key: str) -> str:
    return text.replace(key, mask_key(key)) if key else text


def _groq_error_code(response: httpx.Response) -> str:
    """Groq's machine-readable error code, e.g. "model_not_found" ("" if none)."""
    try:
        error = response.json().get("error")
    except (ValueError, AttributeError):
        return ""
    return str(error.get("code") or "") if isinstance(error, dict) else ""


def choose_model(available: list[str], rejected: set[str]) -> str | None:
    """The best model of PREFERRED_MODELS that the key can use (None: none of them)."""
    usable = set(available) - rejected
    return next((m for m in PREFERRED_MODELS if m in usable), None)


def _model_options(model: str) -> dict[str, Any]:
    """Extra request fields some model families need."""
    if model.startswith("openai/gpt-oss"):
        # Reasoning model: keep the "thinking" short so the report fits the token limit.
        return {"reasoning_effort": "low"}
    return {}


def _groq_error(response: httpx.Response) -> str:
    """Groq's explanation: `{"error": {"message", "type", "code"}}`, or the raw body."""
    try:
        error = response.json().get("error")
    except (ValueError, AttributeError):
        error = None
    if isinstance(error, dict) and error.get("message"):
        kind = " / ".join(str(error[k]) for k in ("type", "code") if error.get(k))
        return f"{error['message']} [{kind}]" if kind else str(error["message"])
    body = response.text.strip() or "<empty body>"
    if len(body) > LOGGED_BODY_MAX:
        body = body[:LOGGED_BODY_MAX] + "..."
    return body


def _useful_headers(response: httpx.Response) -> dict[str, str]:
    return {name: response.headers[name] for name in LOGGED_HEADERS if name in response.headers}


def default_model() -> str:
    """GROQ_MODEL from the environment (development, `.env`), else the built-in one."""
    return (os.environ.get("GROQ_MODEL") or "").strip() or GROQ_MODEL


@dataclass
class GroqClient:
    api_key: str
    model: str = field(default_factory=default_model)
    transport: httpx.AsyncBaseTransport | None = None  # tests use a mock transport
    url: str = GROQ_URL
    models_url: str = GROQ_MODELS_URL
    # Models Groq refused for this key; the client never switches back to them.
    rejected_models: set[str] = field(default_factory=set)

    async def complete(self, system: str, user: str) -> str:
        if not self.api_key:
            logger.warning("Groq: no API key, nothing was sent.")
            raise ReportAIError("missing_key", "no API key")
        async with httpx.AsyncClient(transport=self.transport, timeout=TIMEOUT_SECONDS) as client:
            try:
                return await self._complete(client, system, user)
            except ReportAIError as error:
                if error.code != "model":
                    raise
            # The model can't be used with this key: switch once and try again.
            replacement = await self._replacement_model(client)
            if replacement is None:
                raise ReportAIError(
                    "model",
                    f"model {self.model!r} is not available for this key and none of "
                    f"{list(PREFERRED_MODELS)} is either (set GROQ_MODEL)",
                )
            logger.warning(
                "Groq: model %r is not available for this key; switching to %r. "
                "To make it permanent, set GROQ_MODEL in reports/ai.py (or .env).",
                self.model, replacement,
            )
            self.model = replacement  # also used for the next students of this run
            return await self._complete(client, system, user)

    async def list_models(self, client: httpx.AsyncClient) -> list[str]:
        """Ids of the models this key can use (GET /models). Empty list on failure."""
        try:
            response = await client.get(
                self.models_url, headers={"Authorization": f"Bearer {self.api_key}"}
            )
        except Exception as error:  # only a diagnosis: never fail because of it
            logger.warning("Groq: could not list the models (%s: %s) url=%s",
                           type(error).__name__, _redact(str(error), self.api_key),
                           self.models_url)
            return []
        if response.status_code >= 400:
            logger.warning("Groq: could not list the models: HTTP %s: %s url=%s",
                           response.status_code,
                           _redact(_groq_error(response), self.api_key), self.models_url)
            return []
        try:
            models = sorted(
                str(m["id"]) for m in response.json()["data"] if m.get("active", True)
            )
        except (ValueError, KeyError, TypeError, AttributeError):
            logger.warning("Groq: unexpected model list: %s",
                           _redact(_groq_error(response), self.api_key))
            return []
        logger.info("Groq: models available for this key (%d): %s", len(models),
                    ", ".join(models))
        return models

    async def _replacement_model(self, client: httpx.AsyncClient) -> str | None:
        self.rejected_models.add(self.model)
        available = await self.list_models(client)
        choice = choose_model(available, self.rejected_models)
        if choice is None and available:
            logger.error(
                "Groq: none of the preferred models %s is available for this key. "
                "Pick one of the available models above and set GROQ_MODEL.",
                list(PREFERRED_MODELS),
            )
        return choice

    async def _complete(self, client: httpx.AsyncClient, system: str, user: str) -> str:
        body = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            # Low: the report must stick to the records, not be creative.
            "temperature": 0.2,
            "max_completion_tokens": 1800,
            **_model_options(self.model),
        }
        logger.info(
            "Groq request: POST %s model=%s key=%s prompt=%d+%d chars",
            self.url, self.model, mask_key(self.api_key), len(system), len(user),
        )
        started = time.monotonic()
        try:
            response = await client.post(
                self.url,
                json=body,
                headers={"Authorization": f"Bearer {self.api_key}"},
            )
        except httpx.TimeoutException as error:
            detail = f"no answer after {TIMEOUT_SECONDS}s ({type(error).__name__}: {error})"
            logger.warning("Groq request failed: %s url=%s", detail, self.url)
            raise ReportAIError("timeout", detail) from error
        except httpx.HTTPError as error:
            # DNS, proxy, firewall, TLS/certificate, connection refused...
            detail = _redact(f"{type(error).__name__}: {error}", self.api_key)
            logger.warning("Groq request failed (network): %s url=%s", detail, self.url)
            raise ReportAIError("network", detail) from error
        except Exception as error:
            # e.g. an invalid character in the key (headers must be ASCII).
            detail = _redact(f"{type(error).__name__}: {error}", self.api_key)
            logger.exception("Groq request could not be sent: %s url=%s", detail, self.url)
            raise ReportAIError("service", detail) from error
        elapsed = time.monotonic() - started

        if response.status_code >= 400:
            detail = f"HTTP {response.status_code}: " + _redact(_groq_error(response), self.api_key)
            logger.warning(
                "Groq error response: %s | url=%s model=%s key=%s elapsed=%.1fs headers=%s",
                detail, self.url, self.model, mask_key(self.api_key), elapsed,
                _useful_headers(response),
            )
            if response.status_code in (401, 403):
                raise ReportAIError("invalid_key", detail)
            if response.status_code == 429:
                raise ReportAIError("rate_limited", detail)
            if _groq_error_code(response) in MODEL_UNAVAILABLE_CODES:
                raise ReportAIError("model", detail)
            raise ReportAIError("service", detail)

        try:
            data: Any = response.json()
            choice = data["choices"][0]
            text = choice["message"]["content"] or ""
        except (ValueError, KeyError, IndexError, TypeError) as error:
            detail = (
                f"HTTP {response.status_code} but unexpected answer format "
                f"({type(error).__name__}: {error}): {_redact(_groq_error(response), self.api_key)}"
            )
            logger.warning("Groq: %s url=%s model=%s", detail, self.url, self.model)
            raise ReportAIError("service", detail) from error

        usage = data.get("usage") or {}
        logger.info(
            "Groq response: HTTP %s in %.1fs model=%s finish_reason=%s answer=%d chars "
            "tokens(prompt=%s, completion=%s) request_id=%s",
            response.status_code, elapsed, data.get("model", self.model),
            choice.get("finish_reason"), len(text), usage.get("prompt_tokens"),
            usage.get("completion_tokens"), response.headers.get("x-request-id"),
        )
        if not text.strip():
            detail = f"empty answer (finish_reason={choice.get('finish_reason')})"
            logger.warning("Groq: %s", detail)
            raise ReportAIError("empty", detail)
        return text
