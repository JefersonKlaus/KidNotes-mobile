"""Groq API client (OpenAI-compatible chat completions) for report drafts."""

from dataclasses import dataclass

import httpx

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
# Change here if Groq retires the model: https://console.groq.com/docs/models
GROQ_MODEL = "llama-3.3-70b-versatile"
TIMEOUT_SECONDS = 60


class ReportAIError(Exception):
    """`code`: missing_key, invalid_key, rate_limited, timeout, network, service, empty."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass
class GroqClient:
    api_key: str
    model: str = GROQ_MODEL
    transport: httpx.AsyncBaseTransport | None = None  # tests use a mock transport

    async def complete(self, system: str, user: str) -> str:
        if not self.api_key:
            raise ReportAIError("missing_key")
        body = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": 0.4,
            "max_completion_tokens": 1800,
        }
        try:
            async with httpx.AsyncClient(
                transport=self.transport, timeout=TIMEOUT_SECONDS
            ) as client:
                response = await client.post(
                    GROQ_URL,
                    json=body,
                    headers={"Authorization": f"Bearer {self.api_key}"},
                )
        except httpx.TimeoutException as error:
            raise ReportAIError("timeout") from error
        except httpx.HTTPError as error:
            raise ReportAIError("network") from error
        if response.status_code in (401, 403):
            raise ReportAIError("invalid_key")
        if response.status_code == 429:
            raise ReportAIError("rate_limited")
        if response.status_code >= 400:
            raise ReportAIError("service")
        try:
            text = response.json()["choices"][0]["message"]["content"] or ""
        except (ValueError, KeyError, IndexError, TypeError) as error:
            raise ReportAIError("service") from error
        if not text.strip():
            raise ReportAIError("empty")
        return text
