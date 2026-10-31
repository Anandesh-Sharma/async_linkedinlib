"""Origin-bound HTTP exchanges with cookie rotation, cooldowns, and no automatic retries."""

import asyncio
import time
from collections.abc import Mapping
from datetime import UTC
from datetime import datetime
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any
from urllib.parse import unquote
from urllib.parse import urlsplit

import httpx

from ..config import ClientOptions
from ..exceptions import AuthenticationError
from ..exceptions import ChallengeRequired
from ..exceptions import HTTPError
from ..exceptions import NetworkError
from ..exceptions import ProtocolError
from ..exceptions import RateLimited
from ..session import Session

ORIGIN = "https://www.linkedin.com"


class Transport:
    """Own the connection pool and serialize updates to one account's cookie jar."""

    def __init__(
        self,
        session: Session,
        options: ClientOptions,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.session = session
        self.session_file: Path | None = None
        self._lock = asyncio.Lock()
        self._closed = False
        self._client = httpx.AsyncClient(
            timeout=options.timeout,
            http2=True,
            trust_env=False,
            follow_redirects=False,
            limits=httpx.Limits(max_connections=options.max_connections),
            transport=transport,
        )

    async def request(
        self,
        method: str,
        path: str,
        data: Mapping[str, str] | None = None,
        *,
        json: object | None = None,
        content: bytes | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> httpx.Response:
        """Send one exchange.

        `json` bodies and extra headers serve the Voyager API; `content` sends raw upload
        bytes (set its content-type in `headers`).
        """
        if not path.startswith("/") or path.startswith("//") or "#" in path:
            raise ValueError("A LinkedIn origin-relative path is required.")
        if sum(body is not None for body in (data, json, content)) > 1:
            raise ValueError("Send one body: form data, JSON or raw content.")
        async with self._lock:
            if self._closed:
                raise RuntimeError("LinkedIn client is closed.")
            remaining = self.session.rate_limit_until - time.time()
            if remaining > 0:
                raise RateLimited(remaining)
            sent = self.session.profile.auth_headers(self.session.device_id)
            csrf = self.session.cookie_value("JSESSIONID", path)
            if csrf:
                sent["csrf-token"] = csrf.strip('"')
            if path == "/mob/tracking":
                sent = {"user-agent": self.session.profile.user_agent}
            sent.update(headers or {})
            self._client.cookies = self.session.to_httpx()
            try:
                response = await self._client.request(
                    method,
                    ORIGIN + path,
                    headers=sent,
                    data=data,
                    json=json,
                    content=content,
                )
            except httpx.RequestError:
                raise NetworkError("LinkedIn request failed and was not retried.") from None
            finally:
                self.session.update_cookies(self._client.cookies)
                self.checkpoint()
            if response.status_code == 429:
                delay = self._retry_after(response.headers.get("retry-after"))
                self.session.rate_limit_until = time.time() + delay
                self.checkpoint()
                raise RateLimited(delay)
            if response.status_code == 401:
                self.session.clear_authentication()
                self.checkpoint()
                raise AuthenticationError("LinkedIn rejected the session or credentials.")
            if response.status_code == 403:
                raise ChallengeRequired()
            if 300 <= response.status_code < 400:
                raise ProtocolError("LinkedIn returned a redirect; it was not followed.")
            if response.status_code >= 400:
                raise HTTPError(response.status_code, self._service_message(response))
            return response

    @staticmethod
    def upload_path(url: object, prefix: str) -> str | None:
        """The origin path of an upload URL LinkedIn handed out, or None if it is not ours.

        Only https://www.linkedin.com URLs under `prefix` qualify; dot segments (also
        percent-encoded) are refused because the HTTP client would resolve them elsewhere.
        """
        if not isinstance(url, str):
            return None
        parts = urlsplit(url)
        segments = unquote(parts.path).split("/")
        if (
            parts.scheme != "https"
            or parts.netloc != "www.linkedin.com"
            or not parts.path.startswith(prefix)
            or "." in segments
            or ".." in segments
            or "\\" in parts.path
        ):
            return None
        return parts.path + (f"?{parts.query}" if parts.query else "")

    def checkpoint(self) -> None:
        if self.session_file is not None:
            self.session.save(self.session_file)

    @staticmethod
    def json_object(response: httpx.Response) -> dict[str, Any]:
        try:
            data = response.json()
        except ValueError:
            raise ProtocolError("LinkedIn returned an unsupported response format.") from None
        if not isinstance(data, dict):
            raise ProtocolError("LinkedIn returned an unsupported response shape.")
        return data

    @staticmethod
    def _service_message(response: httpx.Response) -> str | None:
        """Rest.li's short client-error reason; server traces and bodies are never kept."""
        if not 400 <= response.status_code < 500:
            return None
        try:
            data = response.json()
        except ValueError:
            return None
        message = data.get("message") if isinstance(data, dict) else None
        if isinstance(message, str) and message and "\n" not in message:
            return message[:300]
        return None

    @staticmethod
    def _retry_after(value: str | None) -> float:
        if value:
            try:
                return max(0.0, float(int(value)))
            except ValueError:
                try:
                    date = parsedate_to_datetime(value)
                    if date.tzinfo is None:
                        date = date.replace(tzinfo=UTC)
                    return max(0.0, (date - datetime.now(UTC)).total_seconds())
                except (ValueError, TypeError, OverflowError):
                    pass
        return 60.0

    async def aclose(self) -> None:
        async with self._lock:
            if not self._closed:
                self._closed = True
                await self._client.aclose()
