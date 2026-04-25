"""Lightweight OpenAI-compatible chat completions client."""

from __future__ import annotations

import json
import os
import random
import re
import threading
import time
from typing import Any, Protocol

import httpx

from app.core.config import AppSettings


# 全局并发闸：避免在并行 propose/revise 时打爆上游限流
_DEFAULT_CONCURRENCY = int(os.getenv("OPENAI_MAX_CONCURRENCY", "3"))
_concurrency_gate = threading.Semaphore(_DEFAULT_CONCURRENCY)


class ChatModelClient(Protocol):
    """Protocol used by agents for structured JSON generations."""

    def generate_json(self, *, system_prompt: str, user_prompt: str) -> dict[str, Any]:
        """Return one parsed JSON object from the model response."""


class OpenAIChatCompletionsClient:
    """Small client for OpenAI-compatible chat completions endpoints."""

    def __init__(
        self,
        *,
        endpoint: str,
        api_key: str,
        model: str,
        timeout_seconds: float = 30.0,
    ) -> None:
        self.endpoint = self._resolve_endpoint(endpoint)
        self.api_key = api_key
        self.model = model
        self.timeout_seconds = timeout_seconds

    @classmethod
    def from_settings(cls, settings: AppSettings) -> "OpenAIChatCompletionsClient | None":
        """Build a client from app settings when model access is configured."""

        if not settings.llm_enabled:
            return None
        if not settings.openai_api_key or not settings.openai_api_base or not settings.openai_model:
            return None
        return cls(
            endpoint=settings.openai_api_base,
            api_key=settings.openai_api_key,
            model=settings.openai_model,
            timeout_seconds=settings.openai_timeout_seconds,
        )

    def generate_json(self, *, system_prompt: str, user_prompt: str) -> dict[str, Any]:
        """Send one chat completion request and parse the result as JSON.

        Uses a global semaphore to cap concurrency and retries on 429 / 5xx
        with exponential backoff so parallel agent calls don't all crash.
        """

        max_attempts = 4
        backoff = 0.8

        with _concurrency_gate:
            response = None
            last_err: Exception | None = None
            for attempt in range(max_attempts):
                try:
                    response = httpx.post(
                        self.endpoint,
                        headers={
                            "Authorization": f"Bearer {self.api_key}",
                            "Content-Type": "application/json",
                        },
                        json={
                            "model": self.model,
                            "messages": [
                                {"role": "system", "content": system_prompt},
                                {"role": "user", "content": user_prompt},
                            ],
                            "stream": False,
                        },
                        timeout=self.timeout_seconds,
                    )
                    if response.status_code == 429 or 500 <= response.status_code < 600:
                        if attempt == max_attempts - 1:
                            response.raise_for_status()
                        sleep_for = backoff * (2 ** attempt) + random.uniform(0, 0.5)
                        time.sleep(sleep_for)
                        continue
                    response.raise_for_status()
                    break
                except httpx.HTTPStatusError as exc:
                    last_err = exc
                    if attempt == max_attempts - 1:
                        raise
                    sleep_for = backoff * (2 ** attempt) + random.uniform(0, 0.5)
                    time.sleep(sleep_for)
            if response is None:
                raise RuntimeError(f"LLM call failed after retries: {last_err}")

        # Some Chinese OpenAI-compatible proxies return GBK-encoded JSON without a charset
        # header; try utf-8 first, then fall back to gbk / gb18030.
        raw_bytes = response.content
        payload = None
        last_err: Exception | None = None
        for encoding in ("utf-8", "gbk", "gb18030"):
            try:
                payload = json.loads(raw_bytes.decode(encoding))
                break
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                last_err = exc
                continue
        if payload is None:
            raise ValueError(f"Failed to decode LLM response: {last_err}") from last_err
        choices = payload.get("choices") or []
        if not choices:
            raise ValueError("Model response did not include any choices.")

        message = choices[0].get("message") or {}
        content = message.get("content", "")
        if isinstance(content, list):
            content = "".join(
                part.get("text", "") if isinstance(part, dict) else str(part)
                for part in content
            )
        if not isinstance(content, str):
            raise ValueError("Model response content was not a string.")

        return self._extract_json_object(content)

    @staticmethod
    def _resolve_endpoint(endpoint: str) -> str:
        """Accept either a base URL or the full chat completions URL."""

        normalized = endpoint.strip().rstrip("/")
        if normalized.endswith("/chat/completions"):
            return normalized
        if normalized.endswith("/v1"):
            return f"{normalized}/chat/completions"
        return f"{normalized}/v1/chat/completions"

    @staticmethod
    def _extract_json_object(content: str) -> dict[str, Any]:
        """Parse a JSON object, tolerating fenced code blocks."""

        text = content.strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*", "", text)
            text = re.sub(r"\s*```$", "", text)

        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            start = text.find("{")
            end = text.rfind("}")
            if start < 0 or end <= start:
                raise
            parsed = json.loads(text[start : end + 1])

        if not isinstance(parsed, dict):
            raise ValueError("Model response JSON must be an object.")
        return parsed
