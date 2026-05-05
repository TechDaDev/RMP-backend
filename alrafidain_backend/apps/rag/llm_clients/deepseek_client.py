"""
DeepSeek API client for the RAG layer.

Uses httpx for synchronous HTTP calls.
Raises clean exceptions on configuration or API errors.
"""

from __future__ import annotations

from typing import Any

import httpx
from django.conf import settings


class DeepSeekConfigError(Exception):
    """Raised when the DeepSeek API key is missing or misconfigured."""


class DeepSeekAPIError(Exception):
    """Raised when the DeepSeek API returns an unexpected response."""


class DeepSeekClient:
    """Thin synchronous client for the DeepSeek Chat Completions API."""

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        timeout: int | None = None,
    ) -> None:
        self.api_key = api_key or getattr(settings, "DEEPSEEK_API_KEY", "")
        self.base_url = (
            base_url or getattr(settings, "DEEPSEEK_BASE_URL", "https://api.deepseek.com")
        ).rstrip("/")
        self.model = model or getattr(settings, "DEEPSEEK_MODEL", "deepseek-chat")
        self.timeout = timeout or getattr(settings, "DEEPSEEK_TIMEOUT_SECONDS", 60)

        if not self.api_key:
            raise DeepSeekConfigError(
                "DEEPSEEK_API_KEY is not configured. Set it in your environment or settings file."
            )

    def chat(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.2,
        max_tokens: int = 1200,
    ) -> dict[str, Any]:
        """
        Send a chat completion request to the DeepSeek API.

        Args:
            messages: List of {role, content} dicts.
            temperature: Sampling temperature (0–1).
            max_tokens: Maximum tokens for the response.

        Returns:
            Normalized dict: {content, model, usage: {prompt_tokens, completion_tokens}, raw}

        Raises:
            DeepSeekAPIError: On non-200 responses or malformed JSON.
            httpx.TimeoutException: On request timeout.
        """
        url = f"{self.base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        try:
            with httpx.Client(timeout=self.timeout) as client:
                response = client.post(url, json=payload, headers=headers)
        except httpx.TimeoutException as exc:
            raise httpx.TimeoutException(
                f"DeepSeek API request timed out after {self.timeout}s."
            ) from exc

        if response.status_code != 200:
            raise DeepSeekAPIError(
                f"DeepSeek API returned status {response.status_code}: {response.text[:500]}"
            )

        try:
            data = response.json()
        except Exception as exc:
            raise DeepSeekAPIError(
                f"DeepSeek API returned malformed JSON: {response.text[:500]}"
            ) from exc

        try:
            content = data["choices"][0]["message"]["content"]
            model_name = data.get("model", self.model)
            usage = data.get("usage", {})
            return {
                "content": content,
                "model": model_name,
                "usage": {
                    "prompt_tokens": usage.get("prompt_tokens", 0),
                    "completion_tokens": usage.get("completion_tokens", 0),
                },
                "raw": data,
            }
        except (KeyError, IndexError) as exc:
            raise DeepSeekAPIError(
                f"DeepSeek API response missing expected fields: {data}"
            ) from exc


_default_client: DeepSeekClient | None = None


def get_default_deepseek_client() -> DeepSeekClient:
    """Return the module-level singleton DeepSeek client."""
    global _default_client  # noqa: PLW0603
    if _default_client is None:
        _default_client = DeepSeekClient()
    return _default_client
