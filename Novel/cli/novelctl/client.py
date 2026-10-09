from __future__ import annotations

import json
from typing import Any

import httpx


class APIClientError(RuntimeError):
    def __init__(self, message: str, *, connection: bool = False) -> None:
        super().__init__(message)
        self.connection = connection


class APIClient:
    """Small synchronous client; the CLI never connects to the database directly."""

    def __init__(self, base_url: str, token: str | None = None, *, timeout: float = 15.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.timeout = timeout

    def _headers(self) -> dict[str, str]:
        headers = {"Accept": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    def request(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
        idempotency_key: str | None = None,
        raise_for_status: bool = True,
    ) -> tuple[int, Any]:
        headers = self._headers()
        if idempotency_key:
            headers["Idempotency-Key"] = idempotency_key
        try:
            response = httpx.request(
                method,
                f"{self.base_url}{path}",
                headers=headers,
                json=json,
                timeout=self.timeout,
            )
        except httpx.HTTPError as exc:
            raise APIClientError(f"Could not connect to {self.base_url}: {exc}", connection=True) from exc
        try:
            body = response.json()
        except ValueError:
            body = {"text": response.text}
        if raise_for_status and response.status_code >= 400:
            if isinstance(body, dict) and isinstance(body.get("error"), dict):
                error = body["error"]
                message = f"{error.get('code', 'API_ERROR')}: {error.get('message', 'Request failed')}"
            else:
                message = f"HTTP {response.status_code}: {body}"
            raise APIClientError(message)
        return response.status_code, body

    def health(self) -> tuple[int, Any]:
        return self.request("GET", "/api/health", raise_for_status=False)

    def get(self, path: str) -> Any:
        return self.request("GET", path)[1]

    def post(self, path: str, payload: dict[str, Any], *, idempotency_key: str | None = None) -> Any:
        return self.request("POST", path, json=payload, idempotency_key=idempotency_key)[1]

    def post_empty(self, path: str, *, idempotency_key: str | None = None) -> Any:
        return self.request("POST", path, idempotency_key=idempotency_key)[1]

    def stream_events(self, run_id: str, *, after: int = 0):
        """Yield `(sequence, event_type, payload)` tuples from the SSE endpoint.

        The stream resumes from `after` via `Last-Event-ID`, so a dropped
        connection does not lose events (spec §11).
        """

        headers = {**self._headers(), "Accept": "text/event-stream"}
        if after:
            headers["Last-Event-ID"] = str(after)
        try:
            with httpx.stream(
                "GET",
                f"{self.base_url}/api/v1/runs/{run_id}/events/stream",
                headers=headers,
                timeout=None,
            ) as response:
                if response.status_code >= 400:
                    response.read()
                    raise APIClientError(f"HTTP {response.status_code}: {response.text}")
                event_type = ""
                data = ""
                sequence = 0
                for line in response.iter_lines():
                    if line.startswith("id: "):
                        sequence = int(line[4:].strip() or 0)
                    elif line.startswith("event: "):
                        event_type = line[7:].strip()
                    elif line.startswith("data: "):
                        data = line[6:]
                    elif line == "":
                        if event_type and data:
                            yield sequence, event_type, json.loads(data)
                        event_type, data = "", ""
        except httpx.HTTPError as exc:
            raise APIClientError(f"Event stream failed: {exc}", connection=True) from exc
