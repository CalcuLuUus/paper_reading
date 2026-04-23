"""OpenAI-compatible chat completions client."""

from __future__ import annotations

import json
from json import JSONDecodeError
from time import perf_counter
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
        request_name: str = "llm_request",
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
                request_name=request_name,
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
                self._log(
                    f"[LLM] {request_name}: invalid JSON/schema, retrying "
                    f"({json_attempt + 1}/{json_retries})"
                )
        raise InvalidLLMOutputError("unreachable")

    def _complete_text(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        request_name: str,
        temperature: float,
        max_tokens: int,
        transient_retries: int,
    ) -> str:
        last_error: Exception | None = None
        self._log_request(request_name, system_prompt, user_prompt, temperature, max_tokens)
        for attempt in range(transient_retries + 1):
            try:
                started_at = perf_counter()
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
                elapsed = perf_counter() - started_at
                if isinstance(choice, list):
                    text = "".join(part.get("text", "") for part in choice if isinstance(part, dict))
                else:
                    text = str(choice)
                self._log_response(request_name, elapsed, text)
                return text
            except (httpx.TimeoutException, httpx.NetworkError, TransientLLMError) as exc:
                last_error = exc
                self._log(
                    f"[LLM] {request_name}: transient error on attempt "
                    f"{attempt + 1}/{transient_retries + 1}: {exc}"
                )
                if attempt >= transient_retries:
                    raise TransientLLMError(str(exc)) from exc
        raise TransientLLMError(str(last_error))

    def _chat_completions_url(self) -> str:
        normalized = self.settings.openai_base_url.rstrip("/") + "/"
        return urljoin(normalized, "chat/completions")

    def _log_request(
        self,
        request_name: str,
        system_prompt: str,
        user_prompt: str,
        temperature: float,
        max_tokens: int,
    ) -> None:
        if not self.settings.llm_debug_enabled:
            return
        self._log(
            f"[LLM] {request_name}: sending request "
            f"model={self.settings.openai_model} temp={temperature} max_tokens={max_tokens} "
            f"system_chars={len(system_prompt)} user_chars={len(user_prompt)}"
        )
        self._log_prompt("system", request_name, system_prompt)
        self._log_prompt("user", request_name, user_prompt)

    def _log_response(self, request_name: str, elapsed: float, text: str) -> None:
        if not self.settings.llm_debug_enabled:
            return
        preview = self._preview_text(text)
        self._log(
            f"[LLM] {request_name}: received response "
            f"elapsed={elapsed:.2f}s response_chars={len(text)}"
        )
        self._log(f"[LLM] {request_name}: response preview\n{preview}")

    def _log_prompt(self, role: str, request_name: str, prompt: str) -> None:
        if not self.settings.llm_debug_enabled:
            return
        body = prompt if self.settings.llm_log_full_prompts else self._preview_text(prompt)
        self._log(f"[LLM] {request_name}: {role} prompt\n{body}")

    def _preview_text(self, text: str) -> str:
        limit = max(self.settings.llm_log_preview_chars, 1)
        if len(text) <= limit:
            return text
        return f"{text[:limit]}\n...<truncated {len(text) - limit} chars>"

    @staticmethod
    def _log(message: str) -> None:
        print(message, flush=True)

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
