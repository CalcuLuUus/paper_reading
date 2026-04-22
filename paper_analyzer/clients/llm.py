"""OpenAI-compatible chat completions client."""

from __future__ import annotations

import json
from json import JSONDecodeError
from typing import Any
from urllib.parse import urljoin

import httpx
from pydantic import BaseModel, ValidationError

from paper_analyzer.config import Settings


class LLMError(RuntimeError):
    """Base LLM error."""


class TransientLLMError(LLMError):
    """Temporary network or upstream error."""


class InvalidLLMOutputError(LLMError):
    """Raised when the model output is not valid JSON."""


class OpenAICompatibleClient:
    """Thin wrapper around the Chat Completions API."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.timeout = httpx.Timeout(settings.llm_request_timeout_sec)

    def complete_json(
        self,
        *,
        schema: type[BaseModel],
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.2,
        max_tokens: int = 4000,
        json_retries: int = 1,
        transient_retries: int = 2,
    ) -> BaseModel:
        prompt = user_prompt
        for json_attempt in range(json_retries + 1):
            raw_text = self._complete_text(
                system_prompt=system_prompt,
                user_prompt=prompt,
                temperature=temperature,
                max_tokens=max_tokens,
                transient_retries=transient_retries,
            )
            try:
                payload = self._extract_json(raw_text)
                return schema.model_validate(payload)
            except (JSONDecodeError, ValidationError) as exc:
                if json_attempt >= json_retries:
                    raise InvalidLLMOutputError(str(exc)) from exc
                prompt = (
                    f"{user_prompt}\n\n"
                    "上一次输出不是合法 JSON 或字段不匹配。"
                    "这一次只返回单个 JSON 对象，不要包含代码块、注释或额外解释。"
                )
        raise InvalidLLMOutputError("unreachable")

    def _complete_text(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        temperature: float,
        max_tokens: int,
        transient_retries: int,
    ) -> str:
        last_error: Exception | None = None
        for attempt in range(transient_retries + 1):
            try:
                with httpx.Client(timeout=self.timeout) as client:
                    response = client.post(
                        self._chat_completions_url(),
                        headers={
                            "Authorization": f"Bearer {self.settings.openai_api_key}",
                            "Content-Type": "application/json",
                        },
                        json={
                            "model": self.settings.openai_model,
                            "temperature": temperature,
                            "max_tokens": max_tokens,
                            "messages": [
                                {"role": "system", "content": system_prompt},
                                {"role": "user", "content": user_prompt},
                            ],
                        },
                    )
                if response.status_code in {408, 409, 429} or response.status_code >= 500:
                    raise TransientLLMError(
                        f"temporary upstream error: {response.status_code} {response.text}"
                    )
                response.raise_for_status()
                payload = response.json()
                choice = payload["choices"][0]["message"]["content"]
                if isinstance(choice, list):
                    return "".join(part.get("text", "") for part in choice if isinstance(part, dict))
                return str(choice)
            except (httpx.TimeoutException, httpx.NetworkError, TransientLLMError) as exc:
                last_error = exc
                if attempt >= transient_retries:
                    raise TransientLLMError(str(exc)) from exc
        raise TransientLLMError(str(last_error))

    def _chat_completions_url(self) -> str:
        normalized = self.settings.openai_base_url.rstrip("/") + "/"
        return urljoin(normalized, "chat/completions")

    @staticmethod
    def _extract_json(text: str) -> dict[str, Any]:
        stripped = text.strip()
        if stripped.startswith("```"):
            lines = [line for line in stripped.splitlines() if not line.strip().startswith("```")]
            stripped = "\n".join(lines).strip()
        try:
            return json.loads(stripped)
        except JSONDecodeError:
            start = stripped.find("{")
            end = stripped.rfind("}")
            if start == -1 or end == -1 or end <= start:
                raise
            return json.loads(stripped[start : end + 1])

