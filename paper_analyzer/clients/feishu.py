"""Feishu Open Platform client."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

import httpx

from paper_analyzer.config import Settings


class FeishuAPIError(RuntimeError):
    """Raised when Feishu returns a non-successful response."""


@dataclass
class TokenCache:
    value: str | None = None
    expires_at: datetime | None = None


class FeishuClient:
    """Minimal Feishu API wrapper for Bitable and file download operations."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.base_url = "https://open.feishu.cn/open-apis"
        self.timeout = httpx.Timeout(settings.llm_request_timeout_sec)
        self._token_cache = TokenCache()

    def _client(self) -> httpx.Client:
        return httpx.Client(timeout=self.timeout)

    def _request(
        self,
        method: str,
        path: str,
        *,
        json_body: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
        authenticated: bool = True,
    ) -> dict[str, Any]:
        headers = {"Content-Type": "application/json; charset=utf-8"}
        if authenticated:
            headers["Authorization"] = f"Bearer {self.get_tenant_access_token()}"

        with self._client() as client:
            response = client.request(
                method,
                f"{self.base_url}{path}",
                headers=headers,
                json=json_body,
                params=params,
            )
            response.raise_for_status()
            payload = response.json()

        if payload.get("code", 0) != 0:
            raise FeishuAPIError(payload.get("msg", "unknown Feishu error"))

        return payload

    def get_tenant_access_token(self) -> str:
        now = datetime.utcnow()
        if (
            self._token_cache.value
            and self._token_cache.expires_at
            and self._token_cache.expires_at > now
        ):
            return self._token_cache.value

        payload = self._request(
            "POST",
            "/auth/v3/tenant_access_token/internal",
            json_body={
                "app_id": self.settings.feishu_app_id,
                "app_secret": self.settings.feishu_app_secret,
            },
            authenticated=False,
        )
        token = payload["tenant_access_token"]
        expires_in = int(payload.get("expire", 7200))
        self._token_cache = TokenCache(
            value=token,
            expires_at=now + timedelta(seconds=max(expires_in - 60, 60)),
        )
        return token

    def get_record(self, base_token: str, table_id: str, record_id: str) -> dict[str, Any]:
        payload = self._request(
            "GET",
            f"/bitable/v1/apps/{base_token}/tables/{table_id}/records/{record_id}",
        )
        return payload["data"]["record"]

    def update_record(
        self,
        base_token: str,
        table_id: str,
        record_id: str,
        fields: dict[str, Any],
    ) -> dict[str, Any]:
        payload = self._request(
            "PUT",
            f"/bitable/v1/apps/{base_token}/tables/{table_id}/records/{record_id}",
            json_body={"fields": fields},
        )
        return payload["data"]["record"]

    def download_attachment(self, file_token: str) -> bytes:
        headers = {"Authorization": f"Bearer {self.get_tenant_access_token()}"}
        with self._client() as client:
            response = client.get(
                f"{self.base_url}/drive/v1/medias/{file_token}/download",
                headers=headers,
            )
            response.raise_for_status()
            return response.content

